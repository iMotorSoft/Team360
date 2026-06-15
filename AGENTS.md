# Team360 - Instrucciones Para Agentes

Trabajar siempre desde la raiz del proyecto:

`/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`

Antes de cambios relevantes, leer:

- `.agents/skills/team360-project/SKILL.md`
- `SrvRestAstroLS_v1/docs/status_actual.md`
- `lat.md/lat.md` cuando el cambio afecte arquitectura, dominio, IA, workers, knowledge, seguridad, paquetes o reglas transversales.

Convencion operativa de ramas:

- `main`: estado estable validado.
- `feature/console-backend-core`: rama de desarrollo e integracion general de plataforma, backend, DB, documentacion tecnica y alineacion UX-backend.
- Desarrollo funcional real, incluyendo backend, runtime, servicios, endpoints, persistencia, assistant runtime, providers, conversation state, guardrails productivos e interfaces internas funcionales, debe realizarse desde `origin/feature/console-backend-core` o una rama derivada explicitamente de esa base.
- `feature/knowledge-ingestion-service`: rama para labs, investigacion, knowledge ingestion, pruebas RAG/asistente, decision notes y validaciones previas a implementacion funcional.
- `ux/team360-console-design-handoff`: rama de diseno visual, frontend mock y handoff UX antes de integrar.
- Las ramas de UX/diseno quedan para mocks, referencias visuales, Home premium, prototipos estaticos y handoff para disenadores. No deben mezclarse con runtime funcional.
- Antes de avanzar con una tarea, clasificarla como lab/investigacion, desarrollo funcional o UX/mock. Si cambia de categoria, cambiar tambien la rama/base de trabajo.
- Cuando una instruccion de trabajo mencione `desarrollo`, `dev` o `backend`, interpretar que la rama destino es `feature/console-backend-core`.
- `Objetivo: desarrollo` dentro de `SrvRestAstroLS_v1/docs/status_actual.md` describe el tipo de bitacora tecnica; para trabajo Git corresponde usar `feature/console-backend-core`.
- No crear una rama local llamada `desarrollo`.

Regla de trabajo paralelo entre ramas:

- No trabajar en paralelo sobre dos ramas cuando una depende de la otra. Si una tarea necesita codigo, contratos, migraciones, decisiones, documentos tecnicos, runtime, APIs o resultados de otra rama, primero cerrar, validar o integrar la rama base/dependencia.
- Se puede trabajar en paralelo cuando las ramas son independientes: objetivos separados, sin dependencia funcional o documental, sin archivos compartidos relevantes y sin necesidad de integrar el resultado de una para avanzar con la otra.
- Si aparece dependencia durante el trabajo, pausar el paralelo y reclasificar la tarea contra la rama/base correcta antes de seguir.
- Mantener aislamiento operativo: no mezclar cambios de distintas ramas en el mismo worktree, no mover cambios entre ramas sin instruccion explicita y preferir worktrees separados cuando el trabajo paralelo sea real.

Separacion documental:

- Comercial / negocio / producto / reportes no tecnicos: `docs/` y `data/reports/`
- Tecnico / codigo / backend / Astro / migraciones / runtime: `SrvRestAstroLS_v1/docs/`

Estructura documental vigente:

- `lat.md/`: arquitectura viva, invariantes estables, reglas de dominio y referencias anclables desde codigo.
- `docs/README.md`: indice raiz de documentacion no tecnica de runtime.
- `docs/negocio/`: contexto comercial, tesis de negocio, analisis de clientes, mercados y oportunidades.
- `docs/estrategia/`: decisiones de producto/plataforma, continuidad, inventarios y estrategia tecnico-negocio.
- `docs/analisis-tecnico/`: analisis tecnico no operativo, factibilidad y automatizacion que no pertenece al runtime.
- `docs/templates/`: plantillas documentales reutilizables.
- `data/reports/README.md`: indice de reportes y evidencias generadas.
- `data/reports/mercadolibre/netzaj-racing/`: relevamientos publicos, playbook e intents derivados del seller NETZAJ RACING.
- `data/reports/snapshots/`: snapshots historicos de estado del repo o de tareas puntuales.
- `SrvRestAstroLS_v1/docs/`: documentacion tecnica de desarrollo, backend, Astro, runtime, migraciones y estado tecnico.

Regla de ubicacion:

- Un documento narrativo de negocio/producto/estrategia va en `docs/`.
- Una evidencia generada, muestra, reporte exportable o snapshot va en `data/reports/`.
- Una nota tecnica ligada a codigo, backend, Astro, migraciones, runtime o validacion de desarrollo va en `SrvRestAstroLS_v1/docs/`.
- Un invariante estable de arquitectura, dominio, IA, workers, paquetes, knowledge o seguridad va en `lat.md/`.
- No duplicar el mismo contenido entre `lat.md/`, `docs/`, `data/reports/` y `SrvRestAstroLS_v1/docs/`; mover o enlazar, segun corresponda.

Convencion para `lat.md`:

- `lat.md/lat.md` es el indice raiz de arquitectura viva.
- `lat.md/` guarda reglas estables e invariantes de Team360, no bitacoras diarias, evidencias ni status de implementacion.
- Usar documentos `kebab-case.md` por concepto, por ejemplo `multi-package-workers.md` o `knowledge-rag-graphrag.md`.
- Usar referencias `[[concepto]]` entre documentos y comentarios `# @lat: [[concepto#Seccion]]` en codigo solo cuando una funcion, clase o modulo implemente una regla no trivial.
- No llenar el codigo de anchors triviales; anclar cerca del punto decisivo donde se aplica la regla.
- Al crear o modificar documentos dentro de `lat.md/`, actualizar `lat.md/status_actual.md`.
- `SrvRestAstroLS_v1/docs/status_actual.md` sigue siendo la bitacora tecnica principal de desarrollo; `lat.md/` no reemplaza esa bitacora.

Convencion para `status_actual.md`:

- `SrvRestAstroLS_v1/docs/status_actual.md`
- Objetivo actual: `desarrollo`

Convencion para status locales por directorio documental:

- Todo directorio documental activo debe tener su propio `status_actual.md`.
- Ese archivo describe el ultimo estado y la ultima accion relevante dentro de ese directorio, no el estado global del proyecto.
- Al crear, mover, eliminar o reorganizar documentos dentro de un directorio, actualizar el `status_actual.md` de ese directorio.
- Si el cambio afecta a una subcarpeta y tambien al indice del padre, actualizar ambos status cuando corresponda.
- `SrvRestAstroLS_v1/docs/status_actual.md` sigue siendo la bitacora tecnica principal de desarrollo.
- Los status locales de `docs/` y `data/reports/` no deben mezclar decisiones tecnicas de runtime con material comercial o reportes.
- Carpetas auxiliares vacias que solo contienen `.gitkeep` no requieren `status_actual.md` hasta tener contenido documental real.

Que significa `desarrollo`:

- bitacora tecnica del estado de implementacion
- decisiones tecnicas y cambios realizados
- validaciones ejecutadas
- pendientes recomendados
- notas operativas o de seguridad relevantes para ingenieria

No interpretar ese documento como material comercial, de ventas, marketing o presentacion ejecutiva.

Si en el futuro se crean estados para otros objetivos, deben declararse de forma explicita.

Ejemplos posibles:

- `comercial`
- `producto`
- `operaciones`

Reglas rapidas:

- No mezclar criterios tecnicos con criterios comerciales.
- No inventar estructuras nuevas fuera del patron actual del repo.
- No tocar `team360_orquestador` salvo que el objetivo lo pida.
- No mezclar browser lab de Mercado Libre con AG-UI o frontend salvo que el objetivo lo pida.
- Preferir cambios chicos, claros y reversibles.
- Actualizar `SrvRestAstroLS_v1/docs/status_actual.md` al cerrar tareas tecnicas importantes.
- Para Team360, la politica DB runtime se define en `lat.md/postgres-driver-policy.md`.

Formato recomendado para `status_actual.md`:

- `Objetivo: ...`
- `Ultima actualizacion: YYYY-MM-DD`
- `## Estado general`
- `## Acciones realizadas`
- entradas por fecha con titulo corto, por ejemplo: `### 2026-05-13 - Integracion inicial de ...`
- dentro de cada entrada: que se cambio, que no se toco, validacion, riesgos o notas si aplica
- `## Validacion`
- `## Pendientes recomendados`
- `## Notas de seguridad`
- Plantilla base disponible en: `docs/templates/status_actual_template.md`
