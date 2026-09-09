#!/usr/bin/env python3
"""Profilado de grain de OINM (inventory_movements).

Solo ejecutable con HANA accesible (127.0.0.1:30015).
No usa sudo ni Podman; credenciales desde el secret root privado configurado.

Mide (seccion 8-9 spec):
  - rows total por ventana
  - candidate keys: TransNum / TransNum+ItemCode / TransNum+DocLineNum /
    TransNum+ItemCode+Warehouse / TransType+BASE_REF+DocLineNum+ItemCode /
    TransNum+TransType+DocLineNum+ItemCode+Warehouse
  - distinct count, grupos duplicados, max rows por key, muestras
  - distribucion TransType (Feb / Mar / 2023 agregado)
  - nulls de campos clave por TransType
  - invariantes InQty/OutQty/TransValue
"""
from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

from modules.telchi.investigation.paths import SECRET_ROOT

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = SECRET_ROOT / "sap" / "hana.env"
OUT_DIR = ROOT / "validation" / "inventory_movements"


def load_env() -> dict:
    vals = {}
    for line in ENV_FILE.read_text().splitlines():
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


def query(cur, sql: str) -> pd.DataFrame:
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def grain_report(df: pd.DataFrame, keys: list) -> dict:
    out = {}
    total = len(df)
    for k in keys:
        n = df.drop_duplicates(subset=k).shape[0]
        dups = df.duplicated(subset=k).sum()
        if n == 0:
            out[",".join(k)] = {"rows": total, "distinct": 0, "dup_rows": dups, "unique": False, "why": "empty"}
            continue
        max_per_key = df[k].value_counts().max()
        is_unique = n == total
        out[",".join(k)] = {
            "rows": total,
            "distinct": int(n),
            "dup_rows": int(dups),
            "max_rows_per_key": int(max_per_key),
            "unique": bool(is_unique),
            "why": "UNIQUE" if is_unique else "NON_UNIQUE",
        }
        if not is_unique:
            sample = df[df.duplicated(subset=k, keep=False)][k].drop_duplicates().head(5)
            out[",".join(k)]["sample_dup_keys"] = [[str(x) for x in r] for r in sample.values.tolist()]
    return out


def main() -> int:
    if not os.environ.get("HANA_HOST"):
        os.environ["HANA_HOST"] = "127.0.0.1"
        os.environ["HANA_PORT"] = "30015"
        os.environ["HANA_SCHEMA"] = "TELCHI"

    conn = connect()
    cur = conn.cursor()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    base_cols = [
        "TransNum", "TransType", "BASE_REF", "DocLineNum", "Ref1", "Ref2",
        "Comments", "JrnlMemo", "DocDate", "DocDueDate", "DocTime",
        "CardCode", "CardName", "ItemCode", "Dscription",
        "InQty", "OutQty", "TransValue", "CalcPrice", "Price", "Balance",
        "SlpCode", "Warehouse", "UserSign",
    ]
    col_list = ", ".join(f'OINM."{c}"' for c in base_cols)
    windows = {"feb2023": ("2023-02-01", "2023-03-01"), "mar2023": ("2023-03-01", "2023-04-01")}

    report: dict = {"windows": {}, "annual": {}, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}

    for wname, (d0, d1) in windows.items():
        t0 = time.time()
        sql = (
            f"SELECT {col_list} FROM TELCHI.OINM OINM "
            f"WHERE OINM.\"DocDate\" >= '{d0} 00:00:00' AND OINM.\"DocDate\" < '{d1} 00:00:00'"
        )
        df = query(cur, sql)
        elapsed = round(time.time() - t0, 2)

        keys = [
            ["TransNum"],
            ["TransNum", "ItemCode"],
            ["TransNum", "DocLineNum"],
            ["TransNum", "ItemCode", "Warehouse"],
            ["TransType", "BASE_REF", "DocLineNum", "ItemCode"],
            ["TransNum", "TransType", "DocLineNum", "ItemCode", "Warehouse"],
        ]
        gr = grain_report(df, keys)

        tt = df.groupby("TransType").size().sort_index()
        tt_rows = df[(df["InQty"] > 0) | (df["OutQty"] > 0)].groupby("TransType").size()

        nulls = {}
        for col in ["BASE_REF", "DocLineNum", "CardCode", "ItemCode", "Warehouse", "SlpCode", "UserSign", "Ref1", "Ref2"]:
            nulls[col] = int(df[col].isna().sum())

        qty = {
            "both_gt0": int(((df["InQty"] > 0) & (df["OutQty"] > 0)).sum()),
            "both_eq0": int(((df["InQty"] == 0) & (df["OutQty"] == 0)).sum()),
            "InQty_gt0": int((df["InQty"] > 0).sum()),
            "OutQty_gt0": int((df["OutQty"] > 0).sum()),
            "sum_InQty": float(df["InQty"].sum()),
            "sum_OutQty": float(df["OutQty"].sum()),
            "sum_TransValue": float(df["TransValue"].sum()),
        }

        report["windows"][wname] = {
            "window": [d0, d1],
            "rows": int(len(df)),
            "elapsed_seconds": elapsed,
            "grain": gr,
            "transtype_count": tt.astype(int).to_dict(),
            "transtype_with_qty": tt_rows.astype(int).to_dict(),
            "nulls": nulls,
            "quantity_invariants": qty,
        }
        print(f"{wname}: rows={len(df)} elapsed={elapsed}s")

    # Annual aggregated TransType profile (lightweight, aggregate only)
    t0 = time.time()
    sql = (
        "SELECT OINM.\"TransType\" AS tt, COUNT(*) AS n "
        "FROM TELCHI.OINM OINM "
        "WHERE OINM.\"DocDate\" >= '2023-01-01 00:00:00' AND OINM.\"DocDate\" < '2024-01-01 00:00:00' "
        "GROUP BY OINM.\"TransType\" ORDER BY OINM.\"TransType\""
    )
    cur.execute(sql)
    annual = {str(r[0]): int(r[1]) for r in cur.fetchall()}
    report["annual"] = {"transtype_count_2023": annual, "elapsed_seconds": round(time.time() - t0, 2)}
    print("annual 2023 transtype profile done")

    # Per-TransType FIELD NULL rates (base fields) for the Feb window
    feb = report["windows"]["feb2023"]
    sql = (
        f"SELECT OINM.\"TransType\", "
        f"SUM(CASE WHEN OINM.\"BASE_REF\" IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN OINM.\"DocLineNum\" IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN OINM.\"CardCode\" IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN OINM.\"ItemCode\" IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN OINM.\"Warehouse\" IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN OINM.\"SlpCode\" IS NULL THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN OINM.\"UserSign\" IS NULL THEN 1 ELSE 0 END), "
        f"COUNT(*) FROM TELCHI.OINM OINM "
        f"WHERE OINM.\"DocDate\" >= '2023-02-01 00:00:00' AND OINM.\"DocDate\" < '2023-03-01 00:00:00' "
        f"GROUP BY OINM.\"TransType\" ORDER BY OINM.\"TransType\""
    )
    cur.execute(sql)
    cols = ["TransType", "null_BASE_REF", "null_DocLineNum", "null_CardCode", "null_ItemCode", "null_Warehouse", "null_SlpCode", "null_UserSign", "n"]
    report["windows"]["feb2023"]["null_by_transtype"] = [
        {c: (None if r[i] is None else int(r[i])) for i, c in enumerate(cols)} for r in cur.fetchall()
    ]

    out = OUT_DIR / "grain_profile.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"WROTE {out}")
    cur.close()
    conn.close()

    # Gate evaluation
    feb_g = report["windows"]["feb2023"]["grain"]
    unique_keys = [k for k, v in feb_g.items() if v["unique"]]
    print("UNIQUE_KEYS_FEB:", unique_keys)
    return 0


if __name__ == "__main__":
    sys.exit(main())