from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import EXCEL_PATH, inspect_path  # noqa: E402


NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> tuple[str, str]:
    cell_type = cell.attrib.get("t")
    inline = cell.find("m:is", NS)
    value_node = cell.find("m:v", NS)
    formula_node = cell.find("m:f", NS)
    formula = formula_node.text or "" if formula_node is not None else ""

    value = ""
    if cell_type == "inlineStr" and inline is not None:
        value = "".join(text.text or "" for text in inline.findall(".//m:t", NS))
    elif value_node is not None:
        value = value_node.text or ""
        if cell_type == "s" and value.isdigit():
            index = int(value)
            if index < len(shared_strings):
                value = shared_strings[index]
    return value, formula


def _column(cell_ref: str) -> str:
    return re.sub(r"\d+", "", cell_ref)


def _load_shared_strings(workbook_zip: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook_zip.namelist():
        return []
    root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.findall(".//m:t", NS))
        for item in root.findall("m:si", NS)
    ]


def inspect_workbook(path: Path = EXCEL_PATH) -> dict:
    with zipfile.ZipFile(path) as workbook_zip:
        shared_strings = _load_shared_strings(workbook_zip)
        workbook = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        rels = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        sheets = []
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = rel_targets[rel_id]
            sheet_path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            worksheet = ET.fromstring(workbook_zip.read(sheet_path))
            dimension_node = worksheet.find("m:dimension", NS)
            dimension = dimension_node.attrib.get("ref", "") if dimension_node is not None else ""

            rows = []
            formulas = []
            for row in worksheet.findall("m:sheetData/m:row", NS):
                cells = {}
                for cell in row.findall("m:c", NS):
                    ref = cell.attrib.get("r", "")
                    value, formula = _cell_value(cell, shared_strings)
                    if value or formula:
                        cells[_column(ref)] = {
                            "ref": ref,
                            "value": value,
                            "formula": formula,
                        }
                    if formula:
                        formulas.append({"cell": ref, "formula": formula})
                if cells:
                    rows.append({"row": int(row.attrib["r"]), "cells": cells})

            sheets.append(
                {
                    "name": name,
                    "dimension": dimension,
                    "rows": rows,
                    "formula_count": len(formulas),
                    "formulas": formulas,
                }
            )
    return {"path": str(path), "sheets": sheets}


def extract_kpis(workbook: dict) -> list[dict]:
    catalog = next((sheet for sheet in workbook["sheets"] if sheet["name"] == "KPIs CEO Proyectos"), None)
    if not catalog:
        return []

    kpis = []
    for row in catalog["rows"]:
        number = row["cells"].get("A", {}).get("value", "")
        area = row["cells"].get("B", {}).get("value", "")
        name = row["cells"].get("C", {}).get("value", "")
        if not number.isdigit() or not name:
            continue
        kpis.append({"number": int(number), "area": area, "kpi": name})
    return kpis


def classify_source(kpi: str, area: str) -> str:
    text = f"{area} {kpi}".lower()
    if any(token in text for token in ["fuente", "facebook", "whatsapp"]):
        return "Kommo / Facebook Page-Inbox / Meta Ads"
    if any(token in text for token in ["inversión", "ctr", "cpc", "cpl", "pauta", "campaña", "formato", "marketing", "meta ads"]):
        return "Meta Ads"
    if any(token in text for token in ["conversión", "ranking", "costo", "diferencia", "cac", "roi", "ticket promedio"]):
        return "Cálculo local"
    if any(token in text for token in ["lead", "respondieron", "reuniones", "visitas", "negociaciones", "cierres", "perdidos", "asesor", "seguimientos", "facturación", "objetivo"]):
        return "Kommo"
    return "Manual / no definido"


def main() -> None:
    workbook = inspect_workbook()
    kpis = extract_kpis(workbook)
    inventory = {
        "excel": {
            "path": workbook["path"],
            "sheets": [
                {
                    "name": sheet["name"],
                    "dimension": sheet["dimension"],
                    "formula_count": sheet["formula_count"],
                }
                for sheet in workbook["sheets"]
            ],
            "kpis": [
                {
                    **kpi,
                    "source": classify_source(kpi["kpi"], kpi["area"]),
                }
                for kpi in kpis
            ],
        }
    }
    output = inspect_path("excel_inventory.json")
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[excel] inventario guardado: {output}")
    print(json.dumps(inventory["excel"]["sheets"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
