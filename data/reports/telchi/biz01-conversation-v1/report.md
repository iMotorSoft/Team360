# Conversación empresarial de Presidencia — BIZ01 V1

- Fecha: 2026-10-21
- Rama: `feature/console-backend-core`
- Módulo: TelchiAI (`SrvRestAstroLS_v1/backend/modules/telchi/assistant`)
- Alcance: implementación DEV de la memoria empresarial, la composición analítica acreditada y el contrato de respuesta. Sin promoción, sin entrega WhatsApp, sin commit ni push.
- Referencia de arquitectura: [auditoría conversacional V1](../conversational-architecture-audit-v1/report.md) (usada como entrada, no repetida).

## 1. Resultado

```
BIZ01_CONVERSATION_PASS=YES
BIZ01_TURNS=10
BIZ01_CORRECT=10/10
BIZ01_UNJUSTIFIED_CLARIFICATIONS=0
BIZ01_UNJUSTIFIED_UNAVAILABILITY=0
BIZ01_CONTEXT_LOSS=0
BIZ01_MONETARY_RECONCILIATION=PASS
BIZ01_AUTHORIZATION=PASS
```

La conversación se ejecutó sobre el pipeline real (MessageDispatcher → TelchiHandler → State Engine → capabilities → Foundation → PostgreSQL) por el endpoint DEV autenticado, con el usuario piloto real, el tenant `telchi`, el workspace `telchi_dev` y un único hilo persistido. No se enviaron mensajes WhatsApp.

## 2. Qué cambió

El estado conversacional modelaba una consulta (`metric` + `period` + `comparison` + un `entity_mention` genérico) y no un contexto de negocio. Eso producía exactamente el incidente del 21/10: sin slot propio para el producto, la categoría podía ser sobrescrita; sin slot para el cliente ni para un conjunto de períodos, "esos dos meses" no era expresable y la respuesta terminaba con un único mes en el texto.

### 2.1 Alcance empresarial explícito

Slots aditivos (`state_engine.SCOPE_FIELDS`), de modo que un estado persistido que no los usa conserva su forma y sigue siendo válido:

| Slot | Significado | Autoría |
| --- | --- | --- |
| `/business_category` | Categoría acreditada, con slot propio | modelo |
| `/product_target` | Código SAP del producto en foco, transferible entre métricas | modelo |
| `/customer_target` | CardCode del cliente facturado en foco | modelo |
| `/group_by` | Dimensión: `sap_product` o `card_code` | modelo |
| `/periods` + `/period_mode` | Conjunto de períodos y cómo se lee (`union` / `compare`) | modelo |
| `/breakdown_by` | Lectura de cada mes por separado | modelo |
| `/focus` | Producto y cliente en foco, con sus nombres publicados | servicio |

`entity_mention` queda para una entidad comercial todavía no resuelta y **no admite un código de producto**: una operación de producto o categoría rechaza una mención que no sea código de categoría. Ése es el cierre directo del incidente P1, que antes se aceptaba y se persistía como estado dañado.

`/focus` es la memoria de resultado: el servicio la proyecta después de cada ejecución, de modo que «ese producto», «ese cliente» y «nos compró» se resuelven desde el estado persistido, no desde el historial de texto.

### 2.2 Períodos

`union` exige períodos contiguos y el motor calcula la ventana; el conjunto queda guardado, de modo que un turno posterior puede seguir nombrando los meses individuales. `compare` sigue siendo un período contra su base. Al declarar una unión, el motor descarta el `comparison` heredado: en una unión no hay línea base.

### 2.3 Plan de negocio

`business_plan.py` es el único contrato que Team360 compila:

```
dataset + filters + period + group_by + measure + ordering + limit
```

Vocabulario cerrado, validación en backend y ninguna tabla, columna, dataset ni expresión SQL exposed al modelo. La primera familia acreditada es `sales.commercial_line_amount_by.v1`.

### 2.4 Lector acreditado

`datalake/commercial_line_amount_by_query.py` reutiliza la medida, las guardas de moneda, la guarda de linaje, la puerta de clasificación y la reconciliación de tolerancia cero ya acreditadas para el total de categoría (`category_line_amount_query.scoped_source` / `scoped_aggregate`). El lector sólo agrega una dimensión de agrupación cerrada y filtros cerrados.

- Producto → documento → CardCode: `atomic.sales_document.card_code` ⋈ `atomic.sales_line.doc_entry`.
- Nombres publicados: catálogo de productos y maestro de clientes de la referencia versionada (nunca nombres inventados).
- Reconciliación: suma del desglose = total del alcance, diferencia 0; por cliente, las facturas se particionan.

### 2.5 BUSINESS ANSWER FIRST

La respuesta entrega primero el resultado empresarial verificable, luego la excepción, el riesgo concreto, su efecto sobre la conclusión y el próximo paso útil. La ruta de indisponibilidad nombra el alcance completo (todos los períodos), el faltante exacto y el siguiente paso; cuando existe una parte acreditada del alcance, esa parte se entrega en lugar de una indisponibilidad desnuda.

## 3. Evidencia BIZ01

Corridas: `run3`, `run4`, `run5`, `run6` en `data/reports/telchi/biz01-conversation-v1/`. Cada corrida tiene `runtime_http_results.json` (estado, auditoría y tiempos por turno) y `biz01_evaluation.json` (evaluación de continuidad).

| # | Pregunta | Operación ejecutada | Dato acreditado en la respuesta |
| --- | --- | --- | --- |
| 1 | ¿Cuánto facturamos en septiembre? | `sales.period_billed_amount.v1` | Bs 8.891.439,79; neto documental Bs 8.562.769,55 |
| 2 | ¿Y cuánto corresponde a productos terminados de laboratorio? | `sales.category_line_amount.v1` | Bs 2.679.208,66 en líneas comerciales de la categoría, universo distinto del turno 1 y declarado como tal |
| 3 | ¿Cuáles fueron los cinco productos con mayor importe vendido? | `sales.product_line_amount_ranking.v1` | L03281 Bs 259.922,61 entre 5 productos terminados |
| 4 | ¿En qué puesto estuvo L03281 en julio y agosto? | ranking histórico | Julio puesto 2 de 283 (Bs 271.255,49); agosto puesto 1 de 289 (Bs 314.971,57); diferencia Bs 43.716,08 |
| 5 | ¿A qué cliente le vendimos más ese producto entre ambos meses? | `sales.commercial_line_amount_by.v1` (card_code) | FARMACORP S.A. (C000061) Bs 115.044,44; total del alcance Bs 586.227,06 |
| 6 | ¿Cuánto compró ese cliente en julio y cuánto en agosto? | desglose por mes | Julio Bs 72.383,99; agosto Bs 42.660,45; variación −Bs 29.723,54 (−41,06 %) |
| 7 | ¿Qué otros productos nos compró durante esos meses? | desglose por producto | L01613 Bs 52.200,00; L01003 Bs 14.786,52; L01612 Bs 12.906,45; el producto en foco queda marcado |
| 8 | ¿Qué porcentaje representa ese cliente sobre las ventas de L03281? | desglose + total del universo | 19,62 % de los Bs 586.227,06 del mismo alcance sin filtrar por cliente |
| 9 | ¿Qué otros clientes importantes compraron ese producto? | desglose por cliente | ranking de 468 cuentas facturadas, 10 mostradas |
| 10 | ¿Qué cambió entre julio y agosto? | desglose por mes de la unión | variación por cuenta facturada, en valor y en porcentaje |

Continuidad comprobada: los diez turnos usan el mismo hilo persistido, el mismo usuario, el mismo tenant y el mismo workspace. El producto L03281, el cliente C000061, la unión julio+agosto y la métrica sobreviven a los cambios de dimensión. Cero aclaraciones innecesarias, cero indisponibilidades injustificadas, cero pérdidas de período y cero sustituciones indebidas de métrica.

### 3.1 Prueba crítica L03281

```
PRODUCT=L03281
PERIOD=JULY+AUGUST_2026
TOP_BILLED_CUSTOMER=FARMACORP S.A. (C000061)
TOP_BILLED_CUSTOMER_TOTAL_BS=115044.44
MONTHLY_BREAKDOWN=2026-07:72383.99 | 2026-08:42660.45
RECONCILIATION=PASS
CUSTOMER_TAXONOMY_WARNING=PASS
```

El desglose por cliente del producto reconcilia exactamente contra el total del producto en la unión de los dos meses: Bs 586.227,06 = Bs 271.255,49 (julio) + Bs 314.971,57 (agosto), sobre 2.014 líneas, 2.012 documentos y 468 cuentas facturadas, con 0 líneas en moneda distinta de BS.

La advertencia de taxonomía está presente en cada respuesta de cliente: «Cliente facturado en SAP» es la cuenta que recibe las líneas de factura, no el comprador final ni un cliente comercial validado; la taxonomía `customer_business_type` no está acreditada (0 clientes clasificados como comerciales) y por eso no se afirma cuál es el cliente comercial final. Las cuentas de control tributario de SAP se muestran y se cuantifican (4 de las 10 mostradas, Bs 192.577,96) y no se depuran, porque no existe una taxonomía acreditada que las distinga.

## 4. Fases

| Fase | Estado | Entregable | Verificación |
| --- | --- | --- | --- |
| F0 | PASS | Regresión del incidente del 21/10 y línea base | `test_business_conversation.py`: la mención con código de producto se rechaza y el estado previo sobrevive |
| F1 | PASS | Memoria de resultado (`/focus`, `result_references.interpreter_context`) | el turno posterior recupera producto, cliente, períodos y métrica desde el estado |
| F2 | PASS | Separación de entidades | `business_category` y `product_target` propios; la colisión se rechaza |
| F3 | PASS | Temporalidad conversacional | unión, comparación y continuidad; la unión nunca se colapsa |
| F4 | PASS | Familia cliente/producto | `commercial_line_amount_by_query` con reconciliación de tolerancia cero |
| F5 | PASS | Respuestas con riesgo | el texto entrega el resultado, la excepción, el riesgo y el próximo paso |
| F6 | PASS | Seguimientos | desglose mensual, otros productos, participación, ranking de clientes, variación |
| F7 | PASS | Batería integral | `BIZ01` 10/10 en el pipeline autenticado y persistido |

## 5. Operación

```
SIX_GATES=VALID
RUNTIME_CHANGED=YES
WHATSAPP_E2E=NOT_RUN
GIT_COMMIT=NO
GIT_PUSH=NO
```

- `SIX_GATES=VALID`: los cambios de código invalidan la huella de las seis garantías DEV. Se ejecutó el procedimiento local de revalidación (`data/reports/telchi/biz01-conversation-v1/six_gates_reaccredit.py`), la misma evidencia real de HTTP inerte, aislamiento de identidad, autorización comercial, idempotencia durable, Fundación y modelo sin fallback. El manifiesto privado se republicó con copia del anterior, ventana técnica de cuatro horas y `READY_FOR_MANUAL_START=YES`. Cero WhatsApp enviados, cero cambios de runtime, grants, bindings, webhook o Fundación; el runtime quedó `STOPPED`.
- `RUNTIME_CHANGED=YES`: cambia el comportamiento del asistente en DEV (alcance, plan, nueva capability, permisos). No cambia Srv01, Srv05, Foundation, SAP, RBAC de otros módulos ni Evolution.
- `WHATSAPP_E2E=NOT_RUN`: la validación por WhatsApp real es manual y pertenece al owner. No se envió ningún mensaje ni se inició el runtime.
- Permiso nuevo `telchi.sales.commercial_line_amount_by.read.v1` registrado en DEV por el mecanismo local idempotente, con backup privado: capability y permiso nuevos, **sin** asignaciones, roles, perfiles ni cambio de FULL_ACCESS.

## 6. Archivos

Código nuevo:

- `backend/modules/telchi/datalake/commercial_line_amount_by_query.py`
- `backend/modules/telchi/assistant/business_plan.py`
- `backend/modules/telchi/assistant/business_scope.py`
- `backend/modules/telchi/assistant/commercial_answer.py`
- `backend/modules/telchi/provisioning/commercial_by_repository.py`
- `backend/modules/telchi/provisioning/commercial_by_cli.py`
- `backend/modules/telchi/assistant/tests/test_business_conversation.py`
- `backend/modules/telchi/assistant/tests/test_biz01_evaluator.py`
- `backend/modules/telchi/assistant/tests/runtime_http/biz01_evaluator.py`
- `backend/modules/telchi/datalake/tests/test_commercial_line_amount_by_query.py`

Código modificado:

- `backend/modules/telchi/assistant/state_engine.py` (slots de alcance, unión de períodos, guardas semánticas)
- `backend/modules/telchi/assistant/capabilities.py` (disponibilidad, ejecución y formato de la familia nueva)
- `backend/modules/telchi/assistant/handler.py` (proyección de alcance, respuesta con resultado acreditado primero)
- `backend/modules/telchi/assistant/business_categories.py` (categoría dedicada, período del alcance)
- `backend/modules/telchi/assistant/result_references.py` (ámbito del resultado, presentación de la familia nueva)
- `backend/modules/telchi/assistant/luna.py` (contrato de alcance, unión, participación, enfoque por resultado)
- `backend/modules/telchi/datalake/category_line_amount_query.py` (origen y agregado compartidos y parametrizados)
- `backend/modules/telchi/datalake/foundation_reader_scan.py` (los ayudantes de prueba del asistente se clasifican como prueba)
- `backend/modules/telchi/assistant/tests/runtime_http/run_battery.py` (escenario BIZ01 y evaluación)
- `backend/modules/telchi/assistant/README.md`, `backend/modules/telchi/status_actual.md`

## 7. Pruebas

```
uv run pytest modules/telchi/assistant/tests modules/telchi/datalake/tests modules/telchi/provisioning/tests -q
1148 passed, 5 skipped
```

Los cinco skips son preexistentes (requieren condiciones opcionales del entorno). Se corrigió, dentro del alcance y sin relajar controles, un escaneo estático que no clasificaba los ayudantes de prueba del asistente y que ya fallaba antes de esta tarea.

## 8. Límites reales

- La taxonomía de cliente comercial sigue sin acreditar. No se fabricó ni se alteró: la respuesta declara la definición de "cliente facturado en SAP" y advierte el límite.
- La conversación depende del modelo para resolver pronombres y periods; el contrato, los slots, la plan y las guardas son deterministas. La evaluación comprueba el resultado acreditado y la continuidad del estado, no una frase literal.
- La cobertura de Foundation está acotada a la publicación vigente (`foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408) y a la cobertura observada; no se certifica el cierre completo de los períodos.
- El importe es el de líneas comerciales en BS: sin IVA de línea, antes de notas de crédito y sin ajustes globales. No es facturación documental neta ni monto cobrado, y así se dice en cada respuesta.
- El desglose por producto reparte líneas, no facturas: el importe de un producto es el de sus líneas y no incluye los demás productos de la misma factura.

## 9. Siguiente paso

Validación manual del owner por WhatsApp real con el launcher existente y el mismo hilo del piloto. La evidencia autenticada de esta tarea no sustituye esa entrega: `WHATSAPP_E2E` queda `NOT_RUN` hasta que se observen respuestas efectivamente entregadas.
