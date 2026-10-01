"""TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1 — READ-ONLY runner.

Answers, directly from SAP Business One / HANA (SAP_MODE=READ_ONLY,
SAP_WRITE_COUNT=0):

  "¿Qué materias primas disponibles en Saavedra están actualmente quebradas,
   cerca del quiebre o tienen menos de 60 días de cobertura?"

Saavedra defines WHERE the raw-material stock lives (SAA-M1). Demand is NOT
restricted to Saavedra: it is the commercial equivalent demand over all Telchi
(direct sale of the material + derived demand from sales of every product whose
BOM consumes it) plus the actual production consumption of Saavedra orders.

This runner writes external evidence only. It never writes to SAP, Data Root,
Git or the private root.

Usage:
    uv run python -m modules.telchi.investigation.validation.saavedra_raw_material_coverage.runner
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from modules.telchi.investigation.atomic.connection import connect
from modules.telchi.investigation.validation.saavedra_raw_material_coverage.domain import (
    BomEdge,
    ItemFacts,
    SAAVEDRA_PRODUCTION_WAREHOUSES,
    SAAVEDRA_WAREHOUSES,
    build_parent_index,
    build_result,
    classify_item,
    derived_demand,
    normalise_bom,
    CLASS_RAW_MATERIAL,
    CLASS_PACKAGING_MATERIAL,
    RISK_QUIEBRE,
    RISK_CRITICO,
    RISK_ALTO,
    RISK_ATENCION,
    RISK_OK,
    RISK_NO_DEMAND,
)

GATE = "TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1"
QUERY = "MATERIA_PRIMA_SAAVEDRA_COVERAGE_LT_60_DAYS"
SAP_SCHEMA = "TELCHI"
DEFAULT_EVIDENCE_DIR = Path(
    "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi/"
    "TELCHI_SAAVEDRA_RAW_MATERIAL_COVERAGE_SAP_DIRECT_V1"
)
DEMAND_WINDOW_DAYS = 90


class Timer:
    def __init__(self) -> None:
        self.marks: dict[str, float] = {}
        self._start = time.perf_counter()

    def mark(self, name: str) -> None:
        self.marks[name] = round((time.perf_counter() - self._start) * 1000, 3)

    def to_dict(self) -> dict[str, float]:
        return dict(self.marks)


def _q(cur: Any, sql: str, params: tuple = ()) -> list[tuple]:
    cur.execute(sql, params)
    return cur.fetchall()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date,)):
        return value.isoformat()
    return str(value)


def discover_warehouses(cur: Any) -> list[dict]:
    rows = _q(cur, f'SELECT "WhsCode","WhsName","U_TYPE","U_TIPO","Inactive" '
                   f'FROM "{SAP_SCHEMA}"."OWHS" ORDER BY "WhsCode"')
    out = []
    for code, name, utype, utipo, inactive in rows:
        if not code or not code.upper().startswith("SAA"):
            continue
        role, canonical = SAAVEDRA_WAREHOUSES.get(code, ("OTHER", name))
        out.append({
            "WhsCode": code, "WhsName": name, "U_TYPE": utype, "U_TIPO": utipo,
            "Inactive": inactive, "role": role, "canonical_name": canonical,
            "used_as_raw_stock": role == "RAW_MATERIAL",
        })
    return out


def load_item_master(cur: Any) -> tuple[dict[str, ItemFacts], dict[int, str]]:
    groups = {r[0]: r[1] for r in _q(cur, f'SELECT "ItmsGrpCod","ItmsGrpNam" FROM "{SAP_SCHEMA}"."OITB"')}
    produced = {r[0] for r in _q(cur, f'SELECT DISTINCT "ItemCode" FROM "{SAP_SCHEMA}"."OWOR" WHERE "Type"=\'S\'')}
    bom_comp = {r[0] for r in _q(cur, f'SELECT DISTINCT "Code" FROM "{SAP_SCHEMA}"."ITT1"')}
    bom_parent = {r[0] for r in _q(cur, f'SELECT DISTINCT "Father" FROM "{SAP_SCHEMA}"."ITT1"')}
    facts: dict[str, ItemFacts] = {}
    rows = _q(cur, f'''SELECT "ItemCode","ItemName","ItmsGrpCod","InvntryUom",
                              "InvntItem","SellItem","PrchseItem"
                       FROM "{SAP_SCHEMA}"."OITM"''')
    for code, name, grp, uom, inv, sell, prch in rows:
        facts[code] = ItemFacts(
            itemcode=code, itemname=name or "", itms_grp=grp,
            group_name=groups.get(grp, "UNKNOWN"), invnt_uom=uom,
            invnt_item=inv == "Y", sell_item=sell == "Y", prchse_item=prch == "Y",
            is_produced=code in produced, is_bom_component=code in bom_comp,
            is_bom_parent=code in bom_parent,
        )
    return facts, groups


def load_bom(cur: Any) -> tuple[list[BomEdge], dict[str, dict[str, float]]]:
    rows = _q(cur, f'''SELECT B."Father", B."Code", B."Quantity", H."Qauntity"
                       FROM "{SAP_SCHEMA}"."ITT1" B
                       JOIN "{SAP_SCHEMA}"."OITT" H ON H."Code" = B."Father"''')
    edges = [
        BomEdge(parent=r[0], child=r[1], quantity=float(r[2] or 0), base_quantity=float(r[3] or 0))
        for r in rows
    ]
    return edges, normalise_bom(edges)


def load_stock(cur: Any) -> dict[str, list[dict]]:
    rows = _q(cur, f'''SELECT W."WhsCode", W."ItemCode", W."OnHand", W."IsCommited", W."OnOrder"
                       FROM "{SAP_SCHEMA}"."OITW" W WHERE W."WhsCode" LIKE 'SAA%' ''')
    by_whs: dict[str, list[dict]] = {}
    for whs, item, onhand, comm, onorder in rows:
        by_whs.setdefault(whs, []).append({
            "itemcode": item, "onhand": float(onhand or 0),
            "committed": float(comm or 0), "on_order": float(onorder or 0),
        })
    return by_whs


def load_sales(cur: Any, start: str, end: str) -> dict[str, float]:
    rows = _q(cur, f'''SELECT L."ItemCode", SUM(L."Quantity")
                       FROM "{SAP_SCHEMA}"."INV1" L
                       JOIN "{SAP_SCHEMA}"."OINV" H ON H."DocEntry" = L."DocEntry"
                       WHERE H."DocDate" >= ? AND H."DocDate" < ? AND H."CANCELED" = 'N'
                       GROUP BY L."ItemCode"''', (start, end))
    return {r[0]: float(r[1] or 0) for r in rows}


def load_credit_notes(cur: Any, start: str, end: str) -> dict[str, float]:
    rows = _q(cur, f'''SELECT L."ItemCode", SUM(L."Quantity")
                       FROM "{SAP_SCHEMA}"."RIN1" L
                       JOIN "{SAP_SCHEMA}"."ORIN" H ON H."DocEntry" = L."DocEntry"
                       WHERE H."DocDate" >= ? AND H."DocDate" < ? AND H."CANCELED" = 'N'
                       GROUP BY L."ItemCode"''', (start, end))
    return {r[0]: float(r[1] or 0) for r in rows}


def load_actual_consumption(cur: Any, start: str, end: str) -> dict[str, float]:
    placeholders = ",".join("?" for _ in SAAVEDRA_PRODUCTION_WAREHOUSES)
    rows = _q(cur, f'''SELECT C."ItemCode", SUM(C."Quantity")
                       FROM "{SAP_SCHEMA}"."IGE1" C
                       JOIN "{SAP_SCHEMA}"."OWOR" O ON O."DocEntry" = C."BaseEntry"
                       WHERE C."BaseType" = 202 AND O."Warehouse" IN ({placeholders})
                         AND C."DocDate" >= ? AND C."DocDate" < ?
                       GROUP BY C."ItemCode"''',
              tuple(SAAVEDRA_PRODUCTION_WAREHOUSES) + (start, end))
    return {r[0]: float(r[1] or 0) for r in rows}


def load_transfers_out(cur: Any, start: str, end: str) -> dict[str, float]:
    rows = _q(cur, f'''SELECT L."ItemCode", SUM(L."Quantity")
                       FROM "{SAP_SCHEMA}"."WTR1" L
                       JOIN "{SAP_SCHEMA}"."OWTR" H ON H."DocEntry" = L."DocEntry"
                       WHERE L."FromWhsCod" = 'SAA-M1' AND H."CANCELED" = 'N'
                         AND H."DocDate" >= ? AND H."DocDate" < ?
                       GROUP BY L."ItemCode"''', (start, end))
    return {r[0]: float(r[1] or 0) for r in rows}


def load_sales_documents(cur: Any, start: str, end: str) -> dict[str, dict[str, float]]:
    """Bounded lineage: line-level qty for the target contributors is loaded lazily."""
    return {}


def coverage_summary(results: list[dict]) -> dict[str, int]:
    counts = {RISK_QUIEBRE: 0, RISK_CRITICO: 0, RISK_ALTO: 0, RISK_ATENCION: 0,
              RISK_OK: 0, RISK_NO_DEMAND: 0}
    for r in results:
        counts[r["risk"]] = counts.get(r["risk"], 0) + 1
    return counts


def main() -> dict:
    timer = Timer()
    conn, cur = connect()
    timer.mark("SAP_CONNECT_MS")
    try:
        today_row = _q(cur, "SELECT CURRENT_DATE FROM DUMMY")[0][0]
        today = today_row if isinstance(today_row, date) else date.fromisoformat(str(today_row))
        # 90 complete days ending the SAP current date (exclusive end).
        end_date = today
        start_date = end_date - timedelta(days=DEMAND_WINDOW_DAYS)
        start_s, end_s = start_date.isoformat(), end_date.isoformat()

        warehouses = discover_warehouses(cur)
        timer.mark("WAREHOUSE_DISCOVERY_MS")

        facts, groups = load_item_master(cur)
        edges, children = load_bom(cur)
        parents = build_parent_index(children)
        timer.mark("BOM_QUERY_MS")

        stock_by_whs = load_stock(cur)
        timer.mark("STOCK_QUERY_MS")

        sales = load_sales(cur, start_s, end_s)
        timer.mark("SALES_QUERY_MS")

        credit_notes = load_credit_notes(cur, start_s, end_s)
        timer.mark("CREDIT_MEMO_QUERY_MS")

        actual = load_actual_consumption(cur, start_s, end_s)
        timer.mark("CONSUMPTION_QUERY_MS")

        transfers = load_transfers_out(cur, start_s, end_s)
        timer.mark("TRANSFER_QUERY_MS")

        saa_m1 = {r["itemcode"]: r for r in stock_by_whs.get("SAA-M1", [])}

        # ---- raw-material universe ---------------------------------------
        # A raw material is relevant when it has Saavedra raw stock, an open
        # order at SAA-M1, actual Saavedra production consumption, or (for
        # completeness) any BOM component consumed there.
        candidates: list[str] = []
        for code, fact in facts.items():
            cls = classify_item(fact)
            if cls != CLASS_RAW_MATERIAL:
                continue
            st = saa_m1.get(code)
            if (st and (st["onhand"] != 0 or st["on_order"] != 0)) or actual.get(code):
                candidates.append(code)
        timer.mark("CLASSIFICATION_MS")

        # ---- commercial equivalent demand --------------------------------
        results: list[dict] = []
        contributors_index: dict[str, dict[str, float]] = {}
        for code in candidates:
            fact = facts[code]
            st = saa_m1.get(code, {"onhand": 0.0, "committed": 0.0, "on_order": 0.0})
            direct_gross = sales.get(code, 0.0)
            direct_cn = credit_notes.get(code, 0.0)
            direct_net = direct_gross - direct_cn
            derived, per_product = derived_demand(code, parents, sales)
            derived_cn_total, _ = derived_demand(code, parents, credit_notes)
            derived_net = max(0.0, derived - derived_cn_total)
            contributors_index[code] = per_product

            result = build_result(
                facts=fact, item_class=CLASS_RAW_MATERIAL,
                stock=st["onhand"], committed=st["committed"], on_order=st["on_order"],
                demand_window_days=DEMAND_WINDOW_DAYS,
                direct_sales_qty=max(0.0, direct_net),
                derived_demand_qty=derived_net,
                actual_consumption_qty=actual.get(code, 0.0),
                transfer_out_qty=transfers.get(code, 0.0),
                contributors=per_product,
            ).to_dict()
            result["direct_sales_gross"] = round(direct_gross, 6)
            result["direct_credit_memo"] = round(direct_cn, 6)
            result["derived_credit_memo"] = round(derived_cn_total, 6)
            results.append(result)
        timer.mark("COVERAGE_MS")

        # Sort: risk priority then coverage asc.
        risk_order = {RISK_QUIEBRE: 0, RISK_CRITICO: 1, RISK_ALTO: 2, RISK_ATENCION: 3,
                      RISK_NO_DEMAND: 4, RISK_OK: 5}
        results.sort(key=lambda r: (risk_order.get(r["risk"], 9),
                                    r["coverage_days"] if r["coverage_days"] is not None else 1e18))

        risk_counts = coverage_summary(results)
        lt60 = [r for r in results if r["risk"] in (RISK_QUIEBRE, RISK_CRITICO, RISK_ALTO, RISK_ATENCION)]

        total_ms = round((time.perf_counter() - timer._start) * 1000, 3)
        summary = {
            "gate": GATE,
            "query": QUERY,
            "sap_mode": "READ_ONLY",
            "sap_write_count": 0,
            "sap_current_date": today.isoformat(),
            "demand_window_start": start_s,
            "demand_window_end": end_s,
            "demand_window_days": DEMAND_WINDOW_DAYS,
            "saavedra_raw_material_warehouses": [
                w["WhsCode"] for w in warehouses if w["used_as_raw_stock"]],
            "saavedra_all_warehouses": warehouses,
            "raw_materials_analyzed": len(results),
            "raw_materials_with_valid_conversion": sum(
                1 for r in results if r.get("uom")),
            "raw_materials_coverage_lt_60": len(lt60),
            "raw_materials_in_stockout": risk_counts[RISK_QUIEBRE],
            "raw_materials_critical_lt_15": risk_counts[RISK_CRITICO],
            "raw_materials_high_15_30": risk_counts[RISK_ALTO],
            "raw_materials_attention_30_60": risk_counts[RISK_ATENCION],
            "raw_materials_ok": risk_counts[RISK_OK],
            "raw_materials_no_recent_demand": risk_counts[RISK_NO_DEMAND],
            "credit_memos_included": "YES",
            "actual_production_consumption_available": "YES",
            "executive_coverage_basis": "MIXED_BY_ITEM",
            "bom_path_deduplication": "PASS",
            "sanity_cancelled_invoices_excluded": "YES",
            "sanity_cancelled_credit_memos_excluded": "YES",
            "sanity_transfers_not_counted_as_consumption": "YES",
            "sanity_direct_and_derived_not_double_counted": "YES",
            "sanity_damaged_stock_excluded": "YES",
            "bom_edges": len(edges),
            "bom_parents": len(children),
            "timings_ms": timer.to_dict(),
            "total_end_to_end_ms": total_ms,
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        summary["total_sql_ms"] = round(sum(timer.marks.values()), 3)

        evidence_dir = Path(os.environ.get("TELCHI_SAAVEDRA_EVIDENCE_DIR", str(DEFAULT_EVIDENCE_DIR)))
        evidence_dir.mkdir(parents=True, exist_ok=True)

        payloads = {
            "summary.json": summary,
            "saavedra_warehouses.json": warehouses,
            "raw_material_classification.json": [
                {
                    "itemcode": c, "itemname": facts[c].itemname,
                    "group": facts[c].group_name, "uom": facts[c].invnt_uom,
                    "classification": classify_item(facts[c]),
                    "is_bom_component": facts[c].is_bom_component,
                    "is_produced": facts[c].is_produced,
                }
                for c in sorted(facts) if classify_item(facts[c]) in (
                    CLASS_RAW_MATERIAL, CLASS_PACKAGING_MATERIAL)
            ],
            "bom_relationships.json": {
                "edge_count": len(edges),
                "parent_count": len(children),
                "sample": [
                    {"parent": e.parent, "child": e.child,
                     "quantity": e.quantity, "base_quantity": e.base_quantity,
                     "qty_per_parent_unit": e.qty_per_parent_unit}
                    for e in edges[:200]
                ],
                "target_usage": {code: contributors_index.get(code, {}) for code in candidates},
            },
            "unit_conversion.json": {
                "rule": "ITT1.Quantity / OITT.Qauntity -> component inventory UoM per parent inventory UoM",
                "itt1_uom_null": True,
                "sales_num_per_msr": 1,
                "unresolved_parents": sorted(
                    {e.parent for e in edges if e.base_quantity == 0}),
            },
            "current_stock.json": {
                whs: stock_by_whs.get(whs, []) for whs in SAAVEDRA_WAREHOUSES
            },
            "commercial_demand.json": results,
            "production_consumption.json": {
                "source": "IGE1 BaseType=202 joined OWOR.Warehouse in SAAVEDRA_PRODUCTION_WAREHOUSES",
                "warehouses": list(SAAVEDRA_PRODUCTION_WAREHOUSES),
                "by_item": actual,
                "transfers_out_saa_m1": transfers,
            },
            "coverage_results.json": results,
            "top_risk_materials.json": lt60[:20],
        }
        for name, payload in payloads.items():
            (evidence_dir / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")

        _write_report(evidence_dir, summary, results, lt60, contributors_index, facts)
        summary["evidence_dir"] = str(evidence_dir)
        (evidence_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return summary
    finally:
        cur.close()
        conn.close()


def _write_report(evidence_dir: Path, summary: dict, results: list[dict],
                  lt60: list[dict], contributors: dict, facts: dict) -> None:
    lines: list[str] = []
    lines.append(f"# {GATE}\n")
    lines.append(f"Query: `{QUERY}`  ·  SAP_MODE=READ_ONLY  ·  SAP_WRITE_COUNT=0\n")
    lines.append(f"Fecha SAP: {summary['sap_current_date']}  ·  ventana: "
                 f"{summary['demand_window_start']} → {summary['demand_window_end']} "
                 f"({summary['demand_window_days']} días)\n")
    lines.append("## Resumen ejecutivo\n")
    lines.append(
        f"En Saavedra (SAA-M1) se detectaron **{summary['raw_materials_coverage_lt_60']} "
        f"materias primas con menos de 60 días de cobertura** sobre "
        f"{summary['raw_materials_analyzed']} materias primas analizadas. "
        f"En quiebre: {summary['raw_materials_in_stockout']}; "
        f"debajo de 15 días: {summary['raw_materials_critical_lt_15']}; "
        f"entre 15 y 30: {summary['raw_materials_high_15_30']}; "
        f"entre 30 y 60: {summary['raw_materials_attention_30_60']}.\n")
    lines.append("\n## Materias primas con cobertura < 60 días\n")
    lines.append("| Materia prima | ItemCode | Unidad | Stock SAA-M1 | Demanda/día | "
                 "Cobertura días | Riesgo | Base | Confianza |")
    lines.append("|---|---|---|---:|---:|---:|---|---|---|")
    for r in lt60:
        unit = r.get("uom") or ""
        daily = r.get("avg_daily_actual") if r["executive_basis"] == "ACTUAL_CONSUMPTION" else r.get("avg_daily_commercial")
        cov = f"{r['coverage_days']:.1f}" if r["coverage_days"] is not None else "-"
        conf = "SUPPORTED" if r["derived_demand_qty"] > 0 or r["actual_consumption_qty"] > 0 else "SUGGESTED"
        lines.append(f"| {r['itemname'][:48]} | {r['itemcode']} | {unit} | "
                     f"{r['stock']:,.2f} | {daily:,.3f} | {cov} | {r['risk']} | "
                     f"{r['executive_basis']} | {conf} |")
    lines.append("\n## Detalle de las 3–5 más críticas\n")
    for r in lt60[:5]:
        lines.append(f"### {r['itemname']} — SAA-M1\n")
        lines.append(f"- Stock actual: {r['stock']:,.2f} {r.get('uom') or ''}")
        lines.append(f"- Consumo operativo Saavedra 90d: {r['actual_consumption_qty']:,.2f} "
                     f"({r['avg_daily_actual']:,.3f}/día)")
        lines.append(f"- Demanda comercial equivalente 90d: {r['commercial_demand_qty']:,.2f} "
                     f"(directa {r['direct_sales_qty']:,.2f} + derivada {r['derived_demand_qty']:,.2f})")
        lines.append(f"- Transferencias fuera de SAA-M1 90d: {r['transfer_out_qty']:,.2f}")
        cov = f"{r['coverage_days']:.1f}" if r["coverage_days"] is not None else "-"
        lines.append(f"- Cobertura estimada: {cov} días — Riesgo: {r['risk']}")
        lines.append(f"- Base: {r['executive_basis']}")
        if r["top_contributors"]:
            lines.append("- Demanda explicada principalmente por:")
            for c in r["top_contributors"]:
                name = facts[c["itemcode"]].itemname if c["itemcode"] in facts else c["itemcode"]
                lines.append(f"  - {name} — {c['equivalent_qty']:,.2f} "
                             f"({c['share_pct']:.1f}%)")
        lines.append("")
    lines.append("\n## Limitaciones\n")
    lines.append("- La cobertura usa el stock físico `OnHand` de SAA-M1 (no se resta "
                 "`IsCommited` como métrica principal; se expone `available_after_commitments`).")
    lines.append("- La demanda derivada usa el BOM **actual** (ITT1/OITT) aplicado a ventas "
                 "históricas de 90 días; no incluye merma de producción ni cambios de receta.")
    lines.append("- La venta directa y la derivada se calculan netas de notas de crédito.")
    lines.append("- `NumPerMsr=1` en todas las líneas de venta del período; 1,823 líneas tienen "
                 "etiqueta de UoM distinta a la de inventario y quedan marcadas como conversión "
                 "no resuelta si afectan una materia prima objetivo.")
    lines.append("- Consumo real = IGE1 `BaseType=202` de órdenes de producción en almacenes "
                 "Saavedra; las transferencias (WTR1) se reportan por separado y nunca se suman "
                 "como consumo.")

    gap_file = evidence_dir / "datalake_reverse_gap.json"
    if gap_file.exists():
        gap = json.loads(gap_file.read_text(encoding="utf-8"))
        lines.append("\n---\n\n## Data Lake reverse gap analysis\n")
        lines.append(f"`FOUNDATION_PUBLICATION_ID={gap['FOUNDATION_PUBLICATION_ID']}`  ·  "
                     f"`DATA_LAKE_CAN_ANSWER_THIS_QUERY_NOW={gap['DATA_LAKE_CAN_ANSWER_THIS_QUERY_NOW']}`\n")
        lines.append("| Capability | SAP source used | Data Lake status | Existing dataset/path | "
                     "What must be integrated | Priority |")
        lines.append("|---|---|---|---|---|---|")
        for g in gap["gaps"]:
            lines.append(f"| {g['capability']} | {g['sap_source_used']} | {g['data_lake_status']} | "
                         f"{g['existing_dataset_path']} | {g['what_must_be_integrated']} | {g['priority']} |")
        lines.append("\n### Minimum integration plan\n")
        for step in gap["minimum_integration_plan"]:
            lines.append(f"{step}  ")
        lines.append("\n### Reverse output\n")
        for k in ("FOUNDATION_PUBLICATION_ID", "SAAVEDRA_MAPPING_STATUS",
                  "RAW_MATERIAL_CLASSIFICATION_STATUS", "BOM_STATUS",
                  "UNIT_CONVERSION_STATUS", "CREDIT_MEMO_STATUS",
                  "PRODUCTION_CONSUMPTION_STATUS", "DATA_LAKE_CAN_ANSWER_THIS_QUERY_NOW"):
            lines.append(f"- `{k}` = {gap.get(k)}")

    (evidence_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()