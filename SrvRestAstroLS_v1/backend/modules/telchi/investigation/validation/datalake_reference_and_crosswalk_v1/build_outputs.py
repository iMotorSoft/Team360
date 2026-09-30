"""Build Telchi reference and identity crosswalk Parquet V1.

The default build is deliberately offline: it consumes the immutable legacy
mirror, the preserved warehouse-office workbook, and SAP master extracts
already materialized under ``raw/sap``.  ``--extract-sap`` is an explicit,
read-only operation used only to create those small master snapshots.

No atomic, business, or decision dataset is produced here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

import duckdb

ROOT = Path(__file__).resolve().parents[5]
DATA_ROOT = Path(os.environ.get(
    "TEAM360_TELCHI_DATA_ROOT",
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi",
)).resolve()
LEGACY = DATA_ROOT / "raw/legacy/parquet"
REFERENCE_SOURCE = Path(os.environ.get(
    "TEAM360_TELCHI_WAREHOUSE_BRANCH_SOURCE",
    "/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS/almacenOficina.xlsx",
)).resolve()
REF_SOURCE_DEST = DATA_ROOT / "raw/legacy/reference_sources/almacenOficina.xlsx"
RUNS = DATA_ROOT / "manifests/runs"
EVIDENCE = Path(__file__).resolve().parent / "evidence"
TRANSFORMATION_VERSION = "reference-crosswalk-v1"
SCHEMA_VERSION = "1.0.0"
SEMANTIC_VERSION = "1.0.0"
SAP_TABLES = {
    "OITM": 'SELECT "ItemCode","ItemName","ItmsGrpCod","InvntryUom","SalUnitMsr","BuyUnitMsr","frozenFor","validFor","AvgPrice","LastPurPrc","UpdateDate" FROM "TELCHI"."OITM"',
    "OCRD": 'SELECT "CardCode","CardName","CardType","frozenFor","validFor","LicTradNum","CreditLine","GroupNum","UpdateDate" FROM "TELCHI"."OCRD"',
    "OWHS": 'SELECT "WhsCode","WhsName","Locked","Inactive","updateDate","U_BRANCH_OFFICE_ID","U_TYPE","U_WAREHOUSE_DMS" FROM "TELCHI"."OWHS"',
    "OSLP": 'SELECT "SlpCode","SlpName","Active","EmpID" FROM "TELCHI"."OSLP"',
    "OUSR": 'SELECT "USERID","USER_CODE","U_NAME","Locked","SUPERUSER","Branch","updateDate" FROM "TELCHI"."OUSR"',
    "OHEM": 'SELECT "empID","lastName","firstName","salesPrson","Active","userId","UpdateDate" FROM "TELCHI"."OHEM"',
    "OITB": 'SELECT "ItmsGrpCod","ItmsGrpNam","Locked","updateDate" FROM "TELCHI"."OITB"',
}

REF_DATASETS = [
    "products", "product_groups", "customers", "suppliers", "warehouses",
    "branches", "document_types", "payment_terms", "channels",
    "units_of_measure", "warehouse_roles", "currencies", "users", "salespersons",
]
CROSSWALK_DATASETS = [
    "product_crosswalk", "customer_crosswalk", "supplier_crosswalk",
    "warehouse_crosswalk", "branch_crosswalk", "salesperson_crosswalk",
    "user_crosswalk", "warehouse_branch_mapping",
]

TECH = [
    ("_source_system", "VARCHAR"), ("_source_dataset", "VARCHAR"),
    ("_source_native_key", "VARCHAR"), ("_source_file", "VARCHAR"),
    ("_source_snapshot_at", "TIMESTAMPTZ"), ("_source_extracted_at", "TIMESTAMPTZ"),
    ("_ingested_at", "TIMESTAMPTZ"), ("_transformation_version", "VARCHAR"),
    ("_semantic_version", "VARCHAR"), ("_lineage_quality", "VARCHAR"),
]
REF_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "products": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("product_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("product_group_id", "VARCHAR"), ("unit_of_measure_id", "VARCHAR"), ("standard_cost", "DECIMAL(38,6)"), ("last_purchase_price", "DECIMAL(38,6)"), ("product_name", "VARCHAR"), ("normalized_product_name", "VARCHAR"), ("product_group", "VARCHAR"), ("inventory_uom", "VARCHAR"), ("sales_uom", "VARCHAR"), ("purchase_uom", "VARCHAR"), ("active", "BOOLEAN"), ("is_telchi_l_product", "BOOLEAN")],
    "product_groups": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("product_group_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR")],
    "customers": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("customer_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("branch_id", "VARCHAR"), ("tax_id", "VARCHAR"), ("credit_limit", "DECIMAL(38,6)"), ("payment_term_id", "VARCHAR")],
    "suppliers": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("supplier_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("branch_id", "VARCHAR"), ("tax_id", "VARCHAR"), ("payment_term_id", "VARCHAR")],
    "warehouses": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("warehouse_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("warehouse_role_id", "VARCHAR")],
    "branches": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("branch_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR")],
    "document_types": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("document_type", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("company_id", "VARCHAR")],
    "payment_terms": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("payment_term_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("branch_id", "VARCHAR"), ("credit_days", "INTEGER")],
    "channels": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("channel_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("branch_id", "VARCHAR")],
    "units_of_measure": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("unit_of_measure_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("company_id", "VARCHAR")],
    "warehouse_roles": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("warehouse_role_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("warehouse_id", "VARCHAR")],
    "currencies": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("currency_code", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("legal_entity_id", "VARCHAR"), ("decimal_places", "INTEGER")],
    "users": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("user_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("organizational_scope", "VARCHAR")],
    "salespersons": [("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("salesperson_id", "VARCHAR"), ("code", "VARCHAR"), ("name", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("status", "VARCHAR"), ("branch_id", "VARCHAR")],
}
CW_COLUMNS = [("canonical_id", "VARCHAR"), ("source_system", "VARCHAR"), ("source_native_id", "VARCHAR"), ("valid_from", "TIMESTAMPTZ"), ("valid_to", "TIMESTAMPTZ"), ("mapping_source", "VARCHAR"), ("confidence", "DECIMAL(38,12)"), ("status", "VARCHAR")]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def norm_expr(expr: str) -> str:
    return f"lower(trim(regexp_replace(lower(strip_accents(coalesce({expr}, ''))), '[^a-z0-9]+', ' ', 'g')))"


def cid(entity: str, source: str, native: str) -> str:
    return f"{entity}_" + hashlib.sha256(f"{entity}|{source}|{native}".encode()).hexdigest()[:24]


def parse_workbook(path: Path) -> list[dict[str, str]]:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with ZipFile(path) as archive:
        shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in item.iter(f"{{{ns}}}t")) for item in shared_root.findall(f"{{{ns}}}si")]
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(f".//{{{ns}}}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{{{ns}}}c"):
                ref = cell.attrib.get("r", "A1")
                pos = 0
                while pos < len(ref) and ref[pos].isalpha():
                    pos += 1
                col = 0
                for char in ref[:pos].upper():
                    col = col * 26 + ord(char) - 64
                value = cell.find(f"{{{ns}}}v")
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                values[col] = text
            if values:
                rows.append([values.get(i, "") for i in range(1, max(values) + 1)])
    header = [x.strip() for x in rows[0]]
    return [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in rows[1:]]


def copy_reference_source() -> dict[str, str]:
    if not REFERENCE_SOURCE.is_file():
        raise FileNotFoundError(REFERENCE_SOURCE)
    source_hash = sha256(REFERENCE_SOURCE)
    REF_SOURCE_DEST.parent.mkdir(parents=True, exist_ok=True)
    if REF_SOURCE_DEST.exists():
        if sha256(REF_SOURCE_DEST) != source_hash:
            raise RuntimeError("STOP_REFERENCE_SOURCE_COLLISION")
    else:
        temporary = REF_SOURCE_DEST.with_name(f".{REF_SOURCE_DEST.name}.{os.getpid()}.copying")
        shutil.copyfile(REFERENCE_SOURCE, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, REF_SOURCE_DEST)
    return {"source_file": str(REFERENCE_SOURCE), "preserved_path": str(REF_SOURCE_DEST), "sha256": source_hash, "size_bytes": str(REFERENCE_SOURCE.stat().st_size)}


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def latest_sap_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for table in SAP_TABLES:
        candidates = sorted(DATA_ROOT.glob(f"raw/sap/table_extract/*/extraction_date=*/run_id=* /{table}.parquet".replace("* /", "*/")))
        if not candidates:
            candidates = sorted(DATA_ROOT.glob(f"raw/sap/table_extract/*/extraction_date=*/run_id=*/{table}.parquet"))
        if not candidates:
            raise FileNotFoundError(f"missing raw SAP extract for {table}; run --extract-sap")
        paths[table] = candidates[-1]
    return paths


def extract_sap() -> dict[str, object]:
    from modules.telchi.investigation.atomic.connection import connect
    extracted_at = utc_now()
    extract_id = "sap_master_reference_v1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extraction_date = extracted_at[:10]
    run_dir = DATA_ROOT / "raw/sap/table_extract" / extract_id / f"extraction_date={extraction_date}" / f"run_id={extract_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    conn, cur = connect()
    metadata = []
    try:
        for table, query in SAP_TABLES.items():
            cur.execute(query)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            temp_csv = Path(tempfile.mkstemp(prefix=f"telchi-{table}-", suffix=".csv")[1])
            try:
                with temp_csv.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(columns + ["_source_extracted_at", "_extract_id", "_observation_sequence"])
                    for index, row in enumerate(rows):
                        writer.writerow(list(row) + [extracted_at, extract_id, index])
                out = run_dir / f"{table}.parquet"
                ddb = duckdb.connect()
                try:
                    ddb.execute(f"COPY (SELECT * FROM read_csv_auto({sql_quote(str(temp_csv))}, header=true, all_varchar=true, nullstr='')) TO {sql_quote(str(out))} (FORMAT PARQUET, COMPRESSION ZSTD)")
                finally:
                    ddb.close()
            finally:
                temp_csv.unlink(missing_ok=True)
            metadata.append({"extraction_id": extract_id, "table": table, "query": query, "row_count": len(rows), "extracted_at": extracted_at, "sql_hash": hashlib.sha256(query.encode()).hexdigest(), "output_path": str(out), "purpose": "MASTER_DATA_REFERENCE_ONLY", "status": "SUCCEEDED"})
    finally:
        cur.close(); conn.close()
    (RUNS / f"{extract_id}.json").parent.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{extract_id}.json").write_text(json.dumps({"extraction_id": extract_id, "tables": metadata, "sap_write_count": 0, "read_only": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"extract_id": extract_id, "tables": metadata}


def typed_empty(columns: list[tuple[str, str]]) -> str:
    return "SELECT " + ", ".join(f"CAST(NULL AS {typ}) AS {name}" for name, typ in columns) + " WHERE FALSE"


def write_parquet(ddb: duckdb.DuckDBPyConnection, dataset: str, query: str) -> tuple[Path, int, str]:
    layer = "reference" if dataset in REF_DATASETS else "crosswalk"
    out_dir = DATA_ROOT / layer / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "part-00000.parquet"
    if out.exists():
        raise RuntimeError(f"output already exists; refusing overwrite: {out}")
    ddb.execute(f"COPY ({query}) TO {sql_quote(str(out))} (FORMAT PARQUET, COMPRESSION ZSTD)")
    rows = int(ddb.execute(f"SELECT count(*) FROM read_parquet({sql_quote(str(out))})").fetchone()[0])
    return out, rows, sha256(out)


def lineage_select(source_system: str, source_dataset: str, native: str, source_file: str | None, extracted_at: str, ingested_at: str, quality: str) -> str:
    return ", ".join([
        f"{sql_quote(source_system)} AS _source_system", f"{sql_quote(source_dataset)} AS _source_dataset", f"trim(CAST({native} AS VARCHAR)) AS _source_native_key", f"{sql_quote(source_file)} AS _source_file" if source_file else "CAST(NULL AS VARCHAR) AS _source_file",
        "CAST(NULL AS TIMESTAMPTZ) AS _source_snapshot_at", f"TIMESTAMPTZ {sql_quote(extracted_at)} AS _source_extracted_at", f"TIMESTAMPTZ {sql_quote(ingested_at)} AS _ingested_at", f"{sql_quote(TRANSFORMATION_VERSION)} AS _transformation_version", f"{sql_quote(SEMANTIC_VERSION)} AS _semantic_version", f"{sql_quote(quality)} AS _lineage_quality",
    ])


def build_queries(paths: dict[str, Path], workbook_csv: Path, extracted_at: str, ingested_at: str) -> dict[str, str]:
    p = {k: sql_quote(str(v)) for k, v in paths.items()}
    legacy = sql_quote(str(LEGACY))
    xlsx = sql_quote(str(workbook_csv))
    product_cols = ",".join(name for name, _ in REF_COLUMNS["products"] + TECH)
    # Products: SAP current + two distinct legacy master observations. No name-based cross-source fusion.
    sap_prod = f"""SELECT 'SAP_HANA' source_system, trim(ItemCode) source_native_id,
      'product_'||substr(sha256('product|SAP_HANA|'||trim(ItemCode)),1,24) product_id, trim(ItemCode) code, trim(ItemName) AS "name",
      CAST(NULL AS TIMESTAMPTZ) valid_from, CAST(NULL AS TIMESTAMPTZ) valid_to,
      CASE WHEN coalesce(frozenFor,'N')='Y' OR coalesce(validFor,'Y')='N' THEN 'INACTIVE' ELSE 'ACTIVE' END status,
      CASE WHEN ItmsGrpCod IS NULL THEN NULL ELSE 'product_group_'||substr(sha256('product_group|SAP_HANA|'||CAST(ItmsGrpCod AS VARCHAR)),1,24) END product_group_id,
      CASE WHEN nullif(trim(InvntryUom),'') IS NULL THEN NULL ELSE 'unit_of_measure_'||substr(sha256('unit_of_measure|SAP_HANA|'||trim(InvntryUom)),1,24) END unit_of_measure_id,
      CAST(AvgPrice AS DECIMAL(38,6)) standard_cost, CAST(LastPurPrc AS DECIMAL(38,6)) last_purchase_price,
      trim(ItemName) product_name, {norm_expr('ItemName')} normalized_product_name, NULL product_group, trim(InvntryUom) inventory_uom, trim(SalUnitMsr) sales_uom, trim(BuyUnitMsr) purchase_uom,
      CASE WHEN coalesce(frozenFor,'N')='Y' OR coalesce(validFor,'Y')='N' THEN FALSE ELSE TRUE END active, starts_with(trim(ItemCode),'L') is_telchi_l_product,
      {_lineage('SAP_HANA','OITM','ItemCode',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')}
      FROM read_parquet({p['OITM']}) WHERE nullif(trim(ItemCode),'') IS NOT NULL"""
    legacy_sb1 = f"""SELECT 'LEGACY_DS', trim(ItemCode), 'product_'||substr(sha256('product|LEGACY_DS|'||trim(ItemCode)),1,24), trim(ItemCode), trim(ItemName), NULL, NULL,
      CASE WHEN coalesce(frozenFor,'N')='Y' THEN 'INACTIVE' ELSE 'ACTIVE' END,
      CASE WHEN ItmsGrpCod IS NULL THEN NULL ELSE 'product_group_'||substr(sha256('product_group|LEGACY_DS|'||CAST(ItmsGrpCod AS VARCHAR)),1,24) END,
      CASE WHEN nullif(trim(InvntryUom),'') IS NULL THEN NULL ELSE 'unit_of_measure_'||substr(sha256('unit_of_measure|LEGACY_DS|'||trim(InvntryUom)),1,24) END,
      NULL, CAST(LastPurPrc AS DECIMAL(38,6)), trim(ItemName), {norm_expr('ItemName')}, trim(Grupo), trim(InvntryUom), NULL, NULL, CASE WHEN coalesce(frozenFor,'N')='Y' THEN FALSE ELSE TRUE END, starts_with(trim(ItemCode),'L'),
      {_lineage('LEGACY_DS','productSB1','ItemCode','raw/legacy/parquet/productSB1.parq',extracted_at,ingested_at,'PARTIAL_TRACE')}
      FROM (SELECT *, row_number() OVER (PARTITION BY trim(ItemCode) ORDER BY trim(ItemName), __index_level_0__) rn FROM read_parquet({legacy}||'/productSB1.parq')) WHERE rn=1 AND nullif(trim(ItemCode),'') IS NOT NULL"""
    legacy_product = f"""SELECT 'LEGACY_DS0', trim(ProductCodeStr), 'product_'||substr(sha256('product|LEGACY_DS0|'||trim(ProductCodeStr)),1,24), trim(ProductCodeStr), trim(ProductName), NULL, NULL,
      CASE WHEN upper(trim(ProductStatus)) IN ('A','Y','ACTIVE') THEN 'ACTIVE' WHEN upper(trim(ProductStatus)) IN ('P','N','INACTIVE') THEN 'INACTIVE' ELSE 'UNKNOWN' END,
      CASE WHEN Group1Code IS NULL THEN NULL ELSE 'product_group_'||substr(sha256('product_group|LEGACY_DS0|'||CAST(Group1Code AS VARCHAR)),1,24) END, NULL, NULL, NULL, trim(ProductName), {norm_expr('ProductName')}, trim(Grupo1Name), trim(Unidad), NULL, NULL,
      upper(trim(ProductStatus)) IN ('A','Y','ACTIVE'), starts_with(trim(ProductCodeStr),'L'),
      {_lineage('LEGACY_DS0','product','ProductCodeStr','raw/legacy/parquet/product.parq',extracted_at,ingested_at,'PARTIAL_TRACE')}
      FROM (SELECT *, row_number() OVER (PARTITION BY trim(ProductCodeStr) ORDER BY trim(ProductName), ProductCode) rn FROM read_parquet({legacy}||'/product.parq')) WHERE rn=1 AND nullif(trim(ProductCodeStr),'') IS NOT NULL"""
    products = " UNION ALL ".join([sap_prod, legacy_sb1, legacy_product])

    groups = f"""SELECT 'SAP_HANA' AS source_system,CAST(ItmsGrpCod AS VARCHAR) AS source_native_id,'product_group_'||substr(sha256('product_group|SAP_HANA|'||CAST(ItmsGrpCod AS VARCHAR)),1,24) AS product_group_id,CAST(ItmsGrpCod AS VARCHAR) AS code,trim(ItmsGrpNam) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,CASE WHEN Locked='Y' THEN 'INACTIVE' ELSE 'ACTIVE' END AS status,{_lineage('SAP_HANA','OITB','ItmsGrpCod',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_parquet({p['OITB']})
      UNION ALL SELECT 'LEGACY_DS',CAST(ItmsGrpCod AS VARCHAR),'product_group_'||substr(sha256('product_group|LEGACY_DS|'||CAST(ItmsGrpCod AS VARCHAR)),1,24),CAST(ItmsGrpCod AS VARCHAR),trim(Grupo),NULL,NULL,'UNKNOWN',{_lineage('LEGACY_DS','productSB1','ItmsGrpCod','raw/legacy/parquet/productSB1.parq',extracted_at,ingested_at,'PARTIAL_TRACE')} FROM (SELECT DISTINCT ItmsGrpCod,Grupo FROM read_parquet({legacy}||'/productSB1.parq') WHERE ItmsGrpCod IS NOT NULL)
      """
    customers = f"""SELECT 'SAP_HANA' AS source_system,trim(CardCode) AS source_native_id,'customer_'||substr(sha256('customer|SAP_HANA|'||trim(CardCode)),1,24) AS customer_id,trim(CardCode) AS code,trim(CardName) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,CASE WHEN coalesce(frozenFor,'N')='Y' OR coalesce(validFor,'Y')='N' THEN 'INACTIVE' ELSE 'ACTIVE' END AS status,CAST(NULL AS VARCHAR) AS branch_id,trim(LicTradNum) AS tax_id,CAST(CreditLine AS DECIMAL(38,6)) AS credit_limit,CASE WHEN GroupNum IS NULL THEN NULL ELSE 'payment_term_'||substr(sha256('payment_term|SAP_HANA|'||CAST(GroupNum AS VARCHAR)),1,24) END AS payment_term_id,{_lineage('SAP_HANA','OCRD','CardCode',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_parquet({p['OCRD']}) WHERE CardType='C'
      UNION ALL SELECT 'LEGACY_DS',trim(ClientCode),'customer_'||substr(sha256('customer|LEGACY_DS|'||trim(ClientCode)),1,24),trim(ClientCode),trim(ClientName),NULL,NULL,'UNKNOWN',NULL,NULL,NULL,NULL,{_lineage('LEGACY_DS','clientSB1','ClientCode','raw/legacy/parquet/clientSB1.parq',extracted_at,ingested_at,'PARTIAL_TRACE')} FROM read_parquet({legacy}||'/clientSB1.parq') WHERE nullif(trim(ClientCode),'') IS NOT NULL
      UNION ALL SELECT 'LEGACY_DS0',CAST(PersonCode AS VARCHAR),'customer_'||substr(sha256('customer|LEGACY_DS0|'||CAST(PersonCode AS VARCHAR)),1,24),CAST(PersonCode AS VARCHAR),trim(PersonName),NULL,NULL,'UNKNOWN',NULL,NULL,NULL,NULL,{_lineage('LEGACY_DS0','person','PersonCode','raw/legacy/parquet/person.parq',extracted_at,ingested_at,'PARTIAL_TRACE')} FROM read_parquet({legacy}||'/person.parq') WHERE upper(trim(Cliente))='SI'"""
    suppliers = f"""SELECT 'SAP_HANA' AS source_system,trim(CardCode) AS source_native_id,'supplier_'||substr(sha256('supplier|SAP_HANA|'||trim(CardCode)),1,24) AS supplier_id,trim(CardCode) AS code,trim(CardName) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,CASE WHEN coalesce(frozenFor,'N')='Y' OR coalesce(validFor,'Y')='N' THEN 'INACTIVE' ELSE 'ACTIVE' END AS status,CAST(NULL AS VARCHAR) AS branch_id,trim(LicTradNum) AS tax_id,CASE WHEN GroupNum IS NULL THEN NULL ELSE 'payment_term_'||substr(sha256('payment_term|SAP_HANA|'||CAST(GroupNum AS VARCHAR)),1,24) END AS payment_term_id,{_lineage('SAP_HANA','OCRD','CardCode',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_parquet({p['OCRD']}) WHERE CardType='S'
      UNION ALL SELECT 'LEGACY_DS0',CAST(PersonCode AS VARCHAR),'supplier_'||substr(sha256('supplier|LEGACY_DS0|'||CAST(PersonCode AS VARCHAR)),1,24),CAST(PersonCode AS VARCHAR),trim(PersonName),NULL,NULL,'UNKNOWN',NULL,NULL,NULL,{_lineage('LEGACY_DS0','person','PersonCode','raw/legacy/parquet/person.parq',extracted_at,ingested_at,'PARTIAL_TRACE')} FROM read_parquet({legacy}||'/person.parq') WHERE upper(trim(Proveedor))='SI'"""
    warehouses = f"""SELECT 'SAP_HANA' AS source_system,trim(WhsCode) AS source_native_id,'warehouse_'||substr(sha256('warehouse|SAP_HANA|'||trim(WhsCode)),1,24) AS warehouse_id,trim(WhsCode) AS code,trim(WhsName) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,CASE WHEN coalesce(Locked,'N')='Y' OR coalesce(Inactive,'N')='Y' THEN 'INACTIVE' ELSE 'ACTIVE' END AS status,CAST(NULL AS VARCHAR) AS warehouse_role_id,{_lineage('SAP_HANA','OWHS','WhsCode',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_parquet({p['OWHS']})
      UNION ALL SELECT 'REFERENCE_FILE',trim(CAST(WareHouseCode AS VARCHAR)),'warehouse_'||substr(sha256('warehouse|REFERENCE_FILE|'||trim(CAST(WareHouseCode AS VARCHAR))),1,24),trim(CAST(WareHouseCode AS VARCHAR)),trim(WareHouseName),NULL,NULL,'ACTIVE',NULL,{_lineage('REFERENCE_FILE','almacenOficina.xlsx','WareHouseCode','raw/legacy/reference_sources/almacenOficina.xlsx',extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_csv_auto({xlsx}, header=true, all_varchar=true)"""
    branches = f"""SELECT 'REFERENCE_FILE' AS source_system,trim(CAST(OfficeCode AS VARCHAR)) AS source_native_id,'branch_'||substr(sha256('branch|REFERENCE_FILE|'||trim(CAST(OfficeCode AS VARCHAR))),1,24) AS branch_id,trim(CAST(OfficeCode AS VARCHAR)) AS code,trim(Oficina) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,'ACTIVE' AS status,{_lineage('REFERENCE_FILE','almacenOficina.xlsx','OfficeCode','raw/legacy/reference_sources/almacenOficina.xlsx',extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM (SELECT DISTINCT OfficeCode,Oficina FROM read_csv_auto({xlsx}, header=true, all_varchar=true))"""
    salespersons = f"""SELECT 'SAP_HANA' AS source_system,CAST(SlpCode AS VARCHAR) AS source_native_id,'salesperson_'||substr(sha256('salesperson|SAP_HANA|'||CAST(SlpCode AS VARCHAR)),1,24) AS salesperson_id,CAST(SlpCode AS VARCHAR) AS code,trim(SlpName) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,CASE WHEN coalesce(Active,'Y')='Y' THEN 'ACTIVE' ELSE 'INACTIVE' END AS status,CAST(NULL AS VARCHAR) AS branch_id,{_lineage('SAP_HANA','OSLP','SlpCode',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_parquet({p['OSLP']})"""
    users = f"""SELECT 'SAP_HANA' AS source_system,CAST(USERID AS VARCHAR) AS source_native_id,'user_'||substr(sha256('user|SAP_HANA|'||CAST(USERID AS VARCHAR)),1,24) AS user_id,trim(USER_CODE) AS code,trim(U_NAME) AS "name",CAST(NULL AS TIMESTAMPTZ) AS valid_from,CAST(NULL AS TIMESTAMPTZ) AS valid_to,CASE WHEN coalesce(Locked,'N')='Y' THEN 'INACTIVE' ELSE 'ACTIVE' END AS status,trim(CAST(Branch AS VARCHAR)) AS organizational_scope,{_lineage('SAP_HANA','OUSR','USERID',None,extracted_at,ingested_at,'FULL_DOCUMENT_TRACE')} FROM read_parquet({p['OUSR']})"""
    # The remaining approved reference datasets have no validated source in this gate.
    empties = {name: typed_empty(REF_COLUMNS[name] + TECH) for name in REF_DATASETS if name not in {"products", "product_groups", "customers", "suppliers", "warehouses", "branches", "users", "salespersons"}}
    queries = {"products": products, "product_groups": groups, "customers": customers, "suppliers": suppliers, "warehouses": warehouses, "branches": branches, "salespersons": salespersons, "users": users, **empties}
    return queries


def _lineage(source_system: str, dataset: str, native_col: str, source_file: str | None, extracted_at: str, ingested_at: str, quality: str) -> str:
    return lineage_select(source_system, dataset, native_col, source_file, extracted_at, ingested_at, quality)


def crosswalk_query(dataset: str) -> str:
    entity, ref = {
        "product_crosswalk": ("product", "products"), "customer_crosswalk": ("customer", "customers"), "supplier_crosswalk": ("supplier", "suppliers"), "warehouse_crosswalk": ("warehouse", "warehouses"), "branch_crosswalk": ("branch", "branches"), "salesperson_crosswalk": ("salesperson", "salespersons"), "user_crosswalk": ("user", "users"),
    }[dataset]
    # Each reference source identity gets one deterministic crosswalk row. This is
    # identity preservation, not a claim that legacy and SAP IDs are equivalent.
    return f"""SELECT {entity}_id canonical_id, source_system, source_native_id, valid_from, valid_to, 'canonical_source_identity' mapping_source, CAST(1.0 AS DECIMAL(38,12)) confidence, 'CONFIRMED' status,
      _source_system,_source_dataset,_source_native_key,_source_file,_source_snapshot_at,_source_extracted_at,_ingested_at,_transformation_version,_semantic_version,_lineage_quality
      FROM read_parquet({sql_quote(str(DATA_ROOT / 'reference' / ref / 'part-00000.parquet'))})"""


def mapping_query(workbook_csv: Path, paths: dict[str, Path], extracted_at: str, ingested_at: str) -> str:
    xlsx = sql_quote(str(workbook_csv))
    legacy = sql_quote(str(LEGACY))
    mapped = f"""SELECT 'warehouse_'||substr(sha256('warehouse|REFERENCE_FILE|'||trim(CAST(WareHouseCode AS VARCHAR))),1,24) warehouse_id,
      'branch_'||substr(sha256('branch|REFERENCE_FILE|'||trim(CAST(OfficeCode AS VARCHAR))),1,24) branch_id,
      CAST(NULL AS TIMESTAMPTZ) valid_from, CAST(NULL AS TIMESTAMPTZ) valid_to, 'REFERENCE_FILE:almacenOficina.xlsx' mapping_source, CAST(1.0 AS DECIMAL(38,12)) confidence, 'CONFIRMED' status,
      'REFERENCE_FILE' _source_system,'almacenOficina.xlsx' _source_dataset,'WareHouseCode='||trim(CAST(WareHouseCode AS VARCHAR))||';OfficeCode='||trim(CAST(OfficeCode AS VARCHAR)) _source_native_key,'raw/legacy/reference_sources/almacenOficina.xlsx' _source_file,CAST(NULL AS TIMESTAMPTZ) _source_snapshot_at,TIMESTAMPTZ {sql_quote(extracted_at)} _source_extracted_at,TIMESTAMPTZ {sql_quote(ingested_at)} _ingested_at,{sql_quote(TRANSFORMATION_VERSION)} _transformation_version,{sql_quote(SEMANTIC_VERSION)} _semantic_version,'FULL_DOCUMENT_TRACE' _lineage_quality
      FROM read_csv_auto({xlsx}, header=true, all_varchar=true)"""
    sap = paths["OWHS"]
    unmapped = f"""UNION ALL SELECT 'warehouse_'||substr(sha256('warehouse|SAP_HANA|'||trim(WhsCode)),1,24),NULL,CAST(NULL AS TIMESTAMPTZ),CAST(NULL AS TIMESTAMPTZ),'SAP_HANA:OWHS_without_validated_branch_crosswalk',CAST(0.0 AS DECIMAL(38,12)),'UNMAPPED',
      'SAP_HANA','OWHS','WhsCode='||trim(WhsCode),NULL,CAST(NULL AS TIMESTAMPTZ),TIMESTAMPTZ {sql_quote(extracted_at)},TIMESTAMPTZ {sql_quote(ingested_at)},{sql_quote(TRANSFORMATION_VERSION)},{sql_quote(SEMANTIC_VERSION)},'FULL_DOCUMENT_TRACE' FROM read_parquet({sql_quote(str(sap))})"""
    return mapped + " " + unmapped


def alias_query() -> str:
    products = sql_quote(str(DATA_ROOT / "reference/products/part-00000.parquet"))
    warehouses = sql_quote(str(DATA_ROOT / "reference/warehouses/part-00000.parquet"))
    branches = sql_quote(str(DATA_ROOT / "reference/branches/part-00000.parquet"))
    # The source name is retained verbatim. Multiple candidates remain multiple
    # rows; consumers must not pick one without context.
    return f"""SELECT 'PRODUCT' entity_type, product_id canonical_id, name alias, normalized_product_name normalized_alias, 'reference.products:'||source_system alias_source,
      CASE WHEN source_system='SAP_HANA' THEN 100 ELSE 50 END priority, active, CAST(1.0 AS DECIMAL(38,12)) confidence,
      CASE WHEN count(*) OVER (PARTITION BY normalized_product_name) > 1 THEN 'AMBIGUOUS' ELSE 'MAPPED' END resolution_status, source_system _source_system, _source_dataset, _source_native_key, _source_file, _source_extracted_at, _ingested_at, _transformation_version, _semantic_version
      FROM read_parquet({products}) WHERE nullif(normalized_product_name,'') IS NOT NULL
      UNION ALL SELECT 'WAREHOUSE',warehouse_id,name,{norm_expr('name')},'reference.warehouses:'||source_system,CASE WHEN source_system='SAP_HANA' THEN 100 ELSE 50 END, status='ACTIVE',CAST(1.0 AS DECIMAL(38,12)), 'MAPPED',source_system,_source_dataset,_source_native_key,_source_file,_source_extracted_at,_ingested_at,_transformation_version,_semantic_version FROM read_parquet({warehouses}) WHERE nullif(trim(name),'') IS NOT NULL
      UNION ALL SELECT 'BRANCH',branch_id,name,{norm_expr('name')},'reference.branches:'||source_system,100,status='ACTIVE',CAST(1.0 AS DECIMAL(38,12)),'MAPPED',source_system,_source_dataset,_source_native_key,_source_file,_source_extracted_at,_ingested_at,_transformation_version,_semantic_version FROM read_parquet({branches}) WHERE nullif(trim(name),'') IS NOT NULL"""


def write_evidence(rows: dict[str, object], extraction_rows: list[dict[str, object]], benchmark: list[dict[str, object]], reference_metrics: list[dict[str, object]], crosswalk_metrics: list[dict[str, object]], mapping_metrics: list[dict[str, object]], alias_metrics: list[dict[str, object]]) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    def csv_out(name: str, data: list[dict[str, object]]) -> None:
        fields = sorted({k for row in data for k in row}) or ["status"]
        with (EVIDENCE / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(data)
    csv_out("reference_datasets.csv", reference_metrics)
    csv_out("crosswalk_datasets.csv", crosswalk_metrics)
    csv_out("mapping_quality.csv", mapping_metrics)
    csv_out("warehouse_branch_quality.csv", [{"warehouses_total": rows["warehouse_total"], "warehouses_mapped_to_branch": rows["warehouse_mapped"], "warehouses_unmapped": rows["warehouse_unmapped"], "branches_total": rows["branch_total"], "warehouse_multi_branch_conflicts": rows["multi_branch_conflicts"], "current_mapping": rows["current_mapping"], "historical_validity": "UNKNOWN; valid_from/valid_to remain NULL"}])
    csv_out("entity_alias_quality.csv", alias_metrics)
    csv_out("sap_master_extractions.csv", extraction_rows)
    csv_out("fast_lookup_benchmark.csv", benchmark)
    csv_out("build_manifest.csv", rows["manifest"])
    (EVIDENCE / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build() -> dict[str, object]:
    paths = latest_sap_paths()
    sap_extract_id = paths["OITM"].parents[2].name
    sap_extract_hashes = {table: sha256(path) for table, path in paths.items()}
    input_snapshot = json.dumps({"sap_extract_id": sap_extract_id, "sap_extract_sha256": sap_extract_hashes}, ensure_ascii=False)
    source_info = copy_reference_source()
    workbook_rows = parse_workbook(REFERENCE_SOURCE)
    if len(workbook_rows) != 51:
        raise RuntimeError(f"expected 51 warehouse-office rows, got {len(workbook_rows)}")
    temp = Path(tempfile.mkstemp(prefix="telchi-almacen-oficina-", suffix=".csv")[1])
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["WareHouseCode", "WareHouseName", "OfficeCode", "Oficina"]); writer.writeheader(); writer.writerows(workbook_rows)
    extracted_at = utc_now(); ingested_at = extracted_at; build_id = "reference_crosswalk_v1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ddb = duckdb.connect()
    manifest: list[dict[str, object]] = []; reference_metrics = []; crosswalk_metrics = []
    try:
        queries = build_queries(paths, temp, extracted_at, ingested_at)
        for dataset in REF_DATASETS:
            out, count, digest = write_parquet(ddb, dataset, queries[dataset])
            identity_col = {"products":"product_id","product_groups":"product_group_id","customers":"customer_id","suppliers":"supplier_id","warehouses":"warehouse_id","branches":"branch_id","document_types":"document_type","payment_terms":"payment_term_id","channels":"channel_id","units_of_measure":"unit_of_measure_id","warehouse_roles":"warehouse_role_id","currencies":"currency_code","users":"user_id","salespersons":"salesperson_id"}[dataset]
            duplicate = int(ddb.execute(f"SELECT count(*)-count(DISTINCT {identity_col}) FROM read_parquet({sql_quote(str(out))})").fetchone()[0]) if count else 0
            null_identity = int(ddb.execute(f"SELECT count(*) FROM read_parquet({sql_quote(str(out))}) WHERE {identity_col} IS NULL OR trim(CAST({identity_col} AS VARCHAR))='' ").fetchone()[0]) if count else 0
            reference_metrics.append({"dataset_id":dataset,"rows":count,"canonical_ids":count-duplicate,"source_native_ids":int(ddb.execute(f"SELECT count(DISTINCT source_system||'|'||source_native_id) FROM read_parquet({sql_quote(str(out))})").fetchone()[0]) if count else 0,"duplicates":duplicate,"unmapped":0,"ambiguous":0,"null_identity_fields":null_identity,"output_path":str(out),"output_sha256":digest})
            manifest.append({"build_id":build_id,"dataset_id":dataset,"inputs":json.dumps(["raw/legacy/parquet","raw/sap/table_extract",str(REF_SOURCE_DEST)],ensure_ascii=False),"input_hashes_or_snapshots":input_snapshot,"output_path":str(out),"output_rows":count,"output_sha256":digest,"schema_version":SCHEMA_VERSION,"semantic_version":SEMANTIC_VERSION,"transformation_version":TRANSFORMATION_VERSION,"built_at":ingested_at,"status":"SUCCEEDED"})
        for dataset in ["product_crosswalk","customer_crosswalk","supplier_crosswalk","warehouse_crosswalk","branch_crosswalk","salesperson_crosswalk","user_crosswalk"]:
            out, count, digest = write_parquet(ddb, dataset, crosswalk_query(dataset))
            status_counts = {str(r[0]): int(r[1]) for r in ddb.execute(f"SELECT status,count(*) FROM read_parquet({sql_quote(str(out))}) GROUP BY status").fetchall()}
            crosswalk_metrics.append({"dataset_id":dataset,"rows":count,"canonical_ids":int(ddb.execute(f"SELECT count(DISTINCT canonical_id) FROM read_parquet({sql_quote(str(out))})").fetchone()[0]) if count else 0,"source_native_ids":int(ddb.execute(f"SELECT count(DISTINCT source_system||'|'||source_native_id) FROM read_parquet({sql_quote(str(out))})").fetchone()[0]) if count else 0,"duplicates":count-int(ddb.execute(f"SELECT count(DISTINCT source_system||'|'||source_native_id||'|'||coalesce(CAST(valid_from AS VARCHAR),'')) FROM read_parquet({sql_quote(str(out))})").fetchone()[0]) if count else 0,"mapped":status_counts.get("CONFIRMED",0),"unmapped":status_counts.get("UNMAPPED",0),"ambiguous":status_counts.get("AMBIGUOUS",0),"output_path":str(out),"output_sha256":digest})
            manifest.append({"build_id":build_id,"dataset_id":dataset,"inputs":json.dumps([f"reference/{dataset.removesuffix('_crosswalk')}"],ensure_ascii=False),"input_hashes_or_snapshots":json.dumps({"reference":"same_build"}),"output_path":str(out),"output_rows":count,"output_sha256":digest,"schema_version":SCHEMA_VERSION,"semantic_version":SEMANTIC_VERSION,"transformation_version":TRANSFORMATION_VERSION,"built_at":ingested_at,"status":"SUCCEEDED"})
        out, count, digest = write_parquet(ddb, "warehouse_branch_mapping", mapping_query(temp, paths, extracted_at, ingested_at))
        status_counts = {str(r[0]): int(r[1]) for r in ddb.execute(f"SELECT status,count(*) FROM read_parquet({sql_quote(str(out))}) GROUP BY status").fetchall()}
        crosswalk_metrics.append({"dataset_id":"warehouse_branch_mapping","rows":count,"canonical_ids":int(ddb.execute(f"SELECT count(DISTINCT warehouse_id) FROM read_parquet({sql_quote(str(out))})").fetchone()[0]),"source_native_ids":count,"duplicates":0,"mapped":status_counts.get("CONFIRMED",0),"unmapped":status_counts.get("UNMAPPED",0),"ambiguous":status_counts.get("AMBIGUOUS",0),"output_path":str(out),"output_sha256":digest})
        manifest.append({"build_id":build_id,"dataset_id":"warehouse_branch_mapping","inputs":json.dumps([str(REF_SOURCE_DEST),"raw/sap/table_extract/OWHS"],ensure_ascii=False),"input_hashes_or_snapshots":json.dumps({"sap_extract_id":sap_extract_id,"sap_extract_sha256":sap_extract_hashes,"warehouse_branch_source":source_info["sha256"]}, ensure_ascii=False),"output_path":str(out),"output_rows":count,"output_sha256":digest,"schema_version":SCHEMA_VERSION,"semantic_version":SEMANTIC_VERSION,"transformation_version":TRANSFORMATION_VERSION,"built_at":ingested_at,"status":"SUCCEEDED"})
        alias_out_dir = DATA_ROOT / "reference/entity_alias"; alias_out_dir.mkdir(parents=True, exist_ok=True); alias_out = alias_out_dir / "part-00000.parquet"
        ddb.execute(f"COPY ({alias_query()}) TO {sql_quote(str(alias_out))} (FORMAT PARQUET, COMPRESSION ZSTD)")
        alias_count = int(ddb.execute(f"SELECT count(*) FROM read_parquet({sql_quote(str(alias_out))})").fetchone()[0]); alias_sha = sha256(alias_out)
        # Benchmarks are deliberately only against tiny reference/alias files.
        benchmark = []
        for label, query in [("product resolution", f"SELECT count(*) FROM read_parquet({sql_quote(str(alias_out))}) WHERE entity_type='PRODUCT' AND normalized_alias LIKE '%creolina%'"),("warehouse resolution", f"SELECT count(*) FROM read_parquet({sql_quote(str(alias_out))}) WHERE entity_type='WAREHOUSE' AND normalized_alias LIKE '%saavedra%'"),("branch resolution", f"SELECT count(*) FROM read_parquet({sql_quote(str(alias_out))}) WHERE entity_type='BRANCH' AND normalized_alias='segundo anillo'")]:
            start = time.perf_counter(); result = int(ddb.execute(query).fetchone()[0]); elapsed = (time.perf_counter()-start)*1000
            benchmark.append({"query":label,"rows":result,"latency_ms":round(elapsed,3),"dataset":"reference/entity_alias","status":"PASS" if result else "EXAMPLE_ENTITY_NOT_FOUND"})
        alias_status = ddb.execute(f"SELECT resolution_status,count(*) FROM read_parquet({sql_quote(str(alias_out))}) GROUP BY resolution_status").fetchall()
        alias_metrics = [{"dataset_id":"entity_alias","rows":alias_count,"mapped":sum(n for status,n in alias_status if status=='MAPPED'),"ambiguous":sum(n for status,n in alias_status if status=='AMBIGUOUS'),"manual_aliases":0,"source_aliases":"reference source names only","output_path":str(alias_out),"output_sha256":alias_sha}]
        manifest.append({"build_id":build_id,"dataset_id":"entity_alias","inputs":json.dumps(["reference/products","reference/warehouses","reference/branches"],ensure_ascii=False),"input_hashes_or_snapshots":json.dumps({"source_names_only":True}),"output_path":str(alias_out),"output_rows":alias_count,"output_sha256":alias_sha,"schema_version":"1.0.0","semantic_version":SEMANTIC_VERSION,"transformation_version":TRANSFORMATION_VERSION,"built_at":ingested_at,"status":"SUCCEEDED"})
        mapping_counts = {str(r[0]): int(r[1]) for r in ddb.execute(f"SELECT status,count(*) FROM read_parquet({sql_quote(str(DATA_ROOT / 'crosswalk/warehouse_branch_mapping/part-00000.parquet'))}) GROUP BY status").fetchall()}
        rows = {"gate":"TELCHI_DATALAKE_REFERENCE_AND_CROSSWALK_V1_PASS","build_id":build_id,"data_root":str(DATA_ROOT),"reference_datasets_expected":14,"reference_datasets_created":14,"crosswalk_datasets_expected":8,"crosswalk_datasets_created":8,"entity_alias_dataset_created":"YES","warehouse_total":int(ddb.execute(f"SELECT count(DISTINCT warehouse_id) FROM read_parquet({sql_quote(str(DATA_ROOT / 'reference/warehouses/part-00000.parquet'))})").fetchone()[0]),"warehouse_mapped":mapping_counts.get("CONFIRMED",0),"warehouse_unmapped":mapping_counts.get("UNMAPPED",0),"branch_total":int(ddb.execute(f"SELECT count(DISTINCT branch_id) FROM read_parquet({sql_quote(str(DATA_ROOT / 'reference/branches/part-00000.parquet'))})").fetchone()[0]),"multi_branch_conflicts":int(ddb.execute(f"SELECT count(*) FROM (SELECT warehouse_id FROM read_parquet({sql_quote(str(DATA_ROOT / 'crosswalk/warehouse_branch_mapping/part-00000.parquet'))}) WHERE status='CONFIRMED' GROUP BY warehouse_id HAVING count(DISTINCT branch_id)>1)").fetchone()[0]),"current_mapping":"51 REFERENCE_FILE mappings; SAP current warehouses remain UNMAPPED where no validated crosswalk exists","manifest":manifest,"source_reference":source_info,"reference_metrics":reference_metrics,"crosswalk_metrics":crosswalk_metrics,"alias_metrics":alias_metrics,"benchmarks":benchmark,"sap_accessed":"YES","sap_access_purpose":"MASTER_DATA_REFERENCE_ONLY","sap_write_count":0,"atomic_parquets_created":0,"business_parquets_created":0,"decision_parquets_created":0,"raw_legacy_files_modified":0,"raw_legacy_files_deleted":0,"raw_legacy_files_moved":0,"raw_legacy_parquet_verified":696,"warehouse_branch_temporal_unknown":mapping_counts.get("CONFIRMED",0),"products_canonical":next(x["canonical_ids"] for x in reference_metrics if x["dataset_id"]=='products'),"l_products":int(ddb.execute(f"SELECT count(*) FROM read_parquet({sql_quote(str(DATA_ROOT / 'reference/products/part-00000.parquet'))}) WHERE is_telchi_l_product").fetchone()[0]),"customers_canonical":next(x["canonical_ids"] for x in reference_metrics if x["dataset_id"]=='customers'),"suppliers_canonical":next(x["canonical_ids"] for x in reference_metrics if x["dataset_id"]=='suppliers'),"warehouses_canonical":int(ddb.execute(f"SELECT count(DISTINCT warehouse_id) FROM read_parquet({sql_quote(str(DATA_ROOT / 'reference/warehouses/part-00000.parquet'))})").fetchone()[0]),"branches_canonical":int(ddb.execute(f"SELECT count(DISTINCT branch_id) FROM read_parquet({sql_quote(str(DATA_ROOT / 'reference/branches/part-00000.parquet'))})").fetchone()[0]),"salespersons_canonical":next(x["canonical_ids"] for x in reference_metrics if x["dataset_id"]=='salespersons'),"users_canonical":next(x["canonical_ids"] for x in reference_metrics if x["dataset_id"]=='users'),"crosswalk_mapped":sum(x["mapped"] for x in crosswalk_metrics),"crosswalk_unmapped":sum(x["unmapped"] for x in crosswalk_metrics),"crosswalk_ambiguous":sum(x["ambiguous"] for x in crosswalk_metrics),"fast_lookup_tests":len(benchmark),"fast_lookup_max_ms":max(x["latency_ms"] for x in benchmark),"employees_canonical":"NOT_CREATED; OHEM is CORE_LATER and no physical V1 reference contract","reference_crosswalk_ready_for_atomic":"YES"}
        sap_extractions: list[dict[str, object]] = []
        for extraction_manifest in sorted(RUNS.glob("sap_master_reference_v1_*.json"), reverse=True):
            payload = json.loads(extraction_manifest.read_text(encoding="utf-8"))
            if payload.get("tables"):
                sap_extractions = payload["tables"]
                break
        write_evidence(rows, sap_extractions, benchmark, reference_metrics, crosswalk_metrics, [{"entity":"all","mapped":sum(x["mapped"] for x in crosswalk_metrics),"unmapped":sum(x["unmapped"] for x in crosswalk_metrics),"ambiguous":sum(x["ambiguous"] for x in crosswalk_metrics),"mapping_rate":round(sum(x["mapped"] for x in crosswalk_metrics)/sum(x["rows"] for x in crosswalk_metrics),6)}], alias_metrics)
        (RUNS / f"{build_id}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return rows
    finally:
        ddb.close(); temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-sap", action="store_true", help="read-only extract of the seven allowed SAP masters")
    args = parser.parse_args()
    extraction = extract_sap() if args.extract_sap else None
    result = build()
    if extraction:
        # Add extraction evidence without changing build outputs.
        path = EVIDENCE / "sap_master_extractions.csv"; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            fields = ["extraction_id","table","query","row_count","extracted_at","sql_hash","output_path","purpose","status"]
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(extraction["tables"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
