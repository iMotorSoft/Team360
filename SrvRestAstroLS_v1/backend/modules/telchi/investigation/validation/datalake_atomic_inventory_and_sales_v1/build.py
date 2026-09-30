"""Deterministic raw -> DuckLake Atomic publisher."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import duckdb

from modules.telchi.investigation.validation.ducklake_postgres18_foundation_v1.runtime import TelchiDuckLakeRuntime

from .common import (CROSSWALK_V2, DATA_ROOT, EVIDENCE_ROOT, LEGACY_ROOT, REFERENCE_MANIFEST,
                     SCHEMA_VERSION, TRANSFORMATION_VERSION, canonical_json, reference_identity,
                     sha256_bytes, sha256_file, utc_now, write_csv, write_json)
from .extract import latest_manifests

TABLES = {
    "sales_documents": "sales",
    "sales_lines": "sales",
    "credit_note_documents": "credit_notes",
    "credit_note_lines": "credit_notes",
    "inventory_movements": "inventory_movements",
    "inventory_balance_snapshots": "inventory_balance_snapshot",
}


def _files(manifest: dict[str, Any]) -> list[str]:
    root = Path(manifest["manifest_path"]).parent
    return [str(root / item["file"]) for item in manifest["files"]]


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _register_raw(connection: duckdb.DuckDBPyConnection, manifests: dict[str, dict[str, Any]]) -> None:
    for domain, manifest in manifests.items():
        paths = "[" + ",".join(_sql_string(path) for path in _files(manifest)) + "]"
        connection.execute(f"CREATE OR REPLACE TEMP VIEW raw_{domain} AS SELECT * FROM read_parquet({paths}, filename=true, union_by_name=true)")


def _mapping_views(connection: duckdb.DuckDBPyConnection) -> None:
    for kind in ("product", "customer", "warehouse"):
        path = _sql_string(str(CROSSWALK_V2 / f"{kind}_crosswalk" / "part-00000.parquet"))
        connection.execute(f"CREATE OR REPLACE TEMP VIEW map_{kind} AS SELECT source_native_id, canonical_id, status FROM read_parquet({path}) WHERE source_system='SAP_HANA' QUALIFY row_number() OVER (PARTITION BY source_native_id ORDER BY status='CONFIRMED' DESC)=1")
    path = _sql_string(str(CROSSWALK_V2 / "warehouse_branch_mapping" / "part-00000.parquet"))
    connection.execute(f"CREATE OR REPLACE TEMP VIEW map_branch AS SELECT warehouse_id, branch_id, status FROM read_parquet({path}) QUALIFY row_number() OVER (PARTITION BY warehouse_id ORDER BY status='CONFIRMED' DESC)=1")


def _common_lineage(domain: str, alias: str = "r") -> str:
    return f"'{domain}' AS source_dataset, '{TRANSFORMATION_VERSION}' AS transformation_version, '{SCHEMA_VERSION}' AS schema_version, '{alias}'"


def _build_temp_tables(connection: duckdb.DuckDBPyConnection, manifests: dict[str, dict[str, Any]], build_id: str, ingested_at: str, ref_version: str, ref_hash: str) -> None:
    sx = manifests["sales"]["extraction_id"]
    cx = manifests["credit_notes"]["extraction_id"]
    mx = manifests["inventory_movements"]["extraction_id"]
    ix = manifests["inventory_balance_snapshot"]["extraction_id"]
    snapshot_at = manifests["inventory_balance_snapshot"]["snapshot_at"]
    # Header values are source-native. No NET_SALES or cash/credit field exists.
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE stage_sales_documents AS
      SELECT 'sales_document_'||substr(sha256('SAP_B1|13|'||DocEntry),1,32) atomic_id,
        'SAP_B1_HANA' source_system, 'OINV' source_dataset, CAST(DocEntry AS VARCHAR) source_document_id,
        NULL::VARCHAR source_line_id, 'OINV:'||DocEntry source_record_locator, '{sx}' source_extraction_id,
        min(filename) source_file, NULL::VARCHAR source_file_hash,
        sha256(concat_ws('|',DocEntry,any_value(UpdateDate),any_value(UpdateTS),any_value(DocStatus),any_value(CANCELED),any_value(DocTotal))) source_row_hash,
        '13' document_type, DocEntry source_doc_entry, any_value(DocNum) document_number, any_value(Series) series,
        any_value(NumAtCard) external_number, any_value(CardCode) source_customer_id,
        any_value(mc.canonical_id) canonical_customer_id, coalesce(any_value(mc.status),'UNMAPPED') customer_mapping_status,
        any_value(CardName) customer_name, any_value(DocDate)::DATE document_date, any_value(DocDueDate)::DATE due_date,
        any_value(TaxDate)::DATE tax_date, any_value(CreateDate) source_created_at, any_value(UpdateDate) source_updated_at,
        any_value(UpdateTS) source_update_time, any_value(DocStatus) document_status, any_value(CANCELED) cancellation_status,
        any_value(DocSubType) document_subtype, any_value(DocCur) document_currency, any_value(DocRate) document_rate,
        any_value(SysRate) system_rate, any_value(DocTotal) source_document_total, any_value(DocTotalFC) source_document_total_fc,
        any_value(DocTotalSy) source_document_total_system, any_value(DiscPrcnt) source_discount_percent,
        any_value(DiscSum) source_discount_sum, any_value(VatSum) source_tax_sum, any_value(PaidToDate) source_paid_to_date,
        any_value(GroupNum) source_payment_terms_id, any_value(SlpCode) source_salesperson_id, any_value(UserSign) source_user_id,
        any_value(BPLId) source_branch_evidence, any_value(DataSource) source_channel_evidence,
        '{TRANSFORMATION_VERSION}' transformation_version, '{SCHEMA_VERSION}' schema_version, '{ref_version}' reference_version,
        '{ref_hash}' reference_manifest_hash, '{build_id}' build_id, TIMESTAMPTZ '{ingested_at}' ingested_at
      FROM raw_sales r LEFT JOIN map_customer mc ON mc.source_native_id=CAST(r.CardCode AS VARCHAR)
      WHERE DocEntry IS NOT NULL GROUP BY DocEntry""")
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE stage_sales_lines AS
      SELECT 'sales_line_'||substr(sha256('SAP_B1|13|'||r.DocEntry||'|'||r.LineNum),1,32) atomic_id,
        'sales_document_'||substr(sha256('SAP_B1|13|'||r.DocEntry),1,32) document_atomic_id,
        'SAP_B1_HANA' source_system, 'INV1' source_dataset, CAST(r.DocEntry AS VARCHAR) source_document_id,
        CAST(r.LineNum AS VARCHAR) source_line_id, 'INV1:'||r.DocEntry||':'||r.LineNum source_record_locator,
        '{sx}' source_extraction_id, filename source_file, NULL::VARCHAR source_file_hash,
        sha256(concat_ws('|',r.DocEntry,r.LineNum,r.ItemCode,r.Quantity,r.LineTotal,r.LineStatus)) source_row_hash,
        r.DocEntry source_doc_entry, r.LineNum source_line_number, r.ItemCode source_product_id,
        mp.canonical_id canonical_product_id, coalesce(mp.status,'UNMAPPED') product_mapping_status,
        r.Dscription description, r.Quantity source_quantity, r.unitMsr source_uom, r.NumPerMsr source_units_per_measure,
        r.WhsCode source_warehouse_id, mw.canonical_id canonical_warehouse_id, coalesce(mw.status,'UNMAPPED') warehouse_mapping_status,
        mb.branch_id canonical_branch_id, coalesce(mb.status,'UNMAPPED') branch_mapping_status,
        r.Price source_price, r.PriceBefDi source_price_before_discount, r.LineCurrency source_currency, r.LineRate source_rate,
        r.LineDiscPrcnt source_discount_percent, r.LineTotal source_line_total, r.TotalFrgn source_line_total_fc,
        r.TotalSumSy source_line_total_system, r.VatPrcnt source_tax_percent, r.LineVatSum source_tax_sum,
        r.GTotal source_gross_total, r.StockPrice source_stock_price, r.StockValue source_stock_value,
        r.BaseType source_base_type, r.BaseEntry source_base_entry, r.BaseLine source_base_line,
        r.LineStatus source_line_status, '{TRANSFORMATION_VERSION}' transformation_version, '{SCHEMA_VERSION}' schema_version,
        '{ref_version}' reference_version, '{ref_hash}' reference_manifest_hash, '{build_id}' build_id, TIMESTAMPTZ '{ingested_at}' ingested_at
      FROM raw_sales r LEFT JOIN map_product mp ON mp.source_native_id=CAST(r.ItemCode AS VARCHAR)
      LEFT JOIN map_warehouse mw ON mw.source_native_id=CAST(r.WhsCode AS VARCHAR)
      LEFT JOIN map_branch mb ON mb.warehouse_id=mw.canonical_id
      WHERE r.DocEntry IS NOT NULL AND r.LineNum IS NOT NULL
      QUALIFY row_number() OVER (PARTITION BY r.DocEntry,r.LineNum ORDER BY filename DESC)=1""")
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE stage_credit_note_documents AS
      SELECT 'credit_note_document_'||substr(sha256('SAP_B1|14|'||DocEntry),1,32) atomic_id,
        'SAP_B1_HANA' source_system, 'ORIN' source_dataset, CAST(DocEntry AS VARCHAR) source_document_id,
        NULL::VARCHAR source_line_id, 'ORIN:'||DocEntry source_record_locator, '{cx}' source_extraction_id,
        min(filename) source_file, NULL::VARCHAR source_file_hash,
        sha256(concat_ws('|',DocEntry,any_value(UpdateDate),any_value(UpdateTS),any_value(DocStatus),any_value(CANCELED),any_value(DocTotal))) source_row_hash,
        '14' document_type, DocEntry source_doc_entry, any_value(DocNum) document_number, any_value(Series) series,
        any_value(CardCode) source_customer_id, any_value(mc.canonical_id) canonical_customer_id,
        coalesce(any_value(mc.status),'UNMAPPED') customer_mapping_status, any_value(CardName) customer_name,
        any_value(DocDate)::DATE document_date, any_value(DocDueDate)::DATE due_date, any_value(TaxDate)::DATE tax_date,
        any_value(CreateDate) source_created_at, any_value(UpdateDate) source_updated_at, any_value(UpdateTS) source_update_time,
        any_value(DocStatus) document_status, any_value(CANCELED) cancellation_status, any_value(DocCur) document_currency,
        any_value(DocRate) document_rate, any_value(SysRate) system_rate, any_value(DocTotal) source_document_total,
        any_value(DocTotalFC) source_document_total_fc, any_value(DocTotalSy) source_document_total_system,
        any_value(DiscPrcnt) source_discount_percent, any_value(DiscSum) source_discount_sum,
        any_value(VatSum) source_tax_sum, any_value(PaidToDate) source_paid_to_date,
        any_value(GroupNum) source_payment_terms_id, any_value(SlpCode) source_salesperson_id,
        '{TRANSFORMATION_VERSION}' transformation_version, '{SCHEMA_VERSION}' schema_version, '{ref_version}' reference_version,
        '{ref_hash}' reference_manifest_hash, '{build_id}' build_id, TIMESTAMPTZ '{ingested_at}' ingested_at
      FROM raw_credit_notes r LEFT JOIN map_customer mc ON mc.source_native_id=CAST(r.CardCode AS VARCHAR)
      WHERE DocEntry IS NOT NULL GROUP BY DocEntry""")
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE stage_credit_note_lines AS
      SELECT 'credit_note_line_'||substr(sha256('SAP_B1|14|'||r.DocEntry||'|'||r.LineNum),1,32) atomic_id,
        'credit_note_document_'||substr(sha256('SAP_B1|14|'||r.DocEntry),1,32) document_atomic_id,
        'SAP_B1_HANA' source_system, 'RIN1' source_dataset, CAST(r.DocEntry AS VARCHAR) source_document_id,
        CAST(r.LineNum AS VARCHAR) source_line_id, 'RIN1:'||r.DocEntry||':'||r.LineNum source_record_locator,
        '{cx}' source_extraction_id, filename source_file, NULL::VARCHAR source_file_hash,
        sha256(concat_ws('|',r.DocEntry,r.LineNum,r.ItemCode,r.Quantity,r.LineTotal,r.LineStatus)) source_row_hash,
        r.DocEntry source_doc_entry, r.LineNum source_line_number, r.ItemCode source_product_id,
        mp.canonical_id canonical_product_id, coalesce(mp.status,'UNMAPPED') product_mapping_status,
        r.Dscription description, r.Quantity source_quantity, r.unitMsr source_uom, r.WhsCode source_warehouse_id,
        mw.canonical_id canonical_warehouse_id, coalesce(mw.status,'UNMAPPED') warehouse_mapping_status,
        mb.branch_id canonical_branch_id, coalesce(mb.status,'UNMAPPED') branch_mapping_status,
        r.Price source_price, r.PriceBefDi source_price_before_discount, r.LineCurrency source_currency,
        r.LineDiscPrcnt source_discount_percent, r.LineTotal source_line_total, r.TotalFrgn source_line_total_fc,
        r.TotalSumSy source_line_total_system, r.VatPrcnt source_tax_percent, r.LineVatSum source_tax_sum,
        r.GTotal source_gross_total, r.StockPrice source_stock_price, r.StockValue source_stock_value,
        r.BaseType source_base_type, r.BaseEntry source_base_entry, r.BaseLine source_base_line,
        r.LineStatus source_line_status, '{TRANSFORMATION_VERSION}' transformation_version, '{SCHEMA_VERSION}' schema_version,
        '{ref_version}' reference_version, '{ref_hash}' reference_manifest_hash, '{build_id}' build_id, TIMESTAMPTZ '{ingested_at}' ingested_at
      FROM raw_credit_notes r LEFT JOIN map_product mp ON mp.source_native_id=CAST(r.ItemCode AS VARCHAR)
      LEFT JOIN map_warehouse mw ON mw.source_native_id=CAST(r.WhsCode AS VARCHAR)
      LEFT JOIN map_branch mb ON mb.warehouse_id=mw.canonical_id
      WHERE r.DocEntry IS NOT NULL AND r.LineNum IS NOT NULL
      QUALIFY row_number() OVER (PARTITION BY r.DocEntry,r.LineNum ORDER BY filename DESC)=1""")
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE stage_inventory_movements AS
      SELECT 'inventory_movement_'||substr(sha256(concat_ws('|','SAP_B1',r.TransNum,r.Instance,r.DocLineNum,r.ItemCode,r.Warehouse)),1,32) atomic_id,
        'SAP_B1_HANA' source_system, 'OINM' source_dataset, CAST(r.TransNum AS VARCHAR) source_document_id,
        CAST(r.DocLineNum AS VARCHAR) source_line_id,
        'OINM:'||concat_ws(':',r.TransNum,r.Instance,r.DocLineNum,r.ItemCode,r.Warehouse) source_record_locator,
        '{mx}' source_extraction_id, filename source_file, NULL::VARCHAR source_file_hash,
        sha256(concat_ws('|',r.TransNum,r.Instance,r.DocLineNum,r.ItemCode,r.Warehouse,r.InQty,r.OutQty,r.TransValue,r.Balance)) source_row_hash,
        r.TransNum source_transaction_number, r.Instance source_instance, r.TransType source_transaction_type,
        r.CreatedBy source_created_by, r.BaseRef source_base_reference, r.DocLineNum source_document_line_number,
        r.Ref1 source_reference_1, r.Ref2 source_reference_2, r.DocDate::DATE business_date,
        r.DocDueDate::DATE due_date, r.CardCode source_customer_id, mc.canonical_id canonical_customer_id,
        coalesce(mc.status,'UNMAPPED') customer_mapping_status, r.ItemCode source_product_id,
        mp.canonical_id canonical_product_id, coalesce(mp.status,'UNMAPPED') product_mapping_status,
        r.Dscription description, r.InQty source_in_quantity, r.OutQty source_out_quantity,
        r.TransValue source_transaction_value, r.CalcPrice source_calculated_price, r.Price source_price,
        r.Balance source_balance_evidence, r.Warehouse source_warehouse_id, mw.canonical_id canonical_warehouse_id,
        coalesce(mw.status,'UNMAPPED') warehouse_mapping_status, mb.branch_id canonical_branch_id,
        coalesce(mb.status,'UNMAPPED') branch_mapping_status, r.SlpCode source_salesperson_id, r.UserSign source_user_id,
        '{TRANSFORMATION_VERSION}' transformation_version, '{SCHEMA_VERSION}' schema_version, '{ref_version}' reference_version,
        '{ref_hash}' reference_manifest_hash, '{build_id}' build_id, TIMESTAMPTZ '{ingested_at}' ingested_at
      FROM raw_inventory_movements r LEFT JOIN map_product mp ON mp.source_native_id=CAST(r.ItemCode AS VARCHAR)
      LEFT JOIN map_customer mc ON mc.source_native_id=CAST(r.CardCode AS VARCHAR)
      LEFT JOIN map_warehouse mw ON mw.source_native_id=CAST(r.Warehouse AS VARCHAR)
      LEFT JOIN map_branch mb ON mb.warehouse_id=mw.canonical_id
      WHERE r.TransNum IS NOT NULL AND r.Instance IS NOT NULL AND r.DocLineNum IS NOT NULL
        AND r.ItemCode IS NOT NULL AND r.Warehouse IS NOT NULL
      QUALIFY row_number() OVER (PARTITION BY r.TransNum,r.Instance,r.DocLineNum,r.ItemCode,r.Warehouse ORDER BY filename DESC)=1""")
    connection.execute(f"""CREATE OR REPLACE TEMP TABLE stage_inventory_balance_snapshots AS
      SELECT 'inventory_balance_snapshot_'||substr(sha256(concat_ws('|','SAP_B1','{snapshot_at}',r.ItemCode,r.WhsCode)),1,32) atomic_id,
        'snapshot_'||substr(sha256('SAP_B1|OITW|{snapshot_at}'),1,32) snapshot_id,
        TIMESTAMPTZ '{snapshot_at}' snapshot_at, 'SAP_B1_HANA' source_system, 'OITW' source_dataset,
        NULL::VARCHAR source_document_id, NULL::VARCHAR source_line_id, 'OITW:'||r.ItemCode||':'||r.WhsCode source_record_locator,
        '{ix}' source_extraction_id, filename source_file, NULL::VARCHAR source_file_hash,
        sha256(concat_ws('|',r.ItemCode,r.WhsCode,r.OnHand,r.IsCommited,r.OnOrder,r.AvgPrice,r.StockValue)) source_row_hash,
        r.ItemCode source_product_id, mp.canonical_id canonical_product_id, coalesce(mp.status,'UNMAPPED') product_mapping_status,
        r.ItemName product_name, r.InvntryUom source_inventory_uom, r.WhsCode source_warehouse_id,
        mw.canonical_id canonical_warehouse_id, coalesce(mw.status,'UNMAPPED') warehouse_mapping_status,
        mb.branch_id canonical_branch_id, coalesce(mb.status,'UNMAPPED') branch_mapping_status,
        r.OnHand source_on_hand, r.IsCommited source_committed, r.OnOrder source_on_order, r.Consig source_consignment,
        r.Counted source_counted, r.MinStock source_min_stock, r.MaxStock source_max_stock, r.MinOrder source_min_order,
        r.AvgPrice source_average_price, r.StockValue source_stock_value, r.Locked source_locked, r.Freezed source_frozen,
        '{TRANSFORMATION_VERSION}' transformation_version, '{SCHEMA_VERSION}' schema_version, '{ref_version}' reference_version,
        '{ref_hash}' reference_manifest_hash, '{build_id}' build_id, TIMESTAMPTZ '{ingested_at}' ingested_at
      FROM raw_inventory_balance_snapshot r LEFT JOIN map_product mp ON mp.source_native_id=CAST(r.ItemCode AS VARCHAR)
      LEFT JOIN map_warehouse mw ON mw.source_native_id=CAST(r.WhsCode AS VARCHAR)
      LEFT JOIN map_branch mb ON mb.warehouse_id=mw.canonical_id
      WHERE r.ItemCode IS NOT NULL AND r.WhsCode IS NOT NULL
      QUALIFY row_number() OVER (PARTITION BY r.ItemCode,r.WhsCode ORDER BY filename DESC)=1""")


def _logical_hash(connection: duckdb.DuckDBPyConnection, table: str) -> str:
    columns = [row[0] for row in connection.execute(f"DESCRIBE stage_{table}").fetchall() if row[0] not in {"build_id", "ingested_at"}]
    expression = ",".join(f'coalesce(cast("{column}" as varchar),\'∅\')' for column in columns)
    row = connection.execute(f"SELECT count(*), bit_xor(hash(row_hash)), sum(hash(row_hash)::HUGEINT) FROM (SELECT atomic_id, sha256(concat_ws('|',{expression})) row_hash FROM stage_{table})").fetchone()
    return sha256_bytes(f"{row[0]}|{row[1]}|{row[2]}".encode())


def _snapshot(connection: duckdb.DuckDBPyConnection) -> int:
    return int(connection.execute("SELECT * FROM ducklake_current_snapshot('telchi')").fetchone()[0])


def build(*, simulate_failure: bool = False) -> dict[str, Any]:
    manifests = latest_manifests()
    missing = sorted(set({"sales", "credit_notes", "inventory_movements", "inventory_balance_snapshot"}) - set(manifests))
    if missing:
        raise RuntimeError(f"missing completed raw SAP extractions: {missing}")
    ref_version, ref_hash, _ = reference_identity()
    input_identity = {domain: manifest["manifest_hash"] for domain, manifest in manifests.items()}
    build_key = sha256_bytes(canonical_json({"inputs": input_identity, "reference": ref_hash, "transformation": TRANSFORMATION_VERSION}))
    build_id = f"atomic_v1_{build_key[:20]}"
    ingested_at = utc_now().isoformat()
    runtime = TelchiDuckLakeRuntime()
    started = time.perf_counter()
    with runtime.session() as connection:
        _register_raw(connection, manifests)
        _mapping_views(connection)
        _build_temp_tables(connection, manifests, build_id, ingested_at, ref_version, ref_hash)
        logical_hashes = {table: _logical_hash(connection, table) for table in TABLES}
        rows = {table: int(connection.execute(f"SELECT count(*) FROM stage_{table}").fetchone()[0]) for table in TABLES}
        before = _snapshot(connection)
        run_manifest_path = DATA_ROOT / "manifests" / "runs" / f"{build_id}.json"
        previous = json.loads(run_manifest_path.read_text()) if run_manifest_path.exists() else None
        idempotent = bool(previous and previous.get("logical_hashes") == logical_hashes and previous.get("status") == "COMPLETED")
        if not idempotent:
            connection.execute("BEGIN")
            try:
                connection.execute("CREATE SCHEMA IF NOT EXISTS telchi.atomic")
                connection.execute("CREATE SCHEMA IF NOT EXISTS telchi.ops")
                for table in TABLES:
                    connection.execute(f"CREATE OR REPLACE TABLE telchi.atomic.{table} AS SELECT * FROM stage_{table}")
                connection.execute("CREATE TABLE IF NOT EXISTS telchi.ops.atomic_build_runs (build_id VARCHAR, transformation_version VARCHAR, reference_version VARCHAR, reference_manifest_hash VARCHAR, input_hash VARCHAR, status VARCHAR, completed_at TIMESTAMPTZ)")
                connection.execute("DELETE FROM telchi.ops.atomic_build_runs WHERE build_id=?", [build_id])
                connection.execute("INSERT INTO telchi.ops.atomic_build_runs VALUES (?,?,?,?,?,'COMPLETED',current_timestamp)", [build_id, TRANSFORMATION_VERSION, ref_version, ref_hash, build_key])
                if simulate_failure:
                    raise RuntimeError("simulated failure before DuckLake commit")
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                if simulate_failure:
                    after_failure = _snapshot(connection)
                    return {"build_id": build_id, "simulated_failure": True, "snapshot_before": before, "snapshot_after": after_failure, "failed_build_atomicity_pass": before == after_failure}
                raise
        after = _snapshot(connection)
        counts_after = {table: int(connection.execute(f"SELECT count(*) FROM telchi.atomic.{table}").fetchone()[0]) for table in TABLES}
    raw_rows = sum(int(manifests[domain]["row_count"]) for domain in manifests)
    legacy_counts: dict[str, int] = {}
    local = duckdb.connect()
    try:
        for family in ("saleSB1Product", "ncB1Product", "movProductSB1", "movProduct"):
            files = [str(path) for path in sorted(LEGACY_ROOT.glob(f"{family}-*.parq"))]
            legacy_counts[family] = int(local.execute("SELECT count(*) FROM read_parquet(?, union_by_name=true)", [files]).fetchone()[0]) if files else 0
    finally:
        local.close()
    excluded = sum(legacy_counts.values())
    manifest = {
        "gate": "TELCHI_DATALAKE_ATOMIC_INVENTORY_AND_SALES_V1", "build_id": build_id,
        "started_at": ingested_at, "completed_at": utc_now().isoformat(), "transformation_version": TRANSFORMATION_VERSION,
        "schema_version": SCHEMA_VERSION, "reference_version": ref_version, "reference_manifest_hash": ref_hash,
        "source_extraction_ids": {k: v["extraction_id"] for k, v in manifests.items()},
        "source_file_hashes": {k: [item["sha256"] for item in v["files"]] for k, v in manifests.items()},
        "watermark_state": {k: {"strategy": v["watermark_strategy"], "from": v["watermark_from"], "to": v["watermark_to"]} for k, v in manifests.items()},
        "rows_read": raw_rows + excluded, "rows_accepted": raw_rows, "rows_quarantined": 0, "rows_rejected": 0,
        "rows_excluded": excluded, "legacy_exclusion_rule": "VALIDATION_ONLY: native line identity/cutover equivalence not sufficient for publication",
        "rows_inserted": 0 if idempotent else sum(rows.values()), "rows_updated": 0, "rows_unchanged": sum(rows.values()) if idempotent else 0,
        "atomic_row_count_after": sum(counts_after.values()), "dataset_rows": counts_after,
        "logical_hashes": logical_hashes, "ducklake_snapshot_before": before, "ducklake_snapshot_after": after,
        "second_build_idempotent": idempotent, "status": "COMPLETED", "duration_ms": round((time.perf_counter()-started)*1000, 3),
    }
    write_json(run_manifest_path, manifest)
    write_json(EVIDENCE_ROOT / "build_manifest.json", manifest)
    return manifest
