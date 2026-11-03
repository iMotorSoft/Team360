# Contrato contable offline V1

Diseño investigativo subordinado a [CONTEXT](../../../CONTEXT.md). No es una publicación, reader runtime, permiso registrado ni capability del asistente. SQL reproducible en `accounting_queries.py`; fixtures sintéticas en `test_accounting_queries.py`.

## Fuentes y reutilización

Primero se reutilizan Atomic, contratos históricos y readers canónicos; no se construye una segunda arquitectura financiera.

- Foundation actual: resolver `FoundationReader` y fijar publicación, snapshot de datos y snapshot de derivación por separado. Nunca usar latest Atomic en un consumidor productivo.
- `receivable_document` en snapshot de derivación 1322 contiene `transaction_id` procedente de OINV.TransId y `branch_id` procedente de OINV.BPLId. Su `source_table` real es **OINV+INV6**, no OINV. Es lineage investigativo reutilizable, no una API contable habilitada.
- Reutilizar `investigation/atomic/accounting.py` para trazabilidad ORCT cuando corresponda; ese contrato de caja no demuestra la relación OINV/OJDT.
- `financial_foundation/structure_discovery_v1.json` acredita nombres de columnas al 08/09/2026. Su perfil real usa TransType=30 para asientos; otra entrada histórica del inventario dice 59. **No reutilizar esa clasificación contradictoria**: 59 tiene CreatedBy distinto de TransId en el perfil. Tipo 30 tampoco prueba captura humana: acreditar DataSource, origen, reversas y automatizaciones.
- OACT legacy tiene 523 filas; no sustituye el maestro HANA histórico de 824 cuentas ni un catálogo publicado vigente.

## Extracción mínima pendiente

Este es un contrato de captura futuro, no autorización para ejecutarlo. La primera operación autorizada deberá comprobar metadata, tipos, nulos y configuración; no ejecutar SQL con nombres supuestos.

| Fuente | Clave / selección mínima | Columnas necesarias y estado local |
| --- | --- | --- |
| OJDT | company/schema + TransId; todos los IDs vinculados a documentos objetivo y todos los asientos del período del Mayor | Confirmadas históricamente: TransId, RefDate, TaxDate, DueDate, TransType, BaseRef, CreatedBy, DataSource, StornoToTr, AutoStorno. Incluir Memo, Ref1, Ref2 y monedas/totales sólo tras cotejar metadata. **BPLId no está en el schema OJDT histórico**: no inventar sucursal de cabecera. |
| JDT1 | company + TransId + Line_ID; TODAS las líneas de cada asiento seleccionado, sin filtros por cuentas ni dimensiones al extraer | Confirmadas: TransId, Line_ID, Account, Debit, Credit, SYSDeb, SYSCred, FCDebit, FCCredit, FCCurrency, ShortName, RefDate, TaxDate, DueDate, BaseRef, TransType, ProfitCode, OcrCode2, OcrCode3, OcrCode4, OcrCode5, BPLId. Añadir LineMemo y campos de distribución sólo con metadata. No suponer OcrCode de primera dimensión en JDT1: el campo observado es ProfitCode. |
| OACT | company + AcctCode; cuentas referidas y ancestros de jerarquía | AcctCode, AcctName, FatherNum, GroupMask, ActCurr, Postable; tipos y flags desde schema histórico. La naturaleza/presentación exige validación contable, no inferencia por nombre. CurrTotal actual NO es apertura histórica. |
| OINV / ORIN | company + object_type + DocEntry; claves explícitas, series y cancelaciones | DocEntry, DocNum, Series, TransId, BPLId, CardCode, DocDate, TaxDate, DocDueDate, CANCELED, DocCur, DocTotal y bases monetarias verificadas. Reutilizar mapping OINV Atomic acreditado; ORIN.TransId falta en Foundation. No cruzar por DocNum/BaseRef/importes/fechas. |
| INV1 / RIN1 | company + object_type + DocEntry + LineNum | Reutilizar líneas existentes para ItemCode y WhsCode. Capturar dimensiones comerciales sólo después de metadata; son distintas de las contables. No multiplicar líneas JDT1 por join directo N:N con líneas comerciales. |
| OCRD | company + CardCode | Maestro actual con lineage; ShortName sólo es socio cuando tiene match acreditado, no siempre. Mantener cliente facturado separado de comprador final y clasificación comercial. |
| OBPL | company + BPLId | Existencia histórica verificada; **0 registros** en evidencia RRHH del 10/09/2026. No prueba sucursales habilitadas. Capturar código/nombre/configuración únicamente si realmente existen. |
| Dimensiones | metadata primero; ODIM / OPRC / OOCR / OCR1 son candidatos, no schemas acreditados | Determinar si ProfitCode/OcrCode2..5 son centros directos o reglas de distribución. Obtener dimensión, código, vigencia, centros, pesos/base de reparto y versiones efectivas. No distribuir importes sin probar regla, denominador y redondeo. Conservar regla raw y residuo. |
| Configuración monetaria y períodos | metadata primero; OADM / OFPR y configuración aplicable | Monedas local/sistema, precisión, ejercicio, aperturas/cierres y reglas efectivas. No deducir moneda contable de DocCur o FCCurrency. |
| Oficina empresarial | crosswalk aprobado y efectivo | company + tipo de unidad + código fuente + valid_from/valid_to + evidencia + aprobador; relación con sucursal, dimensión o depósito sólo si la organización la acredita. |

Cada extracción requiere manifest con schema/version/hash, extractor y SQL parametrizado exacto, filtros, claves solicitadas/devueltas/ausentes, fechas, snapshot o ventana consistente de origen, moneda/base, precision, counts y cobertura. Sin credenciales. Segmentación bounded y reanudable; no LIMIT silencioso ni truncamiento. No volcar tablas completas innecesariamente.

Para septiembre debe declararse el año. La captura de movimientos usa RefDate en `[AAAA-09-01, AAAA-10-01)` y añade los asientos explícitos de facturas objetivo fuera de esa ventana. Las cabeceras y todas sus líneas deben capturarse coherentemente; registrar modificaciones tardías y revalidar si cambian.

La apertura necesita un saldo certificado al inicio, por cuenta, sucursal y dimensión solicitadas, **en la misma base/moneda y alcance autorizado**. Alternativa: historial íntegro hasta inicio más origen/apertura probado. Nunca asumir cero por ausencia de registros. No sumar apertura certificada e historial previo dos veces. Conservar asientos de apertura, cierre y reversa; una vista de resultados puede excluirlos sólo mediante contrato distinto.

## Dataset Diario

El grano fuente se mantiene como company + TransId + Line_ID. Las proyecciones monetarias añaden base y moneda sin reemplazar el registro original.

- Mantener fecha contable, documental y vencimiento separadas; referencias, origen y reversas originales.
- Mantener cuenta y descripción con versión del plan, ShortName raw y socio acreditado opcional.
- `documentary_branch_id`, `accounting_branch_id`, `dimension1..5`, depósito de línea comercial y `office_id` son campos independientes. UNKNOWN explícito; no coalesce entre ellos.
- Cada importe conserva Decimal exacto, escala, base LOCAL/SYSTEM/FOREIGN y currency. No convertir ni sumar monedas/bases.
- Las dimensiones raw pueden ser reglas; `dimension1` NO significa automáticamente centro de costo final. El reparto acreditado se guarda aparte con grano línea + dimensión + centro + vigencia, importe asignado y residuo. No atribuir automáticamente el importe completo a cada dimensión como si fueran particiones sumables.
- Débitos/créditos se concilian por asiento en LOCAL y SYSTEM con precisión de origen acreditada. FOREIGN se analiza por moneda: no presumir que todos los asientos multimoneda balancean cada moneda extranjera aisladamente. Explicar diferencias y asientos de conversión, no descartarlos.
- Un asiento balanceado no demuestra por sí solo correspondencia correcta factura/asiento. Acreditar FK, tipo de objeto/origen, cardinalidad, cuenta de control, impuestos, descuentos, anticipos y reversas antes de conciliar el total comercial. No sumar todos los débitos y declararlos importe de factura.

## Mayor y saldos

El contrato SQL preserva movimientos y produce saldo firmado débito menos crédito. La presentación empresarial aplica después la naturaleza acreditada de la cuenta.

`saldo_final_firmado = apertura_firmada + débitos - créditos`. Para cuenta de presentación acreedora se invierte el signo sólo si la convención está acreditada. Sin apertura válida se entregan movimientos verificables y saldos NULL, no cero ni cierre certificado.

`LEDGER` agrupa por sucursal explícita de línea; NULL es imputación desconocida, no Casa Matriz. Mantiene sucursales con apertura pero sin movimientos. La evolución mensual repite ventanas contiguas con aperturas acreditadas o cierre acreditado del período anterior. Por centro requiere apertura con ese mismo grano; la consulta de sucursal no habilita ese saldo.

## Prerrequisitos de ejecución

Las consultas de investigación no implementan permisos ni equivalen a un reader productivo; el futuro adapter debe reutilizar el mecanismo Team360 antes de leer datos.

1. Resolver identidad Console vigente, tenant, workspace y módulo con `authorization.allowed` del handler existente; revalidar permisos efectivos en cada consulta/continuación. Ninguna llamada al intérprete debe revelar datos antes de autorización.
2. Validar compañía, publicación y snapshots exactos, cobertura del período, claves únicas/no nulas, ausencia de líneas/cuentas huérfanas y descripción de campos vigente.
3. Validar igualdad del conjunto de líneas recibido frente a las líneas originales. No acreditar balance sólo sobre una selección parcial de cuentas; verificar el asiento íntegro en gate privilegiado autorizado, sin filtrar ni revelar líneas ajenas.
4. Exigir unicidad de apertura por cuenta/base/moneda/branch NULL-safe, fecha y scope; cobertura de movimientos certificada aparte. `balance_accredited` del SQL significa **apertura encontrada en fixture**, no certificación real integral.
5. Resolver DocNum a clave real company+object_type+series+DocEntry. Ante ambigüedad preguntar; no elegir primera coincidencia. Detalle documental y contabilidad requieren permisos independientes.
6. Aplicar alcance por cuenta/sucursal/dimensiones antes de exponer detalle y agregados; prohibir inferencias por diferencias entre agregados autorizados y no autorizados. No filtrar las líneas de un asiento y declarar balance completo.
7. Fijar límites/paginación completos y procedencia. Sin fallback al latest, raw o investigación desde runtime.

## Permisos propuestos

Los nombres siguientes son un diseño pendiente; no se registraron, otorgaron ni validaron contra identidades empresariales reales.

- `telchi.accounting.journal.read.v1`: Diario y líneas contables.
- `telchi.accounting.ledger.read.v1`: Mayor y saldos autorizados.
- `telchi.accounting.document_trace.read.v1`: documento a asiento; además del permiso de detalle comercial existente.
- `telchi.accounting.branch_analysis.read.v1`: desgloses por sucursal/dimensiones autorizadas.
- Separar restricciones de cuentas, agregado y detalle dentro del mecanismo vigente. Si el resolver actual no expresa esas restricciones, bloquear habilitación y coordinar extensión; no resolverlas mediante un booleano casero.
- Presidencia conserva únicamente lectura empresarial realmente autorizada. No hay equivalencia con FULL_ACCESS técnico y esta tarea no asigna ninguno.

## Pruebas empresariales pendientes con datos reales

Cada respuesta futura debe registrar dataset, publicación, snapshot, SQL y parámetros, resultado, conciliación, cobertura, advertencia, permisos efectivos y hashes de evidencia.

| Pregunta | Consulta/contrato reproducible | Estado actual |
| --- | --- | --- |
| Sucursal imputada de factura | INVOICE; clave interna explícita; accounting_branch_id por línea | Diseño SQL sintético; sin JDT1 publicado |
| Asiento asociado | INVOICE + FK explícita document_link.trans_id | TransId OINV disponible en Atomic; OJDT pendiente |
| Cuentas afectadas | INVOICE; account/account_name de cada línea original | Sin cuentas publicadas |
| Débitos y créditos | INVOICE o DIARY; filtrar una base/moneda; BALANCE sobre asiento íntegro | Sin importes contables publicados |
| Facturas de sucursal/período | DIARY filtrado por branch de línea, EXISTS document_link por TransId y período contable; DISTINCT company/object_type/DocEntry | No usar sucursal documental ni sumar factura por cada línea |
| Movimiento mensual de cuenta | DIARY filtrado por cuenta; agrupar posting_date a mes y base/moneda/branch; mantener referencia al original | SQL base sintético, real pendiente |
| Saldo de cuenta | LEDGER con apertura y cobertura; naturaleza acreditada | Apertura real ausente; saldos no acreditados |
| Centros de costo en factura | INVOICE raw + resolución efectiva de reglas + reparto separado | Raw en fixture; catálogo/reglas reales pendientes |
| Divergencias documento/contabilidad | INVOICE; comparar sólo códigos resueltos al mismo namespace, nulos como UNKNOWN; nunca nombres de depósito | Sin sucursal documental no nula ni JDT1 publicado |
| Documentos sin relación acreditada | UNLINKED y reporte de FK, líneas, cuentas o semántica faltantes | 0 relaciones completas acreditadas no significa 0 asientos SAP |

Facturas, NC, manuales, automáticos, cancelados/reversados, multimoneda y varias dimensiones requieren resultados separados. Los tests sintéticos no sustituyen esta matriz real. Al faltar JDT1 se bloquea la parte contable y se conserva la respuesta documental autorizada que sí tenga evidencia.
