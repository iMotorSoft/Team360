# Telchi Context

Este documento es la autoridad canónica para el modelo de contexto, la arquitectura, los límites y las ubicaciones actuales de Telchi dentro de Team360.

## 1. Canonical context model

Toda tarea Telchi se comprende en el orden `ENTITY → DOMAIN → STAGE → SOURCES / OUTPUTS / POLICIES`. SAP, HANA, Data Lake, legacy, API y endpoint no son entidades, dominios ni etapas equivalentes.

| AXIS | MEANING |
| --- | --- |
| `ENTITY` | Contexto principal. Para este módulo, siempre `TELCHI`. |
| `DOMAIN` | Área funcional sobre la que se trabaja. |
| `STAGE` | Momento de la capacidad: `INVESTIGATION`, `DEVELOPMENT` o `PRODUCTION`. |
| `SOURCES` | Sistemas o insumos consultados, como `SAP_HANA`, `LEGACY_DS`, `LEGACY_DS0`, `RETAIL_ONE`, `DMS`, `EXTERNAL_FILES` o `DATA_LAKE`. |
| `OUTPUTS` | Resultado solicitado, como `ANALYSIS`, `REPORT`, `DATA_LAKE`, `PARQUET`, `SERVICE`, `API`, `ENDPOINT`, `DECISION` o `CONVERSATIONAL_CONTEXT`. |
| `POLICIES` | Restricciones aplicables, como `SAP_READ_ONLY`, `GIT_POLICY`, `PRIVATE_CONFIG`, `PROMOTION_REQUIRED` o `DATA_ROOT_DATA_ONLY`. |

Este vocabulario es conceptual; todavía no define enums, un resolver ni routing automático.

## 2. Entity

`TELCHI` es la entidad y el contexto principal. Su ownership lógico y root de software están en `SrvRestAstroLS_v1/backend/modules/telchi/`; Telchi no es un proyecto separado.

Una mención aislada de `SAP` o `HANA`, fuera de una conversación Telchi ya establecida, no confirma `ENTITY=TELCHI`. La ambigüedad debe conservarse o resolverse con una aclaración.

## 3. Functional domains

Los dominios son áreas funcionales, no sistemas fuente, outputs ni subáreas. Una subárea puede vivir bajo un dominio sin convertirse automáticamente en un nuevo contexto de routing.

| # | DOMAIN | CURRENT DOMAIN STATUS |
| ---: | --- | --- |
| 1 | `VENTAS` | `DEFINED` |
| 2 | `COBRANZAS` | `DEFINED` |
| 3 | `CRÉDITO_Y_DEUDORES` | `DEFINED` |
| 4 | `COMPRAS_Y_ABASTECIMIENTO` | `DEFINED` |
| 5 | `STOCK_E_INVENTARIOS` | `DEFINED` |
| 6 | `PRODUCCIÓN` | `DEFINED` |
| 7 | `TRANSFERENCIAS_Y_DEPÓSITOS` | `DEFINED` |
| 8 | `REPOSICIÓN` | `DEFINED` |
| 9 | `CLIENTES` | `DEFINED` |
| 10 | `PROVEEDORES` | `DEFINED` |
| 11 | `USUARIOS_ROLES_Y_PERMISOS` | `DEFINED` |
| 12 | `FORECAST_Y_ESTACIONALIDAD` | `DEFINED` |
| 13 | `TRAZABILIDAD_DOCUMENTAL` | `DEFINED` |
| 14 | `CONTABILIDAD` | `INCOMPLETE` / `INVESTIGATION_PENDING` |

`DEFINED` confirma pertenencia a la taxonomía y no declara que toda capacidad del dominio esté implementada. Contabilidad sigue incompleta porque aún no fue investigada con la profundidad de los demás dominios.

## 4. Stage model

Las etapas describen madurez e intención de trabajo. El flujo fundamental es `INVESTIGATION → DEVELOPMENT → PRODUCTION`, con promoción explícita y sin destruir la etapa anterior.

### 4.1. Investigation

`INVESTIGATION` descubre, analiza, audita, prueba y cierra semántica bajo `backend/modules/telchi/investigation/`.

Incluye SQL, análisis HANA, tests, gates, auditoría, reverse engineering, backtesting, reglas experimentales, validación y documentación investigativa. Si Telchi está confirmado y no existe intención explícita de desarrollo o producción, esta es la etapa por defecto.

### 4.2. Development

`DEVELOPMENT` toma conocimiento validado de investigation y construye una capacidad real del módulo bajo `backend/modules/telchi/`, fuera de `investigation/`.

Según una necesidad concreta puede incluir dominio, servicio, adapter, contrato, endpoint, API, productor de Data Lake, reader o inferencia runtime. No se crean capas preventivamente: cada desarrollo debe tener capacidad y consumidor definidos.

Pedir construir un endpoint, implementar un servicio, crear una API, transformar investigación en funcionalidad, desarrollar un productor real o construir capacidad runtime resuelve `STAGE=DEVELOPMENT`, no producción.

### 4.3. Production

`PRODUCTION` promueve una capacidad Development ya validada al runtime productivo y siempre requiere un gate explícito.

Crear o implementar un endpoint no equivale a desplegarlo. Solo pedidos explícitos de desplegar, promover a producción, habilitar runtime productivo o publicar una capacidad desarrollada resuelven esta etapa.

## 5. Default routing rules

Las reglas por defecto minimizan promociones accidentales y mantienen la investigación como destino seguro.

- `TELCHI confirmado + DOMAIN conocido + STAGE ausente → INVESTIGATION`.
- `INVESTIGATION_BY_DEFAULT=YES`.
- `PRODUCTIVE_ONLY_WHEN_EXPLICIT=YES`.
- Una petición explícita de construir funcionalidad resuelve `DEVELOPMENT`.
- Una petición explícita de desplegar o habilitar una capacidad ya desarrollada resuelve `PRODUCTION`.
- Una fuente u output mencionados no sustituyen al dominio ni a la etapa.

## 6. Source model

Las fuentes indican de dónde proviene la información. No constituyen etapas ni intents principales.

### 6.1. SAP Business One / HANA

`SAP_HANA` es una fuente operacional principal de Telchi. Dentro de investigation se consulta `READ ONLY` por defecto y mantiene `SAP_WRITE_COUNT=0`.

En un contexto Telchi activo, “HANA ventas”, “SAP ventas”, “Telchi ventas” o “revisemos ventas” pueden converger en `ENTITY=TELCHI`, `DOMAIN=VENTAS`, `STAGE=INVESTIGATION`; cuando la tarea requiere datos operacionales y no indica otra fuente, puede resolver `SOURCE=SAP_HANA`.

No existe routing independiente para SAP Telchi. Consultar, auditar, reconciliar, validar, medir y extraer datasets aprobados está permitido; modificar SAP no lo está.

### 6.2. Legacy DS / DS0

`LEGACY_DS` y `LEGACY_DS0` son fuentes históricas externas y `READ ONLY`; no son dominio, etapa ni ubicación de nuevo desarrollo.

Las capacidades nuevas no se desarrollan dentro de `LEGACY_ROOT`. Una comparación puede usar varias fuentes, por ejemplo `SOURCES=[LEGACY_DS0, SAP_HANA]`.

### 6.3. Other sources

`RETAIL_ONE`, `DMS`, `EXTERNAL_FILES` y `DATA_LAKE` pueden actuar como fuentes cuando una tarea consume información de esos sistemas o soportes.

Su mención añade una facet de fuente y no crea por sí sola una entidad, dominio o etapa nueva.

## 7. Output and Data Lake model

Data Lake es infraestructura transversal y puede ser fuente u output según el flujo; no es un intent principal de Telchi.

`DATA_ROOT != DEVELOPMENT_ROOT`. El software productor, reader, Python, SQL fuente, tests y documentación se desarrolla en Team360; Parquet, datasets, snapshots, staging físico, manifests y caches aprobados van a `DATA_ROOT`.

Para “generar Parquet de compras”, el contexto conserva `DOMAIN=COMPRAS_Y_ABASTECIMIENTO`; la tarea decide `INVESTIGATION` o `DEVELOPMENT`, añade `OUTPUTS=[DATA_LAKE, PARQUET]` y resuelve `physical_output_root=DATA_ROOT`. Nunca se escribe source en Data Root.

## 8. Promotion model

La promoción crea una implementación separada sin mover ni destruir investigation. Cada transición requiere evidencia y una intención explícita.

```text
INVESTIGATION
    ↓ validated knowledge + explicit promotion
DEVELOPMENT
    ↓ validated capability + explicit production gate
PRODUCTION
```

Investigation permanece como baseline, auditoría, evidencia, regresión y origen semántico. Development materializa una capacidad candidata fuera de `investigation/`. Production habilita esa capacidad ya validada en runtime.

Está prohibido que el código productivo importe runners de `investigation/`. La promoción debe preservar contratos, lineage y pruebas relevantes sin convertir artefactos experimentales en dependencias runtime.

## 9. Canonical debt promotion example

Deudas es el ejemplo oficial del ciclo completo. Su estado actual es `ENTITY=TELCHI`, `DOMAIN=CRÉDITO_Y_DEUDORES`, `STAGE=INVESTIGATION`.

El conocimiento investigado incluye deuda, deuda vencida, aging, pagos, pagos parciales, crédito, límites, excepciones, autorizaciones, riesgo abierto, reconstrucción histórica y trazabilidad documental.

“Quiero pasar el manejo de deudas de investigación a desarrollo de endpoint” resuelve el siguiente contrato conceptual:

```text
entity=TELCHI
domain=CRÉDITO_Y_DEUDORES
stage=DEVELOPMENT
source_of_knowledge=investigation correspondiente
target=MODULE_ROOT fuera de investigation
outputs=[SERVICE, ENDPOINT, CONTRACT, TESTS]
promotion_required=YES
```

La investigación original permanece intacta. Después de validar esa implementación, “el endpoint de deudas ya funciona, pasémoslo a producción” resuelve `STAGE=PRODUCTION` y `promotion_required=YES`; no salta directamente de investigation a runtime.

## 10. Canonical locations

Estas ubicaciones separan software, datos, configuración privada y fuentes históricas. `CURRENT` significa que existe hoy; `FUTURE` no autoriza capas preventivas.

| CONCEPT | PATH | PURPOSE | POLICY |
| --- | --- | --- | --- |
| `REPOSITORY_ROOT` | raíz Git Team360 | Repositorio compartido | Respetar ownership y política Git |
| `MODULE_ROOT` | `SrvRestAstroLS_v1/backend/modules/telchi/` | Software Telchi (`CURRENT`) | Development vive aquí fuera de `investigation/` solo con capacidad concreta |
| `INVESTIGATION_ROOT` | `SrvRestAstroLS_v1/backend/modules/telchi/investigation/` | Investigación Telchi (`CURRENT`) | Default de trabajo Telchi no productivo |
| `DATA_ROOT` | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/lab/dataclient/telchi` | Datos físicos (`CURRENT`) | `DATA ONLY`; no es source root |
| `PRIVATE_ROOT` | `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi` | Configuración y secretos (`CURRENT`) | Fuera de Git y del Data Root |
| `LEGACY_ROOT` | `/media/issajar/DEVELOP/Projects/telchi/Insiding/DataScience` | DS/DS0 históricos | Consulta read-only; sin nuevo desarrollo |

La estructura física actual de `DATA_ROOT` es `atomic/`, `business/`, `decision/`, `manifests/`, `raw/`, `snapshots/` y `staging/`. El package histórico `investigation/datalake/` no es el Data Lake físico.

## 11. Root resolution contract

El futuro resolver portable deberá producir este contrato conceptual, sin que esta documentación implique su implementación técnica.

| FIELD | PURPOSE |
| --- | --- |
| `entity`, `entity_confidence` | Entidad resuelta y confianza de esa resolución |
| `domain`, `domain_status` | Área funcional y estado vigente del dominio |
| `stage`, `stage_confidence` | Etapa y confianza de esa resolución |
| `sources`, `outputs` | Fuentes consultadas y resultados esperados |
| `context_files` | Documentos de autoridad cargados |
| `repository_root`, `module_root`, `investigation_root` | Roots versionados relevantes |
| `source_root` | Root de source code elegido para la tarea |
| `physical_output_root`, `data_root` | Destino físico autorizado y Data Root |
| `private_root`, `legacy_root` | Configuración privada y fuente histórica externa |
| `sap_policy`, `write_policy`, `git_policy` | Políticas efectivas de acceso y escritura |
| `promotion_required` | Si la transición exige gate de promoción |
| `ambiguity`, `resolution_reason` | Ambigüedad preservada y fundamento de resolución |

No se agregan enums ni un schema técnico hasta que exista una implementación aprobada.

## 12. Canonical examples

Estos ejemplos validan el idioma común. Los resultados omiten campos no relevantes y asumen contexto conversacional solo cuando se indica.

| PROMPT | CONTEXT | RESULT |
| --- | --- | --- |
| “Telchi ventas” | Ninguno previo | `ENTITY=TELCHI; DOMAIN=VENTAS; STAGE=INVESTIGATION` |
| “HANA ventas” | Conversación Telchi | `ENTITY=TELCHI; DOMAIN=VENTAS; STAGE=INVESTIGATION; SOURCE=SAP_HANA; SAP_POLICY=READ_ONLY` |
| “probar compras en SAP” | Conversación Telchi | `ENTITY=TELCHI; DOMAIN=COMPRAS_Y_ABASTECIMIENTO; STAGE=INVESTIGATION; SOURCE=SAP_HANA` |
| “Telchi compras” | Ninguno previo | `ENTITY=TELCHI; DOMAIN=COMPRAS_Y_ABASTECIMIENTO; STAGE=INVESTIGATION` |
| “generar parquet de compras” | Conversación Telchi | `DOMAIN=COMPRAS_Y_ABASTECIMIENTO; OUTPUTS=[DATA_LAKE, PARQUET]; physical_output_root=DATA_ROOT; STAGE=INVESTIGATION o DEVELOPMENT según la tarea` |
| “quiero pasar deudas a desarrollo de endpoint” | Conversación Telchi | `DOMAIN=CRÉDITO_Y_DEUDORES; STAGE=DEVELOPMENT; OUTPUT=ENDPOINT; promotion_required=YES` |
| “el endpoint de deudas ya funciona, pasémoslo a producción” | Conversación Telchi | `DOMAIN=CRÉDITO_Y_DEUDORES; STAGE=PRODUCTION; promotion_required=YES` |
| “comparar ventas DS0 con HANA” | Conversación Telchi | `DOMAIN=VENTAS; STAGE=INVESTIGATION; SOURCES=[LEGACY_DS0, SAP_HANA]` |
| “analizar contabilidad” | Conversación Telchi | `DOMAIN=CONTABILIDAD; STAGE=INVESTIGATION; DOMAIN_STATUS=INCOMPLETE` |

Una frase aislada como “SAP” o “HANA” sin contexto Telchi no aparece como ejemplo de resolución automática porque debe permanecer ambigua.

## 13. Policies

Las políticas se aplican después de resolver entidad, dominio, etapa, fuentes y outputs; no compiten con esos ejes.

- `SAP_READ_ONLY`: default de SAP/HANA durante investigation; `SAP_WRITE_COUNT=0`.
- `GIT_POLICY`: preservar ownership, cambios concurrentes y restricciones Git del proyecto.
- `PRIVATE_CONFIG`: secretos y configuración privada únicamente en `PRIVATE_ROOT`.
- `PROMOTION_REQUIRED`: obligatorio para pasar a Development desde conocimiento investigado y para habilitar Production.
- `DATA_ROOT_DATA_ONLY`: ningún Python, SQL fuente, test, Markdown fuente, `.venv`, `.env` o secreto en `DATA_ROOT`.
- `LEGACY_READ_ONLY`: DS/DS0 se consultan sin desarrollar nuevas capacidades allí.
- `SHARED_HOST_SAFETY`: aplicar siempre la sección 19, incluso si el prompt solo pide ejecutar un gate; complementar la política global de `AGENTS.md` sin sustituir guards existentes.

## 14. Multi-agent authority

El modelo es tool-agnostic. Pi, Codex CLI, OpenCode, OMP / Oh My Pi y agentes futuros deben llegar a esta misma autoridad mediante instrucciones de proyecto mínimas.

```text
PI / CODEX CLI / OPENCODE / OMP / OTHER
                    ↓
       AGENTS.md / project instructions
                    ↓
     backend/modules/telchi/CONTEXT.md
```

`CONTEXT.md` es `SOURCE_OF_TRUTH`. Las configuraciones particulares no deben duplicar reglas funcionales Telchi; solo pueden actuar como adaptadores mínimos.

La regla raíz de `AGENTS.md` ya exige cargar este archivo antes de elegir paths, ejecutar scripts o escribir, y resolver dominio, etapa, fuentes y outputs. Telchi queda en investigation salvo Development o Production explícitos.

## 15. Documentation authority

La jerarquía evita duplicación entre contrato, introducción, operación investigativa y evidencia histórica.

| PRIORITY | FILE | PURPOSE |
| ---: | --- | --- |
| 1 | `backend/modules/telchi/CONTEXT.md` | Autoridad única del modelo, arquitectura, límites y roots actuales |
| 2 | `backend/modules/telchi/CONTEXT_ROUTING_DESIGN.md` | Nota de diseño subordinada y transición desde el modelo sustituido |
| 3 | `backend/modules/telchi/README.md` y `status_actual.md` | Introducción y estado local; no sustituyen CONTEXT |
| 4 | `backend/modules/telchi/investigation/README.md` | Operación de investigation |
| 5 | `investigation/LAT.md`, `DECISIONS.md`, `STATUS_ACTUAL.md` y reportes | Evidencia o historia; no autoridad actual |
| 6 | `SrvRestAstroLS_v1/docs/status_actual.md` | Estado global de Team360 |

Si una referencia histórica contradice este archivo, `CONTEXT.md` prevalece. La historia se conserva y se etiqueta, no se reescribe como si el modelo anterior nunca hubiera existido.

## 16. Superseded routing concepts

El modelo anterior agrupaba sistemas, infraestructura y madurez como intents pares. Esta decisión posterior sustituye solo esa parte conceptual; su auditoría técnica de agentes y herramientas sigue siendo válida.

| OLD DESCRIPTIVE LABEL | NEW CLASSIFICATION | REASON |
| --- | --- | --- |
| `TELCHI_SAP` | `ENTITY=TELCHI` + dominio + etapa + `SOURCE=SAP_HANA` | SAP/HANA aporta datos; no define el trabajo funcional ni su madurez |
| `TELCHI_DATALAKE` | `ENTITY=TELCHI` + dominio + etapa + `SOURCE/OUTPUT=DATA_LAKE` | Data Lake es infraestructura transversal |
| `TELCHI_LEGACY` | `ENTITY=TELCHI` + dominio + etapa + `SOURCE=LEGACY_DS` o `LEGACY_DS0` | Legacy es fuente histórica read-only |
| `TELCHI_PRODUCTIVE_MODULE` | `ENTITY=TELCHI` + dominio + `STAGE=DEVELOPMENT` o `PRODUCTION` | Desarrollo y producción son etapas distintas y exigen promoción explícita |

Esos nombres pueden permanecer en gates, filenames o reportes históricos. No deben interpretarse como contexts o intents vigentes equivalentes.

## 17. Before changing Telchi

Antes de elegir paths o escribir, se debe resolver el contexto conceptual y aplicar sus políticas.

1. Leer este `CONTEXT.md`.
2. Confirmar `ENTITY=TELCHI`; no inferirla de “SAP” o “HANA” aislados.
3. Resolver el dominio funcional.
4. Resolver la etapa; usar `INVESTIGATION` por defecto.
5. Identificar fuentes, outputs y roots físicos sin confundirlos con source code.
6. Aplicar políticas SAP, Git, secretos, legacy y promoción.
7. Preservar el scope `MODULE_LOCAL` y los cambios concurrentes.
8. No crear capas preventivas ni importar runners de investigation desde código productivo.

## 18. Current implementation status

Este gate alinea documentación; no implementa routing, endpoints ni runtime y no modifica SAP, Data Root, Private Root o Legacy Root.

El módulo y su árbol de investigation existen; `AGENTS.md` ya carga este contexto. API formal, `routes.py`, scheduler y resolver automático no se declaran implementados. El [estado local](status_actual.md) distingue Foundation, candidatos y frontend en trabajo sin gate/deploy. SAP/HANA permanece read-only con `SAP_WRITE_COUNT=0`.

## 19. Shared development host safety

Esta política operativa aplica automáticamente en todas las etapas Telchi: Data Lake, Foundation, investigations, business analysis, tests, scans, materialización, lineage, parity/gold, UI y promociones.

### 19.1. Preflight y concurrencia adaptativa

El guard protege la capacidad compartida y permite aprovechar recursos libres. Sigue `USE AVAILABLE CAPACITY, DO NOT DESTABILIZE THE HOST` y `CORRECTNESS > HOST STABILITY > SPEED` de `AGENTS.md`.

- Una consulta SQL pequeña no necesita ceremonia; un test local necesita un contexto rápido. Suites grandes (por ejemplo 200+ tests), scans grandes, Chromium, benchmarks y operaciones largas requieren guard explícito; toda promoción Foundation exige preflight.
- Antes de carga intensiva, observar sin modificar el host load relativo a cores disponibles, CPU aproximada, `MemAvailable`, swap usada y su crecimiento, procesos pesados y runners activos. Para scans/materialización, incluir disco y espacio temporal.
- En Linux pueden usarse `uptime`, `nproc`, `free -m`, `vmstat 1 3` y `ps -eo pid,ppid,comm,pcpu,pmem,rss --sort=-pcpu`. Evitar exponer argumentos o entornos con secretos. Si faltan métricas, no asumir host libre: completar observación o diferir carga pesada.
- Evaluar señales conjuntamente y repetir observación cuando haya dudas o durante una ejecución larga, entre segmentos. No decidir solo por `load > N` o `RAM < X`; un pico corto o swap histórica estable no equivalen por sí solos a peligro.
- `SAFE`: capacidad libre permite concurrencia moderada. `BUSY_BUT_SAFE`: reducir workers y threads; con carga alta, focalizar/secuenciar. `UNSAFE`: presión sostenida, swap creciente, agotamiento inminente o degradación visible impiden iniciar carga intensiva.
- Elegir presupuesto conservador según capacidad real y memoria estimada por worker; sumar pools, threads DuckDB/numéricos, browsers y procesos hijos. No fijar un número universal ni imponer single-thread siempre; escalar progresivamente con observación.
- El guard existente en `runtime/resource_guard.py` conserva sus límites y `SAFE_ABORT`: esta política complementa su preflight y checks continuos, no autoriza ignorarlos ni elevar límites para obtener PASS. Un aborto del guard impide confiar candidatos o avanzar watermarks.

### 19.2. Orden y evidencia reutilizable

La ejecución comienza por la garantía más barata y solo amplía el alcance cuando la tarea lo necesita. No lanzar todas las validaciones simultáneamente.

1. Inspección barata de contexto, diff y evidencia disponible.
2. Validaciones estáticas.
3. Tests focalizados.
4. Consulta o scan necesario y acotado.
5. Parity/gold focalizado.
6. Suite ampliada solo si agrega una garantía necesaria.
7. Chromium/UI solo cuando corresponde al comportamiento afectado.

Reutilizar tests PASS, hashes, parity/gold, candidate validation y artefactos cuando correspondan al código, inputs, configuración y garantía actuales. Registrar origen y por qué siguen válidos; recencia sola no basta. Reejecutar lo invalidado por el cambio, sin repetir suites caras por ritual.

### 19.3. Pytest, DuckDB y PostgreSQL

Tests y consultas comparten el presupuesto del host. Las decisiones de concurrencia se toman antes de iniciar cada workload relevante.

- Pytest: comenzar con paths focalizados; no usar automáticamente `pytest -n auto` ni equivalentes de todos los cores. Si paralelizar es necesario y está disponible, elegir `-n <N>` conservador tras preflight y registrar N en ejecuciones relevantes. Evitar suites masivas simultáneas o repetidas sin evidencia invalidada.
- DuckDB/Parquet: elegir threads razonables, por ejemplo `PRAGMA threads=<N>` en la conexión propia, reducirlos con host ocupado y ajustar memoria/temp según capacidad. No hardcodear 1 universalmente ni ejecutar múltiples scans grandes simultáneos.
- Acotar particiones, columnas y fechas; evitar leer todo Data Lake si un scan focalizado resuelve la pregunta. Reutilizar resultados/materializaciones productivos válidos y capacidad existente de Foundation antes de repetir discovery; respetar permisos y validez, sin modificar esos artefactos para ahorrar trabajo.
- PostgreSQL: consultas acotadas y conexiones/concurrencia limitadas de la tarea; respetar pools y política DB vigentes. No reconfigurar ni reiniciar el servidor compartido para obtener capacidad.

### 19.4. Browsers y ownership de procesos

La atribución de procesos pertenece a la ejecución actual; compartir nombre, puerto o repositorio no prueba ownership.

- Antes de crear runners, workers, Chromium o servidores temporales, conservar baseline y registrar handles/PID, identidad de inicio y relación de hijos propios. Reutilizar servicios disponibles; no cerrar browsers existentes.
- Evitar múltiples instancias de Chromium simultáneas salvo necesidad real y presupuesto demostrado. Cerrar contexts/browsers propios al terminar, también ante fallo o interrupción controlada.
- NO terminar procesos que la ejecución actual no haya creado. Prohibidos `killall`, `pkill` genérico y matar backend/frontend, PostgreSQL, browsers, IDE u otros agentes ajenos; no reiniciar servicios para liberar recursos.
- Cleanup: cerrar primero mediante su lifecycle; verificar hijos y workers propios, incluidos pytest, scripts y servidores temporales. Antes de señalizar, comprobar identidad y ownership para evitar PID reutilizados. Si hay dudas, dejar intacto y reportar atribución pendiente.
- Ante presión, no iniciar carga nueva; reducir próximos segmentos y concurrencia, preservar evidencia/checkpoints y detener solo workers propios si es seguro. No acumular runners ni hacer retry intensivo para conseguir PASS.

### 19.5. Foundation promotions y estados

Toda promoción Foundation requiere resource preflight antes de iniciar y comprobación de condiciones antes del commit. Estabilidad del host, atomicidad, integridad y rollback preceden a velocidad.

- `BLOCKED_HOST` es el motivo de host inseguro del estado `RESOURCE_BLOCKED`; es válido para un gate de promoción y nunca equivale a PASS ni a promoción completada. No iniciar promoción bajo presión.
- Si aparece presión durante una promoción, usar el protocolo existente de safe abort/rollback y preservar atomicidad; no matar procesos a mitad del commit ni inventar una recuperación que deje estado parcial. Reanudar solo tras nueva evaluación y verificar estado/checkpoints.
- `FUNCTIONAL_FAILURE`: test, lógica o gate falla con defecto funcional demostrado.
- `RESOURCE_BLOCKED`: ejecución diferida o detenida de forma segura por recursos; no es test failure.
- `ENVIRONMENTAL_ABORT`: interrupción por recursos/entorno sin defecto funcional demostrado. Conservar logs, salida y evidencia para diagnosticar; no atribuir automáticamente cualquier fallo al ambiente ni modificar lógica para ocultarlo.
- Reportar separadamente fallos funcionales, bloqueos y abortos ambientales; evidencia previa no demuestra PASS de una ejecución abortada.

### 19.6. Reporte y cierre del guard

Gates, promociones, suites grandes, benchmarks y operaciones largas reportan la evaluación y el presupuesto real; consultas triviales no necesitan esta salida.

```text
HOST_PREFLIGHT=<SAFE|BUSY_BUT_SAFE|UNSAFE>
RESOURCE_GUARD=<PASS|BLOCKED>
CONCURRENCY_USED=<N>
UNRELATED_PROCESSES_TERMINATED=0
ENVIRONMENTAL_ABORTS=<N>
OWN_PROCESSES_LEFT_RUNNING=<N>
```

Explicar N (workers, threads por conexión e instancias browser según corresponda), señales observadas y cambios de presupuesto. `RESOURCE_GUARD=PASS` describe seguridad de recursos, no éxito funcional. Cleanup verificado debe dar `OWN_PROCESSES_LEFT_RUNNING=0`; si no se confirma, declarar cantidad conocida o `UNKNOWN` y motivo, nunca inventar cero. Preservar procesos ajenos y no declarar PASS del guard mientras queden procesos propios sin resolver.
