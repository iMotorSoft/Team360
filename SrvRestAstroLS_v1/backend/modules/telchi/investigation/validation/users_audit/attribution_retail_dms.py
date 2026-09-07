"""RETAIL ONE × DMS — user attribution real-data validation (READ ONLY).

Answers: how many REAL humans/persons operate Retail One, DMS and SAP direct,
distinguishing technical SAP accounts from named users from human operators.

Sources:
  Retail One operator: @SO1_01VENTA.U_SO1_USUARIO (=OHEM.empID)
  Retail One seller:   @SO1_01VENTA.U_SO1_VENDEDOR (=OSLP.SlpCode)
  DMS seller:          OINV.SlpCode (where U_ORIGIN='DMS')
  SAP direct:          OINV.UserSign (named vs technical)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.users_audit.identity_model import (
    IdentityLevel,
    is_technical_user,
    TECHNICAL_SAP_USERS,
)


def q(cursor: Any, sql: str, params: tuple = ()) -> Any:
    cursor.execute(sql, params)
    return cursor.fetchone()


def retail_one_attribution(cursor: Any) -> dict[str, Any]:
    """Operators + sellers + branches from @SO1_01VENTA."""
    t, d_user, d_ven, d_suc, d_est = q(
        cursor,
        'SELECT COUNT(*), COUNT(DISTINCT "U_SO1_USUARIO"), COUNT(DISTINCT "U_SO1_VENDEDOR"), '
        'COUNT(DISTINCT "U_SO1_SUCURSAL"), COUNT(DISTINCT "U_SO1_ESTACION") '
        'FROM "TELCHI"."@SO1_01VENTA"',
    )

    # operators matched to employee
    matched = q(
        cursor,
        'SELECT COUNT(DISTINCT V."U_SO1_USUARIO") FROM "TELCHI"."@SO1_01VENTA" V '
        'JOIN "TELCHI"."OHEM" E ON E."empID" = V."U_SO1_USUARIO"',
    )[0]

    # sellers matched to OSLP
    sellers_matched = q(
        cursor,
        'SELECT COUNT(DISTINCT V."U_SO1_VENDEDOR") FROM "TELCHI"."@SO1_01VENTA" V '
        'JOIN "TELCHI"."OSLP" S ON S."SlpCode" = V."U_SO1_VENDEDOR"',
    )[0]

    # operators per branch
    branch_ops = q(
        cursor,
        'SELECT "U_SO1_SUCURSAL", COUNT(DISTINCT "U_SO1_USUARIO"), COUNT(DISTINCT "U_SO1_VENDEDOR"), COUNT(*) '
        'FROM "TELCHI"."@SO1_01VENTA" GROUP BY "U_SO1_SUCURSAL" ORDER BY COUNT(*) DESC',
    )

    return {
        "documents": t,
        "distinct_operators": d_user,
        "operators_matched_employee": matched,
        "distinct_sellers": d_ven,
        "sellers_matched_oslp": sellers_matched,
        "distinct_branches": d_suc,
        "distinct_stations": d_est,
    }


def retail_one_temporal(cursor: Any) -> dict[str, Any]:
    """Active operators in recent windows (using U_SO1_FECHA)."""
    windows = {
        "all_history": None,
        "last_12_months": "ADD_MONTHS(CURRENT_DATE, -12)",
        "last_90_days": "ADD_MONTHS(CURRENT_DATE, -3)",
        "last_30_days": "ADD_MONTHS(CURRENT_DATE, -1)",
    }
    result = {}
    for label, cutoff in windows.items():
        if cutoff is None:
            n = q(cursor, 'SELECT COUNT(DISTINCT "U_SO1_USUARIO") FROM "TELCHI"."@SO1_01VENTA"')[0]
        else:
            n = q(cursor, f'SELECT COUNT(DISTINCT "U_SO1_USUARIO") FROM "TELCHI"."@SO1_01VENTA" WHERE "U_SO1_FECHA" >= {cutoff}')[0]
        result[label] = n
    return result


def dms_attribution(cursor: Any) -> dict[str, Any]:
    """DMS sellers from OINV where U_ORIGIN='DMS'."""
    t, d_slp, d_route, d_user = q(
        cursor,
        'SELECT COUNT(*), COUNT(DISTINCT "SlpCode"), COUNT(DISTINCT "U_OSLP_ID"), COUNT(DISTINCT "UserSign") '
        'FROM "TELCHI"."OINV" WHERE "U_ORIGIN"=\'DMS\'',
    )
    # technical users among DMS UserSign
    cursor.execute(
        'SELECT "U"."USER_CODE", COUNT(*) FROM "TELCHI"."OINV" O '
        'JOIN "TELCHI"."OUSR" U ON U."USERID"=O."UserSign" '
        'WHERE O."U_ORIGIN"=\'DMS\' GROUP BY U."USER_CODE" ORDER BY COUNT(*) DESC'
    )
    user_dist = dict(cursor.fetchall())

    technical = {k: v for k, v in user_dist.items() if is_technical_user(k)}
    named = {k: v for k, v in user_dist.items() if not is_technical_user(k)}

    # DMS sellers matched to employee (via OHEM.salesPrson)
    sellers = q(
        cursor,
        'SELECT COUNT(DISTINCT O."SlpCode") FROM "TELCHI"."OINV" O '
        'JOIN "TELCHI"."OSLP" S ON S."SlpCode"=O."SlpCode" '
        'WHERE O."U_ORIGIN"=\'DMS\' AND S."SlpCode" > 0',
    )[0]

    return {
        "documents": t,
        "distinct_sellers": d_slp,
        "distinct_routes": d_route,
        "distinct_sap_users": d_user,
        "technical_sap_users": len(technical),
        "named_sap_users": len(named),
        "sellers_positive": sellers,
    }


def sap_direct_attribution(cursor: Any) -> dict[str, Any]:
    t, d_user, d_slp = q(
        cursor,
        'SELECT COUNT(*), COUNT(DISTINCT "UserSign"), COUNT(DISTINCT "SlpCode") '
        'FROM "TELCHI"."OINV" WHERE "U_ORIGIN"=\'SAP\' AND "U_SO1_01RETAILONE"=\'N\'',
    )
    cursor.execute(
        'SELECT U."USER_CODE", U."SUPERUSER", COUNT(*) FROM "TELCHI"."OINV" O '
        'JOIN "TELCHI"."OUSR" U ON U."USERID"=O."UserSign" '
        'WHERE O."U_ORIGIN"=\'SAP\' AND O."U_SO1_01RETAILONE"=\'N\' '
        'GROUP BY U."USER_CODE", U."SUPERUSER" ORDER BY COUNT(*) DESC'
    )
    user_dist = {r[0]: r[2] for r in cursor.fetchall()}

    technical = {k: v for k, v in user_dist.items() if is_technical_user(k)}
    named = {k: v for k, v in user_dist.items() if not is_technical_user(k)}

    # named users with employee link
    named_with_emp = q(
        cursor,
        'SELECT COUNT(DISTINCT O."UserSign") FROM "TELCHI"."OINV" O '
        'JOIN "TELCHI"."OHEM" E ON E."userId"=O."UserSign" '
        'WHERE O."U_ORIGIN"=\'SAP\' AND O."U_SO1_01RETAILONE"=\'N\'',
    )[0]

    return {
        "documents": t,
        "distinct_sap_users": d_user,
        "distinct_sellers": d_slp,
        "technical_sap_users": len(technical),
        "named_sap_users": len(named),
        "named_users_with_employee": named_with_emp,
    }


def main() -> int:
    conn, cur = connect()
    try:
        ro = retail_one_attribution(cur)
        ro_t = retail_one_temporal(cur)
        dms = dms_attribution(cur)
        sapd = sap_direct_attribution(cur)

        result = {
            "phase": "USER_ATTRIBUTION",
            "retail_one": {**ro, "temporal_operators": ro_t},
            "dms": dms,
            "sap_direct": sapd,
            "technical_sap_users_registry": TECHNICAL_SAP_USERS,
        }

        print(json.dumps(result, indent=2, default=str))

        print(f"\n{'='*64}")
        print("RETAIL ONE × DMS — USER ATTRIBUTION")
        print(f"{'='*64}")
        print(f"\nRETAIL ONE")
        print(f"  documents:               {ro['documents']:,}")
        print(f"  operadores (empID):      {ro['distinct_operators']}")
        print(f"  operadores con empleado: {ro['operators_matched_employee']}")
        print(f"  vendedores (SlpCode):    {ro['distinct_sellers']}")
        print(f"  vendedores en OSLP:      {ro['sellers_matched_oslp']}")
        print(f"  sucursales:              {ro['distinct_branches']}")
        print(f"  estaciones:              {ro['distinct_stations']}")
        print(f"  operadores activos:      {ro_t}")

        print(f"\nDMS")
        print(f"  documents:               {dms['documents']:,}")
        print(f"  vendedores (SlpCode):    {dms['distinct_sellers']}")
        print(f"  rutas (U_OSLP_ID):       {dms['distinct_routes']}")
        print(f"  usuarios SAP:            {dms['distinct_sap_users']}")
        print(f"  técnicos SAP:            {dms['technical_sap_users']}")
        print(f"  usuarios nombrados:      {dms['named_sap_users']}")

        print(f"\nSAP DIRECT")
        print(f"  documents:               {sapd['documents']:,}")
        print(f"  usuarios SAP:            {sapd['distinct_sap_users']}")
        print(f"  técnicos SAP:            {sapd['technical_sap_users']}")
        print(f"  usuarios nombrados:      {sapd['named_sap_users']}")
        print(f"  nombrados con empleado:  {sapd['named_users_with_employee']}")

    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
