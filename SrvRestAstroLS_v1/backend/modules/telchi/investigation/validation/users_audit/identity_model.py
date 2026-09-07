"""RETAIL ONE × DMS — user attribution identity model (pure logic).

Defines the identity-resolution hierarchy (§9) and channel attribution
semantics validated against real HANA schema.

Identity levels:
  LEVEL 1 — EXACT HUMAN OPERATOR    (Retail One U_SO1_USUARIO = OHEM.empID)
  LEVEL 2 — EXACT EXTERNAL USER     (external user id, person unresolved)
  LEVEL 3 — STRONG SALESPERSON LINK (SlpCode stable)
  LEVEL 4 — SAP USER ONLY           (UserSign)
  LEVEL 5 — TECHNICAL ACCOUNT ONLY  (soluone/dms/manager...)
  LEVEL 6 — UNKNOWN

Validated field semantics (TELCHI, READ ONLY):
  Retail One:
    @SO1_01VENTA.U_SO1_USUARIO  = OHEM.empID  (POS cashier/operator)  EXACT
    @SO1_01VENTA.U_SO1_VENDEDOR = OSLP.SlpCode (seller)                EXACT
    @SO1_01VENTA.U_SO1_SUCURSAL = branch code   (5 values)             EXACT
    @SO1_01VENTA.U_SO1_ESTACION = terminal/station (54 values)         EXACT
    @SO1_01VENTA.Name           = OINV.U_SO1_01FOLIORETAIL1 (join 1:1) EXACT
  DMS:
    OINV.U_OSLP_ID  = DMS route/zone (NOT a single seller)   INFERRED
    OINV.SlpCode    = seller                                   EXACT
    (no human operator field in SAP)
  SAP direct:
    OINV.UserSign   = SAP user (may be personal or technical)  LEVEL 4/5
"""
from __future__ import annotations

from enum import Enum


class IdentityLevel(str, Enum):
    L1_EXACT_HUMAN_OPERATOR = "LEVEL_1_EXACT_HUMAN_OPERATOR"
    L2_EXACT_EXTERNAL_USER = "LEVEL_2_EXACT_EXTERNAL_USER"
    L3_STRONG_SALESPERSON = "LEVEL_3_STRONG_SALESPERSON_LINK"
    L4_SAP_USER_ONLY = "LEVEL_4_SAP_USER_ONLY"
    L5_TECHNICAL_ACCOUNT = "LEVEL_5_TECHNICAL_ACCOUNT_ONLY"
    L6_UNKNOWN = "LEVEL_6_UNKNOWN"


class Confidence(str, Enum):
    EXACT = "EXACT"
    STRONG = "STRONG"
    HEURISTIC = "HEURISTIC"
    UNKNOWN = "UNKNOWN"


# Technical SAP accounts that must NOT be counted as human operators
TECHNICAL_SAP_USERS = {
    "soluone": "Retail One integration",
    "dms": "DMS integration",
    "manager": "admin/technical (multi-endpoint)",
    "B1i": "B1 integration",
    "Workflow": "workflow service",
    "AlertSvc": "alert service",
    "EDsUser": "electronic documents service",
    "alianza": "third-party integration",
    "manager2": "legacy admin",
    "manager6": "legacy admin",
    "managerserv": "service manager",
    "managerso": "simple one manager",
    "manager16": "legacy admin",
    "Support": "support account",
    "terbol": "third-party (Terbol)",
}


def is_technical_user(user_code: str) -> bool:
    return (user_code or "").upper() in {k.upper() for k in TECHNICAL_SAP_USERS}
