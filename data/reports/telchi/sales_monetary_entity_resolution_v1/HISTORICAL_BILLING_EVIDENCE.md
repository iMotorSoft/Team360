# Historical billing evidence

La facturación no era desconocida: existen contrato financiero, informes con montos, SQL financieros originales e implementación Foundation monetaria previa. La recuperación específica distingue evidencia documental de ejecución y recepción.

## Definición recuperada

La selección reutiliza DocTotal documental y las reglas del contrato oficial, sin crear una venta neta por producto ni convertir cobros en facturación.

- [contrato financiero histórico](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/FINANCIAL_REPORTING_CONTRACT.md), versión 1.0.0 del 21/08/2026, §§2, 13 y 18: SALES_VALID_GROSS = facturas N; SALES_CREDIT_NOTES = NC N positivas; SALES_NET = diferencia. «Cuánto vendimos» corresponde a SALES_NET.
- [informe corporativo original](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/CORPORATE_SALES_FINAL_REPORT.md), 20/08/2026, §§A/J/L/P/R/S: declara monto corporativo entregado; grano DocEntry único y controles de doble conteo. No existe comprobante externo de recepción en la evidencia revisada.
- [implementación monetaria Foundation previa](../../../../SrvRestAstroLS_v1/backend/modules/telchi/datalake/executive_sales.py): SQL exacto previo con CTE invoices/credits, DocTotal DECIMAL(38,6), fechas exclusivas, moneda BS y categoría corporativa 2. ID de índice HS-d5edfa79b93bef8444. No se afirma que el texto dinámico sea el SQL literalmente ejecutado el 20/08.
- [SQL FINANCIAL-001](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/financial/invoice_contract_v1.sql) y [SQL FINANCIAL-002](../../../../SrvRestAstroLS_v1/backend/modules/telchi/investigation/sql/current/financial/credit_note_contract_v1.sql): extracción financiera original de cabeceras y campos fiscales; preservados, no ejecutados contra SAP.

## Cálculos históricos localizados

Los valores siguientes son históricos, no resultados nuevos ni prueba de aceptación individual. Las referencias permiten conservar sus universos sin fusionarlos.

| Cálculo / pregunta | Resultado original | Período y fecha declarada | Fuente / grano | Reglas y validación | Entrega / limitación |
| --- | --- | --- | --- | --- | --- |
| Ventas corporativas de agosto 2026 | facturas 1.516.859,75; NC 45.889,46; neto 1.470.970,29; 376 facturas / 7 NC | MTD 01/08–20/08, informe 20/08/2026; timestamp fino y exclusividad del día final no acreditados | OINV, ORIN, OSLP; DocEntry; categoría vendedor 2 | N; NC restadas una vez; descuentos incluidos en DocTotal según §J; impuestos no desglosados; §S declara unicidad y controles | §A declara delivered; sin acuse externo. Original usa símbolo $, no codifica DocCur; no inferir USD. BS explícito en implementación ejecutiva posterior |
| Luz, mismo informe | 220.870,83 facturas − 4.594,66 NC = 216.276,17 | mismo MTD | SlpCode 13 / cabecera | misma definición, no canal transaccional | misma declaración de informe, no aceptación individual demostrada |
| Vendedores corporativos, mismo informe | Selva 741.459,63; Heglin 332.673,79; Diego 180.560,70 netos | mismo MTD | SlpCode 11/139/236 | suman con Luz el neto corporativo; no total compañía | no ampliar a venta horizontal |
| Corporativo agosto 2022, §H | Federico 2.310.292,86; Selva 2.301.950,88; Kaly 454.814,92; Luz 698.029,55 DocTotal | agosto 2022, revisión del 20/08/2026 | Parquet histórico; informe muestra rows | NC/impuestos/moneda/grano de agregado 2022 no suficientemente acreditados | no seleccionado para implementación ni certificado por ausencia de reclamos |
| Agosto mensual directo / productos / clientes / almacenes | registro histórico EXACT, Quantity y LineTotal | agosto y otras ventanas del registry, cutoff histórico 15/09/2026 | líneas DocEntry+LineNum | sin filtro universal de cancelación ni NC; SUM Quantity multi-SKU no es unidad física | operación ejecutada, no evidencia automática de entrega; no sustituye DocTotal |
| Ejecutivo septiembre / venta horizontal | SQL ejecutivo y clasificación de series existentes | función parametrizada; rótulo septiembre no prueba ejecución | Foundation, DocTotal; clasificación distinta de categoría vendedor | no fusionar atributo vendedor, canal de cliente y canal transaccional | no se recuperó un monto septiembre entregado verificable en esta búsqueda focalizada |

El artefacto externo `investigation-consolidation-v1/files/validation/corporate_sales/august_2026_corporate_sales.json` conserva esos resultados y la fecha declarada. El directorio histórico `TELCHI_DATALAKE_EXECUTIVE_SALES_FOUNDATION_V1` estaba vacío al inspeccionarlo: sus referencias de índice no se transforman en resultados disponibles.

## Aceptación y fidelidad

La declaración expresa del responsable se conserva como evidencia contextual: Telchi recibió informes monetarios y no reclamó. No se atribuye automáticamente esa ausencia de reclamos a cada cifra anterior.

SQL existente, resultados declarados, validación declarada, entrega declarada, utilización contextual y reconciliación nueva son niveles distintos. Falta recuperar el SQL agregado literalmente ejecutado para el informe corporativo y comprobantes externos, si existen. HISTORICAL_BILLING_RECOVERY=PARTIAL; la definición documental seleccionada sí está explícita y se verifica técnicamente ahora.

La recuperación usó los CSV/índices ya existentes y los reportes de activation/RBAC. No se repitió la auditoría de 4.186 archivos, no se ejecutó SAP ni se inventó otra métrica.
