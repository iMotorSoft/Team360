# Billing semantics

Se reutiliza el contrato financiero histórico: facturación válida y ventas netas documentales son magnitudes distintas, expuestas simultáneamente y etiquetadas.

Autoridad: [contrato financiero histórico](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/FINANCIAL_REPORTING_CONTRACT.md).

| Aspecto | Contrato seleccionado |
| --- | --- |
| Facturación válida | SALES_VALID_GROSS = SUM OINV.DocTotal con CANCELED=N |
| Notas de crédito | SALES_CREDIT_NOTES = SUM ORIN.DocTotal con CANCELED=N; importe positivo fuente |
| Ventas solicitadas | SALES_NET = facturación válida − NC; criterio oficial histórico para «Ventas de mayo» |
| Moneda | BS únicamente; sin USD, conversión ni mezcla de monedas |
| Grano | Una cabecera por (source_system, DocEntry), separada por tipo OINV/ORIN; sin join de líneas |
| Fechas | DocDate >= date_from y DocDate < date_to_exclusive; nunca fecha de cobro, actualización o ingestión |
| Cancelaciones | N exclusivamente; excluye Y y reversas C; estado publicado, no reconstrucción de anulaciones as-of histórica |
| Descuentos / impuestos | DocTotal fuente conserva el cálculo SAP; no sustituir por LineTotal, recalcular impuestos ni repartir descuentos |
| Signos | NC restada exactamente una vez; no reutilizar settlement como segunda resta |
| Cantidades | Conteos de documentos separados de unidades físicas; ranking fijo por SKU conserva límites nativos |

No se confunde facturación con pagos, reconciliación, deuda ni caja. Foundation no expone aquí VatSum/DiscSum: la fidelidad del total de cabecera es acreditada; una reconciliación fiscal separada no lo es. No se certifica cierre contable absoluto ni completitud empresarial.

Esta es una capacidad válida con restricciones explícitas, no un neto comercial por producto. Se rechazan filtros no acreditados de entidad, sucursal, canal y comparación; Calenta no puede convertir una consulta filtrada en un total global.
