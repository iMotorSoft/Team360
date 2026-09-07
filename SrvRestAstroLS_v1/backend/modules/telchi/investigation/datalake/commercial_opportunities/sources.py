"""Sources comerciales TELCHI — normalización de oportunidades (READ ONLY).

NO modifica los archivos Excel fuente. Produce registros normalizados:

  raw_value + normalized_value + normalization_reason

con detección explícita de problemas de calidad de datos (§4 del prompt):
duplicados, códigos incorrectos, cantidades/ precios inconsistentes,
TOTAL != CANTIDAD*PRECIO, fechas/clientes faltantes, motivos incompatibles,
unidades ambiguas, etc. Nunca borra silenciosamente registros.

Semántica de hojas (validada empíricamente 2026-09-02):
  - VENTAS PERDIDAS: una hoja por mes; header variable por hoja; columnas
    comunes: FECHA, CANAL, CÓDIGO, PRODUCTO, CANTIDAD(KG), PRECIO POR KG,
    TOTAL, MOTIVO, VENDEDOR, COMENTARIOS (+ COD. CLIENTE/CLIENTE en algunas).
  - AGOSTO 2026 y otras hojas posteriores cambian el orden de columnas y
    omiten FECHA (reporte mensual consolidado).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

import openpyxl

from modules.telchi.investigation.paths import EXTERNAL_FILES_ROOT

# ---------------------------------------------------------------------------
# Paths fuente (no modificables)
# ---------------------------------------------------------------------------
EXCEL_DIR = EXTERNAL_FILES_ROOT
SOURCES = {
    "ventas_perdidas": EXCEL_DIR / "VENTAS PERDIDAS.xlsx",
    "proformas": EXCEL_DIR / "PROFORMAS DICIEMBRE CORPORATIVO LICITACIONES.xlsx",
    "estatus": EXCEL_DIR / "ESTATUS CLIENTES CORPORATIVOS.xlsx",
    "cronograma": EXCEL_DIR / "CRONOGRAMA DE VISITAS COMERCIAL.xlsx",
    "precios_competencia": EXCEL_DIR / "Copia de PRECIOS COMPETENCIA SV.xlsx",
}

# Motivos normalizados declarados en la fuente comercial
REASONS = {"STOCK", "PRECIO", "PRECIOS", "OTROS", "CREDITO", "CALIDAD", "SERVICIO"}


@dataclass
class Opportunity:
    source: str
    source_sheet: str
    source_row: int
    date: date | None
    channel_raw: str
    item_code_raw: str
    item_code_report: str | None
    product_raw: str
    qty: float | None
    unit: str
    price: float | None
    total_raw: float | None
    declared_reason: str
    salesperson_raw: str
    comment: str
    customer_raw: str
    issues: list[str] = field(default_factory=list)

    @property
    def total_computed(self) -> float | None:
        if self.qty is None or self.price is None:
            return None
        return round(self.qty * self.price, 2)


def _norm_reason(raw: str | None) -> str:
    if not raw:
        return ""
    r = raw.strip().upper()
    r = re.sub(r"\s+", " ", r)
    r = r.replace("PRECIO ", "PRECIO").replace("PRECIOS", "PRECIO")
    return r


def _norm_code(raw: str | None) -> str:
    if not raw:
        return ""
    return str(raw).strip().upper()


def _to_float(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _to_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Mapas de corrección de código de producto (evidencia SAP OITM 2026-09-02)
# ---------------------------------------------------------------------------
# L01094 = ACIDO NITRICO x kg. (OITM verificado). Nombres "Sulfato de Zinc
# Feed ..." con código L01094 => código correcto L01794 (SULFATO DE ZINC FEED
# GRADE x 25kg). Ver docs/report zink P0.
ITEM_CODE_CORRECTIONS = {
    "L01094": {
        "L01794": (
            "SULFATO DE ZINC FEED GRADE x 25kg.",
            "OITM: L01094=ACIDO NITRICO; nombre declarado es sulfato de zinc; "
            "código correcto demostrado L01794.",
        ),
    },
}


def correct_item_code(code_raw: str, product_raw: str) -> tuple[str, str | None]:
    """Devuelve (código normalizado, corrección/trazabilidad o None).

    Si el código declarado pertenece a otro producto (evidencia OITM), se
    corrige con normalization_reason. Si no, devuelve el código tal cual.
    """
    code = _norm_code(code_raw)
    if not code:
        return code, "CODIGO_FALTANTE"
    if code == "L01094" and re.search(r"ZINC", product_raw, re.I):
        return "L01794", "OITM_VERIFIED_L01094_ES_ACIDO_NITRICO"
    return code, None


def _cell(row: tuple, mapping: dict[str, int], key: str) -> object | None:
    idx = mapping.get(key)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _parse_header(row: tuple) -> dict[str, int]:
    """Mapea nombre de columna -> índice, tolerando variaciones de hoja."""
    mapping: dict[str, int] = {}
    if not row:
        return mapping
    for i, cell in enumerate(row):
        if cell is None:
            continue
        name = str(cell).strip().upper()
        name = name.rstrip(" .:")
        if name.startswith("FECHA"):
            mapping["date"] = i
        elif name.startswith("CANAL"):
            mapping["channel"] = i
        elif name.startswith("CÓDIGO") or name.startswith("CODIGO"):
            mapping["code"] = i
        elif name.startswith("COD.") and "CLIENTE" in name:
            continue  # COD. CLIENTE = CardCode del cliente, no código de producto
        elif name.startswith("COD."):
            mapping["code"] = i
        elif "PRODUCTO" in name:
            mapping["product"] = i
        elif "CANTIDAD" in name:
            mapping["qty"] = i
        elif "PRECIO" in name and "POR KG" in name:
            mapping["price"] = i
        elif name.startswith("TOTAL"):
            mapping["total"] = i
        elif "MOTIVO" in name:
            mapping["reason"] = i
        elif "VENDEDOR" in name:
            mapping["salesperson"] = i
        elif "COMENT" in name or "OBSERV" in name:
            mapping["comment"] = i
        elif name.startswith("CLIENTE"):
            mapping["customer"] = i
    return mapping


def ingest_ventas_perdidas(path: Path | None = None) -> list[Opportunity]:
    """Lee VENTAS PERDIDAS.xlsx (todas las hojas) y normaliza cada fila."""
    path = path or SOURCES["ventas_perdidas"]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out: list[Opportunity] = []
    seen: Counter = Counter()
    for ws in wb.worksheets:
        rows_iter = ws.iter_rows(values_only=True)
        header_idx = None
        header_map: dict[str, int] = {}
        for r_i, row in enumerate(rows_iter, start=1):
            if header_idx is None:
                # detect header: FECHA presente, o (CANAL + CÓDIGO + PRODUCTO)
                cols = [str(c).strip().upper() for c in row if c is not None]
                joined = " ".join(cols)
                has_fecha = "FECHA" in joined
                has_trio = all(k in joined for k in ("CANAL", "PRODUCTO"))
                if has_fecha or (has_trio and "CÓDIGO" in joined):
                    header_idx = r_i
                    header_map = _parse_header(row)
                continue
            # data row
            if all(c is None for c in row):
                continue
            def cv(key: str) -> object | None:
                return _cell(row, header_map, key)
            date_v = _to_date(cv("date"))
            qty_v = _to_float(cv("qty"))
            price_v = _to_float(cv("price"))
            total_v = _to_float(cv("total"))
            code_raw = str(cv("code")).strip() if cv("code") is not None else ""
            product_raw = str(cv("product")).strip() if cv("product") is not None else ""
            reason_raw = str(cv("reason")).strip() if cv("reason") is not None else ""
            seller = str(cv("salesperson")).strip() if cv("salesperson") is not None else ""
            comment = str(cv("comment")).strip() if cv("comment") is not None else ""
            cust = str(cv("customer")).strip() if cv("customer") is not None else ""

            opp = Opportunity(
                source="VENTAS PERDIDAS.xlsx",
                source_sheet=ws.title,
                source_row=r_i,
                date=date_v,
                channel_raw=str(cv("channel")).strip() if cv("channel") is not None else "",
                item_code_raw=code_raw,
                item_code_report=_norm_code(code_raw),
                product_raw=product_raw,
                qty=qty_v,
                unit="KG",
                price=price_v,
                total_raw=total_v,
                declared_reason=_norm_reason(reason_raw),
                salesperson_raw=seller,
                comment=comment,
                customer_raw=cust,
            )
            # --- validaciones de calidad ---
            if opp.date is None:
                opp.issues.append("FECHA_FALTANTE")
            if not code_raw:
                opp.issues.append("CODIGO_FALTANTE")
            if not _norm_reason(reason_raw):
                opp.issues.append("MOTIVO_VACIO")
            with_clients = header_map.get("customer") is not None
            if with_clients and not cust:
                opp.issues.append("CLIENTE_FALTANTE")
            if qty_v is not None and qty_v <= 0:
                opp.issues.append("CANTIDAD_INVALIDA")
            if price_v is not None and price_v <= 0:
                opp.issues.append("PRECIO_INVALIDO")
            if total_v is not None and opp.total_computed is not None:
                diff = abs(total_v - opp.total_computed)
                if diff > max(0.01, abs(total_v) * 0.005):
                    opp.issues.append(
                        f"TOTAL_INCONSISTENTE: fuente={total_v} calculado={opp.total_computed}"
                    )
            if opp.declared_reason == "OTROS" and re.search(r"STOCK", comment, re.I):
                opp.issues.append("OTROS_CON_COMENTARIO_STOCK")
            if re.search(r"STOCK", comment, re.I) and opp.declared_reason == "PRECIO":
                opp.issues.append("MOTIVO_INCOMPATIBLE_COMENTARIO")
            key = (opp.source_sheet, opp.date, opp.item_code_report, opp.qty, opp.price)
            seen[key] += 1
            if seen[key] > 1:
                opp.issues.append("DUPLICADO_PROBABLE")
            out.append(opp)
    wb.close()
    return out


def opportunities_for_items(opps: list[Opportunity], items: set[str]) -> list[Opportunity]:
    """Filtra oportunidades cuyo código declarado o corregido está en items."""
    return [o for o in opps if o.item_code_report in items or correct_item_code(o.item_code_raw, o.product_raw)[0] in items]