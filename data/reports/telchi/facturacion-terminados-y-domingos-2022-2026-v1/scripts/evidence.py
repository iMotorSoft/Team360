"""Assemble the evidence bundle for the report (read-only inputs, no writes to sources)."""
import json
import shutil
from pathlib import Path

import duckdb

OUT = Path("/tmp/opencode/telchi-hist")
DST = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360/data/reports/telchi/"
           "facturacion-terminados-y-domingos-2022-2026-v1")
DST.mkdir(parents=True, exist_ok=True)

fm = json.load(open(OUT / "out/final_metrics.json"))
cr = json.load(open(OUT / "out/credits.json"))
ck = json.load(open(OUT / "out/checks.json"))
bs = json.load(open(OUT / "out/branch_summary.json"))
su = json.load(open(OUT / "out/successions.json"))
cw = json.load(open(OUT / "out/crosswalk_summary.json"))

lab = fm["lab_finished"]
dec = fm["decomposition"]
cr26 = [x["amt"] for x in cr["credits_2026"] if x["btype"] == "LAB_FINISHED_PRODUCT"][0]
cr22 = abs([x["amt"] for x in cr["credits_2022_sap"] if x["btype"] == "LAB_FINISHED_PRODUCT"][0])
tender = cr["tender_L02924"]["amt"]
pack = 479131.77  # verified box/pallet presentations among the unmapped legacy codes

types = {}
con = duckdb.connect()
con.execute("SET threads=2")
for bt, a22, a26 in con.execute("""
SELECT btype, sum(CASE WHEN period IN ('2022Q1','2022SAP') THEN amount ELSE 0 END),
       sum(CASE WHEN period='2026' THEN amount ELSE 0 END)
FROM read_parquet('/tmp/opencode/telchi-hist/out/facts_all.parquet') GROUP BY 1""").fetchall():
    types[bt] = {"2022": round(a22, 2), "2026": round(a26, 2),
                 "delta_pct": round((a26 / a22 - 1) * 100, 2) if a22 else None}

bundle = {
    "generado": "2026-10-22",
    "alcance": {
        "periodo_2022": "2022-01-01..2022-09-30",
        "periodo_2026": "2026-01-01..2026-09-30 (máximo disponible)",
        "fuente_2022_q1": "legacy saleProduct (2022-01-01..2022-04-05)",
        "fuente_2022_abr_sep": "SAP B1 saleSB1Product (2022-04-06..2022-09-30)",
        "fuente_2026": "Foundation CURRENT foundation_afd08d9eca6a725be53cdc3f9d5709c9, snapshot 1408",
        "metrica": "importe neto de línea en Bs, facturas activas, antes de notas de crédito",
    },
    "crosswalk": cw.get("summary") if isinstance(cw, dict) and "summary" in cw else cw,
    "totales_por_tipo": types,
    "total_2022": round(sum(v["2022"] for v in types.values()), 2),
    "total_2026": round(sum(v["2026"] for v in types.values()), 2),
    "lab_finished": {
        "skus_ambos": lab["both_skus"], "skus_solo_2022": lab["dropped_skus"],
        "skus_solo_2026": lab["new_skus"],
        "bruto_2022": round(lab["amt22"], 2), "bruto_2026": round(lab["amt26"], 2),
        "crecimiento_bruto_pct": round((lab["amt26"] / lab["amt22"] - 1) * 100, 2),
        "notas_credito_2022": round(cr22, 2), "notas_credito_2026": round(cr26, 2),
        "neto_2022": round(lab["amt22"] - cr22, 2), "neto_2026": round(lab["amt26"] - cr26, 2),
        "crecimiento_neto_pct": round(((lab["amt26"] - cr26) / (lab["amt22"] - cr22) - 1) * 100, 2),
        "base_ajustada_presentaciones_2022": round(lab["amt22"] + pack, 2),
        "crecimiento_base_ajustada_pct": round((lab["amt26"] / (lab["amt22"] + pack) - 1) * 100, 2),
        "comunes_bruto_2022": round(lab["both_amt22"], 2),
        "comunes_bruto_2026": round(lab["both_amt26"], 2),
        "comunes_delta": round(dec["delta"], 2),
        "efecto_precio": round(dec["price_effect"], 2),
        "efecto_volumen": round(dec["volume_effect"], 2),
        "efecto_precio_pct_delta": round(dec["price_effect"] / dec["delta"] * 100, 1),
        "efecto_volumen_pct_delta": round(dec["volume_effect"] / dec["delta"] * 100, 1),
        "ratio_precio_mediano": round(dec["median_ratio"], 4),
        "ratio_precio_ponderado": round(dec["weighted_ratio"], 4),
        "ratio_precio_p25": round(dec["p25_ratio"], 4),
        "ratio_precio_p75": round(dec["p75_ratio"], 4),
        "descontinuados_2022": round(lab["dropped_amt22"], 2),
        "nuevos_2026": round(lab["new_amt26"], 2),
        "churn_neto": round(lab["new_amt26"] - lab["dropped_amt22"], 2),
        "tender_licitacion_2022": tender,
        "crecimiento_sin_tender_neto_pct": round(
            ((lab["amt26"] - cr26) / (lab["amt22"] - tender - cr22) - 1) * 100, 2),
    },
    "top_2022": fm["top_2022"],
    "top_2026": fm["top_2026"],
    "mayores_cambios": fm["top_delta"],
    "anomalias": {
        "factura_3247102": cr["anomaly_3247102"],
        "licitacion_L02924": cr["tender_L02924"],
        "notas_credito_2026_total": round(sum(x["amt"] for x in cr["credits_2026"]), 2),
        "presentaciones_caja_no_mapeadas_2022": pack,
        "skus_2026_sin_nombre_maestro": [
            {"item": r[0], "amt": round(r[1], 2)}
            for r in con.execute("""
                SELECT c.item_code, c.amt26 FROM read_parquet('/tmp/opencode/telchi-hist/out/products_cmp.parquet') c
                LEFT JOIN (SELECT sap_item_code, any_value(sap_name) sap_name
                           FROM read_parquet('/tmp/opencode/telchi-hist/out/crosswalk_sap_legacy.parquet') GROUP BY 1) n
                  ON n.sap_item_code=c.item_code
                WHERE c.btype='LAB_FINISHED_PRODUCT' AND c.status='NEW_2026' AND n.sap_name IS NULL
                ORDER BY c.amt26 DESC""").fetchall()
        ],
    },
    "cobertura": ck["reconciliation"],
    "sucesiones": su["summary"],
    "skus_2026_sin_nombre_resumen": {
        "n": len([1 for r in con.execute("""
            SELECT c.item_code FROM read_parquet('/tmp/opencode/telchi-hist/out/products_cmp.parquet') c
            LEFT JOIN (SELECT sap_item_code, any_value(sap_name) sap_name
                       FROM read_parquet('/tmp/opencode/telchi-hist/out/crosswalk_sap_legacy.parquet') GROUP BY 1) n
              ON n.sap_item_code=c.item_code
            WHERE c.btype='LAB_FINISHED_PRODUCT' AND c.status='NEW_2026' AND n.sap_name IS NULL""").fetchall()]),
        "amt": round(sum(r[1] for r in con.execute("""
            SELECT c.item_code, c.amt26 FROM read_parquet('/tmp/opencode/telchi-hist/out/products_cmp.parquet') c
            LEFT JOIN (SELECT sap_item_code, any_value(sap_name) sap_name
                       FROM read_parquet('/tmp/opencode/telchi-hist/out/crosswalk_sap_legacy.parquet') GROUP BY 1) n
              ON n.sap_item_code=c.item_code
            WHERE c.btype='LAB_FINISHED_PRODUCT' AND c.status='NEW_2026' AND n.sap_name IS NULL""").fetchall()), 2),
    },
    "domingos_feriados": {
        "2026": bs["2026"],
        "domingos_comunes_2026": bs["common_sundays"],
        "feriados_2026": bs["holidays_2026"],
        "feriados_2026_total": bs["holiday_2026_total"],
        "historico": bs["old"],
    },
}
json.dump(bundle, open(DST / "datos_clave.json", "w"), indent=1, ensure_ascii=False, default=str)

# CSVs
shutil.copy(OUT / "out/domingos_feriados_2026.csv", DST / "domingos_feriados_2026.csv")
shutil.copy(OUT / "out/feriados_bolivia.csv", DST / "feriados_bolivia.csv")

con.execute("""
COPY (
 SELECT c.status, c.item_code, c.btype,
        COALESCE(c.legacy_name, n.sap_name) nombre,
        round(c.amt22,2) importe_2022_bs, round(c.amt26,2) importe_2026_bs,
        round(COALESCE(c.amt26,0)-COALESCE(c.amt22,0),2) variacion_bs,
        round(c.qty22,3) cantidad_2022, round(c.qty26,3) cantidad_2026
 FROM read_parquet('/tmp/opencode/telchi-hist/out/products_cmp.parquet') c
 LEFT JOIN (SELECT sap_item_code, any_value(sap_name) sap_name
            FROM read_parquet('/tmp/opencode/telchi-hist/out/crosswalk_sap_legacy.parquet') GROUP BY 1) n
   ON n.sap_item_code=c.item_code
 WHERE c.btype='LAB_FINISHED_PRODUCT'
 ORDER BY abs(COALESCE(c.amt26,0)-COALESCE(c.amt22,0)) DESC
) TO '""" + str(DST / "comparacion_skus_lab_finished.csv") + """' (FORMAT CSV, HEADER)
""")

# scripts
(DST / "scripts").mkdir(exist_ok=True)
for name in ["extract.py", "crosswalk.py", "coverage.py", "products.py", "successions.py",
             "checks.py", "credits.py", "final_metrics.py", "sundays.py", "branch_summary.py",
             "evidence.py"]:
    src = OUT / name
    if src.exists():
        shutil.copy(src, DST / "scripts" / name)

print("written", DST)
for p in sorted(DST.rglob("*")):
    if p.is_file():
        print(p.relative_to(DST), p.stat().st_size)
