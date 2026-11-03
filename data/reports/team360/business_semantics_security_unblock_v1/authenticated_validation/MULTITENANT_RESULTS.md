# Resultados multitenant

CROSS_TENANT=BLOCKED. No se autenticaron U1/U3; no se crearon conceptos DEV ni se intentó recuperar información privada de otra organización.

## Matriz de evidencia real

Predicados revisados y pruebas descartables históricas no sustituyen operaciones con sesiones autorizadas de tenants distintos.

| Pruebas | Contrato | Resultado |
| --- | --- | --- |
| MT-01 / MT-02 / MT-03 | Exacta / alias / vector Telchi inaccesibles a B | BLOCKED |
| MT-04 / MT-12 | ID válido conocido, lectura directa inaccesible | BLOCKED |
| MT-05 | Historial privado | BLOCKED |
| MT-06 | Propuesta privada | BLOCKED |
| MT-07 | Auditoría privada | BLOCKED |
| MT-08 / MT-09 | Editar/publicar/retirar fuera de tenant | BLOCKED |
| MT-10 | Cachés/sesiones reutilizadas | BLOCKED |
| MT-11 | Aislamiento tras reinicio seguro | BLOCKED |

## SQL efectivo inspeccionado

BusinessConceptRepository contiene SQL parametrizado; BusinessConceptResolver y Administration llaman scope/authorize antes de leer o mutar. La observación dinámica autenticada sigue pendiente.

| Ruta | Controles de aplicación |
| --- | --- |
| catalog / exact / alias | organization_id; workspace NULL o autorizado; module NULL o solicitado; concepto y versión published |
| text_search / vector_search | Mismos predicados tenant/workspace/module/publicación; vector exige versión actual, alias/revision/dimension |
| Contexto/evidencia | IDs recuperados exclusivamente desde catálogo actual autorizado, no referencia ajena/stale arbitraria |
| Administración/propuesta | Actor activo dentro de workspace/organización y organization_admin activo |
| ID/history/publish/retire/alias/embed | owned con tenant, workspace/module exactos y FOR UPDATE antes de operación |
| Conversación/caché | workspace/channel/IDs y owner environment/tenant/workspace/channel/user |
| Auditoría | INSERT core_events con workspace y actor; no hay acción de lectura audit en Business Semantics CLI |

history/relation_evidence/embedding_source en repository filtran sólo concept_id/version; requieren el guard superior. Una llamada directa no es endpoint autorizado. No se certificó exhaustivamente cada consumidor ni lectura audit. La consulta estándar del resolver exige usuario activo, no un grant semántico específico; handler añade el permiso comercial de su política y reconsulta Console.

## Defensa DB y límites

En el destino real las ocho tablas carecen de RLS y políticas. El rol dedicado tiene SELECT multi-tenant en SQL y el pool global usa superusuario: no hay barrera DB independiente.

No se activó RLS ni cambió el pool. [ENVIRONMENT_ATTESTATION.md](ENVIRONMENT_ATTESTATION.md) contiene flags/grants reales. [focused_tests.log](focused_tests.log) prueba referencia ajena/stale y evidencia provisional en ports sintéticos; no prueba MT real ni ausencia universal de rutas sin control.
