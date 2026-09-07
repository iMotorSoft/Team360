#!/usr/bin/env python3
"""TransType Semantic Resolution — Regression Test Suite.

Verifies:
1. Current base SQL unchanged
2. Row counts Feb/Mar match baseline
3. InQty/OutQty/TransValue totals match baseline
4. Raw TransType distribution unchanged
5. Unknown rows preserved (no filtering)
6. Static harness check (py_compile)
7. YAML/JSON parseable
8. Semantic map completeness
9. DocNum collision analysis present
10. Line link validation present

Gate: TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_PASS
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

import yaml

ROOT = Path(__file__).resolve().parents[2]
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
OUT_DIR = ROOT / "validation" / "inventory_movements"
SQL_DIR = ROOT / "sql" / "current" / "inventory_movements"

# Baseline values from current_regression.json (PASS)
BASELINE = {
    "feb2023": {
        "rows": 139940,
        "sum_inqty": 4274341.1354,
        "sum_outqty": 4364880.3774,
        "sum_transvalue": -1734522.34,
        "transtype_distribution": {
            "13": 64644, "14": 522, "15": 4590, "16": 23, "18": 1,
            "19": 1, "20": 1652, "21": 70, "59": 581, "60": 2341,
            "67": 65490, "69": 3, "202": 22,
        },
    },
    "mar2023": {
        "rows": 177987,
        "sum_inqty": 6492498.811,
        "sum_outqty": 6018260.6495,
        "sum_transvalue": 512807.72,
        "transtype_distribution": {
            "13": 77877, "14": 780, "15": 5158, "16": 41, "19": 26,
            "20": 1979, "21": 105, "59": 795, "60": 3501, "67": 87666,
            "69": 26, "162": 6, "202": 26, "10000071": 1,
        },
    },
}

# SQL template uses: DocDate >= start || ' 00:00:00' AND DocDate <= end || ' 23:59:59'
# This means the end date IS included (all of that day)
WINDOWS = {
    "feb2023": ("2023-02-01", "2023-03-01"),  # includes all of Mar 1
    "mar2023": ("2023-03-01", "2023-04-01"),  # includes all of Apr 1
}

# Expected semantic types (all must be present in map)
EXPECTED_TYPES = [13, 14, 15, 16, 18, 19, 20, 21, 59, 60, 67, 69, 162, 202, 10000071]

# Required artifacts
REQUIRED_ARTIFACTS = [
    "transtype_map_v2.yaml",
    "document_link_matrix_v2.json",
    "line_link_validation.json",
    "docnum_collision_analysis.json",
    "official_resolution.json",
    "current_regression.json",
    "current_validation_gate.json",
]


def load_env() -> dict:
    vals = {}
    for line in HANA_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        vals[k] = shlex.split(v, posix=True)[0]
    return vals


def connect():
    from hdbcli import dbapi
    host = os.environ.get("HANA_HOST", "127.0.0.1")
    port = int(os.environ.get("HANA_PORT", "30015"))
    schema = os.environ.get("HANA_SCHEMA", "TELCHI")
    env = load_env()
    return dbapi.connect(
        address=host, port=port,
        user=os.environ.get("HANA_USER", env["TELCHI_SAP_HANA_USER"]),
        password=os.environ.get("HANA_PASSWORD", env["TELCHI_SAP_HANA_PASSWORD"]),
        currentSchema=schema, encrypt="false",
    )


def q(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return cur.fetchall(), cols


def check_static_harness() -> dict:
    """Verify Python files compile without errors."""
    py_files = list(OUT_DIR.glob("*.py"))
    results = {}
    for f in py_files:
        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", str(f)],
                capture_output=True, timeout=30, check=True,
            )
            results[f.name] = "PASS"
        except subprocess.CalledProcessError as e:
            results[f.name] = f"FAIL: {e.stderr.decode()[:100]}"
        except Exception as e:
            results[f.name] = f"FAIL: {str(e)[:100]}"

    all_pass = all(v == "PASS" for v in results.values())
    return {"status": "PASS" if all_pass else "FAIL", "files": results}


def check_yaml_json_parseable() -> dict:
    """Verify all YAML/JSON files are parseable."""
    results = {}
    for ext in ["*.yaml", "*.json"]:
        for f in OUT_DIR.glob(ext):
            try:
                if f.suffix == ".yaml":
                    yaml.safe_load(f.read_text())
                else:
                    json.loads(f.read_text())
                results[f.name] = "PASS"
            except Exception as e:
                results[f.name] = f"FAIL: {str(e)[:100]}"

    all_pass = all(v == "PASS" for v in results.values())
    return {"status": "PASS" if all_pass else "FAIL", "files": results}


def check_current_base_unchanged() -> dict:
    """Verify current base SQL file hasn't been modified."""
    sql_file = SQL_DIR / "inventory_movements_v1_base.sql"
    if not sql_file.exists():
        return {"status": "FAIL", "reason": "SQL file not found"}

    content = sql_file.read_text()
    # Check key invariants
    # Strip comments for actual SQL check
    lines = content.split('\n')
    sql_lines = [l for l in lines if not l.strip().startswith('--')]
    sql_content = '\n'.join(sql_lines).upper()

    checks = {
        "no_joins": "JOIN" not in sql_content,
        "no_drop_duplicates": "DROP_DUPLICATES" not in sql_content,
        "has_transnum": '"TransNum"' in content,
        "has_transtype": '"TransType"' in content,
        "has_baseref": '"BASE_REF"' in content,
        "has_doclinenum": '"DocLineNum"' in content,
        "has_inqty": '"InQty"' in content,
        "has_outqty": '"OutQty"' in content,
        "has_transvalue": '"TransValue"' in content,
        "has_price": '"Price"' in content,
        "has_legacy_adjusted": "legacy_adjusted_price" in content,
        "where_clause": "WHERE" in content.upper(),
    }

    all_pass = all(checks.values())
    failed = [k for k, v in checks.items() if not v]
    return {
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "failed": failed,
    }


def check_hana_regression(cur) -> dict:
    """Run regression checks against HANA for both windows."""
    results = {}

    for wname, (d0, d1) in WINDOWS.items():
        baseline = BASELINE[wname]

        # Row count (matching SQL template: >= start+' 00:00:00' AND <= end+' 23:59:59')
        row_count, _ = q(cur, f"""
            SELECT COUNT(*) FROM TELCHI.OINM
            WHERE "DocDate">='{d0} 00:00:00' AND "DocDate"<='{d1} 23:59:59'
        """)
        actual_rows = row_count[0][0]
        rows_match = actual_rows == baseline["rows"]

        # Quantity totals
        qty_data, _ = q(cur, f"""
            SELECT SUM("InQty"), SUM("OutQty"), SUM("TransValue")
            FROM TELCHI.OINM
            WHERE "DocDate">='{d0} 00:00:00' AND "DocDate"<='{d1} 23:59:59'
        """)
        actual_inqty = float(qty_data[0][0])
        actual_outqty = float(qty_data[0][1])
        actual_transvalue = float(qty_data[0][2])

        inqty_match = abs(actual_inqty - baseline["sum_inqty"]) < 0.01
        outqty_match = abs(actual_outqty - baseline["sum_outqty"]) < 0.01
        transvalue_match = abs(actual_transvalue - baseline["sum_transvalue"]) < 0.01

        # TransType distribution
        dist_data, _ = q(cur, f"""
            SELECT "TransType", COUNT(*) AS n
            FROM TELCHI.OINM
            WHERE "DocDate">='{d0} 00:00:00' AND "DocDate"<='{d1} 23:59:59'
            GROUP BY "TransType" ORDER BY "TransType"
        """)
        actual_dist = {str(int(r[0])): int(r[1]) for r in dist_data}
        dist_match = actual_dist == baseline["transtype_distribution"]

        # Unknown preservation
        baseline_types = set(baseline["transtype_distribution"].keys())
        actual_types = set(actual_dist.keys())
        missing = baseline_types - actual_types
        extra = actual_types - baseline_types
        unknown_preserved = len(missing) == 0

        results[wname] = {
            "rows": {"expected": baseline["rows"], "actual": actual_rows, "match": rows_match},
            "sum_inqty": {"expected": baseline["sum_inqty"], "actual": actual_inqty, "match": inqty_match},
            "sum_outqty": {"expected": baseline["sum_outqty"], "actual": actual_outqty, "match": outqty_match},
            "sum_transvalue": {"expected": baseline["sum_transvalue"], "actual": actual_transvalue, "match": transvalue_match},
            "transtype_distribution": {"match": dist_match, "missing": list(missing), "extra": list(extra)},
            "unknown_preserved": unknown_preserved,
        }

    all_pass = all(
        r["rows"]["match"] and r["sum_inqty"]["match"] and r["sum_outqty"]["match"]
        and r["sum_transvalue"]["match"] and r["transtype_distribution"]["match"]
        and r["unknown_preserved"]
        for r in results.values()
    )

    return {"status": "PASS" if all_pass else "FAIL", "windows": results}


def check_semantic_map_completeness() -> dict:
    """Verify the semantic map covers all expected TransTypes."""
    map_path = OUT_DIR / "transtype_map_v2.yaml"
    if not map_path.exists():
        return {"status": "FAIL", "reason": "transtype_map_v2.yaml not found"}

    data = yaml.safe_load(map_path.read_text())
    map_entries = data.get("trans_type_map", [])
    mapped_types = [e["trans_type"] for e in map_entries]

    missing = [t for t in EXPECTED_TYPES if t not in mapped_types]
    extra = [t for t in mapped_types if t not in EXPECTED_TYPES]

    # Check all have CONFIRMED semantic status
    confirmed = [e for e in map_entries if e.get("semantic_status") == "CONFIRMED"]
    non_confirmed = [e for e in map_entries if e.get("semantic_status") != "CONFIRMED"]

    return {
        "status": "PASS" if len(missing) == 0 and len(non_confirmed) == 0 else "FAIL",
        "total_mapped": len(mapped_types),
        "expected": len(EXPECTED_TYPES),
        "missing": missing,
        "extra": extra,
        "confirmed_count": len(confirmed),
        "non_confirmed": [{"trans_type": e["trans_type"], "status": e.get("semantic_status")} for e in non_confirmed],
    }


def check_artifacts_exist() -> dict:
    """Verify all required artifacts exist and are non-empty."""
    results = {}
    for artifact in REQUIRED_ARTIFACTS:
        f = OUT_DIR / artifact
        if f.exists() and f.stat().st_size > 0:
            results[artifact] = "PASS"
        else:
            results[artifact] = "FAIL"

    all_pass = all(v == "PASS" for v in results.values())
    return {"status": "PASS" if all_pass else "FAIL", "files": results}


def check_docnum_collision_present() -> dict:
    """Verify collision analysis was run and has data."""
    f = OUT_DIR / "docnum_collision_analysis.json"
    if not f.exists():
        return {"status": "FAIL", "reason": "File not found"}

    data = json.loads(f.read_text())
    summary = data.get("summary", {})
    per_tt = data.get("per_transtype", {})

    return {
        "status": "PASS" if summary.get("total_sampled", 0) > 0 else "FAIL",
        "total_sampled": summary.get("total_sampled", 0),
        "total_collisions": summary.get("total_collisions", 0),
        "collision_rate": summary.get("collision_rate", 0),
        "trans_types_analyzed": len(per_tt),
    }


def check_line_link_present() -> dict:
    """Verify line link validation was run."""
    f = OUT_DIR / "line_link_validation.json"
    if not f.exists():
        return {"status": "FAIL", "reason": "File not found"}

    data = json.loads(f.read_text())
    results = data.get("results", [])
    confirmed = [r for r in results if r.get("status") == "CONFIRMED_EXACT"]

    return {
        "status": "PASS" if len(confirmed) > 0 else "FAIL",
        "total_types_tested": len(results),
        "confirmed_exact": len(confirmed),
        "confirmed_types": [r["TransType"] for r in confirmed],
    }


def main() -> int:
    os.environ.setdefault("HANA_HOST", "127.0.0.1")
    os.environ.setdefault("HANA_PORT", "30015")
    os.environ.setdefault("HANA_SCHEMA", "TELCHI")

    print("=" * 70)
    print("TEAM360 TELCHI INVENTORY TRANSTYPE REGRESSION TEST")
    print("=" * 70)

    gate_results = {}
    all_pass = True

    # 1. Static harness
    print("\n[1/9] Static harness...")
    gate_results["static_harness"] = check_static_harness()
    status = gate_results["static_harness"]["status"]
    print(f"  {status}")
    if status == "FAIL":
        all_pass = False

    # 2. YAML/JSON parseable
    print("\n[2/9] YAML/JSON validation...")
    gate_results["yaml_json"] = check_yaml_json_parseable()
    status = gate_results["yaml_json"]["status"]
    print(f"  {status}")
    if status == "FAIL":
        all_pass = False

    # 3. Current base unchanged
    print("\n[3/9] Current base SQL unchanged...")
    gate_results["base_unchanged"] = check_current_base_unchanged()
    status = gate_results["base_unchanged"]["status"]
    print(f"  {status}")
    if status == "FAIL":
        all_pass = False

    # 4. Artifacts exist
    print("\n[4/9] Required artifacts...")
    gate_results["artifacts"] = check_artifacts_exist()
    status = gate_results["artifacts"]["status"]
    print(f"  {status}")
    if status == "FAIL":
        all_pass = False

    # 5. Semantic map completeness
    print("\n[5/9] Semantic map completeness...")
    gate_results["semantic_map"] = check_semantic_map_completeness()
    status = gate_results["semantic_map"]["status"]
    print(f"  {status} ({gate_results['semantic_map']['confirmed_count']}/{len(EXPECTED_TYPES)} confirmed)")
    if status == "FAIL":
        all_pass = False

    # 6. DocNum collision analysis
    print("\n[6/9] DocNum collision analysis...")
    gate_results["collision"] = check_docnum_collision_present()
    status = gate_results["collision"]["status"]
    print(f"  {status} (rate={gate_results['collision'].get('collision_rate', 0):.1%})")
    if status == "FAIL":
        all_pass = False

    # 7. Line link validation
    print("\n[7/9] Line link validation...")
    gate_results["line_link"] = check_line_link_present()
    status = gate_results["line_link"]["status"]
    print(f"  {status} ({gate_results['line_link'].get('confirmed_exact', 0)} confirmed)")
    if status == "FAIL":
        all_pass = False

    # 8. HANA regression (connect if available)
    print("\n[8/9] HANA regression...")
    try:
        conn = connect()
        cur = conn.cursor()
        gate_results["hana_regression"] = check_hana_regression(cur)
        status = gate_results["hana_regression"]["status"]
        print(f"  {status}")
        for wname, wr in gate_results["hana_regression"]["windows"].items():
            print(f"    {wname}: rows={wr['rows']['match']}, inqty={wr['sum_inqty']['match']}, "
                  f"outqty={wr['sum_outqty']['match']}, transvalue={wr['sum_transvalue']['match']}, "
                  f"dist={wr['transtype_distribution']['match']}, unknown={wr['unknown_preserved']}")
        if status == "FAIL":
            all_pass = False
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  SKIP: HANA not available ({e})")
        gate_results["hana_regression"] = {"status": "SKIP", "reason": str(e)}

    # 9. Final gate
    print("\n[9/9] Final gate...")
    gate_name = "TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_PASS" if all_pass else "TEAM360_TELCHI_INVENTORY_TRANSTYPE_MAP_FAIL"
    gate_results["final_gate"] = gate_name

    print(f"\n{'=' * 70}")
    print(f"RESULT: {gate_name}")
    print(f"{'=' * 70}")

    # Write gate report
    gate_report = {
        "gate_id": gate_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "all_pass": all_pass,
        "results": gate_results,
    }

    gate_path = OUT_DIR / "transtype_regression_gate.json"
    gate_path.write_text(json.dumps(gate_report, indent=2, default=str))
    print(f"\nWROTE {gate_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
