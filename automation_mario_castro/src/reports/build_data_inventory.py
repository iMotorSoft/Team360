from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import inspect_path  # noqa: E402
from excel.analyze_workbook import classify_source, extract_kpis, inspect_workbook  # noqa: E402


def _artifact_status(filename: str) -> str:
    path = inspect_path(filename)
    return "generado" if path.exists() and path.stat().st_size else "no ejecutado"


def main() -> None:
    workbook = inspect_workbook()
    kpis = [
        {
            **kpi,
            "source": classify_source(kpi["kpi"], kpi["area"]),
        }
        for kpi in extract_kpis(workbook)
    ]

    inventory = {
        "excel": {
            "sheets": [
                {
                    "name": sheet["name"],
                    "dimension": sheet["dimension"],
                    "formula_count": sheet["formula_count"],
                }
                for sheet in workbook["sheets"]
            ],
            "kpis": kpis,
        },
        "kommo": {
            "login_status": "no ejecutado",
            "screens_inspected": [
                {"name": "dashboard", "status": _artifact_status("kommo_dashboard.txt")},
                {"name": "leads", "status": _artifact_status("kommo_leads.txt")},
                {"name": "pipeline", "status": _artifact_status("kommo_pipeline.txt")},
                {"name": "whatsapp", "status": _artifact_status("kommo_whatsapp.txt")},
            ],
            "data_candidates": [
                "leads",
                "respondieron",
                "reuniones",
                "visitas",
                "negociaciones",
                "cierres",
                "perdidos",
                "asesor asignado",
                "fuente",
                "proyecto/desarrollo",
                "facturación si existe valor de operación",
            ],
        },
        "facebook": {
            "login_status": "no ejecutado",
            "pages_inspected": [
                {"url": "https://www.facebook.com/Mariocastroremax", "status": _artifact_status("facebook_pages.txt")},
                {"url": "https://www.facebook.com/profile.php?id=100090112818347", "status": _artifact_status("facebook_pages.txt")},
            ],
            "data_candidates": [
                "mensajes entrantes",
                "fecha",
                "nombre/contacto",
                "página de origen",
                "estado de respuesta",
            ],
        },
        "meta_ads": {
            "access_status": _artifact_status("facebook_ads_manager.txt"),
            "download_available": None,
            "data_candidates": [
                "campaña",
                "inversión",
                "impresiones",
                "clics",
                "CTR",
                "CPC",
                "leads",
                "CPL",
                "período",
                "proyecto",
                "formato",
            ],
        },
        "risks": [
            "2FA/captcha puede requerir intervención humana en primer login.",
            "Permisos de Facebook/Meta pueden ser solo visuales o incompletos.",
            "Cambios de UI pueden romper selectores; priorizar descargas CSV/XLSX cuando existan.",
            "Kommo requiere campos estructurados y nombres consistentes de etapa/fuente/proyecto.",
            "Meta Ads requiere nomenclatura consistente de campañas para mapear proyecto y formato.",
        ],
        "recommended_mvp": [
            "Extraer desde Kommo leads, asesores, etapa, fuente y proyecto.",
            "Descargar reporte de Ads Manager con campaña, inversión, impresiones, clics y leads.",
            "Cruzar por período, fuente/proyecto/campaña y calcular conversiones localmente.",
            "Volcar resultados en una copia del Excel base sin alterar la plantilla original.",
        ],
    }

    output = inspect_path("data_inventory.json")
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[report] inventario guardado: {output}")


if __name__ == "__main__":
    main()
