# Pruebas multiusuario y multitenant

Gate real BLOCKED por autenticación y rol runtime. La siguiente matriz es inspección de rutas, no una prueba de no-fuga ni indicio de una fuga ocurrida.

## Fronteras inspeccionadas

El repository usa filtros SQL de aplicación; métodos internos por ID dependen de que el caller valide propiedad antes de llamarlos.

| Superficie | Control inspeccionado | Evidencia real autenticada |
| --- | --- | --- |
| Código/canónico/alias | resolver.scope + authorize; catalog filtra organización, workspace/módulo y publicación | Pendiente |
| FTS / vector | Filtros equivalentes; vector exige versión vigente, alias/revisión/dimensión antes de devolver ranking | Pendiente |
| Referencias conversacionales | IDs intersectados con catálogo autorizado/vigente antes de relation_evidence | Pendiente |
| Listado propuestas | admin_catalog con organización y scope exacto; service exige admin | Pendiente |
| ID directo / versiones | service llama owned antes de history/publish/retire/alias/embed | Pendiente |
| Auditoría administrativa | INSERT core_events con workspace y actor del caller autorizado | Pendiente |
| Lectura auditorías | No endpoint Business Semantics específico localizado; no certificar otras rutas Console | Pendiente |
| Escrituras | authorize(admin=True), owned con FOR UPDATE; propose scope y actor explícitos | Pendiente |
| Caché semántico | Sin caché de catálogo/vector en resolver inspeccionado | No aplica a ese resolver; resto pendiente |
| Caché conversacional | ConversationRepository owner=[environment,tenant,workspace,channel,user]; consultas por thread/event/workspace/channel | Pendiente |

history, relation_evidence, embedding_source/save_embedding y otras primitivas internas no tienen por sí solas predicado tenant. Su seguridad depende del encadenamiento de callers y de no exponerlas directamente. RLS ausente: no hay segunda barrera en DB.

La búsqueda en routes, module_registry y astro/src no encontró endpoints/UX específicos Business Semantics. La administración implementada es service + CLI con PASETO; no presentar un panel Console semántico como validado.

## Contratos aún no ejecutados

Todos necesitan identidades legítimas, runtime controlado y datos exclusivamente DEV.

Dos usuarios Telchi: lectura compartida, estado separado, administración diferenciada, actor real en auditoría y reload/persistencia. Tenant B: exacto, alias, vector, ID, versiones, propuestas, auditorías, mutaciones y caché sin exposición ni diferencias reveladoras.

Variar organización, workspace y módulo; incluir scope NULL válido, concepto retirado/propuesto, versión vieja y referencia ajena. Repetir tras publicar/retirar y tras reload del proceso propio cuando se autorice. Registrar rechazos y verificar ausencia de filas/eventos ajenos tras cada operación negativa.

No se llamaron resolver/service con UUIDs reales elegidos por el agente para simular login. Las fixtures locales de [REGRESSION.md](REGRESSION.md) sólo prueban contratos deterministas.
