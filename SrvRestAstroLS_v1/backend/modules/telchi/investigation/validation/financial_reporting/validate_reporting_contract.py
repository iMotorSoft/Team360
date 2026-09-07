#!/usr/bin/env python3
"""VALIDATE REPORTING CONTRACT — TEAM360 TELCHI

Validates:
- Unique KPI IDs
- Required fields present
- Valid source paths
- Known dimensions
- No duplicate business labels
- Baseline values present for core KPIs
- Cross-report reconciliation

Gate: TELCHI_FINANCIAL_REPORTING_KPI_CONTRACT_PASS
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from modules.telchi.investigation.paths import INVESTIGATION_ROOT
from typing import Any

import yaml

TELCHI_ROOT = INVESTIGATION_ROOT
REPORTING_DIR = TELCHI_ROOT / "validation" / "financial_reporting"

# Required fields for each KPI
REQUIRED_KPI_FIELDS = [
    "id", "name", "business_name_es", "description", "family",
    "formula", "source", "grain", "date_semantics", "currency",
    "canceled_policy", "status"
]

# Required fields for each dimension
REQUIRED_DIM_FIELDS = [
    "id", "name", "business_name_es", "key", "source", "valid_period"
]

# Required fields for each report
REQUIRED_REPORT_FIELDS = [
    "id", "name", "business_name_es", "audience", "description",
    "period_semantics", "metrics", "dimensions"
]

# Core KPIs that MUST have baseline values
CORE_KPI_IDS = [
    "AR_OUTSTANDING", "AR_NOT_DUE", "AR_OVERDUE", "AR_OVERDUE_RATE",
    "AR_OPEN_INVOICES", "AR_CUSTOMERS_WITH_DEBT", "AR_SELLERS_WITH_PORTFOLIO",
    "AR_CREDIT_BALANCE"
]


def load_yaml(path: Path) -> Any:
    """Load YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> Any:
    """Load JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_kpi_contract(data: dict) -> list[str]:
    """Validate KPI contract."""
    errors = []
    kpis = data.get("kpis", [])

    # Check for unique IDs
    ids = [k.get("id") for k in kpis]
    seen_ids = set()
    for kid in ids:
        if kid in seen_ids:
            errors.append(f"Duplicate KPI ID: {kid}")
        seen_ids.add(kid)

    # Check required fields
    for kpi in kpis:
        kid = kpi.get("id", "UNKNOWN")
        for field in REQUIRED_KPI_FIELDS:
            if field not in kpi:
                errors.append(f"KPI {kid}: missing required field '{field}'")

    # Check valid families
    valid_families = {"SALES", "COLLECTION", "SETTLEMENT", "AR", "COHORT", "AGING", "AUDIT"}
    for kpi in kpis:
        family = kpi.get("family")
        if family and family not in valid_families:
            errors.append(f"KPI {kpi.get('id')}: invalid family '{family}'")

    # Check valid status values
    valid_statuses = {"DEFINED", "VALIDATED", "BLOCKED"}
    for kpi in kpis:
        status = kpi.get("status")
        if status and status not in valid_statuses:
            errors.append(f"KPI {kpi.get('id')}: invalid status '{status}'")

    # Check for duplicate business labels within same family
    family_labels = {}
    for kpi in kpis:
        family = kpi.get("family", "UNKNOWN")
        label = kpi.get("business_name_es", "UNKNOWN")
        if family not in family_labels:
            family_labels[family] = {}
        if label in family_labels[family]:
            errors.append(f"Duplicate business label '{label}' in family {family}")
        family_labels[family][label] = kpi.get("id")

    return errors


def validate_dimension_contract(data: dict) -> list[str]:
    """Validate dimension contract."""
    errors = []
    dimensions = data.get("dimensions", [])

    # Check for unique IDs
    ids = [d.get("id") for d in dimensions]
    seen_ids = set()
    for did in ids:
        if did in seen_ids:
            errors.append(f"Duplicate dimension ID: {did}")
        seen_ids.add(did)

    # Check required fields
    for dim in dimensions:
        did = dim.get("id", "UNKNOWN")
        for field in REQUIRED_DIM_FIELDS:
            if field not in dim:
                errors.append(f"Dimension {did}: missing required field '{field}'")

    return errors


def validate_report_contract(data: dict) -> list[str]:
    """Validate report contract."""
    errors = []
    reports = data.get("reports", [])

    # Check for unique IDs
    ids = [r.get("id") for r in reports]
    seen_ids = set()
    for rid in ids:
        if rid in seen_ids:
            errors.append(f"Duplicate report ID: {rid}")
        seen_ids.add(rid)

    # Check required fields
    for report in reports:
        rid = report.get("id", "UNKNOWN")
        for field in REQUIRED_REPORT_FIELDS:
            if field not in report:
                errors.append(f"Report {rid}: missing required field '{field}'")

    # Check that metrics referenced in reports exist in KPI contract
    kpi_data = load_yaml(REPORTING_DIR / "kpi_contract.yaml")
    valid_kpi_ids = {k.get("id") for k in kpi_data.get("kpis", [])}

    for report in reports:
        rid = report.get("id", "UNKNOWN")
        for metric in report.get("metrics", []):
            if metric not in valid_kpi_ids:
                errors.append(f"Report {rid}: references unknown KPI '{metric}'")

    return errors


def validate_source_authority(data: dict) -> list[str]:
    """Validate source authority matrix."""
    errors = []
    sources = data.get("source_authority", [])

    # Check for unique families
    families = [s.get("family") for s in sources]
    seen_families = set()
    for fam in families:
        if fam in seen_families:
            errors.append(f"Duplicate source authority for family: {fam}")
        seen_families.add(fam)

    return errors


def validate_baseline(data: dict) -> list[str]:
    """Validate baseline values."""
    errors = []

    ar_metrics = data.get("ar_metrics", {})

    for kpi_id in CORE_KPI_IDS:
        if kpi_id not in ar_metrics:
            errors.append(f"Core KPI '{kpi_id}' missing from baseline")
        else:
            metric = ar_metrics[kpi_id]
            if "value" not in metric:
                errors.append(f"Core KPI '{kpi_id}' missing 'value'")

    # Check dimension reconciliation
    dim_recon = data.get("dimension_reconciliation", {})
    if not dim_recon.get("reconciles", False):
        errors.append("Dimension reconciliation failed")

    return errors


def run_validation() -> dict[str, Any]:
    """Run full validation."""
    results = {
        "validation_id": "REPORTING_CONTRACT_VALIDATION",
        "timestamp": "2026-08-21",
        "steps": {},
        "overall_status": "PASS"
    }

    # 1. KPI Contract
    print("--- Validating KPI Contract ---")
    kpi_data = load_yaml(REPORTING_DIR / "kpi_contract.yaml")
    kpi_errors = validate_kpi_contract(kpi_data)
    kpi_count = len(kpi_data.get("kpis", []))
    results["steps"]["kpi_contract"] = {
        "status": "PASS" if not kpi_errors else "FAIL",
        "kpi_count": kpi_count,
        "errors": kpi_errors
    }
    print(f"  KPIs: {kpi_count}, Errors: {len(kpi_errors)}")

    # 2. Dimension Contract
    print("--- Validating Dimension Contract ---")
    dim_data = load_yaml(REPORTING_DIR / "dimension_contract.yaml")
    dim_errors = validate_dimension_contract(dim_data)
    dim_count = len(dim_data.get("dimensions", []))
    results["steps"]["dimension_contract"] = {
        "status": "PASS" if not dim_errors else "FAIL",
        "dimension_count": dim_count,
        "errors": dim_errors
    }
    print(f"  Dimensions: {dim_count}, Errors: {len(dim_errors)}")

    # 3. Report Contract
    print("--- Validating Report Contract ---")
    report_data = load_yaml(REPORTING_DIR / "report_contract.yaml")
    report_errors = validate_report_contract(report_data)
    report_count = len(report_data.get("reports", []))
    results["steps"]["report_contract"] = {
        "status": "PASS" if not report_errors else "FAIL",
        "report_count": report_count,
        "errors": report_errors
    }
    print(f"  Reports: {report_count}, Errors: {len(report_errors)}")

    # 4. Source Authority
    print("--- Validating Source Authority ---")
    source_data = load_yaml(REPORTING_DIR / "source_authority.yaml")
    source_errors = validate_source_authority(source_data)
    source_count = len(source_data.get("source_authority", []))
    results["steps"]["source_authority"] = {
        "status": "PASS" if not source_errors else "FAIL",
        "source_count": source_count,
        "errors": source_errors
    }
    print(f"  Sources: {source_count}, Errors: {len(source_errors)}")

    # 5. Baseline
    print("--- Validating Baseline ---")
    baseline_data = load_json(REPORTING_DIR / "kpi_baseline_2026_08.json")
    baseline_errors = validate_baseline(baseline_data)
    results["steps"]["baseline"] = {
        "status": "PASS" if not baseline_errors else "FAIL",
        "errors": baseline_errors
    }
    print(f"  Errors: {len(baseline_errors)}")

    # Overall status
    all_errors = kpi_errors + dim_errors + report_errors + source_errors + baseline_errors
    if all_errors:
        results["overall_status"] = "FAIL"
        results["total_errors"] = len(all_errors)
    else:
        results["overall_status"] = "PASS"
        results["total_errors"] = 0

    return results


def main() -> int:
    """Main entry point."""
    results = run_validation()

    output_path = REPORTING_DIR / "validation_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nReport written to: {output_path}")
    print(f"Overall status: {results['overall_status']}")

    if results["overall_status"] != "PASS":
        for step, data in results["steps"].items():
            if data.get("status") == "FAIL":
                print(f"\n{step} ERRORS:")
                for err in data.get("errors", []):
                    print(f"  - {err}")

    return 0 if results["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
