# Team360 — Orquestación global

Esta sección resume el propósito y el alcance de «Team360 — Orquestación global» dentro de Team360.

## Propósito

Mantener una visión unificada de Team360 entre ramas Git, hilos de chat, frentes técnicos, documentación knowledge, labs y decisiones comerciales/productivas.

Team360 trabaja con ramas separadas para aislar riesgos, pero las decisiones globales deben mantenerse en una vista transversal.

Regla central:

> Trabajar separado, decidir globalmente.

Este documento es la fuente humana canonica de ownership modular, coordinacion entre agentes y limites por path. `AGENTS.md` resume la conducta obligatoria inmediata y enlaza esta politica.

## Modelo de ownership modular

El ownership se declara antes de comenzar y clasifica paths por su alcance real, no solo por el directorio donde viven. `PRODUCTION_PROTECTED` se aplica como una proteccion adicional sobre las otras categorias.

### MODULE_LOCAL

Un scope `MODULE_LOCAL` pertenece a un modulo existente y formalmente asignado. Su agente puede modificar implementacion, rutas, tests y documentacion propios sin pedir una ventana GLOBAL.

- Los scopes de dos agentes escritores simultaneos deben ser explicitos y disjuntos.
- No se reservan paths para modulos que todavia no existen.
- Flow tiene como scope local `SrvRestAstroLS_v1/backend/modules/flow/**` y sus tests inequivocamente propios `SrvRestAstroLS_v1/backend/tests/test_flow_*.py`.
- Match y Data Science no tienen todavia un scope declarado.
- Knowledge conserva sus restricciones de rama actuales; su directorio no autoriza trabajo desde cualquier rama.

### SHARED

Un path `SHARED` tiene varios consumidores, pero no necesariamente controla toda la infraestructura. Su modificacion exige conocer el impacto y coordinar cuando pueda alterar contratos externos al modulo solicitante.

Ejemplos actuales incluyen:

- `SrvRestAstroLS_v1/backend/modules/messaging/**`;
- providers y contratos comunes;
- `SrvRestAstroLS_v1/astro/src/components/ui/**`;
- formatters y utilidades consumidos por mas de un modulo.

Antes de editar `SHARED`, el agente identifica consumidores, informa el cambio, obtiene asignacion o autorizacion y valida los consumidores afectados. `SHARED` nunca se asume `MODULE_LOCAL` por conveniencia.

### GLOBAL

Un path `GLOBAL` afecta bootstrap, configuracion, infraestructura, persistencia, dependencias, runtime o deploy de varios modulos. Un agente de modulo no puede modificarlo libremente.

Ejemplos actuales, sin constituir aun un inventario machine-readable exhaustivo:

- `SrvRestAstroLS_v1/backend/globalVar.py`;
- `SrvRestAstroLS_v1/backend/ls_iMotorSoft_Srv01.py`;
- `SrvRestAstroLS_v1/backend/modules/module_registry.py`;
- `SrvRestAstroLS_v1/backend/modules/db/**` y `SrvRestAstroLS_v1/backend/db/migrations/**`;
- configuracion, dependencias, lockfiles y scripts generales de backend;
- `SrvRestAstroLS_v1/astro/src/components/global.js` y `global.d.ts`;
- configuracion, dependencias, lockfiles y scripts generales de Astro;
- autenticacion, runtime, infraestructura y deploy comunes.

Si necesita cambiar `GLOBAL`, el agente se detiene antes de editar, informa path, motivo, impacto esperado y modulo solicitante, y pide una ventana GLOBAL exclusiva. Mientras espera puede continuar otra tarea `MODULE_LOCAL`.

GLOBAL es un scope real de coordinación: todos pueden leer, pero solo hay un writer GLOBAL simultáneo. Incluye AGENTS, skill, estado técnico GLOBAL, políticas e índices transversales; no depende del nombre del proceso o herramienta.

La ventana declara propósito y paths. Una ventana documental no autoriza modificar bootstrap, registry, launchers, dependencias, lifecycle, infraestructura, Git ni producción. No se necesita un sistema complejo de locks: asignación explícita y coordinación bastan.

Los agentes locales pueden continuar mientras no cambien condiciones GLOBAL. Si necesitan hacerlo, detienen esa parte y coordinan ownership, sin bloquear todo su trabajo local.

Con autorización explícita para reconciliar documentos modificados, inspeccionar primero sus diffs y preservar trabajo preexistente. No exigir worktree limpio ni inferir ownership GLOBAL de procesos `pi`, `opencode` u otros activos.

### PRODUCTION_PROTECTED

`PRODUCTION_PROTECTED` es un overlay y no una categoria excluyente. Un mismo path puede ser `GLOBAL + PRODUCTION_PROTECTED` o `SHARED + PRODUCTION_PROTECTED`; siempre prevalece la restriccion mayor.

Actualmente solo estan declarados `PRODUCTION_PROTECTED`:

- Diagnosticador / Vera;
- el componente/embed productivo.

La Home y Console no adquieren automaticamente esta clasificacion por haber sido desplegadas o por tener tests de regresion. Los contratos vigentes de Vera/embed se detallan en `[[team360-runtime-operational-policy]]`, `[[diagnosticador-embeddable-component-architecture]]` y `SrvRestAstroLS_v1/docs/public_home_vera_protection_contract_v1.md`.

Modificar una frontera protegida requiere detenerse, informar, obtener autorizacion explicita, ejecutar la regresion especifica y evitar cualquier ampliacion accidental de scope.

## Concurrencia y locks

Varios agentes pueden editar simultaneamente un mismo worktree solo cuando tienen scopes `MODULE_LOCAL` existentes, asignados y disjuntos. Esta coordinacion es manual hasta que exista una herramienta local.

Cambios dentro del scope asignado a otro agente son `EXPECTED CONCURRENT CHANGES`. Deben preservarse: no se revierten, borran, formatean, modifican, adoptan como propios ni incluyen accidentalmente en Git.

Un cambio fuera de los scopes concurrentes declarados que no pueda explicarse obliga a detenerse e informar.

La edicion local concurrente no habilita operaciones globales concurrentes. Requieren una ventana exclusiva, sin otro agente escritor activo:

- `git add`, commit, checkout, switch, merge, rebase, reset, stash y clean;
- operaciones equivalentes sobre index, HEAD, working tree global o refs;
- lockfiles, formatters globales y regeneraciones masivas;
- scripts que alteren estado global;
- regresiones completas cuando generen o modifiquen artefactos compartidos.

## Ownership por paths y por ramas

El ownership por paths y el ownership por ramas son controles independientes. Ser dueño de un scope `MODULE_LOCAL` no autoriza a trabajarlo desde cualquier rama.

La tabla de ramas de este documento y `AGENTS.md` sigue vigente. En particular, Knowledge ingestion permanece asignado a `feature/knowledge-ingestion-service` y su contenido editorial a `docs/knowledge-documents-foundation`.

Cualquier cambio de ese reparto requiere una decision transversal separada. Esta politica no habilita Knowledge desde `feature/console-backend-core` ni modifica su ownership actual.

## Module registry

`SrvRestAstroLS_v1/backend/modules/module_registry.py` es `GLOBAL`. El entrypoint `ls_iMotorSoft_Srv01.py` consume `get_module_route_handlers()` y conserva infraestructura, rutas y lifecycle existentes.

La composicion vigente es:

```text
ls_iMotorSoft_Srv01.py
-> get_module_route_handlers()
-> module_registry.py
-> ROUTE_HANDLERS de modulos registrados
```

Un modulo puede exponer desde su propio `routes.py`:

```python
ROUTE_HANDLERS = (
    route_one,
    route_two,
)
```

El alta inicial del modulo requiere un cambio GLOBAL coordinado en `module_registry.py`. Despues, nuevas APIs se agregan a su `routes.py` `MODULE_LOCAL` sin modificar el entrypoint ni el registry por cada endpoint.

El registry está implementado y Flow expone APIs desde `ROUTE_HANDLERS` en `routes.py`, registrado una sola vez. Nuevas rutas se agregan dentro de su scope `MODULE_LOCAL`; el inventario y estado vigente se consultan en el [tablero técnico GLOBAL](../SrvRestAstroLS_v1/docs/status_actual.md).

## Salida de scope

Un agente que descubre una necesidad fuera de su asignacion no expande su scope por inferencia. Debe clasificar el path y coordinar antes de editarlo.

Procedimiento minimo:

1. detener el cambio fuera de scope;
2. informar path, categoria, motivo, impacto y modulo solicitante;
3. solicitar asignacion `SHARED`, ventana `GLOBAL` o autorizacion `PRODUCTION_PROTECTED` segun corresponda;
4. continuar, si existe, otra tarea `MODULE_LOCAL` mientras espera;
5. cambiar el path solo dentro de la ventana autorizada y validar consumidores.

## Representacion ejecutable futura

Una etapa posterior puede incorporar `tools/team360_global_scope.json` como inventario ejecutable de globs para un coordinador Python. No reemplazara esta fuente humana ni explicara nuevamente la politica.

El archivo futuro debera apuntar a `lat.md/team360-global-orchestration.md` mediante `policy_document` y representar como minimo `global`, `shared`, `module_local` y `production_protected`. Todavia no esta implementado.

## Ramas activas

Esta sección resume el propósito y el alcance de «Ramas activas» dentro de Team360.

| Rama | Rol | Uso |
|---|---|---|
| `main` | Producción / snapshot estable | No trabajar directo salvo hotfix o consolidación final |
| `feature/console-backend-core` | Desarrollo funcional principal | Backend, Console, UX real conectada/productiva, diagnosis assistant, LiteLLM, PostgreSQL, runtime y orquestación viva |
| `ux/team360-console-design-handoff` | Referencia visual congelada | Handoff visual, diseño base, no UX viva |
| `feature/knowledge-ingestion-service` | Knowledge ingestion / RAG / labs de knowledge | Embeddings, chunking, scanner, retrieval, package behavior, golden answers, pruebas RAG/asistente como efecto del knowledge package y decision notes técnicas de esa línea |
| `docs/knowledge-documents-foundation` | Documentación knowledge | Estándares, paquetes, manuales, authoring, metadata y contenido curado |

Versión corta:

- `feature/console-backend-core` = producto funcional vivo.
- `feature/knowledge-ingestion-service` = knowledge ingestion / RAG / labs de knowledge.
- `docs/knowledge-documents-foundation` = contenido y documentación knowledge.
- `ux/team360-console-design-handoff` = referencia visual congelada.

## Regla de trabajo para una sola persona

El proyecto lo lleva principalmente una sola persona, por lo que se prefiere:

- pocas ramas;
- roles claros;
- commits pequeños;
- push frecuente;
- revisión por paths antes de publicar cambios grandes;
- evitar ramas nuevas salvo experimento riesgoso, hotfix o necesidad real.

No crear ramas por cada detalle menor.

No crear ramas funcionales nuevas salvo necesidad puntual explícita.

## UX real vs handoff visual

La UX real productiva vive en:

`feature/console-backend-core`

Esto incluye:

- flujos reales;
- navegación;
- estados de componentes;
- integración con API;
- validaciones de UI;
- experiencia final de consola;
- diagnóstico conectado al backend.

La rama:

`ux/team360-console-design-handoff`

queda como referencia visual congelada / diseño base. No debe confundirse con la UX viva del producto.

## Knowledge ingestion vs documentación knowledge

Separar claramente:

### `feature/knowledge-ingestion-service`

Incluye:

- scanner;
- worker;
- schemas;
- validaciones;
- tests de ingestion;
- embeddings;
- chunking;
- retrieval;
- package behavior;
- golden answers;
- labs de ingesta;
- pruebas RAG/asistente como efecto del knowledge package;
- decision notes técnicas de esa línea.

No usar esta rama para desarrollo funcional productivo del runtime, backend o Console.

### `docs/knowledge-documents-foundation`

Incluye:

- documentación knowledge;
- estándares de authoring;
- manuales;
- drafts;
- metadata editorial;
- contenido curado;
- estructura de paquetes.

No mezclar código de ingesta con armado editorial de documentos, salvo corpus mínimo aprobado cuando sea necesario para validar ingestion end-to-end.

## Regla de `lab/`

`SrvRestAstroLS_v1/lab/` no es código temporal descartable.

Es un banco de pruebas técnico:

- reproducible;
- auditable;
- aislado de producción;
- útil para comparar hipótesis;
- útil para conservar evidencia de resultados.

Los experimentos `lab/` pueden existir en distintas ramas.

La rama correcta se decide por:

1. la hipótesis validada;
2. el sistema bajo prueba;
3. el uso real del resultado.

No se decide solo por el nombre del directorio.

Guía:

- `feature/console-backend-core`: labs de backend runtime, diagnosis API, assistant productivo, UX real conectada o experiencia final de consola.
- `feature/knowledge-ingestion-service`: labs de embeddings, chunking, scanner, retrieval, package behavior, golden answers o conversación como efecto de knowledge package.
- `docs/knowledge-documents-foundation`: labs de authoring, metadata, manuales, contenido curado o estructura documental.
- `ux/team360-console-design-handoff`: labs puramente visuales de handoff.

## Decisiones globales de producto

Esta sección establece la decisión técnica vigente y las restricciones derivadas de ella.

- `pkg_sales_diagnosis` es un knowledge package evolutivo.
- Team360.live será el primer contexto de validación.
- Vera es nombre comercial visible, no identificador técnico.
- El modelo funcional/comercial transversal queda definido en `[[team360-pack-task-diagnosis-model]]`: T360 Packs, T360 Tasks, T360 Pack Flows, T360 Pack Integrate y Diagnostico Team360.
- El diagnóstico no se limita a ventas; ventas es la entrada comercial inicial.
- El diagnóstico debe entender la necesidad real aunque todavía no exista el Pack o la Task exacta para resolverla.
- El diagnóstico debe traducir la operación del cliente en una arquitectura posible de solución, no forzarla a un catálogo cerrado.
- Automatizable no significa vendible hoy.
- Step-to-Action, lead capture, diagnostic_code y WhatsApp handoff son capacidades futuras.
- La primera etapa productiva prioriza:
  - conversación clara;
  - slots mínimos;
  - preguntas mínimas necesarias;
  - diagnóstico útil;
  - orientación concreta.

## Comunicación, marketing y distribuidores

Conviene mantener un hilo separado para:

- ventas;
- comunicación;
- marketing;
- distribuidores;
- pricing;
- mensajes comerciales;
- materiales para canales;
- paquetes iniciales.

Nombre sugerido del hilo:

`Team360 — Ventas, Comunicación, Marketing y Distribuidores`

Este frente no debe mezclar detalles de ramas, tests, schemas o implementación salvo que impacten promesas comerciales.

Regla comercial:

> Vender valor real de la primera etapa productiva. No vender capacidades futuras como si ya estuvieran listas.

## Cierre de trabajo por rama

Cada bloque de trabajo debería cerrar con:

- rama usada;
- objetivo del bloque;
- archivos creados/modificados;
- validaciones ejecutadas;
- impacto sobre otros frentes;
- si requiere actualizar esta orquestación global;
- próximo paso recomendado.

Formato sugerido:

```text
Rama:
...

Objetivo:
...

Archivos modificados:
...

Validaciones:
...

Impacto transversal:
...

Próximo paso:
...
```

## Regla contra fragmentación

No asumir que el contexto de una rama representa todo Team360. El único estado técnico GLOBAL vigente es [status_actual.md](../SrvRestAstroLS_v1/docs/status_actual.md); LAT conserva reglas, no otra bitácora global.

Antes de tomar decisiones amplias, revisar:

- este documento;
- `lat.md/lat.md`;
- `lat.md/status_actual.md`;
- `SrvRestAstroLS_v1/docs/status_actual.md`;
- el mapa de ramas;
- el hilo de orquestación global.

Si un cambio técnico afecta producto, knowledge, UX real, documentación o ventas, mencionarlo explícitamente en el cierre.
