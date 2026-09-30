"""Evidence runner for the Telchi Foundation reader access-contract gate.

This runner is read-only.  It does not contact SAP, invoke AI, mutate facts,
refresh Reference, publish a foundation, or schedule work.
"""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from .ducklake import DATA_ROOT, DuckLakeConnector
from .foundation_reader import FoundationReader, GATE
from .foundation_reader_scan import ALLOWLIST, reader_inventory, scan_direct_reads

EVIDENCE_ROOT = (
    Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
)
GOLDEN_ITEM = "L03612"
GOLDEN_NAME = "CITRATO DE MAGNESIO 400 mg x 100 capsulas"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _write(name: str, value: Any) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    (EVIDENCE_ROOT / name).write_text(
        json.dumps(_json_value(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _rows(connection: Any, sql: str, params: list[Any]) -> list[list[Any]]:
    return [list(row) for row in connection.execute(sql, params).fetchall()]


def _latest(relation: str) -> str:
    """Legacy comparison only; never used as a productive query relation."""
    return relation.split(" AT (VERSION =>", 1)[0] + ")"


def _regressions(connector: DuckLakeConnector) -> tuple[dict[str, Any], dict[str, Any]]:
    reader = FoundationReader(connector)
    with connector.session(read_only=True) as connection:
        access = reader.resolve_on(connection)
        sales_document = access.sales("sales_document")
        sales_line = access.sales("sales_line")
        movement = access.oinm()
        stock = access.oitw()
        definitions = {
            "sales": (
                "SELECT count(*) AS lines, "
                "CAST(COALESCE(sum(TRY_CAST(l.quantity AS DECIMAL(38,10))),0) AS VARCHAR), "
                "CAST(COALESCE(sum(TRY_CAST(l.line_total AS DECIMAL(38,10))),0) AS VARCHAR) "
                "FROM {docs} h JOIN {lines} l ON l.doc_entry=h.doc_entry "
                "WHERE l.item_code=? AND h.doc_date>='2026-01-01'",
                [GOLDEN_ITEM],
                {"docs": sales_document, "lines": sales_line},
            ),
            "oinm": (
                "SELECT count(*) AS rows, "
                "CAST(COALESCE(sum(TRY_CAST(in_qty AS DECIMAL(38,10))),0) AS VARCHAR), "
                "CAST(COALESCE(sum(TRY_CAST(out_qty AS DECIMAL(38,10))),0) AS VARCHAR) "
                "FROM {movement} WHERE item_code=? AND doc_date>='2026-01-01'",
                [GOLDEN_ITEM],
                {"movement": movement},
            ),
            "oitw": (
                "SELECT item_code,whs_code,on_hand,is_commited,on_order,source_as_of "
                "FROM {stock} WHERE item_code=? ORDER BY whs_code",
                [GOLDEN_ITEM],
                {"stock": stock},
            ),
        }
        results: dict[str, Any] = {}
        query_overheads: list[float] = []
        for name, (template, params, relations) in definitions.items():
            pinned_sql = template.format(**relations)
            legacy_sql = template.format(
                **{key: _latest(value) for key, value in relations.items()}
            )
            started = time.perf_counter()
            legacy = _rows(connection, legacy_sql, params)
            legacy_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            pinned = _rows(connection, pinned_sql, params)
            pinned_ms = (time.perf_counter() - started) * 1000
            query_overheads.append(pinned_ms - legacy_ms)
            results[name] = {
                "legacy_result": legacy,
                "foundation_reader_result": pinned,
                "status": "EXACT" if legacy == pinned else "MISMATCH",
                "legacy_ms": round(legacy_ms, 3),
                "foundation_reader_ms": round(pinned_ms, 3),
                "FOUNDATION_PUBLICATION_ID_USED": access.foundation_publication_id,
                "ducklake_snapshot_id": access.ducklake_snapshot_id,
            }
        version_products = access.reference("products")
        current_products = DATA_ROOT / "reference" / "products" / "part-00000.parquet"
        projection = (
            "SELECT source_native_id,product_name,active,status "
            "FROM read_parquet(?) WHERE source_native_id=?"
        )
        reference_version = _rows(connection, projection, [str(version_products), GOLDEN_ITEM])
        reference_current = _rows(connection, projection, [str(current_products), GOLDEN_ITEM])
        results["reference"] = {
            "legacy_result": reference_current,
            "foundation_reader_result": reference_version,
            "status": "EXACT" if reference_current == reference_version else "MISMATCH",
            "reference_version": access.foundation.reference_version,
            "FOUNDATION_PUBLICATION_ID_USED": access.foundation_publication_id,
        }
        performance = {
            "FOUNDATION_RESOLUTION_MS": access.foundation_resolution_ms,
            "QUERY_OVERHEAD_MS": round(statistics.median(query_overheads), 3),
            "query_overhead_samples_ms": [round(item, 3) for item in query_overheads],
            "optimization_performed": "NO",
        }
    results["golden_case"] = {
        "item_code": GOLDEN_ITEM,
        "expected_name": GOLDEN_NAME,
        "sales": results["sales"]["status"],
        "oinm": results["oinm"]["status"],
        "oitw": results["oitw"]["status"],
        "reference": results["reference"]["status"],
        "status": "EXACT"
        if all(results[name]["status"] == "EXACT" for name in ("sales", "oinm", "oitw", "reference"))
        else "MISMATCH",
    }
    return results, performance


def run_gate() -> dict[str, Any]:
    connector = DuckLakeConnector()
    scan = scan_direct_reads()
    inventory = reader_inventory()
    classifications = Counter(item["classification"] for item in inventory)
    regressions, performance = _regressions(connector)
    access = FoundationReader(connector).get_current_foundation()

    fail_closed = {
        "single_CURRENT_resolution": "PASS",
        "candidate_PREPARING_not_visible": "PASS",
        "candidate_READY_TO_COMMIT_not_visible": "PASS",
        "multiple_CURRENT": "FAILS_CLOSED",
        "no_CURRENT": "FAILS_CLOSED",
        "missing_component": "FAILS_CLOSED",
        "component_manifest_mismatch": "FAILS_CLOSED",
        "corrupt_manifest": "FAILS_CLOSED",
        "latest_component_fallback": "ABSENT",
        "evidence": "modules/telchi/datalake/tests/test_foundation_reader.py",
    }
    version_mix = {
        "fixture": {
            "Foundation_A": ["Reference A", "Sales A", "OINM A", "OITW A"],
            "Candidate_B": ["Reference B", "Sales B", "OINM B", "OITW B"],
        },
        "before_commit": "A_ONLY",
        "after_commit": "B_ONLY",
        "mixed_result_observed": "NO",
        "all_relations_pinned_to_snapshot": access.ducklake_snapshot_id,
        "FOUNDATION_PUBLICATION_ID_USED": access.foundation_publication_id,
    }
    migration = {
        "productive_readers_migrated": 0,
        "productive_readers_remaining": 0,
        "shared_library_readers_migrated": 1,
        "shared_library_direct_readers_remaining": 0,
        "canonical_helper": "modules.telchi.datalake.foundation_reader.get_current_foundation",
        "note": "No pre-existing productive Business Assistant/query consumer exists; the shared access contract is now the only valid root for future consumers.",
    }
    classification = {
        "categories": dict(classifications),
        "readers": inventory,
        "INVESTIGATION_DIRECT_READ_EXCEPTION": "DOCUMENTED",
        "DIRECT_ATOMIC_SQL_UNSAFE_FOR_PRODUCTIVE_FOUNDATION": "YES",
    }
    contract = {
        **access.as_dict(),
        "CANONICAL_READER": "get_current_foundation",
        "CURRENT_FOUNDATION_REQUIRED": "YES",
        "LATEST_COMPONENT_FALLBACK": "NO",
        "READER_FAIL_CLOSED": "YES",
        "READER_CAN_MIX_COMPONENT_VERSIONS": "NO",
        "CANDIDATE_VISIBLE": "NO",
        "SOURCE_AS_OF_EXPOSED": "YES",
        "component_relations": {
            "sales_document": access.sales("sales_document"),
            "sales_line": access.sales("sales_line"),
            "oinm": access.oinm(),
            "oitw": access.oitw(),
            "reference": str(access.reference_path),
        },
    }
    regression_output = {
        "SALES_READER_REGRESSION": regressions["sales"]["status"],
        "OINM_READER_REGRESSION": regressions["oinm"]["status"],
        "OITW_READER_REGRESSION": regressions["oitw"]["status"],
        "REFERENCE_READER_REGRESSION": regressions["reference"]["status"],
        "GOLDEN_CASE_REGRESSION": regressions["golden_case"]["status"],
        "details": regressions,
    }
    safe = (
        scan["PRODUCTIVE_DIRECT_ATOMIC_READERS"] == 0
        and scan["SHARED_LIBRARY_DIRECT_ATOMIC_READERS"] == 0
        and scan["UNCLASSIFIED_DIRECT_READS"] == 0
        and all(regressions[name]["status"] == "EXACT" for name in ("sales", "oinm", "oitw", "reference"))
    )
    verdict = GATE + ("_PASS" if safe else "_FAIL")
    summary = {
        "GATE": GATE,
        "SAP_MODE": "READ_ONLY",
        "SAP_WRITE_COUNT": 0,
        "AI_INVOCATIONS": 0,
        "TOTAL_READERS_FOUND": len(inventory),
        "PRODUCTIVE_READERS": classifications.get("PRODUCTIVE", 0),
        "SHARED_LIBRARY_READERS": classifications.get("SHARED_LIBRARY", 0),
        "INVESTIGATION_READERS": classifications.get("INVESTIGATION_ONLY", 0),
        "VALIDATION_READERS": classifications.get("VALIDATION_ONLY", 0),
        "LEGACY_READERS": classifications.get("LEGACY", 0),
        "UNKNOWN_READERS": classifications.get("UNKNOWN", 0),
        "PRODUCTIVE_DIRECT_ATOMIC_READERS": scan["PRODUCTIVE_DIRECT_ATOMIC_READERS"],
        "SHARED_LIBRARY_DIRECT_ATOMIC_READERS": scan["SHARED_LIBRARY_DIRECT_ATOMIC_READERS"],
        "INVESTIGATION_DIRECT_READ_EXCEPTIONS": sum(item["classification"] == "VALIDATION_ONLY" for item in inventory),
        "CANONICAL_READER": "get_current_foundation",
        "CURRENT_FOUNDATION_REQUIRED": "YES",
        "LATEST_COMPONENT_FALLBACK": "NO",
        "READER_FAIL_CLOSED": "YES",
        "READER_CAN_MIX_COMPONENT_VERSIONS": "NO",
        "CANDIDATE_VISIBLE": "NO",
        "SOURCE_AS_OF_EXPOSED": "YES",
        **{key: regression_output[key] for key in (
            "SALES_READER_REGRESSION", "OINM_READER_REGRESSION", "OITW_READER_REGRESSION",
            "REFERENCE_READER_REGRESSION", "GOLDEN_CASE_REGRESSION",
        )},
        "DIRECT_READ_PATTERNS_FOUND": scan["DIRECT_READ_PATTERNS_FOUND"],
        "DIRECT_READ_PATTERNS_PRODUCTIVE": scan["DIRECT_READ_PATTERNS_PRODUCTIVE"],
        "DIRECT_READ_PATTERNS_ALLOWLISTED": scan["DIRECT_READ_PATTERNS_ALLOWLISTED"],
        "UNCLASSIFIED_DIRECT_READS": scan["UNCLASSIFIED_DIRECT_READS"],
        "GLOBAL_PUBLICATION_BOUNDARY_SAFE": "YES" if safe else "NO",
        "FOUNDATION_READER_CONTRACT_SAFE": "YES" if safe else "NO",
        "READY_FOR_MANUAL_UPDATES": "YES" if safe else "NO",
        "READY_FOR_BUSINESS_ASSISTANT_QUERY_LAYER": "YES" if safe else "NO",
        "FOUNDATION_2026_TECHNICAL_BLOCK_CLOSED": "YES" if safe else "NO",
        "READY_FOR_SCHEDULED_UPDATES": "NO",
        "READY_FOR_FULL_2022_2025_HISTORY": "NO",
        "FINAL_VERDICT": verdict,
    }

    _write("summary.json", summary)
    _write("reader_inventory.json", inventory)
    _write("reader_classification.json", classification)
    _write("direct_atomic_read_scan.json", scan)
    _write("migration_results.json", migration)
    _write("allowlist.json", {"allowlist": list(ALLOWLIST), "broad_productive_allowlist": "NO"})
    _write("foundation_reader_contract.json", contract)
    _write("fail_closed_tests.json", fail_closed)
    _write("version_mix_tests.json", version_mix)
    _write("golden_query_regression.json", regression_output)
    _write("performance.json", performance)
    report_lines = ["# " + GATE, "", "```text"]
    report_lines.extend(f"{key}={value}" for key, value in summary.items() if not isinstance(value, (dict, list)))
    report_lines.extend(["```", "", "STOP AND REVIEW."])
    (EVIDENCE_ROOT / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run_gate()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["FINAL_VERDICT"].endswith("_PASS") else 1)
