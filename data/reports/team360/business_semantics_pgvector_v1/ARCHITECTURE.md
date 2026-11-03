# Memoria semántica empresarial V1

Implementación DEV real y opt-in en `feature/console-backend-core`, HEAD `09d2ec715a31bb88574d734eacb9f437f008624e`. Cierre global PARTIAL: los resultados ejecutados no sustituyen las garantías pendientes.

## Responsabilidades

El catálogo almacena significados; State Engine conserva conversación; capabilities y RBAC autorizan operaciones. Ninguna definición, regla documental o vector se convierte en SQL.

- Servicio horizontal: [business_semantics](../../../../SrvRestAstroLS_v1/backend/modules/business_semantics/).
- Persistencia: repositories async con conexiones y transacciones proporcionadas por el caller; mismo pool Team360.
- Resolver: alcance e identidad, código/alias, FTS español, cosine pgvector exacto. No HNSW ni Milvus.
- Administración: organización administrativa existente; CLI Console PASETO, sin emisión de tokens ni grants.
- Consumidor: handler Telchi existente, después de autorización viva y antes de una única llamada a Luna.
- Rollout: `TEAM360_ENV=dev` y `TEAM360_BUSINESS_SEMANTICS=1`; sin modificación de env files ni autoactivación global.

## Evidencia y límites

La memoria funciona entre conversaciones y después de reiniciar servidores propios. El catálogo horizontal no añade operaciones comerciales pendientes ni sustituye investigación.

- [Esquema y comandos](POSTGRES_SCHEMA.md), [embeddings](EMBEDDING_CONFIGURATION.md), [conceptos](TELCHI_INITIAL_CONCEPTS.md).
- [Integración](LUNA_STATE_INTEGRATION.md), [aislamiento](RBAC_AND_TENANT_ISOLATION.md), [casos](SEMANTIC_RETRIEVAL_TESTS.md).
- [HTTP](BUSINESS_HTTP_RESULTS.md), [rendimiento](PERFORMANCE.md), [gates](GATES.md).
- Foundation CURRENT permanece `foundation_afd08d9eca6a725be53cdc3f9d5709c9`, snapshot 1408. Sólo lectura focalizada; sin SAP, reingestión, promoción o deploy.
- No se tocó Messaging, Flow, Diagnosis, Srv01, registry, dependencias ni lockfiles. Cambios preexistentes preservados.
- Catálogo pequeño: lectura acotada a 500 conceptos por scope y hasta 5 candidatos por consulta. No certifica escala grande ni administración de scopes globales sin workspace.
- Observaciones guardan sólo hash normalizado y contador; revisión de la expresión necesita evidencia autorizada externa. No hay aprendizaje automático ni UI.
