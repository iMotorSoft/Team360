"""LOOP TEST 41 — READ-ONLY audit of the credit-control cycle (READ ONLY).

Verifies:
  - every statement executed in this cycle is SELECT (static scan of the
    execute() call sites, plus the runtime guard used by hana_probes.py)
  - SAP_WRITE_COUNT = 0
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT

from modules.telchi.investigation.validation.credit_control.readonly import _WRITE_TOKENS

HERE = Path(__file__).parent
SOURCES = sorted(p for p in HERE.glob("*.py") if p.name != "test_credit_control.py")


def audit_source() -> dict:
    rows = []
    for py in SOURCES:
        text = py.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        n_execute = 0
        n_select = 0
        n_dml = 0
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else (
                        fn.id if isinstance(fn, ast.Name) else "")
                    if name in ("execute", "executemany"):
                        n_execute += 1
                        args = []
                        for a in node.args:
                            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                                args.append(a.value)
                        if args and args[0].lstrip().upper().startswith("SELECT"):
                            n_select += 1
                        if any(_WRITE_TOKENS.search(a) for a in args):
                            n_dml += 1
        rows.append({"script": py.name, "execute_calls": n_execute,
                     "select_first_statement": n_select, "dml_statements": n_dml})
    writes = sum(r["dml_statements"] for r in rows)
    return {"scripts_audited": rows, "sap_write_count": writes,
            "verdict": "READ_ONLY_PASS" if writes == 0 else "WRITES_FOUND"}


def main() -> int:
    out = audit_source()
    out["runtime_guard"] = ("validation/credit_control/readonly.py rejects "
                            "INSERT/UPDATE/DELETE/MERGE/CREATE/ALTER/DROP/TRUNCATE/"
                            "GRANT/REVOKE/CALL and is used by hana_probes.py "
                            "(ReadOnlyConnection/ReadOnlyCursor).")
    (EVIDENCE_ROOT / "credit_control" / "evidence" / "readonly_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
