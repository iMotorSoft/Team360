"""Autorizaciones_xGrupos.xlsx — model loader (Phase 1 evidence).

Builds, from the workbook delivered by Telchi:
  USER -> GROUP -> PERMISSION matrix + LICENSE
and the effective authorization per user for the credit-sensitive permissions.

Level normalization (SAP B1 Spanish matrix -> canonical):
  'Autorización total'     -> FULL
  'Sólo lectura'           -> READ
  'Varias autorizaciones'  -> VARIOUS
  'Falta autorización'     -> NONE
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from modules.telchi.investigation.paths import EVIDENCE_ROOT, LEGACY_DATA_ROOT
from typing import Any

# Compatibility default; reusable loaders also accept an explicit workbook.
XLSX_PATH = LEGACY_DATA_ROOT.parents[1] / "Doc" / "Autorizaciones_xGrupos.xlsx"
SHEET_USERS = "Grupos Usuarios"
SHEET_LICENSES = "Licenciamiento SAP"
GROUP_SHEETS = [
    "Gerencia", "Almacenes", "Compras", "Administracion", "Facturacion",
    "Vtas Horizontales", "Vtas Medicamentos", "Produccion", "Externos",
    "Supervisor", "Auxiliar",
]

# the user sheet uses full names; the permission sheets abbreviate
GROUP_NAME_ALIAS = {
    "Vtas Horizontales": "Ventas Horizontales",
    "Vtas Medicamentos": "Ventas Medicamentos",
}

LEVEL_MAP = {
    "Autorización total": "FULL",
    "Sólo lectura": "READ",
    "Varias autorizaciones": "VARIOUS",
    "Falta autorización": "NONE",
}

# Permission subjects (Asunto) considered credit-sensitive; found verbatim in
# every group sheet via the PHASE-1 inventory.
CREDIT_PERMISSIONS = {
    "CONFIRM_CREDIT_LINE_DEVIATION": "Confirmar desviación de línea de crédito",
    "CONFIRM_DEBT_LINE_DEVIATION": "Confirmar desviación de línea de endeudamiento",
    "ALLOW_SERVICE_AFTER_CREDIT_LIMIT": "Permite servicio después de límite de crédito",
    "CREDIT_LIMIT_DEVIATION_REPORT": "Desviación del límite de crédito",
    "OPEN_BALANCE_VS_CREDIT_LIMIT": "Customer Open Balances And Credit Limit Comparison",
}


def _norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


def load_users_sheet(path: Path = XLSX_PATH) -> list[dict[str, Any]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[SHEET_USERS]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None and r[1] is None:
            continue
        out.append({
            "codigo_interno": _norm(r[0]),
            "login": _norm(r[1]),
            "nombre": _norm(r[2]),
            "bloqueado": _norm(r[3]),
            "grupo_cod": _norm(r[4]),
            "grupo_nombre": _norm(r[5]),
            "licencia": _norm(r[6]),
        })
    return out


def load_licenses_sheet(path: Path = XLSX_PATH) -> list[dict[str, Any]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[SHEET_LICENSES]
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None and r[1] is None:
            continue
        out.append({
            "codigo": _norm(r[0]),
            "nombre": _norm(r[1]),
            "bloqueado": _norm(r[2]),
            "licencia": _norm(r[3]),
        })
    return out


def load_group_permissions(path: Path = XLSX_PATH) -> dict[str, list[dict[str, Any]]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    groups: dict[str, list[dict[str, Any]]] = {}
    for sh in GROUP_SHEETS:
        ws = wb[sh]
        perms = []
        for r in ws.iter_rows(min_row=2, values_only=True):
            if r[0] is None and r[1] is None:
                continue
            perms.append({"asunto": _norm(r[0]), "autorizacion": _norm(r[1])})
        groups[sh] = perms
    return groups


def build_authorization_model(path: Path = XLSX_PATH) -> dict[str, Any]:
    users = load_users_sheet(path)
    licenses = load_licenses_sheet(path)
    group_perms = load_group_permissions(path)

    # group code -> name from user sheet
    code_to_name: dict[str, str] = {}
    for u in users:
        if u["grupo_cod"] is not None:
            code_to_name.setdefault(str(u["grupo_cod"]), u["grupo_nombre"])

    # user -> list of groups (multi-membership possible)
    user_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in users:
        if u["grupo_cod"] is not None:
            user_groups[u["login"]].append({
                "cod": str(u["grupo_cod"]),
                "nombre": u["grupo_nombre"],
            })

    # group -> {asunto: level}
    group_level: dict[str, dict[str, str]] = {}
    for gname, perms in group_perms.items():
        d = {}
        skipped = 0
        for p in perms:
            lv = LEVEL_MAP.get(_norm(p["autorizacion"]))
            if lv is None:
                skipped += 1
                d[str(p["asunto"])] = f"UNKNOWN:{p['autorizacion']}"
            else:
                d[str(p["asunto"])] = lv
        group_level[GROUP_NAME_ALIAS.get(gname, gname)] = d
    # keep the sheet-keyed map too for the raw evidence
    group_level_sheet = group_level

    # effective per user for the credit permissions
    users_out = []
    for u in users:
        groups = user_groups.get(u["login"], [])
        eff: dict[str, str] = {}
        sources: dict[str, list[str]] = {}
        for cap, subject in CREDIT_PERMISSIONS.items():
            levels = []
            src = []
            for g in groups:
                gname = g["nombre"]
                if gname in group_level:
                    lvl = group_level[gname].get(subject)
                    if lvl is not None:
                        levels.append(lvl)
                        src.append(f"{gname}:{lvl}")
            # effective level: strongest among groups (documented heuristic)
            rank = {"FULL": 4, "VARIOUS": 3, "READ": 2, "NONE": 1}
            eff_level = max(levels, key=lambda x: rank.get(x, 0)) if levels else "NO_GROUP_OR_UNMAPPED"
            eff[cap] = eff_level
            sources[cap] = src
        users_out.append({
            **u,
            "groups": groups,
            "effective_credit_auth": eff,
            "credit_auth_sources": sources,
        })

    license_map = {}
    for l in licenses:
        if l["codigo"] is not None:
            license_map[str(l["codigo"])] = l

    # de-duplicated per unique login: merge the group memberships
    rows_by_login: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in users_out:
        rows_by_login[u["login"]].append(u)

    users_dedup: list[dict[str, Any]] = []
    for login, rows in sorted(rows_by_login.items(), key=lambda kv: (kv[0] or "").lower()):
        first = dict(rows[0])
        all_groups: list[dict[str, Any]] = []
        seen = set()
        eff: dict[str, str] = {}
        src: dict[str, list[str]] = {}
        for r in rows:
            for g in r["groups"]:
                key = (g["cod"], g["nombre"])
                if key not in seen:
                    seen.add(key)
                    all_groups.append(g)
            for cap, lvl in r["effective_credit_auth"].items():
                rank = {"FULL": 4, "VARIOUS": 3, "READ": 2, "NONE": 1, "NO_GROUP_OR_UNMAPPED": 0}
                if cap not in eff or rank.get(lvl, 0) > rank.get(eff[cap], 0):
                    eff[cap] = lvl
                src.setdefault(cap, []).extend(r["credit_auth_sources"][cap])
        first["groups"] = all_groups
        first["effective_credit_auth"] = eff
        first["credit_auth_sources"] = src
        users_dedup.append(first)

    # cardinalities
    logins = [u["login"] for u in users if u["login"] is not None]
    dup_logins = {l: c for l, c in Counter(logins).items() if c > 1}
    n_grouped = sum(1 for u in users_out if u["groups"])
    n_ungrouped = len(users_out) - n_grouped

    # distinct Asunto across all group sheets and unknown authorization values
    all_asunto = Counter()
    unknown_auth: Counter = Counter()
    for gname, perms in group_perms.items():
        for p in perms:
            all_asunto[str(p["asunto"])] += 1
            av = _norm(p["autorizacion"])
            if av not in LEVEL_MAP:
                unknown_auth[str(av)] += 1

    return {
        "source": str(path),
        "users_total": len(users_out),
        "unique_logins": len(users_dedup),
        "users_with_group": n_grouped,
        "users_without_group": n_ungrouped,
        "duplicate_logins": dup_logins,
        "group_count": len(code_to_name),
        "group_codes": code_to_name,
        "group_sheets_present": sorted(group_level_sheet.keys(), key=str.lower),
        "group_sheets_missing": sorted(
            set(code_to_name.values()) - set(group_level_sheet.keys())
        ),
        "distinct_asunto": len(all_asunto),
        "unknown_authorization_values": dict(unknown_auth),
        "licenses_total": len(licenses),
        "users": users_out,
        "users_by_login": users_dedup,
        "group_permissions": {GROUP_NAME_ALIAS.get(k, k): v for k, v in group_perms.items()},
        "license_assignments": licenses,
    }


if __name__ == "__main__":
    model = build_authorization_model()
    out = EVIDENCE_ROOT / "credit_control" / "evidence" / "excel_authorization_model.json"
    out.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
    print("users:", model["users_total"],
          "grouped:", model["users_with_group"],
          "ungrouped:", model["users_without_group"])
    print("duplicate logins (multi-group):", len(model["duplicate_logins"]))
    print("groups:", model["group_codes"])
    print("distinct asunto:", model["distinct_asunto"])
    print("unknown auth values:", model["unknown_authorization_values"])
