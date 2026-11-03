# TelchiAI — IVA Bolivia 13 % y semántica monetaria de líneas

Investigación READ ONLY en `feature/console-backend-core`, del 20/10/2026. IVA acreditado como causa principal; conciliación PARTIAL. Importe de líneas por categoría semánticamente READY en BS, sin implementación ni promoción.

## Respuesta ejecutiva

El patrón del 13 % es principalmente IVA registrado, no sólo una semejanza numérica. No explica todos los documentos ni autoriza convertir automáticamente importes por categoría.

1. **Sí explica la mayor parte:** 27.308/30.301 facturas, **90,122438 %**, cumplen `DocTotal−SUM(LineTotal)=DocTotal×0,13` dentro de 0,01. Todas contrastan también con el impuesto registrado dentro de 0,01. Su diferencia agregada es 804.862,04, el 95,5044 % de la diferencia neta original; este porcentaje de importe tiene compensaciones y no es porcentaje de error absoluto explicado.
2. **Impuestos realmente registrados:** 27.327 documentos, **90,185142 %**, tienen impuesto no cero y concilian con él dentro de 0,01. Otros 871 concilian con impuesto cero. Total del puente tributario: **28.198 / 93,059635 %**. No llamar IVA positivo a los 871 de impuesto cero.
3. **Pendiente causal:** 2.103 documentos, **6,940365 %**; residuo firmado después del impuesto **−112.919,99**, absoluto **113.120,03**. Incluyendo los residuos tolerados de todos los documentos: −112.920,38 y 113.120,68 absoluto. El residuo de la hipótesis uniforme del 13 % es distinto: **−313.138,9627**.
4. **Extracción:** no se encontró divergencia de los campos comparados entre Foundation y Raw: **65.163/65.163 líneas**, claves y capturas correspondientes. No demuestra ausencia de error en SAP ni paridad viva actual; HANA está inaccesible. Descuentos de cabecera y otros componentes no capturados pueden explicar residuos, pero siguen sin acreditarse.
5. **Materia prima:** se puede defender **Bs 839.582,63 como «Importe registrado en líneas comerciales de facturas activas, sin impuesto de línea y antes de ajustes no atribuidos de cabecera; sin restar notas de crédito»**. Son 34 productos, 526 líneas, 495 facturas, clasificación actual VALIDATED. No llamarlo facturación neta, cobro, venta contable neta ni total facturado con IVA.
6. **Neto por categoría:** falta acordar qué significa neto, acreditar NC y su atribución, devoluciones/base documental, descuentos y ajustes de cabecera por línea/categoría, sin duplicación ni prorrateo fiscal inventado. Eso **no bloquea** mostrar la métrica parcial anterior.

## Universo, linaje y evidencia

Corrida canónica: [reconciliation.json](verified/reconciliation.json), diagnóstico [diagnostics.json](verified/diagnostics.json) y cálculo por factura en [documents.csv](verified/documents.csv).

- Foundation `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot **1408**, base manifest 1322, sales `update_publication_06cba09af83481c325e7aed0688ebace`.
- DocDate `[2026-09-01,2026-10-01)`, OINV activas `N`, INV1 por fuente y DocEntry; grano de línea incluye LineNum. Cobertura observada hasta **24/09**: no es septiembre completo.
- Reference `v2_reference_closure_2088d5885204313a`; crosswalk SHA-256 `7fcfef912cc8ef46868e03b56f90b61da13c08e951c453abc0483690edc36e10`. No se cambia la clasificación ni se interpreta como histórica.
- 30.293 documentos proceden de `manual-update-20260924T123403344453Z_changed`; ocho de `manual-update-20260924T132754050866Z_changed`.
- Cada publicación `_changed` se vincula al Raw del **mismo run_id**, no al último Raw disponible. `update.py` asigna al candidato changed el fin de extracción del run; por eso su source_as_of no es el timestamp de inicio de cada segmento Raw. Se comprobaron manifests y hashes físicos.
- Raw septiembre, primera captura: SHA-256 `137f75ba412665875a50e91c764d72fbe60654de96d7aa4a971b840015dd8b4e`; segunda: `51ad4418d518ed76226124f15e778c0f2472e3779e2ccc153a324e75b9b06e2e`. Paths y timestamps completos en el JSON.
- Paridad por línea: DocEntry/LineNum y run, DocNum, DocDate, CANCELED, DocCur, LineCurrency, DocTotal, LineTotal, Quantity, Price e ItemCode. Cero faltantes o discrepancias. No se atribuyeron impuestos desde otra captura ni desde coincidencias de totales.
- Se reutiliza el [control técnico previo](../category-line-amount-reconciliation-v1/distribution-r3.json) del mismo snapshot: cero duplicados de cabecera/línea, huérfanos o cabeceras sin líneas, 100 % de cobertura de crosswalk. La nueva corrida comprueba además unicidad de documentos y líneas del join.
- La corrida preliminar del root se conserva; `verified/` añade explícitamente paridad ItemCode y DocNum y es la autoridad final. No se sobrescribe evidencia previa.

## Normativa oficial a septiembre de 2026

La autoridad fiscal consultada es el compendio del SIN «Ley 843 y Decretos Reglamentarios», texto ordenado, complementado y actualizado al **30 de septiembre de 2026**. Se distingue esta norma del almacenamiento técnico de SAP.

Fuentes: [índice oficial SIN](https://www.impuestos.gob.bo/index.php/compendio-tributario-actualizado/) y [PDF oficial Ley 843, edición 09-26](https://www.impuestos.gob.bo/wp-content/uploads/2026/10/1.-LEY-N%C2%B0-843-09-26.pdf). Descarga y hash en [sources/index.json](sources/index.json); copia [PDF](sources/sin_ley843.pdf) y [texto extraído](sources/sin_ley843.txt). La carpeta web de octubre es fecha de publicación, no el corte normativo del contenido.

| Regla | Fuente / conclusión |
| --- | --- |
| Alícuota general 13 % | Ley 843, art. 15: «La alícuota general única del impuesto será del 13% (trece por ciento)» |
| IVA incorporado | Art. 5: forma parte integrante del precio neto de venta y se factura conjuntamente, sin mostrarse por separado |
| Base imponible | Art. 5: precio neto consignado en factura; ventas/servicios menos descuentos y bonificaciones según usos de plaza; incorpora servicios accesorios y gastos financieros previstos |
| Débito fiscal | Art. 7: aplicación de alícuota del art. 15 a precios de arts. 5/6; no equivale al impuesto a pagar después de créditos fiscales del período |
| Facturación de ventas | Art. 4.a: entrega/transferencia, al contado o crédito, respaldada obligatoriamente por factura o equivalente; servicios tienen otros momentos de perfeccionamiento |
| Operaciones sin tratamiento general | Art. 11 exportaciones, art. 14 exenciones y normas complementarias; existen exenciones específicas y tasa cero, con condiciones propias |
| Ejemplos de excepciones legales | Importaciones de libros/publicaciones, Ley 366 art. 8.I; tratamientos de libros de producción nacional/tasa cero y turismo receptivo según normas recopiladas; no se asignan a Telchi sin verificar operación y documento |
| Reglamento | D.S. 21530 recopilado en el mismo PDF: desarrollo de base/hecho imponible, facturación física o digital y excepciones; no sustituye el código tributario real de cada factura SAP |

**Distinción crucial:** el «precio neto» fiscal boliviano del art. 5 **incluye el IVA**. No es sinónimo del subtotal técnico de SAP sin impuesto. `LineTotal` no debe etiquetarse automáticamente «base imponible IVA».

Si `P` es el precio final íntegramente sujeto a 13 % incorporado, entonces impuesto `T=0,13P`, importe económico sin impuesto `N=0,87P`, y `P=N/0,87`. El incremento sobre N sería 13/87 = 14,9425287… %, **no 13 %**. Sólo bajo esas condiciones y sin otros componentes puede esperarse `DocTotal=B/0,87`.

Ejemplo: 21,75/0,87=25; 21,75×1,13=24,5775, que no es 25. No se aplica ninguna de estas conversiones al total de RAW_MATERIAL.

## Contrato SAP y publicación Foundation

La documentación oficial SAP B1 10.0 define LineTotal como importe de fila excluido el impuesto; el productor lo copia sin recalcularlo. La moneda se apoya además en configuración OADM, no en semejanzas numéricas.

Fuentes SAP: [LineTotal](https://help.sap.com/doc/089315d8d0f8475a9fc84fb919b501a3/10.0/en-US/SDKHelp/SAPbobsCOM~Document_Lines~LineTotal.html), [tabla INV1](https://help.sap.com/doc/089315d8d0f8475a9fc84fb919b501a3/10.0/en-US/SDKHelp/Marketing_Documents/INV1.htm), [tabla OINV](https://help.sap.com/doc/089315d8d0f8475a9fc84fb919b501a3/10.0/en-US/SDKHelp/Marketing_Documents/OINV.htm). Copias, URLs y hashes en [sources/index.json](sources/index.json) y [sources/supplement-index.json](sources/supplement-index.json).

| Campo | Contrato / alcance acreditado |
| --- | --- |
| OINV.DocTotal | Total documental; no suma imputable por entero a una categoría. El esquema ofrece DocTotalFC y DocTotalSy separadamente |
| OINV.DocCur | Moneda del documento; Foundation la copia a `sales_document.currency` |
| INV1.LineTotal | «total amount (not including tax) per row». Total comercial de línea, con descuento propio de línea; no subtotal recalculado por nuestro runner ni neto fiscal/contable final |
| INV1.Currency | Moneda del **precio** de fila según SAP; no es por sí sola acreditación de LineTotal. Foundation la copia a `sales_line.currency` |
| INV1.TotalFrgn / TotalSumSy | Totales de línea en moneda extranjera / sistema; diferenciados de LineTotal por la documentación SAP. No se mezclan ni convierten |
| Price / PriceBefDi / DiscPrcnt | Precio antes de impuesto / precio unitario bruto previo a descuento / descuento de fila. El registro comercial de línea incorpora su descuento, pero no representa automáticamente todos los descuentos globales |
| INV1.VatPrcnt / VatSum | Tasa e impuesto registrado de línea; SQL productor alias `LineVatSum`. Disponibles en Raw, no en `sales_line` Foundation actual |
| OINV.VatSum, DiscSum, TotalExpns, RoundDif | Campos previstos para impuesto, descuento global, gastos y diferencia de redondeo; no disponibles en los Raw de venta cotejados. No se dan por cero |
| FC/SC de impuesto, descuento y gastos | Requieren campos y moneda correspondientes acreditados; no se sustituyen por tipos de cambio deducidos |

Revisión concreta del productor: `datalake/sql.py::SALES_EXTRACT_SQL` selecciona LineTotal, TotalFrgn, TotalSumSy, VatPrcnt, VatSum, LineDiscPrcnt, LineRate. `create_initial.py::_sales_candidate` copia LineTotal→line_total mediante `_source_value`; no añade/resta IVA, no multiplica por 0,87, no redondea ni asigna cabeceras a líneas. Omite publicar impuestos, descuento y totales alternativos de línea en sales_line. Las cabeceras sí publican totales FC/SC. `update.py` construye candidatos changed con esos campos comerciales, sin reinterpretarlos.

Evidencia de descuentos: de 65.163 líneas, `Quantity×Price` coincide exactamente en 59.888 y dentro de 0,01 en otras 5.185; 90 quedan fuera. La fórmula `Quantity×PriceBefDi×(1−DiscPrcnt/100)` coincide exactamente en 58.760 y dentro de 0,01 en otras 6.321; **82 no coinciden**. Se conservan sin ajustar: no se reemplaza LineTotal por una fórmula aproximada.

Ejemplo reproducible OINV 11499581 / línea 0: PriceBefDi=35, descuento=10 %, Quantity=50, Price=31,50, LineTotal=1.575. Esta evidencia demuestra descuento de fila incorporado; no acredita descuento de cabecera. Los restantes ejemplos están en diagnostics.json.

## Moneda independiente

Dos investigaciones SAP READ ONLY previas del mismo esquema TELCHI leyeron OADM durante septiembre. Se reutiliza evidencia fechada verificable, no una nueva consulta HANA exitosa.

| Evidencia | Fecha UTC | Resultado |
| --- | --- | --- |
| balance_sheet_pnl_reconstruction_v1.json / company_currency | 10/09/2026 12:37:47 | local=BS, sistema=USD, multi=B |
| financial_position_cash_flow_v1_1.json / company_currency | 10/09/2026 01:23:16 | local=BS, sistema=USD |

Paths, hashes de resultados, hashes de scripts y SQL `SELECT MainCurncy,SysCurrncy FROM TELCHI.OADM` se conservan en diagnostics.json. Esto es evidencia independiente de la configuración, no inferencia a partir de DocCur=INV1.Currency ni de una relación de importes.

La [definición SAP de LocalCurrency](https://help.sap.com/doc/089315d8d0f8475a9fc84fb919b501a3/10.0/en-US/SDKHelp/SAPbobsCOM~AdminInfo~LocalCurrency.html) establece moneda de libros locales y declara que no puede modificarse una vez registrados asientos/datos maestros. El esquema ya tenía operación contable en esas lecturas. La evidencia es aplicable a la misma entidad de septiembre; no certifica otra empresa, una restauración/reconfiguración o migración no declarada.

**Conclusión acotada:** LineTotal comercial de esta publicación y universo local se denomina **BS — bolivianos**, no USD ni moneda de sistema. Todas las facturas y precios publicados del universo son BS. El contrato habilitable es **BS-only**. No se certifica aquí sumar documentos FX ni usar `line.currency` como denominación universal de LineTotal; para FX se necesita contrato separado.

El [preflight HANA actual](hana-probe.json) devolvió `ConnectionRefusedError` antes de ejecutar SQL. No se intentó VPN, reinicio ni modificación de infraestructura. Releer OADM/OCRN cuando el acceso sea autorizado y disponible sería confirmación adicional, no motivo para fingir que esta sesión logró consulta viva.

## Conciliación decimal del 13 %

Se calculan A=DocTotal, B=SUM(LineTotal), C=A−B, D=0,13A, E=C−D sin coma flotante ni ajustes. El CSV conserva cada valor, incluidos residuos menores al centavo.

Se usa DECIMAL(38,6) para los campos publicados y Decimal con precisión 50 para el cálculo. Las 65.163 líneas fuente son exactas a centavo. Tolerancia absoluta **0,01 BS por documento**: umbral conservador de comparación monetaria, no afirmación de configuración SAP `SumDec` ni demostración de causa de cada centavo. No se amplía con número de líneas para conseguir un PASS.

| Partición excluyente | Facturas | % | Interpretación |
| --- | ---: | ---: | --- |
| E=0 exacto | 14.467 | 47,744299 | Compatible 13 % y contrastado con impuesto registrado |
| 0<ABS(E)≤0,01 | 12.841 | 42,378139 | Compatible dentro de tolerancia; no se elimina el residuo |
| Fuera de 13 %, pero puente con impuesto registrado dentro de 0,01 | 890 | 2,937197 | 862 exactas y 28 toleradas; incluye impuesto cero y pequeños límites de redondeo |
| Fuera de ambos puentes | 2.103 | 6,940365 | Sin explicación completa; no asignar descuento, gasto o exención por intuición |
| Total | 30.301 | 100 | Sin exclusiones nuevas para mejorar coincidencia |

Totales: A=8.891.439,79; B=8.048.691,58; C=842.748,21; D=1.155.887,1727; **E=−313.138,9627**, ABS(E) agregado=313.309,2519. El patrón previo «porcentaje redondeado a 13,00 %» tenía 20.794 documentos; no es el mismo criterio que tolerancia monetaria absoluta, por eso los conteos difieren.

| ABS(E) | Documentos | E firmado | Suma absoluta de E |
| --- | ---: | ---: | ---: |
| =0 | 14.467 | 0 | 0 |
| (0; 0,01] | 12.841 | −17,5082 | 41,6956 |
| (0,01; 0,10] | 57 | −1,9949 | 2,0493 |
| (0,10; 1] | 364 | −191,9579 | 191,9579 |
| (1; 10] | 1.069 | −4.416,2725 | 4.416,2725 |
| (10; 100] | 959 | −30.247,1023 | 30.393,1497 |
| (100; 1.000] | 474 | −132.217,0863 | 132.217,0863 |
| >1.000 | 70 | −146.047,0406 | 146.047,0406 |

## Verificación independiente del impuesto registrado

El puente adicional es F=SUM(Raw.INV1.VatSum), R=C−F. No se calculó F como el 13 % de A: se leyó el campo fiscal registrado de la captura correspondiente.

| Puente documental | Documentos | % |
| --- | ---: | ---: |
| C=F exactamente | 28.133 | 92,845121 |
| 0<ABS(C−F)≤0,01 | 65 | 0,214514 |
| ABS(C−F)>0,01 | 2.103 | 6,940365 |

SUM(F)=955.668,59. **SUM(R)=−112.920,38**; SUM(ABS(R))=113.120,68. Para los 2.103 no explicados: C=36.363,48, F=149.283,47, R=−112.919,99 y ABS(R)=113.120,03. Los tolerados aportan R=−0,39 y ABS(R)=0,65: se muestran, no se ocultan.

Las 27.308 coincidencias del 13 % tienen C=804.862,04 y F=804.862,23; R=−0,19. Así, el IVA está acreditado para la mayor parte del patrón. No se demuestra una conciliación contable integral ni el IVA declarado/pagado ante SIN: faltan cabecera fiscal y otros componentes.

## Excepciones y patrones

Las excepciones no se explican sólo por múltiples líneas o categorías. La tasa registrada cero existe, pero su fundamento legal por documento no fue identificado; no se la etiqueta automáticamente exención.

| Segmento | Facturas | E exacto | E tolerado | Fuera de tolerancia 13 % |
| --- | ---: | ---: | ---: | ---: |
| Tasa de línea 13 | 29.016 | 14.467 | 12.841 | 1.708 |
| Tasa de línea 0 | 1.285 | 0 | 0 | 1.285 |
| Una línea | 16.530 | 9.993 | 5.237 | 1.300 |
| Varias líneas | 13.771 | 4.474 | 7.604 | 1.693 |
| Una categoría | 22.019 | 11.786 | 8.122 | 2.111 |
| Categorías mezcladas | 8.282 | 2.681 | 4.719 | 882 |

No hay mezcla 0/13 dentro de una factura en este universo. De las 1.285 tasa cero, 871 concilian con impuesto registrado cero y 414 tienen otros residuos. De las 29.016 tasa 13, 27.327 concilian con impuesto positivo y 1.689 no. Sólo moneda documental/precio BS: **cero documentos FX en el universo comparable**, sin convertirlos ni descartarlos.

28.512 documentos tienen sólo descuentos de línea cero y 2.034 de ellos siguen sin conciliar con impuestos. Por tanto no puede atribuirse el remanente automáticamente a esos descuentos de fila. Diagnóstico completo por combinación de descuentos en JSON. No se capturó descuento global, gastos, anticipos/retenciones u otros ajustes para probar una identidad total.

| DocEntry / DocNum | A | B | C | D | E | F registrado | R=C−F |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 11532517 / 260192728 | 25,00 | 21,75 | 3,25 | 3,2500 | 0 | 3,25 | 0 |
| 11507904 / 261407285 | 33.241,04 | 35.392,90 | −2.151,86 | 4.321,3352 | −6.473,1952 | 4.321,34 | −6.473,20 |
| 11508098 / 261407296 | 34.208,31 | 35.392,90 | −1.184,59 | 4.447,0803 | −5.631,6703 | 4.447,08 | −5.631,67 |
| 11503316 / 261407209 | 45.170,40 | 44.657,10 | 513,30 | 5.872,1520 | −5.358,8520 | 5.872,15 | −5.358,85 |
| 11516964 / 261909247 | 25.650,00 | 27.000,00 | −1.350,00 | 3.334,5000 | −4.684,5000 | 0 | −1.350,00 |
| 11515409 / 261909221 | 31.101,33 | 31.101,33 | 0 | 4.043,1729 | −4.043,1729 | 0 | 0 |
| 11502444 / 260184900 | 491,31 | 427,45 | 63,86 | 63,8703 | −0,0103 | 63,87 | −0,01 |
| 11503167 / 260406438 | 96,08 | 83,60 | 12,48 | 12,4904 | −0,0104 | 12,49 | −0,01 |
| 11523946 / 260190428 | 228,84 | 199,08 | 29,76 | 29,7492 | 0,0108 | 29,75 | 0,01 |

Las primeras cinco excepciones por ABS(E) y 20 casos principales están en reconciliation.json, con líneas/categorías, tasa, descuento de línea, captura y fecha. La tabla también ilustra un documento cero-impuesto que falla contra 13 % pero concilia, y pequeños residuos de ambos signos. No se adjudican los grandes negativos a errores ni descuentos globales sin esos campos.

## Materia prima y viabilidad comercial

La métrica parcial tiene significado propio y no necesita igualdad con cabeceras. Se aplica categoría a las líneas, no a todos los importes de las facturas que contienen algún producto de esa categoría.

| RAW_MATERIAL, clasificación VALIDATED actual | Resultado |
| --- | ---: |
| Productos / líneas / facturas | 34 / 526 / 495 |
| Importe registrado LineTotal | **Bs 839.582,63** |
| Líneas con VatPrcnt=13 | 517; LineTotal 794.140,13 |
| Líneas con VatPrcnt=0 | 9; LineTotal 45.442,50 |
| Impuesto de línea registrado, sólo como campo auxiliar Raw | 116.894,07 |
| Descuentos propios de línea | 523 líneas a cero; tres a 12,5 %, 5 % y 10 % |

Se puede presentar ahora, **como conclusión investigativa**, «Materia prima: Bs 839.582,63 de importe registrado en líneas comerciales, sin impuesto de línea; 34 productos, 526 líneas, 495 facturas activas observadas del 1 al 24 de septiembre de 2026. Sin descontar NC ni ajustes globales; clasificación actual». No se certifica cierre del mes.

Una transformación verificable de campos sería sumar `LineTotal+VatSum` por las mismas líneas: 956.476,70 en este conjunto. Es únicamente **importe de línea más impuesto registrado**, no acreditación del total final facturado por categoría: puede faltar efecto del descuento de cabecera sobre su subtotal. Foundation actual ni siquiera publica VatSum para una capability. No se denomina aquí «ventas con IVA por categoría» ni se implementa.

`SUM(LineTotal)/0,87` tampoco es una transformación válida del total de materia prima: hay tasa cero y residuos de cabecera. Las facturas mixtas exigen atribución por líneas, con impuestos propios acreditados y un contrato explícito para descuentos/gastos globales. Nunca repartir DocTotal entero ni el residuo de cabecera a cada categoría.

## Notas de crédito y comprobación adicional

Se conserva la investigación previa de NC como evidencia separada del mismo snapshot. Este trabajo no sustrae sus importes ni acredita un neto nuevo.

La [evidencia previa](../business-categories-sales-v1/reconciliation-r2.json) identifica ORIN/RIN1: 224 NC activas, 1.071 líneas; RAW_MATERIAL 16.317,71 en ocho líneas/siete NC/seis productos. Existen líneas BaseType=13, standalone y una BaseType=16 sin cadena completa. No hubo nueva verificación de impuestos de NC ni de política temporal de atribución original/actual. **CREDIT_NOTES=UNRESOLVED** para el neto por categoría.

Cuando SAP/HANA esté disponible, una consulta READ ONLY acotada debe recuperar OADM/OCRN y, para los DocEntry del CSV, OINV.DocTotal/VatSum/DiscPrcnt/DiscSum/TotalExpns/RoundDif con variantes FC/SC, DocRate, DpmAmnt y retenciones/ajustes disponibles; INV1.VatGroup/VatPrcnt/VatSum, importes antes/después de descuento y gross documentados; componentes de gastos/impuestos adicionales correspondientes. Primero descubrir columnas con SELECT TOP 0 y luego comprobar importes y moneda sin fanout.

Contrastar contra OINV.VatSum y una identidad contable documentada de la localización Bolivia, no una fórmula inventada por nombres de campos. Revisar códigos fiscales y su vigencia para los documentos tasa cero. Aplicar idéntico proceso a ORIN/RIN1 y vínculos base para la definición de neto. Una lectura actual no es la captura histórica: exigir paridad o registrar cambios posteriores antes de mezclar componentes.

## Estados de entrega

READY describe únicamente la semántica acotada BS del importe de línea. No habilita código, permisos, acceso Presidencia, runtime ni producción.

```text
IVA_RATE=VERIFIED
IVA_INCLUDED_IN_PRICE=VERIFIED
SAP_LINETOTAL_SEMANTICS=VERIFIED (importe registrado de línea sin impuesto; no neto final)
LINETOTAL_CURRENCY=VERIFIED (BS-only, esta entidad/publicación; OADM histórico independiente)
DOCUMENTS_ANALYZED=30301
EXACT_13_PERCENT_MATCH=14467 (47.744299%)
ROUNDING_TOLERANCE_MATCH=12841 (42.378139%; adicionales, ABS(E)<=0.01)
EXACT_OR_TOLERANCE_13_PERCENT_MATCH=27308 (90.122438%)
OTHER_REGISTERED_TAX_TREATMENT=890
UNEXPLAINED_DOCUMENTS=2103
AGGREGATE_RESIDUAL=-313138.9627 (E de hipótesis uniforme 13%)
REGISTERED_TAX_BRIDGE_RESIDUAL=-112920.38 (todos)
UNEXPLAINED_RESIDUAL=-112919.99 (2103 documentos)
UNEXPLAINED_ABSOLUTE_RESIDUAL=113120.03
IVA_CAUSE=PARTIAL (principal acreditada; no sólo hipótesis)
RAW_MATERIAL_LINE_AMOUNT=VERIFIED
RAW_MATERIAL_CURRENCY=BS (bolivianos)
RAW_MATERIAL_AMOUNT=839582.63
CATEGORY_MONETARY_METRIC=READY (semántica parcial, BS-only; NO implementación)
CREDIT_NOTES=UNRESOLVED
PROPOSED_NEXT_STEP=Implementar por autorización separada importe de líneas BS-only; investigar cabecera/NC aparte para neto
SAP_WRITE_COUNT=0
FOUNDATION_WRITES=0
WHATSAPP_SENT=0
COMMIT_OR_PUSH=NO
```

## Reproducción, validaciones y límites

Los runners viven sólo en el nuevo scope investigativo `modules/telchi/investigation/validation/iva_bolivia_13_v1/`. Ningún código runtime importa estos análisis.

Desde backend, escoger un directorio de salida nuevo; los artefactos se abren con modo exclusivo para no sobrescribir resultados:

```bash
uv run python -m modules.telchi.investigation.validation.iva_bolivia_13_v1.hana_probe
uv run python -m modules.telchi.investigation.validation.iva_bolivia_13_v1.reconcile --output ../../data/reports/telchi/iva-bolivia-13-v1/verified
uv run python -m modules.telchi.investigation.validation.iva_bolivia_13_v1.enrich --output ../../data/reports/telchi/iva-bolivia-13-v1/verified
uv run pytest modules/telchi/investigation/validation/iva_bolivia_13_v1/test_reconcile.py -q
```

Desde raíz, descarga inicial: `python3 SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/iva_bolivia_13_v1/sources.py`. `pdftotext -layout` generó el texto de la ley; las fuentes suplementarias se descargaron por GET de las URLs preservadas en supplement-index.json. No se usó navegador ni buscador de terceros.

Resultado tests focalizados: **15 passed**, 0,56 s; incluyen Decimal, límites de tolerancia, no aplicar 1,13, particiones sin pérdida, CSV íntegro, impuestos reales, moneda independiente y categoría con tasas diferentes. Gates LAT, diff y hashes finales se registran en validations.json. No se declara PASS de conciliación total ni de HANA vivo.

Incidencias del runner, no defectos de datos: la primera ejecución detectó claves iguales en Raw de dos runs; se corrigió el índice a `(DocEntry,LineNum,run_id)` y se verificó paridad, nunca se eligió arbitrariamente uno. Una consulta exploratoria falló por comparar VARCHAR de descuento con entero; no cambió datos y fue reemplazada por lectura Decimal. Ambas sesiones cerraron por su context/finally. La corrida final se repitió para añadir controles ItemCode/DocNum, no para variar tolerancias.

## Recursos, archivos e impacto

Host compartido seguro para consultas acotadas: 8 cores, load inicial 1,34/2,10/2,97, ~4,57 GB disponibles y CPU ociosa ~90 %. Se ejecutaron consultas secuenciales de septiembre con un thread DuckDB, 256 MB y sin spill; diagnóstico Raw con 128 MB.

Segunda observación: load 3,18/2,89/3,00, ~4,53 GB disponibles, swap pasó de ~1,40 a ~1,60 GB durante el trabajo compartido; sin si/so en las muestras recientes y CPU ociosa ~88 %. No se escaló concurrencia ni se lanzaron scans globales, browsers, LLM, servicios ni benchmarks.

```text
HOST_PREFLIGHT=SAFE (presupuesto acotado; sin escalado con aumento de swap)
RESOURCE_GUARD=PASS
CONCURRENCY_USED=1 (runner/conexión y thread DuckDB, secuenciales)
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=0 (preflight HANA bloqueado, sin workload iniciado)
OWN_PROCESSES_LEFT_RUNNING=0
```

Archivos nuevos: cuatro scripts Python investigativos, un archivo de tests focalizados y este evidence root con JSON, CSV y fuentes oficiales. Ningún archivo preexistente editado; sin actualización de estados GLOBAL/locales ni contrato DEVELOPMENT de otro owner. La presente evidencia es la que cierra el gap semántico para la métrica BS acotada, no una edición silenciosa de ese contrato.

Impacto transversal: ninguno sobre Luna, State Engine, Console, Foundation/CURRENT, clasificación, permisos, SAP, infraestructura o servicios. Riesgos explícitos: evidencia OADM histórica aplicable a la misma entidad, cobertura mensual parcial, otros componentes de cabecera y neto/NC pendientes. Próximo paso: autorización separada para implementar el importe de líneas BS-only; no exigir conciliación contable total para esa métrica parcial.
