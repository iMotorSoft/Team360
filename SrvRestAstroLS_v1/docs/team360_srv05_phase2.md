# Team360 Srv05 — Fase 2 declarativa

La arquitectura comprobada queda consultable sin alterar imports ASGI, configuración, rutas, lifecycle ni deployment. Rama: `feature/console-backend-core`. Evidencia local del worktree; no certifica disponibilidad remota.

## Alcance y ubicación

El inventario describe componentes y relaciones. No compone handlers, selecciona stack ni ejecuta servicios. El registro HTTP existente mantiene su ownership y sus cambios preexistentes de Messaging.

- Nuevo [registro declarativo](../backend/modules/srv05_architecture.py), dentro de la convención backend `modules/`.
- Nuevos [tests de arquitectura](../backend/tests/test_srv05_architecture.py).
- Este informe es el único documento creado; status y documentación preexistentes se preservan.
- [Registry HTTP](../backend/modules/module_registry.py) inspeccionado con su diff, sin edición: su responsabilidad es composición de rutas, no inventario arquitectónico.
- [Srv05](../backend/ls_iMotorSoft_Srv05.py) intacto: continúa reexportando exactamente `app` y `create_app` de Srv01. Inspección mediante API Python independiente, sin nuevos endpoints/imports del entrypoint.
- Baseline: [evidencia Fase 1](team360_srv05_phase1.md), verificada contra las fuentes referenciadas en cada definición y asociación.

## Estructura y consultas

Las definiciones son dataclasses frozen con tuplas, referencias validadas y orden explícito. No leen environment, secretos, DB ni estado de servicios; las consultas desconocidas fallan en vez de declarar ausencia de dependencia.

- `ModuleDefinition`: código, baseline funcional, criticidad, dependencias por capacidad, superficies, bindings y evidencia.
- `ServiceDefinition`: código único, scope horizontal/local, categoría, criticidad, ejecución externa/in-process, descripción y evidencia.
- `ServiceDependency`: servicio, clasificación, capacidad, condición/rationale y evidencia.
- `BindingDefinition`: módulo, superficie, tipo de relación, identificador embed, servicio de almacenamiento y contexto comprobado.
- `ConfigurationAssociation`: nombres de variables, consumidores y efecto observado; no guarda valores ni implementa resolución de configuración.
- `ArchitectureRegistry`: valida unicidad, referencias, pertenencia del binding/superficie y clasificaciones; permite inspección determinística e inmutable.
- `Environment`, `Secret`, `Client/Tenant` y `Distributor` **no** son entidades provisionadas por este registro. `distributor_embed` expresa el rol de una relación comprobada, no crea un distribuidor operacional.

Ejemplo de uso, desde el backend:

```python
from modules.srv05_architecture import (
    REGISTRY,
    get_module_definition,
    get_module_dependencies,
    get_service_consumers,
    get_module_bindings,
)

assert get_module_definition("diagnosis").surfaces == ("home", "web", "embed")
assert tuple(d.service for d in get_module_dependencies("flow", "required")) == ("postgres",)
assert REGISTRY.dependency_kind("flow", "milvus") == "unrelated"
assert get_service_consumers("postgres") == ("flow", "diagnosis")
assert get_service_consumers("milvus") == ("diagnosis",)
assert get_module_bindings("diagnosis")[0].binding_type == "distributor_embed"
```

## Módulos y servicios

Sólo se registran Flow y Diagnosis. Las consultas de consumidores se limitan a esos módulos: no pretenden inventariar todos los consumidores del repositorio ni confunden existencia con disponibilidad operacional.

| Servicio | Scope / ejecución | Criticidad | Consumidores registrados |
| --- | --- | --- | --- |
| `postgres` | Horizontal / externo | Core | Flow, Diagnosis |
| `milvus` | Horizontal / externo, Milvus 2.6 | Core para retrieval real | Diagnosis |
| `litellm` | Horizontal / externo | Core IA real | Flow por capacidad, Diagnosis |
| `gmail` | Horizontal / externo | Capacidad | Flow condicional |
| `scheduler` | **Module-local** / tarea asyncio | Capacidad | Flow |
| `gupshup` | Horizontal / externo | Capacidad | Flow inbound |
| `evolution` | Horizontal / externo | Capacidad | Ninguno dentro de este inventario |
| `auth_permissions` | Horizontal / in-process y permisos PG | Capacidad | Flow autenticado |

Evolution tiene adapter concreto en Messaging DEV y queda reconocido como servicio horizontal potencialmente compartido. Messaging es consumidor real fuera del conjunto registrado, no una dependencia inventada de Flow/Diagnosis. No se inventan bindings, WABA ni números.

## Clasificación Flow

Required expresa función base, no requisitos del import ASGI. Optional habilita capacidades adicionales; runtime_conditional describe caminos activados por settings/modos. Las capacidades pueden exigir otros servicios al ejecutarse.

| Servicio | Clasificación | Evidencia/condición |
| --- | --- | --- |
| PostgreSQL | `required` | Repositories de casos, routing, SLA, auditoría y configuración |
| Scheduler | `optional` | Automatización periódica; CLI finita/manual no lo necesita. Srv01 **todavía lo arranca siempre** |
| Gmail | `runtime_conditional` | Polling, replies, reenvío/delivery. Scheduler crea Gmail con mail intake activo dentro de automatización habilitada |
| LiteLLM | `optional` | Obligatorio dentro de interpretación IA intake/operacional/aprobación/resumen; no para lectura simple/settings. `TEAM360_AI_PROVIDER` no es un switch universal Flow |
| Gupshup | `optional` | Bridge inbound existente con intake LiteLLM y claimer PG; replies outbound no-op |
| Auth/Permissions | `runtime_conditional` | `TEAM360_FLOW_ACCESS_MODE=authenticated`; default_admin conserva identidad MVP sintética |
| Milvus / Evolution | `unrelated` | Ausentes del grafo Flow; tests negativos explícitos |

No se intenta un resolver de capacidades ni se garantiza un stack mínimo. La dependencia funcional del scheduler y su arranque actual son conceptos distintos que este inventario documenta, pero no desacopla.

## Clasificación Diagnosis y Mamamia360

El baseline declarado es el Diagnóstico público **real** Vera: contexto/estado persistente, retrieval scoped y generación/classifier/embeddings reales. Las alternativas de desarrollo no satisfacen esa misma función.

- PostgreSQL: `required` para contexto/estado real y bindings `embed_clients`. Estado memory sigue implementado; no se modifica su prioridad de selección.
- Milvus: `required` para retrieval real; builder público lo selecciona por URI/host, no únicamente por `TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER`. Sin conexión configurada existe NullRetrieval; no se equipara a retrieval real.
- LiteLLM: `required` para IA/embeddings reales; safe acknowledgements/mock existentes no son equivalentes funcionales. No se cambian fallbacks.
- Superficies: `home`, `web`, `embed`, con fuentes Astro/backend referenciadas en el registro.
- Gmail, scheduler Flow, Gupshup, Evolution y login/capabilities Console no se convierten en dependencias del turn público. Los controles HMAC/origin del embed siguen en su implementación, no se confunden con auth enterprise compartida.
- Binding único: `mamamia360_embed`, identificador DB `mamamia360`, tipo `distributor_embed`, superficie `embed`, almacenamiento PostgreSQL.
- Contexto: `team360_sales_diagnosis / team360_live / team360_public_site / pkg_sales_diagnosis / ks_team360_sales_diagnosis`.
- Ese contexto está respaldado por migration 009 y snapshot DEV de Fase 1. El inventario no sobreescribe la fila DB, origins ni HMAC; no asegura que el binding remoto tenga hoy el mismo estado.
- Mamamia360 no se registra como servicio horizontal ni cliente/tenant DB independiente. NETZAJ/Galil permanecen fixtures UX fuera del registro.

## Configuración declarada, consumidor y efecto

Las asociaciones son explicativas y contienen sólo nombres. No migran variables, leen sus valores ni determinan quién arranca qué. Los consumidores efectivos siguen siendo el código existente, no el nuevo registro.

| Variables | Consumidor efectivo | Efecto observado |
| --- | --- | --- |
| `AUTOMATION_DIAGNOSIS_REPOSITORY`, `TEAM360_DIAGNOSIS_STATE_PROVIDER` | Automation service / public state builder | Automation postgres crea pool lazy global; estado público prioriza repository sobre state provider. Pool sigue acoplado al bootstrap Diagnosis y afecta Flow |
| `TEAM360_AI_PROVIDER` | Interpreter Diagnosis / generación pública | Selección Diagnosis; no desactiva adapters Flow |
| `TEAM360_LITELLM_BASE_URL`, `TEAM360_LITELLM_MODEL_ALIAS`, `TEAM360_LITELLM_API_MODE` | LiteLLMClient y adapters Flow/Diagnosis | Gateway/alias/API policy; HTTP embeddings usa BASE_URL y alias embedding propio |
| `TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER` | Legacy Milvus knowledge / public embedding provider | Selección legacy y endurecimiento de errores embeddings público; selección pública retrieval depende de URI/host |
| `TEAM360_MILVUS_URI`, `TEAM360_MILVUS_HOST`, `TEAM360_MILVUS_PORT`, `TEAM360_MILVUS_COLLECTION` | MilvusRuntimeConfig | Conexión lazy/índice; no provisioning |
| `TEAM360_EMBEDDING_VERSION`, `TEAM360_KNOWLEDGE_SCOPE_ID` | MilvusRuntimeConfig | Filtros scope/version; contexto público DB resuelve UUID por separado |
| `TEAM360_EMBEDDING_MODEL` | Provider embeddings público | Alias embedding |
| `TEAM360_FLOW_ACCESS_MODE` | Flow access policy | default_admin/authenticated |
| `TEAM360_FLOW_GMAIL_ACCOUNT`, `TEAM360_GMAIL_DELEGATED_USER`, `TEAM360_GMAIL_SERVICE_ACCOUNT_FILE` | Flow/Gmail provider | Subject delegado y referencia privada al archivo de credenciales |
| `TEAM360_PUBLIC_ORGANIZATION_CODE`, `TEAM360_PUBLIC_WORKSPACE_CODE`, `TEAM360_PUBLIC_PACKAGE_CODE`, `TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE` | Export/log launcher; **sin consumidor resolutor Python inspeccionado** | Marcadores operativos. Defaults/allowlist de rutas y fila embed DB gobiernan el contexto efectivo |

`TEAM360_PUBLIC_*` aparece ahora también como metadata declarativa, lo cual **no** lo convierte en un consumidor runtime. El comportamiento existente y la distinción variable declarada/consumidor/efecto permanecen intactos. Secretos y valores productivos siguen fuera del registro.

## Validación ejecutada

Las pruebas usan memory/mock y no habilitan tests DB opt-in ni envíos reales. El host permitió una ejecución secuencial, con threads internos limitados y sin levantar/reiniciar servicios.

- Tests nuevos: **38**, cubren clasificaciones, casos unrelated, superficies/binding distribuidor, unicidad, consumidores, determinismo, errores por códigos desconocidos, inmutabilidad, referencias inválidas, evidencia/configuración e import sin I/O/workers/rutas.
- `uv run --no-sync pytest -q tests/test_srv05_architecture.py tests/test_srv05_compatibility.py tests/test_srv05_launchers.py`: **45 passed**, incluidos los 7 tests Fase 1.
- Regresión focalizada reproducible debajo: **1588 passed, 48 skipped**, 31,73 s; warning esperado de estado memory. uv advierte la deprecación preexistente de dev-dependencies.
- `lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: **PASS**. LAT advierte ausencia de init/key semántica, sin fallos. Encabezados/párrafos y enlaces locales del documento nuevo comprobados además explícitamente.
- Revisión final y whitespace check de los tres archivos nuevos: **PASS**. Comparación SHA-256: todos los diffs tracked preexistentes más Srv01/Srv05/tests Fase 1 permanecen byte-identical. No commit/stage ni cambio de rama; no quedan procesos pytest/Uvicorn propios.

Comando de regresión:

```bash
cd SrvRestAstroLS_v1/backend
AUTOMATION_DIAGNOSIS_REPOSITORY=memory TEAM360_AI_PROVIDER=mock \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --no-sync pytest -q \
  tests/test_flow_*.py tests/test_gmail_flow_normalization.py \
  tests/test_diagnosis_public_router.py tests/test_embed_clients_contract.py \
  tests/test_automation_diagnosis*.py tests/test_sales_diagnosis*.py \
  tests/test_structured_diagnosis.py tests/test_console_*.py \
  tests/test_messaging_gupshup_*.py tests/test_messaging_whatsapp_*.py \
  tests/test_messaging_evolution.py tests/test_module_registry.py tests/test_srv05_*.py
```

## Límites, riesgos y Fase 3

La fase es declarativa: prueba describibilidad/compatibilidad, no independencia operacional ni seguridad multi-tenant nueva. El registro es explícito y necesitará revisión cuando cambie el código consumidor.

- Intactos: Srv01/Srv05, registry HTTP, globalVar, pyproject/lockfiles, launchers, producción, URLs/puertos, migraciones y todos los scopes preexistentes.
- Startup continúa `PostgreSQL pool → Flow scheduler`; shutdown continúa `Flow scheduler → PostgreSQL pool`. Ninguna decisión de lifecycle consume este registro.
- No hay ejecución autónoma, `--module`, resolver de stack, start/stop de infraestructura, orchestration Docker, secret provider, nueva auth, integración Evolution ni lógica Mamamia360.
- **NOT_TESTED**: servicios externos reales, corpus/retrieval Milvus real, LLM/embeddings facturables, Gmail/DWD/WhatsApp real, DB de escritura/remota, browser E2E Home/web/embed/Mamamia, wheel/deployment. Los 48 skips opt-in se conservan.
- Required Diagnosis refiere al baseline real, no a todos los modos ni a startup; no usarlo como algoritmo de arranque sin modelar variantes/capacidades y sus dependencias transitivas.
- Snapshot binding DEV no reemplaza fuente DB viva. Consumer queries no incluyen Console/Messaging como módulos completos; Evolution con cero consumidores registrados no implica cero consumidores reales.
- Sigue pendiente el acoplamiento pool-bootstrap Diagnosis, scheduler single-process, deudas de autorización/fallback/session-context del baseline Fase 1. Nada se corrige silenciosamente aquí.
- Recomendación Fase 3: acordar primero perfiles funcionales/capacidades y fixtures seguros; después, con ventana GLOBAL explícita, separar bootstrap pool de rutas y lifecycle Flow con regresión de orden/cleanup. Validar independencia operacional sin envíos accidentales antes de implementar launcher o `--module`.
