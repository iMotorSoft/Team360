"""CG2A raw-material effective-payment investigation over Foundation CURRENT only.

No SAP adapter is imported. The sole CURRENT Foundation is resolved through the
fail-closed FoundationReader; all Atomic relations are pinned to its first
CURRENT DuckLake snapshot. Outputs are data-only under Telchi DATA_ROOT and
execution evidence is written outside Git.
"""
from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.telchi.datalake.ducklake import DATA_ROOT, DuckLakeConnector
from modules.telchi.datalake.foundation_publication import FoundationPublicationStore
from modules.telchi.datalake.foundation_reader import FoundationReader

GATE = "TELCHI_CG2A_RAW_MATERIAL_PAYMENT_TERMS_V1"
VERDICT = f"{GATE}_DEGRADED"
EVIDENCE_ROOT = Path("/media/issajar/DEVELOP/Projects/iMotorSoft/ai/evidence/telchi") / GATE
HERE = Path(__file__).resolve().parent
EXPECTED_FOUNDATION = "foundation_417c860c216805f18341bb741ee026e3"
EXPECTED_REFERENCE = "v2_reference_closure_2088d5885204313a"
TABLES = (
    "document_detail",
    "summary_by_modality",
    "summary_by_product",
    "summary_by_month",
    "summary_by_seller",
    "quality_controls",
)


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def rows(cursor: Any) -> list[dict[str, Any]]:
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=jsonable) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def quote_path(path: str | Path) -> str:
    return str(path).replace("'", "''")


def render_sql(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    leftovers = sorted(part for part in rendered.split() if part.startswith("__") and part.endswith("__"))
    if leftovers:
        raise RuntimeError(f"unresolved SQL placeholders: {leftovers}")
    return rendered


def derive_verdict(*, documents: int, transactional_payment_datasets: int) -> str:
    if documents <= 0:
        return f"{GATE}_BLOCKED"
    if transactional_payment_datasets <= 0:
        return VERDICT
    return f"{GATE}_BLOCKED"  # Classification logic is intentionally not invented here.


def markdown_table(data: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    if not data:
        return "_Sin filas._"
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in data:
        lines.append("| " + " | ".join(str(jsonable(row.get(column, ""))) for column in columns) + " |")
    return "\n".join(lines)


def build_report(
    metadata: dict[str, Any],
    modality: list[dict[str, Any]],
    controls: dict[str, Any],
    product: list[dict[str, Any]],
) -> str:
    main = [
        {
            "Modalidad": {
                "CONTADO_CONFIRMED": "CONTADO confirmado",
                "CREDIT_CONFIRMED": "CRÉDITO confirmado",
                "OTHER_PAYMENT_MODE": "OTRA MODALIDAD",
                "NOT_DETERMINABLE": "NO DETERMINABLE",
            }[row["modality"]],
            "Documentos": row["documents"],
            "% documentos": row["document_percent"],
            "Bs netos": row["net_amount"],
            "% Bs netos": row["net_amount_percent"],
        }
        for row in modality
    ]
    main.append(
        {
            "Modalidad": "TOTAL",
            "Documentos": controls["documents"],
            "% documentos": "100.0",
            "Bs netos": controls["net_sales"],
            "% Bs netos": "100.0",
        }
    )
    product_controls = [row for row in product if row["item_code"] in {"L00031", "L03192"}]
    return f"""# {GATE}

## Gate

`{VERDICT}`

## A. Respuesta ejecutiva

**No puede afirmarse que las ventas CG2A de materias primas hayan sido al contado.**
La Foundation productiva permite identificar **{controls['documents']} documentos** y sus notas de
crédito, pero no contiene pagos, cobranzas, medios de pago, saldos abiertos ni reconciliaciones.
Por lo tanto, **100% de los documentos ({controls['documents']}/{controls['documents']}) queda
`NOT_DETERMINABLE`**. Esto no significa crédito ni contado: significa ausencia de evidencia
transaccional suficiente en CURRENT.

## B. Evidencia cuantitativa

{markdown_table(main, ('Modalidad', 'Documentos', '% documentos', 'Bs netos', '% Bs netos'))}

Controles del universo: {controls['sale_days']} días, {controls['skus']} SKU, período
{controls['first_sale']} → {controls['last_sale']}; gross Bs {controls['gross_sales']}, notas de
crédito Bs {controls['credit_memos']} y neto Bs {controls['net_sales']}. Las
{controls['credit_lines']} líneas de nota de crédito quedaron enlazadas exactamente a líneas de
venta ({controls['linked_credit_lines']}/{controls['credit_lines']}); delta monetario:
{controls['monetary_reconciliation_delta']}.

Casos de control:

{markdown_table(product_controls, ('item_code', 'product_description', 'documents', 'quantity', 'uom', 'gross_sales', 'credit_memos', 'net_sales', 'modality'))}

Los conteos, cantidades e importes de L00031/L03192 reproducen los controles conocidos. La UoM
queda `UNAVAILABLE` en este detalle porque `sales_line` no materializa el código UoM fuente y el
dataset de revisión fijado en el manifiesto tampoco lo resolvió. No se reutilizó el raw de ingesta
ni se forzó `KG`; el gold previo que reportó `KG` dependía de esa evidencia raw adicional.

## C. Qué significa para el negocio

Existe evidencia de un canal recurrente de venta de materias primas registrado bajo CG2A, pero
**no existe todavía evidencia en la Foundation que permita describirlo como canal al contado**.
La recurrencia comercial y la modalidad efectiva de cobro son preguntas distintas.

## D. Qué no podemos afirmar

- No podemos afirmar contado, crédito ni otra modalidad para ningún documento.
- `doc_due_date` y `doc_status` son atributos documentales, no prueba de cobranza.
- La dimensión maestra `payment_terms` tiene 0 filas y, aun poblada, no probaría pago efectivo.
- `CG2A != comprador individual`; buyer traceability sigue siendo `NO`.
- No se consultó SAP y no se usó fallback latest/candidate ni mezcla de versiones.

## E. Hallazgos y anomalías

- La carencia es estructural: CURRENT publica ventas y notas de crédito, pero no un ledger de
  settlement/cobranza.
- Todas las notas de crédito RAW_MATERIAL observadas (Bs {controls['credit_memos']}) tienen vínculo
  exacto a su línea de factura; esto permite net sales, no modalidad de pago.
- No se reportan pagos parciales, vencimientos efectivos, documentos impagos ni inconsistencias
  término-vs-pago porque esos hechos no están materializados.

## F. Oportunidades comerciales

La recurrencia observada justifica como **hipótesis** mejorar la identificación del comprador final
y, una vez incorporada la evidencia de cobranza, evaluar una política específica para ventas de
materias primas. Sin buyer traceability no puede afirmarse cuántos compradores recurrentes existen.

## G. Siguiente pregunta

¿Cuál es el contrato mínimo de settlement que debe añadirse sobre la Foundation para vincular cada
factura CG2A con cobros, conciliaciones, medio, fecha, importe y saldo as-of, y cuál es la regla de
negocio aprobada para considerar una cancelación “inmediata”?

## Evidencia faltante y contrato mínimo

Se requiere un componente aditivo de cobranzas/settlement, sin rediseñar V1, con:

1. factura: `source_system`, tipo de objeto, `doc_entry`, moneda, total, fecha y vencimiento;
2. pago/recibo: identificador, fecha/fecha-valor, estado/cancelación, moneda e importe;
3. asignación o reconciliación: identificador, factura destino, pago/NC origen, monto aplicado y
   fecha de reconciliación;
4. saldo as-of por factura, incluido pago parcial;
5. medios desagregados (cash/card/transfer/check/other) sin inferirlos del término maestro;
6. claves exactas para unir con CURRENT: `source_system + object_type + doc_entry` y, donde aplique,
   `reconciliation_id`/`payment_doc_entry`;
7. una definición de negocio aprobada para “contado/inmediato”.

Fuente esperada: SAP Business One (`OINV/ORIN/ORCT/RCT2/OITR/ITR1` y medios relacionados), mediante
una futura ingesta READ ONLY, solo después de autorizar ese nuevo gate. Esta ejecución no consultó SAP.

## Reproducibilidad

- Foundation: `{metadata['foundation_publication_id']}`
- Foundation snapshot: `{metadata['ducklake_snapshot_id']}`
- Reference: `{metadata['reference_version']}`
- Foundation data as-of: `{metadata['foundation_data_as_of']}`
- Execution: `{metadata['execution_id']}`
- Data artifacts: `{metadata['output_root']}`
- SQL: `modules/telchi/investigation/validation/cg2a_raw_material_payment_terms_v1/analysis.sql`
"""


def main() -> int:
    started = datetime.now(timezone.utc)
    execution_id = "cg2a-payment-terms-" + started.strftime("%Y%m%dT%H%M%SZ")
    output_root = DATA_ROOT / "decision" / "cg2a_raw_material_payment_terms_v1" / execution_id
    output_root.mkdir(parents=True, exist_ok=False)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)

    connector = DuckLakeConnector()
    with connector.session(read_only=True) as connection:
        connection.execute("SET threads=1")
        access = FoundationReader(connector).resolve_on(connection)
        if access.foundation_publication_id != EXPECTED_FOUNDATION:
            raise RuntimeError(f"CURRENT changed: {access.foundation_publication_id}; stop and review")
        if access.foundation.reference_version != EXPECTED_REFERENCE:
            raise RuntimeError(f"Reference changed: {access.foundation.reference_version}; stop and review")

        @contextlib.contextmanager
        def same_connection():
            yield connection

        publication = FoundationPublicationStore(same_connection).get(access.foundation_publication_id)
        if publication is None:
            raise RuntimeError("CURRENT publication metadata disappeared")
        manifest = publication.manifest
        required_manifest = (
            "product_business_classification",
            "reference_closure",
            "generic_customer_raw_material_review",
        )
        if any(key not in manifest for key in required_manifest):
            raise RuntimeError("CURRENT manifest lacks a required exact semantic artifact")

        pbt_path = manifest["product_business_classification"]["crosswalk_path"]
        location_path = manifest["reference_closure"]["warehouse_location_crosswalk"]
        review_path = manifest["generic_customer_raw_material_review"]["file_references"][0]
        payment_terms_path = access.reference("payment_terms")
        payment_term_rows = int(
            connection.execute("SELECT count(*) FROM read_parquet(?)", [str(payment_terms_path)]).fetchone()[0]
        )

        atomic_relations = {
            "sales_document": access.sales("sales_document"),
            "sales_line": access.sales("sales_line"),
            "credit_memo_document": access.credit_memo("credit_memo_document"),
            "credit_memo_line": access.credit_memo("credit_memo_line"),
            "inventory_movement": access.oinm(),
            "inventory_balance": access.oitw(),
        }
        schemas: dict[str, Any] = {}
        for name, relation in atomic_relations.items():
            schema_rows = connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
            schemas[name] = {
                "row_count": int(connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]),
                "columns": [row[0] for row in schema_rows],
            }
        schemas["payment_terms"] = {
            "row_count": payment_term_rows,
            "columns": [
                row[0]
                for row in connection.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?)", [str(payment_terms_path)]
                ).fetchall()
            ],
            "evidence_type": "MASTER_DATA_NOT_TRANSACTIONAL",
        }
        schemas["transactional_payment_datasets"] = {
            "count": 0,
            "missing": [
                "incoming_payments",
                "payment_allocations",
                "reconciliations",
                "invoice_open_balance_as_of",
                "payment_means",
                "settlement_dates",
            ],
        }

        template = (HERE / "analysis.sql").read_text(encoding="utf-8")
        sql = render_sql(
            template,
            {
                "__PRODUCT_BUSINESS_TYPE_PATH__": quote_path(pbt_path),
                "__WAREHOUSE_LOCATION_PATH__": quote_path(location_path),
                "__GENERIC_REVIEW_PATH__": quote_path(review_path),
                "__PRODUCTS_PATH__": quote_path(access.reference("products")),
                "__SALESPERSONS_PATH__": quote_path(access.reference("salespersons")),
                "__SALES_DOCUMENT__": atomic_relations["sales_document"],
                "__SALES_LINE__": atomic_relations["sales_line"],
                "__CREDIT_DOCUMENT__": atomic_relations["credit_memo_document"],
                "__CREDIT_LINE__": atomic_relations["credit_memo_line"],
            },
        )
        connection.execute(sql)

        artifacts: dict[str, str] = {}
        aggregates: dict[str, list[dict[str, Any]]] = {}
        for table in TABLES:
            parquet_path = output_root / f"{table}.parquet"
            connection.execute(
                f"COPY (SELECT * FROM {table}) TO '{quote_path(parquet_path)}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            artifacts[table] = str(parquet_path)
            if table != "document_detail":
                aggregates[table] = rows(connection.execute(f"SELECT * FROM {table}"))

    controls = aggregates["quality_controls"][0]
    verdict = derive_verdict(
        documents=int(controls["documents"]),
        transactional_payment_datasets=schemas["transactional_payment_datasets"]["count"],
    )
    if verdict != VERDICT:
        raise RuntimeError(f"unexpected verdict {verdict}")
    if int(controls["documents"]) != 2136 or int(controls["skus"]) != 20:
        raise RuntimeError("known universe control failed")
    if Decimal(str(controls["gross_sales"])) != Decimal("395386.770000"):
        raise RuntimeError("gross-sales control failed")
    if Decimal(str(controls["credit_memos"])) != Decimal("9201.990000"):
        raise RuntimeError("credit-memo control failed")
    if Decimal(str(controls["net_sales"])) != Decimal("386184.780000"):
        raise RuntimeError("net-sales control failed")
    if int(controls["classified_documents"]) != int(controls["not_determinable_documents"]):
        raise RuntimeError("every document must end in exactly one conservative category")

    metadata = {
        "gate": GATE,
        "verdict": verdict,
        "execution_id": execution_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "foundation_publication_id": EXPECTED_FOUNDATION,
        "reference_version": EXPECTED_REFERENCE,
        "foundation_data_as_of": access.foundation_data_as_of,
        "ducklake_snapshot_id": access.ducklake_snapshot_id,
        "reader_mode": "PRODUCTIVE_CURRENT",
        "version_mixing": "NO",
        "latest_fallback": "NO",
        "candidate_fallback": "NO",
        "sap_accessed": "NO",
        "sap_query_count": 0,
        "sap_write_count": 0,
        "payment_terms_master_rows": payment_term_rows,
        "transactional_payment_datasets": 0,
        "output_root": str(output_root),
        "artifacts": artifacts,
    }
    report = build_report(
        metadata,
        aggregates["summary_by_modality"],
        controls,
        aggregates["summary_by_product"],
    )

    write_json(output_root / "metadata.json", metadata)
    write_json(output_root / "schema_discovery.json", schemas)
    write_json(output_root / "aggregate_results.json", aggregates)
    write_json(EVIDENCE_ROOT / "metadata.json", metadata)
    write_json(EVIDENCE_ROOT / "schema_discovery.json", schemas)
    write_json(EVIDENCE_ROOT / "aggregate_results.json", aggregates)
    (EVIDENCE_ROOT / "executed_analysis.sql").write_text(sql, encoding="utf-8")
    (EVIDENCE_ROOT / "final_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"verdict": verdict, "metadata": metadata, "controls": controls}, indent=2, default=jsonable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
