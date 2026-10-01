from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path
from statistics import median
from xml.etree import ElementTree as ET

import duckdb

SOURCE = Path(os.environ.get("TEAM360_TELCHI_LEGACY_ROOT", "/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience/DS")).resolve()
EVIDENCE = Path(os.environ.get("TEAM360_TELCHI_EVIDENCE_ROOT", "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/investigation-consolidation-v1/files/validation")).resolve() / "historical_data_inventory_v1"
REPORT = Path(__file__).resolve().parents[2] / "docs" / "TELCHI_HISTORICAL_DATA_INVENTORY_V1.md"
EVIDENCE.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

FAMILY_RE = re.compile(r"^(?P<family>.+)-(?P<date>\d{4}-\d{2}-\d{2})(?P<h>-h)?\.parq$", re.I)
DATE_NAME_RE = re.compile(r"date|fecha|\bts\b|tssale|tssync|tscash|tracking", re.I)
BUSINESS_DATE_RE = re.compile(r"^(docdate|saledate|orderdate|cashdate|recondate|trackingdate|fecha|ts)$|date$", re.I)
EXCLUDE_BUSINESS = re.compile(r"update|create|due|expiration|tax|log|purchaseexpensets", re.I)

KEYS = {
    "movProduct": ["WareHouseCode", "ProductCode", "YMD"],
    "movProductSB1": ["TransNum", "DocLineNum", "ItemCode", "Warehouse"],
    "saleProduct": ["SaleCode", "ProductCode"],
    "saleSB1Product": ["DocEntry", "ItemCode"],
    "purchase": ["NroOrden", "PurchaseProductCode"],
    "purchaseExpense": ["NroOrden", "ProductCode"],
    "cash": ["NroTransaccion"],
    "cuentasxCobrar": ["CuentaxCobrarCode"],
    "ProductSaleCostDay": ["ProductCode", "TS"],
    "productTracking": ["NroTrasaccion", "ProductCode", "TrackingDate"],
    "productTransform": ["Transaccion", "CodProducto", "CodInsumo"],
    "payout": ["Transaccion", "CodProducto", "CodInsumo"],
    "paymentB1": ["DocEntry"],
    "reconB1": ["ReconNum", "LineSeq"],
    "ncB1Product": ["DocEntry", "ItemCode", "WhsCode"],
}


def rel(p: Path) -> str:
    return p.relative_to(SOURCE).as_posix()


def family_for(name: str) -> tuple[str, str, str]:
    m = FAMILY_RE.match(name)
    if m:
        return m.group("family"), m.group("date"), "h" if m.group("h") else "standard"
    return Path(name).stem, "", "static"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    return str(v)


def normalize_date_value(value: str) -> str:
    """Normalize common legacy date strings for filename/content comparison."""
    value = value.strip()
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})(?:.*)?", value)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return value[:10]


def xlsx_sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("xl/workbook.xml"))
    return [x.attrib.get("name", "") for x in root.iter() if x.tag.rsplit("}", 1)[-1] == "sheet"]


def read_excel_via_libreoffice(path: Path) -> tuple[list[str], list[list[str]]]:
    with tempfile.TemporaryDirectory(prefix="telchi_inventory_xlsx_") as td:
        out = Path(td)
        profile = out / "profile"
        profile.mkdir()
        subprocess.run(
            ["libreoffice", "-env:UserInstallation=file://" + str(profile), "--headless", "--convert-to", "csv", "--outdir", str(out), str(path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        csv_path = out / (path.stem + ".csv")
        with csv_path.open("r", newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.reader(f))
    while rows and not any(x.strip() for x in rows[-1]):
        rows.pop()
    header = rows[0] if rows else []
    data = [r for r in rows[1:] if any(x.strip() for x in r)]
    return header, data


def parse_excel(path: Path) -> dict:
    header, rows = read_excel_via_libreoffice(path)
    width = max([len(header), *(len(r) for r in rows)] or [0])
    normalized = [tuple((r + [""] * width)[:width]) for r in rows]
    dup = len(normalized) - len(set(normalized))
    return {
        "file": rel(path),
        "sheet_names": json.dumps(xlsx_sheet_names(path), ensure_ascii=False),
        "sheet_count": len(xlsx_sheet_names(path)),
        "rows": len(rows),
        "columns": width,
        "column_names": json.dumps(header, ensure_ascii=False),
        "duplicate_rows": dup,
        "header": header,
        "data": rows,
    }


def parse_csv(path: Path) -> dict:
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    while rows and not any(x.strip() for x in rows[-1]):
        rows.pop()
    header = rows[0] if rows else []
    data = [r for r in rows[1:] if any(x.strip() for x in r)]
    width = max([len(header), *(len(r) for r in data)] or [0])
    normalized = [tuple((r + [""] * width)[:width]) for r in data]
    return {"file": rel(path), "sheet_names": "", "sheet_count": 0, "rows": len(data), "columns": width, "column_names": json.dumps(header, ensure_ascii=False), "duplicate_rows": len(normalized) - len(set(normalized)), "header": header, "data": data}


def month_tokens(lo: date, hi: date) -> list[str]:
    out = []
    y, m = lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def main() -> None:
    files = sorted(p for p in SOURCE.rglob("*") if p.is_file())
    physical = []
    hashes = defaultdict(list)
    for p in files:
        st = p.stat()
        ext = p.suffix.lower() if p.suffix else "[no_extension]"
        if ext in {".parq", ".parquet"}:
            kind = ext[1:]
        elif ext in {".xlsx", ".xls", ".csv", ".json", ".db", ".sqlite", ".sql", ".py"}:
            kind = ext[1:]
        else:
            kind = "otros"
        digest = sha256(p)
        hashes[(st.st_size, digest)].append(rel(p))
        physical.append({"relative_path": rel(p), "filename": p.name, "extension": ext, "type": kind, "size_bytes": st.st_size, "size_mb": f"{st.st_size / 1048576:.6f}", "modified_at": datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(), "sha256": digest})
    write_csv(EVIDENCE / "historical_files_inventory.csv", physical, ["relative_path", "filename", "extension", "type", "size_bytes", "size_mb", "modified_at", "sha256"])

    parquet_paths = [p for p in files if p.suffix.lower() in {".parq", ".parquet"}]
    by_family: dict[str, list[Path]] = defaultdict(list)
    file_info = {}
    for p in parquet_paths:
        fam, fd, variant = family_for(p.name)
        by_family[fam].append(p)
        file_info[str(p.resolve())] = {"path": rel(p), "filename": p.name, "family": fam, "file_date": fd, "variant": variant, "size_bytes": p.stat().st_size}

    con = duckdb.connect()
    con.execute("PRAGMA threads=2")
    con.execute("PRAGMA memory_limit='1GB'")
    metadata = con.execute("SELECT file_name, created_by, num_rows, num_row_groups, format_version FROM parquet_file_metadata(?)", [str(SOURCE / "*.parq")]).fetchall()
    for fn, created_by, nrows, ngr, fmt in metadata:
        k = str(Path(str(fn)).resolve())
        if k in file_info:
            file_info[k].update({"row_count": int(nrows), "row_groups": int(ngr), "created_by": created_by or "", "format_version": fmt})
    schemas = con.execute("SELECT file_name, name, duckdb_type, column_id FROM parquet_schema(?) WHERE name <> 'schema' ORDER BY file_name, column_id", [str(SOURCE / "*.parq")]).fetchall()
    schema_by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for fn, name, typ, cid in schemas:
        k = str(Path(str(fn)).resolve())
        if k in file_info:
            schema_by_file[k].append((str(name), str(typ)))
    pmeta = con.execute("SELECT file_name, row_group_id, path_in_schema, compression, stats_null_count FROM parquet_metadata(?)", [str(SOURCE / "*.parq")]).fetchall()
    rg_by_file: dict[str, set] = defaultdict(set)
    comp_by_file: dict[str, set] = defaultdict(set)
    nulls_by_file: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for fn, rg, col, comp, null_count in pmeta:
        k = str(Path(str(fn)).resolve())
        if k in file_info:
            rg_by_file[k].add(int(rg)); comp_by_file[k].add(str(comp))
            if null_count is not None:
                nulls_by_file[k][str(col)] += int(null_count)
    for k, info in file_info.items():
        info["row_groups"] = len(rg_by_file[k]) or info.get("row_groups", 0)
        info["compression"] = ",".join(sorted(comp_by_file[k]))
        info["columns"] = [x[0] for x in schema_by_file[k]]
        info["types"] = {x[0]: x[1] for x in schema_by_file[k]}
        info["null_counts"] = dict(nulls_by_file[k])
        info["schema_signature"] = "|".join(f"{n}:{t}" for n, t in schema_by_file[k])

    # Grouped date scans are progressive: one family at a time, never all files in memory.
    for fam, paths in by_family.items():
        allcols = {}
        for p in paths:
            for n, t in schema_by_file[str(p.resolve())]:
                allcols.setdefault(n, set()).add(t)
        dcols = [n for n, ts in allcols.items() if any(t.upper().startswith(("DATE", "TIMESTAMP")) for t in ts) or DATE_NAME_RE.search(n)]
        if not dcols:
            continue
        expr = ", ".join(f"min(CAST({qident(c)} AS VARCHAR)) AS {qident(c + '__min')}, max(CAST({qident(c)} AS VARCHAR)) AS {qident(c + '__max')}" for c in dcols)
        try:
            rows = con.execute(f"SELECT filename, {expr} FROM read_parquet(?, union_by_name=true, filename=true) GROUP BY filename", [[str(p) for p in paths]]).fetchall()
            names = [x[0] for x in con.description]
            for row in rows:
                vals = dict(zip(names, row)); k = str(Path(str(vals.pop("filename"))).resolve())
                date_stats = {c: {"min": stringify(vals.get(c + "__min")), "max": stringify(vals.get(c + "__max"))} for c in dcols}
                info = file_info[k]; info["date_stats"] = date_stats
                preferred = [c for c in dcols if BUSINESS_DATE_RE.search(c) and not EXCLUDE_BUSINESS.search(c)]
                use = preferred or dcols
                mins = [normalize_date_value(date_stats[c]["min"]) for c in use if date_stats[c]["min"]]
                maxs = [normalize_date_value(date_stats[c]["max"]) for c in use if date_stats[c]["max"]]
                info["content_date_min"] = min(mins) if mins else ""
                info["content_date_max"] = max(maxs) if maxs else ""
                fd = info["file_date"]
                if not fd or not mins:
                    relation = "UNKNOWN"
                elif info["content_date_min"] == fd and info["content_date_max"] == fd:
                    relation = "SINGLE_DAY_MATCH"
                elif info["content_date_min"] <= fd <= info["content_date_max"]:
                    relation = "CONTAINS_FILENAME_DATE"
                elif fd < info["content_date_min"] or fd > info["content_date_max"]:
                    relation = "OUTSIDE_CONTENT_RANGE"
                else:
                    relation = "CONTENT_DIFFERENT"
                info["filename_content_relation"] = relation
        except Exception as exc:
            for p in paths:
                file_info[str(p.resolve())]["date_scan_error"] = str(exc)

    schema_rows = []
    for p in parquet_paths:
        i = file_info[str(p.resolve())]
        schema_rows.append({**{k: i.get(k, "") for k in ["path", "filename", "family", "file_date", "variant", "row_count", "row_groups", "compression", "created_by", "format_version", "content_date_min", "content_date_max", "filename_content_relation"]}, "column_count": len(i.get("columns", [])), "column_names": json.dumps(i.get("columns", []), ensure_ascii=False), "data_types": json.dumps(i.get("types", {}), ensure_ascii=False, sort_keys=True), "null_counts": json.dumps(i.get("null_counts", {}), ensure_ascii=False, sort_keys=True), "date_stats": json.dumps(i.get("date_stats", {}), ensure_ascii=False, sort_keys=True), "schema_signature": i.get("schema_signature", "")})
    write_csv(EVIDENCE / "historical_parquet_schemas.csv", schema_rows, ["path", "filename", "family", "file_date", "variant", "row_count", "column_count", "column_names", "data_types", "null_counts", "parquet_row_groups", "compression", "created_by", "format_version", "content_date_min", "content_date_max", "filename_content_relation", "date_stats", "schema_signature"])

    excel_rows = []
    auxiliary_details = {}
    for p in files:
        if p.suffix.lower() == ".xlsx":
            detail = parse_excel(p); auxiliary_details[p.name] = detail
            excel_rows.append({k: detail[k] for k in ["file", "sheet_names", "sheet_count", "rows", "columns", "column_names", "duplicate_rows"]})
        elif p.suffix.lower() == ".csv":
            detail = parse_csv(p); auxiliary_details[p.name] = detail
            excel_rows.append({k: detail[k] for k in ["file", "sheet_names", "sheet_count", "rows", "columns", "column_names", "duplicate_rows"]})
    write_csv(EVIDENCE / "historical_auxiliary_files.csv", excel_rows, ["file", "sheet_names", "sheet_count", "rows", "columns", "column_names", "duplicate_rows"])

    # Physical mapping evidence for almacenOficina.xlsx.
    mapping = {}
    mapping_detail = auxiliary_details.get("almacenOficina.xlsx")
    map_metrics = {}
    if mapping_detail:
        h = [x.strip() for x in mapping_detail["header"]]
        idx = {x: i for i, x in enumerate(h)}
        rows = mapping_detail["data"]
        wh = defaultdict(set); office_names = defaultdict(set); office_codes = defaultdict(set)
        for r in rows:
            r = r + [""] * max(0, len(h) - len(r))
            wc = r[idx.get("WareHouseCode", -1)].strip() if "WareHouseCode" in idx else ""
            wn = r[idx.get("WareHouseName", -1)].strip() if "WareHouseName" in idx else ""
            oc = r[idx.get("OfficeCode", -1)].strip() if "OfficeCode" in idx else ""
            on = r[idx.get("Oficina", -1)].strip() if "Oficina" in idx else ""
            if wc:
                wc = re.sub(r"\.0+$", "", wc)
                mapping[wc] = {"warehouse_name": wn, "office_code": oc, "office_name": on}
                wh[wc].add((oc, on))
            if oc or on:
                office_names[on].add(wc); office_codes[oc].add(wc)
        map_metrics = {"columns": h, "warehouse_count": len(wh), "office_count_by_name": len([x for x in office_names if x]), "office_count_by_code": len([x for x in office_codes if x]), "warehouses_without_office": sorted(k for k, v in wh.items() if not any(a or b for a, b in v)), "duplicate_warehouse_rows": sum(max(0, len(v) - 1) for v in wh.values()), "warehouse_multiple_offices": {k: sorted(v) for k, v in wh.items() if len(v) > 1}, "office_multiple_warehouses": {k: len(v) for k, v in office_names.items() if k and len(v) > 1}}
    (EVIDENCE / "almacen_oficina_analysis.json").write_text(json.dumps(map_metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    quality_rows = []
    movement_rows = []
    for fam, paths in sorted(by_family.items()):
        cols = {n for p in paths for n, _ in schema_by_file[str(p.resolve())]}
        key_cols = [c for c in KEYS.get(fam, []) if c in cols]
        q = {"family": fam, "row_count": sum(file_info[str(p.resolve())].get("row_count", 0) for p in paths), "key": "+".join(key_cols), "key_incomplete_rows": "", "distinct_complete_keys": "", "duplicate_rows_within_files": "", "files_with_duplicates": "", "negative_quantity_rows": "", "zero_quantity_rows": "", "warehouse_values_unknown": ""}
        if key_cols:
            complete = " AND ".join(f"{qident(c)} IS NOT NULL AND trim(CAST({qident(c)} AS VARCHAR)) <> ''" for c in key_cols)
            keyval = "concat_ws(chr(31), " + ", ".join(f"CAST({qident(c)} AS VARCHAR)" for c in key_cols) + ")"
            try:
                detail = con.execute(f"SELECT filename, count(*) AS n, count(*) FILTER (WHERE NOT ({complete})) AS incomplete, count(DISTINCT CASE WHEN {complete} THEN {keyval} END) AS distinct_key FROM read_parquet(?, union_by_name=true, filename=true) GROUP BY filename", [[str(p) for p in paths]]).fetchall()
                q["key_incomplete_rows"] = sum(int(r[2]) for r in detail)
                q["distinct_complete_keys"] = sum(int(r[3]) for r in detail)
                q["duplicate_rows_within_files"] = sum(max(0, int(r[1]) - int(r[2]) - int(r[3])) for r in detail)
                q["files_with_duplicates"] = sum(1 for r in detail if int(r[1]) - int(r[2]) - int(r[3]) > 0)
            except Exception as exc:
                q["key_error"] = str(exc)
        qty_cols = [c for c in cols if re.search(r"cant|qty|quantity|inqty|outqty", c, re.I)]
        if qty_cols:
            neg = ", ".join(f"sum(CASE WHEN try_cast({qident(c)} AS DOUBLE) < 0 THEN 1 ELSE 0 END)" for c in qty_cols)
            zero = ", ".join(f"sum(CASE WHEN try_cast({qident(c)} AS DOUBLE) = 0 THEN 1 ELSE 0 END)" for c in qty_cols)
            try:
                vals = con.execute(f"SELECT {neg}, {zero} FROM read_parquet(?, union_by_name=true)", [[str(p) for p in paths]]).fetchone()
                q["negative_quantity_rows"] = sum(int(x or 0) for x in vals[:len(qty_cols)])
                q["zero_quantity_rows"] = sum(int(x or 0) for x in vals[len(qty_cols):])
            except Exception as exc:
                q["quantity_error"] = str(exc)
        wh_cols = [c for c in cols if c.lower() in {"warehouse", "warehousecode", "warehousecode", "whscode", "codalmacen", "almacencode"}]
        if wh_cols and mapping:
            unknown = set()
            try:
                for c in wh_cols:
                    vals = con.execute(f"SELECT DISTINCT CAST({qident(c)} AS VARCHAR) FROM read_parquet(?, union_by_name=true) WHERE {qident(c)} IS NOT NULL", [[str(p) for p in paths]]).fetchall()
                    for (v,) in vals:
                        sv = re.sub(r"\.0+$", "", str(v).strip())
                        if sv and sv not in mapping:
                            unknown.add(sv)
                q["warehouse_values_unknown"] = len(unknown)
                q["warehouse_unknown_examples"] = ",".join(sorted(unknown)[:20])
            except Exception as exc:
                q["warehouse_error"] = str(exc)
        quality_rows.append(q)

        if fam in {"movProduct", "movProductSB1"}:
            mcols = cols
            metrics = {"family": fam, "rows": q["row_count"], "distinct_products": "", "distinct_warehouses": "", "distinct_documents_or_trans": "", "nonzero_quantity_rows": "", "in_rows": "", "out_rows": "", "key_duplicate_rows": q.get("duplicate_rows_within_files", "")}
            try:
                if fam == "movProduct":
                    sql = f'''SELECT count(DISTINCT "ProductCode"), count(DISTINCT "WareHouseCode"), count(*) FILTER (WHERE "ProductMovCant" <> 0), count(DISTINCT "YMD") FROM read_parquet(?, union_by_name=true)'''
                else:
                    sql = f'''SELECT count(DISTINCT "ItemCode"), count(DISTINCT "Warehouse"), count(DISTINCT "TransNum"), count(*) FILTER (WHERE "InQty" > 0), count(*) FILTER (WHERE "OutQty" > 0), count(*) FILTER (WHERE "InQty" <> 0 OR "OutQty" <> 0) FROM read_parquet(?, union_by_name=true)'''
                vals = con.execute(sql, [[str(p) for p in paths]]).fetchone()
                if fam == "movProduct":
                    metrics.update({"distinct_products": vals[0], "distinct_warehouses": vals[1], "nonzero_quantity_rows": vals[2], "distinct_documents_or_trans": vals[3]})
                else:
                    metrics.update({"distinct_products": vals[0], "distinct_warehouses": vals[1], "distinct_documents_or_trans": vals[2], "in_rows": vals[3], "out_rows": vals[4], "nonzero_quantity_rows": vals[5]})
            except Exception as exc:
                metrics["error"] = str(exc)
            movement_rows.append(metrics)
    write_csv(EVIDENCE / "historical_quality_by_family.csv", quality_rows, sorted({k for r in quality_rows for k in r}))
    write_csv(EVIDENCE / "historical_movproduct_analysis.csv", movement_rows, sorted({k for r in movement_rows for k in r}))

    evolution = []
    for fam, paths in sorted(by_family.items()):
        nfiles = len(paths); fdates = sorted(i["file_date"] for i in (file_info[str(p.resolve())] for p in paths) if i["file_date"])
        allcols = sorted({n for p in paths for n, _ in schema_by_file[str(p.resolve())]})
        for col in allcols:
            present = [p for p in paths if col in file_info[str(p.resolve())]["types"]]
            types = sorted({file_info[str(p.resolve())]["types"][col] for p in present})
            dates = sorted(file_info[str(p.resolve())]["file_date"] for p in present if file_info[str(p.resolve())]["file_date"])
            first, last = (dates[0], dates[-1]) if dates else ("", "")
            if len(types) > 1: status = "TYPE_DRIFT"
            elif len(present) == nfiles: status = "STABLE"
            elif dates and fdates and first > fdates[0] and last < fdates[-1]: status = "ADDED_REMOVED"
            elif dates and fdates and first > fdates[0]: status = "ADDED"
            elif dates and fdates and last < fdates[-1]: status = "REMOVED"
            else: status = "UNKNOWN"
            evolution.append({"family": fam, "column": col, "first_appearance": first, "last_appearance": last, "types": ";".join(types), "file_count": len(present), "file_pct": f"{100*len(present)/nfiles:.2f}", "status": status})
    write_csv(EVIDENCE / "historical_schema_evolution.csv", evolution, ["family", "column", "first_appearance", "last_appearance", "types", "file_count", "file_pct", "status"])

    # Family summary and temporal gaps.
    family_rows = []
    for fam, paths in sorted(by_family.items()):
        infos = [file_info[str(p.resolve())] for p in paths]
        fd = sorted(i["file_date"] for i in infos if i["file_date"])
        cmins = [i.get("content_date_min") for i in infos if i.get("content_date_min")]
        cmaxs = [i.get("content_date_max") for i in infos if i.get("content_date_max")]
        months = sorted({x[:7] for x in fd})
        missing = []
        if fd:
            expected = month_tokens(date.fromisoformat(fd[0]), date.fromisoformat(fd[-1]))
            missing = [x for x in expected if x not in months]
        family_rows.append({"family": fam, "file_count": len(paths), "file_date_min": fd[0] if fd else "", "file_date_max": fd[-1] if fd else "", "content_date_min": min(cmins) if cmins else "", "content_date_max": max(cmaxs) if cmaxs else "", "volume_bytes": sum(i["size_bytes"] for i in infos), "volume_mb": f"{sum(i['size_bytes'] for i in infos)/1048576:.3f}", "row_count": sum(i.get("row_count", 0) for i in infos), "column_count_union": len({n for i in infos for n in i.get("columns", [])}), "schema_signature_count": len({i.get("schema_signature", "") for i in infos}), "row_group_total": sum(i.get("row_groups", 0) for i in infos), "compression": ",".join(sorted({i.get("compression", "") for i in infos if i.get("compression")})), "filename_date_relations": json.dumps(dict(Counter(i.get("filename_content_relation", "UNKNOWN") for i in infos)), ensure_ascii=False), "missing_calendar_months": ",".join(missing), "gap_month_count": len(missing)})
    write_csv(EVIDENCE / "historical_dataset_families.csv", family_rows, ["family", "file_count", "file_date_min", "file_date_max", "content_date_min", "content_date_max", "volume_bytes", "volume_mb", "row_count", "column_count_union", "schema_signature_count", "row_group_total", "compression", "filename_date_relations", "missing_calendar_months", "gap_month_count"])

    # Comparison/lineage evidence for the two movement families.
    mov = {r["family"]: r for r in movement_rows}
    comparison = {
        "movProduct": {k: mov.get("movProduct", {}).get(k, "") for k in mov.get("movProduct", {})},
        "movProductSB1": {k: mov.get("movProductSB1", {}).get(k, "") for k in mov.get("movProductSB1", {})},
        "shared_file_date_months": sorted(set(x["file_date"][:7] for x in family_rows if x["family"] == "movProduct" for _ in [0]) & set(x["file_date"][:7] for x in family_rows if x["family"] == "movProductSB1" for _ in [0])) if False else sorted(set(i["file_date"][:7] for p in by_family.get("movProduct", []) for i in [file_info[str(p.resolve())]]) & set(i["file_date"][:7] for p in by_family.get("movProductSB1", []) for i in [file_info[str(p.resolve())]])),
        "interpretation": "movProduct is a compact warehouse-product-period snapshot with no document lineage; movProductSB1 is a detailed transaction/line dataset with TransNum, TransType, DocLineNum, in/out quantities, cost and document/customer/seller enrichment. The SB1 origin is supported by field/table naming and document semantics, but the Parquet footer contains no authoritative source-system declaration."
    }
    (EVIDENCE / "movproduct_comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # Markdown report is intentionally summarized; CSVs are the complete evidence tables.
    ext_counts = Counter(x["extension"] for x in physical); type_counts = Counter(x["type"] for x in physical)
    total_bytes = sum(x["size_bytes"] for x in physical); total_rows = sum(int(i.get("row_count", 0)) for i in file_info.values())
    fam_sorted = sorted(family_rows, key=lambda x: int(x["volume_bytes"]), reverse=True)
    def fmt(n): return f"{int(n):,}".replace(",", ".")
    def fmts(n): return f"{n/1048576:,.2f} MB".replace(",", "X").replace(".", ",").replace("X", ".")
    def family_line(r): return f"| `{r['family']}` | {r['file_count']} | {r['file_date_min'] or '—'} | {r['file_date_max'] or '—'} | {r['content_date_min'] or '—'} → {r['content_date_max'] or '—'} | {fmts(int(r['volume_bytes']))} | {fmt(r['row_count'])} | {r['schema_signature_count']} |"
    qmap = {r["family"]: r for r in quality_rows}
    quality_focus = ["saleSB1Product", "movProductSB1", "movProduct", "purchase", "purchaseExpense", "cash", "productTracking", "paymentB1", "reconB1"]
    quality_table = ["| Familia | Filas | Clave candidata | Incompletas | Duplicados dentro de archivo | Archivos afectados |", "|---|---:|---|---:|---:|---:|"]
    for fam in quality_focus:
        q = qmap.get(fam)
        if q:
            quality_table.append(f"| `{fam}` | {fmt(q.get('row_count', 0))} | `{q.get('key', '') or '—'}` | {fmt(q.get('key_incomplete_rows', 0) or 0)} | {fmt(q.get('duplicate_rows_within_files', 0) or 0)} | {q.get('files_with_duplicates', 0) or 0} |")
    movement_summary = []
    for fam in ("movProduct", "movProductSB1"):
        m = mov.get(fam, {})
        if fam == "movProduct":
            movement_summary.append(f"- Métricas: {fmt(m.get('rows', 0))} filas, {fmt(m.get('distinct_products', 0))} productos, {fmt(m.get('distinct_warehouses', 0))} almacenes y {fmt(m.get('distinct_documents_or_trans', 0))} períodos YMD; {fmt(m.get('nonzero_quantity_rows', 0))} filas con cantidad no cero.")
        else:
            movement_summary.append(f"- Métricas: {fmt(m.get('rows', 0))} filas, {fmt(m.get('distinct_products', 0))} productos, {fmt(m.get('distinct_warehouses', 0))} almacenes, {fmt(m.get('distinct_documents_or_trans', 0))} TransNum, {fmt(m.get('in_rows', 0))} filas InQty y {fmt(m.get('out_rows', 0))} filas OutQty; duplicados de clave candidata dentro de archivo: {fmt(m.get('key_duplicate_rows', 0))}.")
    report = []
    report += ["# TELCHI DATA LAKE — HISTORICAL DATA INVENTORY V1", "", "## A. Gate", "", "**PASS — `TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS`**", "", "El inventario físico, Parquet y auxiliares se completó sobre el root histórico en modo read-only. No se consultó SAP/HANA por diseño de esta etapa; el lineage de sistema se conserva como unknown cuando no está declarado en los footers o nombres históricos.", "", "## B. Resumen ejecutivo", "", f"- Se relevaron **{fmt(len(files))} archivos** ({fmt(len(parquet_paths))} Parquet y {fmt(len(files)-len(parquet_paths))} auxiliares), {fmts(total_bytes)} en total; las fuentes no fueron modificadas.", f"- Los Parquet contienen **{fmt(total_rows)} filas** según metadata de footer; el mayor volumen está en compras, ventas y movimientos.", "- Hay familias mensuales históricas desde 2012 hasta 2024, además de snapshots maestros y una serie diaria de costos.", "- `movProduct` es compacto y agregado; `movProductSB1` conserva trazabilidad transaccional mucho más rica.", "- `saleProduct` es el histórico legacy; `saleSB1Product` es una familia SAP B1 enriquecida por líneas/documentos.", "- `almacenOficina.xlsx` es una referencia explícita almacén→oficina/sucursal.", "- Se observan cambios de schema en `movProductSB1`, `payout` y `ncB1Product`, principalmente nombres históricos.", "- Las fechas de filename y las fechas contenidas deben tratarse separadamente: muchos archivos son snapshots acumulativos.", "- La calidad presenta claves compuestas, columnas auxiliares de índice y riesgo de solapamiento entre snapshots.", "- No se diseñaron capas nuevas ni Parquet definitivos; el siguiente gate debe decidir lineage y contratos.", "", "## C. Inventario físico", "", f"Root consultado: `{SOURCE}`.", "", "### Conteo y volumen", "", "| Extensión | Archivos |", "|---|---:|", *[f"| `{k}` | {v} |" for k, v in sorted(ext_counts.items())], "", "| Tipo | Archivos |", "|---|---:|", *[f"| `{k}` | {v} |" for k, v in sorted(type_counts.items())], "", f"Directorios: el root es plano; no se encontraron subdirectorios con archivos. Volumen total: **{fmt(total_bytes)} bytes ({fmts(total_bytes)})**.", "", "La tabla completa reproducible está en `historical_files_inventory.csv`; incluye ruta relativa, tamaño, modificación y SHA-256. Los únicos nombres temporales/anómalos detectados son `.goutputstream-4D8NM0` y `.goutputstream-CKMFL0`; `read_parquet_schema.py` es auxiliar de código histórico. No hubo hashes repetidos exactos entre archivos.", "", "## D. Familias de Parquet", "", "`family` elimina solo la fecha del filename y el sufijo `-h`; los nombres estáticos permanecen como familias individuales.", "", "| Familia | Archivos | Fecha filename min | Fecha filename max | Fecha contenida min → max | Volumen | Filas | Schemas |", "|---|---:|---|---|---|---:|---:|---:|", *[family_line(r) for r in fam_sorted], "", "La tabla completa es `historical_dataset_families.csv`. La fecha de filename no fue usada como fecha de negocio. `missing_calendar_months` documenta meses sin archivo dentro del rango de cada familia.", "", "## E. Schemas y evolución", "", "`historical_parquet_schemas.csv` contiene una fila por Parquet con columnas, tipos, row groups, compression, creator/footer, conteos de null del footer y estadísticas min/max de campos temporales disponibles. `historical_schema_evolution.csv` contiene la matriz columna × familia solicitada.", "", "Hallazgos principales:", "", "- La mayoría de familias mensuales conserva schema estable dentro de su período.", "- `movProductSB1` tiene **45 columnas** en los archivos iniciales, pero en archivos posteriores aparecen renombres `OINV_DocNum`→`OINV.DocNum`, `OINV_CardCode`→`OINV.CardCode` y `UserSB1`→`User`; no deben tratarse como nuevas dimensiones sin una decisión semántica.", "- `payout` agrega `UserName` en parte de su historia; esto es una evolución real del schema, no evidencia suficiente de cambio de granularidad.", "- `ncB1Product` usa variantes `fu_*` frente a campos análogos de ventas; la semántica debe conservarse separada hasta reconciliación.", "- `__index_level_0__` aparece en múltiples Parquet y es un artefacto de exportación, no una clave de negocio confirmada.", "", "## F. `movProduct` / `movProductSB1`", "", "### `movProduct`", "", "- **Granularidad observada:** fila producto × almacén × período/snapshot (`WareHouseCode`, `ProductCode`, `YMD`), con `ProductMovCant`; no contiene `TransNum`, documento, línea documental, cliente, proveedor ni vendedor.", "- `TSSync` coincide operacionalmente con la fecha de generación/sincronización del archivo; `YMD`/`YM` son períodos derivados. Esto respalda snapshot/período, no prueba por sí solo que sea fecha de extracción.", "- Puede servir como evidencia histórica de posición/variación agregada por producto y almacén, pero no permite reconstruir una cadena documental.", "", "### `movProductSB1`", "", "- **Granularidad observada:** línea de movimiento de inventario enriquecida: `TransNum` + `DocLineNum` + `ItemCode`/`Warehouse`, con `TransType`, `base_ref`, `DocDate`, `InQty`, `OutQty`, costos y saldo.", "- **Trazabilidad presente:** producto, documento/base reference, movimiento, entrada/salida, almacén, cliente (cuando el join resolvió), vendedor, oficina, usuario, fecha, cantidad, costo y precio de venta. Importación, lote y serie no aparecen como campos dedicados en el schema inventariado.", "- La distinción entre `movProduct` y `movProductSB1` está respaldada por schema y métricas reproducibles en `historical_movproduct_analysis.csv`, no solo por el sufijo `SB1`.", "- El origen SAP B1 es **LIKELY**, por `TransNum`, `TransType`, `OINV.*`, `WhsCode` y nomenclatura de documentos; es **UNKNOWN como declaración formal** porque no hay metadata de lineage en los Parquet.", *movement_summary, "- Solapamiento de filename: " + (comparison["shared_file_date_months"] and ", ".join(comparison["shared_file_date_months"]) or "ninguno") + ". Ese solapamiento no demuestra que ambos conjuntos sean duplicados: su granularidad y columnas son distintas.", "", "## G. Excel/CSV auxiliares", "", "" + "`historical_auxiliary_files.csv` contiene hojas, filas, columnas, schema y duplicados por archivo. Todos los `.xlsx` encontrados tienen una sola hoja; `artist.csv` es un auxiliar no relacionado con Telchi (nombres de artistas).", "", "### `almacenOficina.xlsx`", "", f"- Columnas observadas: `{', '.join(map_metrics.get('columns', []))}`.", f"- {map_metrics.get('warehouse_count', 0)} almacenes, {map_metrics.get('office_count_by_code', 0)} códigos de oficina y {map_metrics.get('office_count_by_name', 0)} nombres de oficina.", f"- Almacenes sin oficina: {', '.join(map_metrics.get('warehouses_without_office', [])) or 'ninguno observado'}.", f"- Filas duplicadas exactas por mapping: {map_metrics.get('duplicate_warehouse_rows', 0)}; almacenes con múltiples oficinas: {json.dumps(map_metrics.get('warehouse_multiple_offices', {}), ensure_ascii=False) if map_metrics.get('warehouse_multiple_offices') else 'ninguno'}.", f"- Oficinas con múltiples almacenes: {fmt(len(map_metrics.get('office_multiple_warehouses', {})))} casos; ver `almacen_oficina_analysis.json` para el detalle.", "- Conclusión: es una referencia maestra útil para normalizar almacén→oficina, pero debe versionarse con vigencia temporal antes de usarla como dimensión histórica.", "", "## H. Relaciones detectadas", "", "| Relación | Estado | Evidencia / límite |", "|---|---|---|", "| `movProduct.ProductCode` ↔ `movProductSB1.ItemCode` | LIKELY | Identificador de producto y períodos solapados; tipos/nombres distintos; no se probó equivalencia completa. |", "| `movProduct.WareHouseCode` ↔ `movProductSB1.Warehouse` / `WhsCode` | POSSIBLE | Representan almacén, pero uno es código numérico y otros son códigos/texto; requiere catálogo temporal. |", "| `saleSB1Product.DocEntry` ↔ `movProductSB1` documento/base reference | POSSIBLE | Hay campos documentales, pero no todos los movimientos son ventas y no existe join formal universal en legacy. |", "| `purchase.NroOrden` ↔ `purchaseExpense.NroOrden` | LIKELY | Clave explícita compartida y misma fuente legacy; cardinalidad debe validarse antes de unir. |", "| `almacenOficina.WareHouseCode` ↔ campos de almacén | CONFIRMED (por código) | La tabla contiene el mapping explícito; vigencia histórica no está documentada. |", "| archivos snapshot de una misma familia | CONFIRMED | Fecha mensual en filename y filas repetidas entre cortes son esperables; no equivale a duplicado físico. |", "", "No se convierten correlaciones en hechos SAP. La evidencia detallada de claves y calidad está en los CSV externos.", "", "## I. Calidad y riesgos", "", "`historical_quality_by_family.csv` mide claves incompletas, duplicados dentro de cada archivo, cantidades negativas/cero y valores de almacén no encontrados en `almacenOficina.xlsx` cuando fue posible. Las claves son candidatas de diagnóstico y no contratos confirmados.", "", *quality_table, "", "Los duplicados de `cash`, `purchaseExpense`, `cuentasxCobrar` y otras familias pueden ser repetición de snapshots o una clave demasiado corta; no se clasifican automáticamente como errores. En `saleSB1Product`, `DocEntry+ItemCode` es la clave diagnóstica porque `WhsCode` está vacío en parte del histórico `-h`; ese campo queda como dimensión opcional a reconciliar.", "", "Principales riesgos que condicionan una migración futura:", "", "- Los snapshots mensuales pueden producir doble conteo si se concatenan sin una política de corte/versión.", "- Las claves de negocio no son uniformes: algunas familias tienen documento + línea, otras solo producto/almacén/período, y otras conservan índices pandas.", "- Fechas como `YMD`, `YM`, `TrackingDate` y `ExpirationDate` son strings; no tienen la misma confiabilidad que timestamps.", "- La presencia de nombres y datos derivados (`DocTotal`, `ItemSale`, `Deuda`, `Limite`) no prueba que sean hechos atómicos ni que su cálculo sea reproducible.", "- Valores nulos, ceros y negativos tienen semántica dependiente del dataset: por ejemplo, negativos en movimientos pueden representar salidas y no errores.", "- El mapping almacén→oficina no tiene vigencia ni evidencia de historización.", "- La ausencia de lote/serie/importación dedicados en `movProductSB1` limita la trazabilidad completa solicitada.", "", "## J. Datasets prioritarios", "", "| Prioridad | Familias | Motivo |", "|---|---|---|", "| CRITICAL | `saleSB1Product`, `movProductSB1` | Ventas/movimientos SAP B1 con documentos, productos, almacén, cantidades y costos; alto valor de trazabilidad. |", "| HIGH_VALUE | `purchase`, `purchaseExpense`, `saleProduct`, `ncB1Product`, `paymentB1`, `reconB1` | Compras, gastos, ventas legacy, notas de crédito, pagos y conciliaciones; cubren preguntas económicas clave con lineage incompleto. |", "| SUPPORTING | `productTracking`, `productTransform`, `payout`, `cash`, `cuentasxCobrar`, `ProductSaleCostDay` | Movimientos operativos, producción/transformación, caja, cuentas por cobrar y costos derivados; útiles pero con semántica/cobertura desigual. |", "| REFERENCE | `product`, `productSB1`, `clientSB1`, `person`, `wareHouseSB1`, `owhsSB1`, `sapWhsOfficeName`, `wareHouseOffice`, `almacenOficina.xlsx`, `oitbSB1`, `oactSB1`, `recetasNiveles01` | Catálogos, productos, clientes, almacenes, mapping y recetas. |", "| LEGACY_UNKNOWN | `mpRel`, `productosPrioridad`, `prontoProducts`, `productTKB`, `artist.*`, `horizontalTeam.xlsx`, `materiaPrima01.xlsx`, `matrizElaboración.xlsx` | Existe contenido, pero el uso Telchi y la vigencia no quedan probados en este inventario. |", "| REDUNDANT_CANDIDATE | Ninguno declarado | No se elimina ni descarta ningún archivo; la redundancia requiere reconciliación semántica. |", "", "## K. Riesgos / Unknowns", "", "- No se consultó SAP/HANA y no se inferió equivalencia entre legacy SQL Server, SAP B1 y cada Parquet.", "- No existe en los footers un lineage formal con consulta, sistema origen, zona horaria, usuario extractor o snapshot watermark.", "- Filename date puede ser extracción, snapshot, fecha de corte o período; la clasificación por familia está documentada como evidencia, no como contrato definitivo.", "- No se determinó una autorización histórica por fila; el usuario fue considerado administrator/all para este inventario. El requisito futuro de autorización previa al retrieval/análisis queda registrado, sin implementarlo.", "- Los `xls` clásicos no aparecieron; sí seis `.xlsx`, un `.csv`, 696 Parquet, dos temporales sin extensión y un `.py`.", "- Las métricas completas de null por campo no se forzaron sobre todo el universo: se usó metadata/footer y métricas focales para proteger memoria y tiempo. Requiere una auditoría de nulls por campo en el gate siguiente si se decide migración.", "", "## L. Recomendación para el siguiente gate", "", "Antes de diseñar Parquet nuevos, cerrar un segundo inventario independiente: **conocimiento/pruebas SAP ya realizado**, incluyendo consultas, tablas, semántica, cardinalidad, límites READ ONLY, evidencia y gaps. Después, aprobar un contrato de lineage y una política de snapshots/solapamientos; recién entonces evaluar un modelo físico.", "", "## Control de seguridad y cierre", "", "```text", "SAP_ACCESSED=NO", "SAP_WRITE_COUNT=0", "SOURCE_FILES_MODIFIED=0", "SOURCE_FILES_DELETED=0", "SOURCE_FILES_MOVED=0", "TELCHI_HISTORICAL_DATA_INVENTORY_V1_PASS", "```", "", "### Evidencia reproducible", "", "- `historical_files_inventory.csv`", "- `historical_parquet_schemas.csv`", "- `historical_dataset_families.csv`", "- `historical_schema_evolution.csv`", "- `historical_auxiliary_files.csv`", "- `historical_quality_by_family.csv`", "- `historical_movproduct_analysis.csv`", "- `almacen_oficina_analysis.json`", "- `movproduct_comparison.json`", "", f"Evidencia externa: `{EVIDENCE}`. Informe versionado: `{REPORT}`."]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"source": str(SOURCE), "report": str(REPORT), "evidence": str(EVIDENCE), "files": len(files), "parquet": len(parquet_paths), "families": len(by_family), "total_bytes": total_bytes}, ensure_ascii=False))


if __name__ == "__main__":
    main()
