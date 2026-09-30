"""SAAVEDRA_MATERIAL_SUPPLY_RISK_V1 acceptance query over a pinned candidate.

Uses the explicit pinned candidate harness only.  No SAP.  No CURRENT reader.

Usage (from ``SrvRestAstroLS_v1/backend``)::

    uv run python modules/telchi/investigation/validation/\
datalake_material_supply_derivation_v1/run_query.py \
        --candidate foundation_6ab5bf89666671a11d747ef9054e0f42
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from pathlib import Path

import duckdb

from modules.telchi.datalake.ducklake import DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.material_supply_candidate import validate_pinned_candidate
from modules.telchi.datalake.material_supply_fact_capture import EVIDENCE_ROOT, write_json

QUERY = "SAAVEDRA_MATERIAL_SUPPLY_RISK_V1"
PACKAGING_RE = re.compile(
    r"FRASCO|TAPA|ETIQUETA|CAJA|ENVASE|BOLSA|PREFORM|CONTRA|GOTERO|SPRAY|"
    r"PULVERIZ|BOMBA|PRECINTA|PRECINTO|DOSIFIC|BIDON|TURRIL(?!\s*x)|BOTELLA|"
    r"CINTA|STICKER|TAPON|AMPOLLA|SACHET|BLISTER|POTE",
    re.IGNORECASE,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=QUERY)
    parser.add_argument("--candidate", default=os.getenv("FOUNDATION_CANDIDATE_ID"))
    args = parser.parse_args(argv)
    if not args.candidate:
        raise SystemExit("FOUNDATION_CANDIDATE_ID is required (fail closed)")

    connector = DuckLakeConnector()
    store = FoundationPublicationStore(connection_factory=connector.session)
    pinned = validate_pinned_candidate(store, args.candidate)
    files = [str(path) for path in pinned.dataset_files("material_supply_status")]

    connection = duckdb.connect()
    try:
        rows = connection.execute(
            f"SELECT ItemCode, material_name, current_stock, inventory_uom, "
            f"TRY_CAST(coverage_days AS DOUBLE) AS coverage_days, coverage_basis, coverage_confidence, "
            f"procurement_profile, TRY_CAST(lead_time_days AS DOUBLE) AS lead_time_days, lead_time_confidence, "
            f"TRY_CAST(open_po_qty AS DOUBLE) AS open_po_qty, open_po_expected_date, open_po_destination, "
            f"TRY_CAST(other_location_stock AS DOUBLE) AS other_location_stock, "
            f"local_stockout, global_stockout, supply_risk "
            f"FROM read_parquet({files!r}) WHERE is_raw_material = TRUE"
        ).fetchall()
        columns = [d[0] for d in connection.description]
    finally:
        connection.close()

    records = [dict(zip(columns, row)) for row in rows]
    materials = [r for r in records if not PACKAGING_RE.search(str(r["material_name"] or ""))]
    for record in materials:
        record["coverage_band"] = _band(record["coverage_days"], record["current_stock"])
    near = sorted(
        [r for r in materials if r["coverage_days"] is not None and r["coverage_days"] < 60],
        key=lambda r: r["coverage_days"],
    )
    result = {
        "query": QUERY,
        "query_executed": True,
        "data_source": "TELCHI_DATA_LAKE_FOUNDATION",
        "foundation_id": pinned.foundation_publication_id,
        "reader_mode": pinned.reader_mode,
        "sap_accessed": "NO",
        "used_latest_component": "NO",
        "mixed_component_versions": "NO",
        "QUERY_ROWS": len(materials),
        "COVERAGE_LT_60": len(near),
        "SUPPLY_RISK_COUNT": sum(1 for r in materials if r["supply_risk"] not in ("MANAGEABLE", "MITIGATED", "UNKNOWN")),
        "LOCAL_STOCKOUTS": sum(1 for r in materials if r["local_stockout"]),
        "GLOBAL_STOCKOUTS": sum(1 for r in materials if r["global_stockout"]),
        "OPEN_PO_MITIGATED": sum(1 for r in materials if r["supply_risk"] == "MITIGATED"),
        "OPEN_PO_PARTIAL_MITIGATION": sum(1 for r in materials if r["supply_risk"] == "PARTIALLY_MITIGATED"),
        "LEAD_TIME_UNAVAILABLE_IN_RESULT": sum(1 for r in materials if r["lead_time_days"] is None),
        "DENSITY_BLOCKED": 0,
        "UNIT_UNRESOLVED": sum(1 for r in materials if r["coverage_days"] is None),
        "near_60_days": near,
        "supply_risk_view": [r for r in materials if r["supply_risk"] in ("NO_INBOUND", "INBOUND_TOO_LATE", "INBOUND_DESTINATION_UNCERTAIN", "PARTIALLY_MITIGATED")],
    }
    write_json(EVIDENCE_ROOT / "saavedra_query_result.json", result)
    write_json(EVIDENCE_ROOT / "saavedra_query_risk_view.json", result["supply_risk_view"])
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, list)}, indent=2, sort_keys=True, default=str))
    for row in near[:25]:
        print(row)
    return 0


def _band(coverage_days: float | None, stock: float) -> str:
    if stock is not None and float(stock) <= 0:
        return "QUIEBRE"
    if coverage_days is None:
        return "UNRESOLVED"
    if coverage_days < 15:
        return "CRITICO"
    if coverage_days < 30:
        return "ALTO"
    if coverage_days < 60:
        return "ATENCION"
    return "OK"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())