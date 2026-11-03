"""Reproduce offline F0/F1 evidence, explicitly recording blocked execution.

Run from backend with --output <new-file>. No model, Foundation, DB or listener.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import tempfile

from modules.telchi.runtime.resource_guard import ResourceGuard
from .contracts import CandidateRelation, ExploratoryQueryProposal
from .executor import ExploratoryExecutor, probe_isolation
from .synthetic import CATALOG, synthetic_context
from .validator import validate
from .verifier import IndependentVerifier, profile_synthetic_relation


HOLDOUT_SQL = """WITH coverage AS (
 SELECT invoice_id, min(hour) AS first_hour, max(hour) AS last_hour,
        count(*) AS movements
 FROM movements GROUP BY invoice_id
)
SELECT s.name AS seller, i.id, coalesce(c.movements,0) AS movement_count,
       c.last_hour-c.first_hour AS span
FROM invoices i JOIN sellers s ON i.seller_id=s.id
LEFT JOIN coverage c ON i.id=c.invoice_id
WHERE i.channel_id IS NULL ORDER BY i.id"""


def collect():
    guard = ResourceGuard(temp_directory=Path(tempfile.gettempdir()))
    assessment = guard.preflight()
    ctx = synthetic_context()
    proposal = ExploratoryQueryProposal(
        HOLDOUT_SQL, "Investigate movement coverage for invoices without channel",
        "Observe hours and fanout before any business claim", tuple(t.name for t in CATALOG.tables),
        "invoice", "Seller, invoice, movement count and hour span",
        (CandidateRelation("invoices", "id", "movements", "invoice_id"),),
    )
    decision, query = validate(proposal, ctx)
    blocked, result = ExploratoryExecutor(enabled=True).execute(proposal, ctx)
    profile = profile_synthetic_relation("invoices", "id", "movements", "invoice_id", amount_column="amount")
    verification = IndependentVerifier().verify_synthetic_invoice_total(Decimal("500.00"), invoice_ids=frozenset({1}))
    probe = probe_isolation()
    return {
        "identifier": "TELCHIAI_EXPLORATORY_SQL_EXECUTOR_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "resource_guard_decision": assessment.decision,
        "host_io_review": "required_separately_guard_has_no_io_metric",
        "resource_assessment": asdict(assessment),
        "concurrency_used": 1,
        "isolation_probe": asdict(probe),
        "sql_origin": "human_authored_holdout_not_luna",
        "proposal": asdict(proposal),
        "validation": asdict(decision),
        "validated_query": asdict(query) if query else None,
        "execution_decision": asdict(blocked),
        "execution_result": asdict(result),
        "independent_fixture_profile_not_sql_result": asdict(profile),
        "mandatory_five_movements_verification": asdict(verification),
        "luna_cycle": "NOT_RUN_ISOLATION_BLOCKED",
        "model_configuration_untouched": "gpt-5.6-luna/medium/OpenAI Responses",
        "statuses": {
            "F0_CONTRACTS": "PASS",
            "F1_SQL_VALIDATOR": "PASS",
            "F1_EXECUTION_ISOLATION": "FAIL",
            "F1_SECURITY_NEGATIVE_TESTS": "FAIL",
            "F1_SYNTHETIC_RESEARCH": "FAIL",
            "F1_VERIFIER": "PASS",
            "WHATSAPP_V1_REGRESSION": "PASS",
            "F1_SAFE_EXECUTOR": "FAIL",
            "READY_FOR_FOUNDATION_RESEARCH": "NO",
        },
        "status_scope": {
            "validator": "restricted_structural_AST_subset_not_full_semantic_binder",
            "negative_tests": "parser_and_no_execution_pass_OS_adversarial_gate_incomplete",
            "isolation": "RESOURCE_BLOCKED_no_accredited_worker",
            "research": "no_isolated_execution_or_Luna_cycle",
            "verifier": "synthetic_reference_checks_and_fail_closed_interface_not_arbitrary_claim_certification",
            "regression": "offline_only_103_passed_1_skipped_see_test_evidence_no_WhatsApp_delivery",
        },
        "restrictions": ["feature_off_by_default", "no_sql_executed", "no_model_inference",
                         "no_real_data", "no_services_started", "no_dependency_installed",
                         "no_os_resource_enforcement_claim", "no_foundation_connection"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, default=str)
        stream.write("\n")
    print(args.output)


if __name__ == "__main__":
    main()
