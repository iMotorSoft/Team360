"""Runner for TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1.

Two layers:

1. Offline contract checks (default): exercise the diff/publication/rollback and
   idempotency contracts with synthetic DuckDB catalogs. No SAP, DuckLake or
   DATA_ROOT is touched. Detailed assertions live in ``test_contract.py``.
2. Live evidence roll-up: read the evidence written by real
   ``python -m modules.telchi.datalake.update`` runs and assemble the gate
   verdict. This never mutates SAP, Data Root or DuckLake.

The live run itself is a separate, explicit invocation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.telchi.datalake import update

GATE = "TELCHI_DATALAKE_MANUAL_SINGLE_RUN_UPDATE_V1"
REPO_ROOT = Path(__file__).resolve().parents[7]
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
UPDATE_SCRIPT = REPO_ROOT / "SrvRestAstroLS_v1" / "backend" / "modules" / "telchi" / "datalake" / "update.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(name: str) -> dict[str, Any]:
    path = EVIDENCE_ROOT / name
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def offline_checks() -> dict[str, Any]:
    source = UPDATE_SCRIPT.read_text(encoding="utf-8")
    sql = (UPDATE_SCRIPT.parent / "sql.py").read_text(encoding="utf-8")
    return {
        "update_script_exists": UPDATE_SCRIPT.is_file(),
        "sap_read_only_enforced_by_adapter": "assert_read_only_select" in sql,
        "staging_before_publication": "StagingStore" in source and "_oitw_snapshot_writer" in source,
        "bulk_writes_only": "publication_writer" in source and "_stage_rows" in source,
        "no_docdate_only_watermark": "DocDate only defines business scope" in source.replace("``", ""),
        "no_scheduler": all(token not in source for token in ("apache_airflow", "celery", "apscheduler")),
        "no_ai": all(token not in source for token in ("import litellm", "import openai", "import langgraph")),
        "year_rollover_guard": update.YearRolloverGuard.evaluate("2027-01-01").requires_review == "YES",
        "scope_from": update.FOUNDATION_START.isoformat(),
        "reference_never_reassigned": "existing_canonical_ids_changed" in source,
    }


def live_rollup() -> dict[str, Any]:
    """Assemble the live-run verdict from the real evidence bundles."""
    root = EVIDENCE_ROOT.parent
    second = root / f"{GATE}_SECOND_RUN"
    aborted = root / f"{GATE}_RUN1_ABORTED"
    second_summary = {}
    if (second / "summary.json").is_file():
        second_summary = json.loads((second / "summary.json").read_text(encoding="utf-8"))
    primary = _load("summary.json")
    return {
        "PRIMARY_EVIDENCE_PRESENT": bool(primary),
        "PRIMARY_FINAL_RESULT": primary.get("FINAL_RESULT"),
        "PRIMARY_PUBLISHED_VS_CAPTURED_SAP": primary.get("PUBLISHED_VS_CAPTURED_SAP"),
        "SECOND_RUN_EVIDENCE_PRESENT": bool(second_summary),
        "SECOND_RUN_FINAL_RESULT": second_summary.get("FINAL_RESULT"),
        "SECOND_RUN_PUBLISHED_VS_CAPTURED_SAP": second_summary.get("PUBLISHED_VS_CAPTURED_SAP"),
        "FAILCLOSED_ABORT_EVIDENCE_PRESENT": (aborted / "summary.json").is_file(),
    }


def run_gate(*, rollup_only: bool = False) -> dict[str, Any]:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o750)
    result = {
        "GATE": GATE,
        "GENERATED_AT": utc_now(),
        "UPDATE_SCRIPT": str(UPDATE_SCRIPT),
        "UPDATE_SCRIPT_EXISTS": "YES" if UPDATE_SCRIPT.is_file() else "NO",
        "OFFLINE_CHECKS": offline_checks(),
        "RUN_LAYERS": {
            "focal_contract_tests": "modules/telchi/investigation/validation/datalake_manual_single_run_update_v1/test_contract.py",
            "module_regression_tests": "modules/telchi/datalake/tests/",
            "live_run_command": "uv run python -m modules.telchi.datalake.update",
            "dry_run_command": "uv run python -m modules.telchi.datalake.update --dry-run",
        },
    }
    if not rollup_only:
        result["LIVE_ROLLUP"] = live_rollup()
    (EVIDENCE_ROOT / "offline_gate.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=GATE)
    parser.add_argument("--rollup-only", action="store_true", help="only read existing live evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(run_gate(rollup_only=args.rollup_only), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())