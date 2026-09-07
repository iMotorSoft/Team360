#!/usr/bin/env python3
"""Regresión current base vs legacy base — inventory_movements.

Ejecuta:
  legacy : sql/legacy_hana2/inventory_movements/inventory_base.sql
  current: sql/current/inventory_movements/inventory_movements_v1_base.sql
en Feb 2023 y Mar 2023, y compara:
  - row count
  - set de TransNum
  - SUM(InQty), SUM(OutQty), SUM(TransValue)
  - distribución TransType (cobertura)
  - campo por campo (valores mapeados)
  - grain (TransNum duplicados)

Requisito: HANA accesible por 127.0.0.1:30015 (VPN activa).
No escribe en HANA ni genera Parquet.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HANA_ENV = SECRET_ROOT / "sap" / "hana.env"
OUT_DIR = ROOT / "validation" / "inventory_movements"
LEGACY = ROOT / "sql/legacy_hana2/inventory_movements/inventory_base.sql"
CURRENT = ROOT / "sql/current/inventory_movements/inventory_movements_v1_base.sql"

# legacy column alias -> current column name
LEGACY_TO_CURRENT = {
    "TransNum": "TransNum",
    "TransType": "TransType",
    "BASE_REF": "BaseRef",
    "DocLineNum": "DocLineNum",
    "Ref1": "Ref1",
    "Ref2": "Ref2",
    "Comments": "Comments",
    "JrnlMemo": "JrnlMemo",
    "DocDate": "DocDate",
    "DocDueDate": "DocDueDate",
    "DocTime": "DocTime",
    "ClientCode": "CardCode",
    "ClientName": "CardName",
    "ItemCode": "ItemCode",
    "ItemName": "Dscription",
    "InQty": "InQty",
    "OutQty": "OutQty",
    "CostTotal": "TransValue",
    "CostU": "CalcPrice",
    "ItemSaleU": "legacy_adjusted_price",
    "Balance": "Balance",
    "DManCode": "SlpCode",
    "Warehouse": "Warehouse",
    "UserSign": "UserSign",
}


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
        address=host,
        port=port,
        user=os.environ.get("HANA_USER", env["TELCHI_SAP_HANA_USER"]),
        password=os.environ.get("HANA_PASSWORD", env["TELCHI_SAP_HANA_PASSWORD"]),
        currentSchema=schema,
        encrypt="false",
    )


def run(cur, path: Path, window: tuple[str, str]) -> pd.DataFrame:
    sql = path.read_text().replace(":start_date", "?").replace(":end_date", "?")
    cur.execute(sql, window)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def value_match(a, b) -> bool:
    # both missing -> equal
    a_na = pd.isna(a)
    b_na = pd.isna(b)
    if a_na or b_na:
        return a_na and b_na
    # numeric floats compare with tolerance; others compare direct
    try:
        return bool(abs(float(a) - float(b)) < 1e-6)
    except (TypeError, ValueError):
        return a == b


def compare_windows(cur, window: tuple[str, str]) -> dict:
    leg = run(cur, LEGACY, window)
    curnt = run(cur, CURRENT, window)
    out = {
        "window": window,
        "legacy_rows": int(len(leg)),
        "current_rows": int(len(curnt)),
        "row_count_match": int(len(leg)) == int(len(curnt)),
    }

    # TransNum set identity
    s_leg = set(leg["TransNum"].dropna().astype(str))
    s_cur = set(curnt["TransNum"].dropna().astype(str))
    out["transnum_set_equal"] = s_leg == s_cur
    out["transnum_only_legacy"] = len(s_leg - s_cur)
    out["transnum_only_current"] = len(s_cur - s_leg)

    # grain
    out["legacy_transnum_unique"] = int(leg["TransNum"].nunique()) == len(leg)
    out["current_transnum_unique"] = int(curnt["TransNum"].nunique()) == len(curnt)

    # field-by-field comparison (on mapped columns, aligned by TransNum)
    leg_mapped = leg.rename(columns={k: v for k, v in LEGACY_TO_CURRENT.items() if k in leg.columns})
    common = set(leg_mapped.columns) & set(curnt.columns)

    # join on TransNum (positional within TransNum for duplicated key cases)
    leg_a = leg_mapped.sort_values(["TransNum"]).reset_index(drop=True)
    cur_a = curnt.sort_values(["TransNum"]).reset_index(drop=True)
    mism = {}
    if len(leg_a) != len(cur_a):
        out["field_compare"] = "SKIPPED (row count differs)"
    else:
        for col in sorted(common):
            try:
                eq = pd.Series(
                    [value_match(x, y) for x, y in zip(leg_a[col], cur_a[col])],
                    dtype="bool",
                )
                n_mis = int((~eq).sum())
                if n_mis:
                    idx = eq[~eq].index[:3]
                    mism[col] = {
                        "mismatch_count": n_mis,
                        "samples": [
                            {"legacy": str(leg_a.loc[i, col]), "current": str(cur_a.loc[i, col]), "TransNum": str(leg_a.loc[i, "TransNum"])}
                            for i in idx
                        ],
                    }
            except Exception as e:  # noqa: BLE001
                mism[col] = {"error": str(e)}
        out["field_mismatch"] = mism

    # aggregates
    out["sum_InQty"] = {"legacy": float(leg_mapped["InQty"].sum()), "current": float(curnt["InQty"].sum()),
                        "match": abs(float(leg_mapped["InQty"].sum()) - float(curnt["InQty"].sum())) < 1e-6}
    out["sum_OutQty"] = {"legacy": float(leg_mapped["OutQty"].sum()), "current": float(curnt["OutQty"].sum()),
                         "match": abs(float(leg_mapped["OutQty"].sum()) - float(curnt["OutQty"].sum())) < 1e-6}
    out["sum_TransValue"] = {"legacy": float(leg_mapped["TransValue"].sum()), "current": float(curnt["TransValue"].sum()),
                             "match": abs(float(leg_mapped["TransValue"].sum()) - float(curnt["TransValue"].sum())) < 1e-6}

    # TransType coverage
    tt_leg = leg_mapped.groupby("TransType").size().to_dict()
    tt_cur = curnt.groupby("TransType").size().to_dict()
    out["transtype_distribution_equal"] = tt_leg == tt_cur
    out["transtype_legacy"] = {str(k): int(v) for k, v in tt_leg.items()}
    out["transtype_current"] = {str(k): int(v) for k, v in tt_cur.items()}
    out["transtype_missing_in_current"] = sorted(set(map(str, tt_leg)) - set(map(str, tt_cur)))
    out["transtype_extra_in_current"] = sorted(set(map(str, tt_cur)) - set(map(str, tt_leg)))

    all_pass = (
        out["row_count_match"]
        and out["transnum_set_equal"]
        and out["sum_InQty"]["match"]
        and out["sum_OutQty"]["match"]
        and out["sum_TransValue"]["match"]
        and out["transtype_distribution_equal"]
        and bool(not mism)
    )
    out["gate"] = "PASS" if all_pass else "FAIL"
    return out


def main() -> int:
    os.environ.setdefault("HANA_HOST", "127.0.0.1")
    os.environ.setdefault("HANA_PORT", "30015")
    os.environ.setdefault("HANA_SCHEMA", "TELCHI")
    conn = connect()
    cur = conn.cursor()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {"legacy_sql": str(LEGACY), "current_sql": str(CURRENT), "windows": {}}
    for wname, w in {"feb2023": ("2023-02-01", "2023-03-01"), "mar2023": ("2023-03-01", "2023-04-01")}.items():
        r = compare_windows(cur, w)
        report["windows"][wname] = r
        print(f"{wname}: rows legacy={r['legacy_rows']} current={r['current_rows']} gate={r['gate']}")

    overall = all(v["gate"] == "PASS" for v in report["windows"].values())
    report["overall_gate"] = "TELCHI_INVENTORY_CURRENT_BASE_REGRESSION_PASS" if overall else "TELCHI_INVENTORY_CURRENT_BASE_REGRESSION_FAIL"

    out = OUT_DIR / "current_regression.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print("WROTE", out)
    print("OVERALL", report["overall_gate"])

    cur.close()
    conn.close()
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())