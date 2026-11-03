# Baseline efectivo

Inspección de continuidad en feature/console-backend-core, HEAD 09d2ec715a31bb88574d734eacb9f437f008624e. Worktree modificado preexistente preservado; no commit, deploy ni cambio GLOBAL.

## PostgreSQL observado

Preflight ejecutado con psycopg async, connect_timeout=5, transacción READ ONLY, statement_timeout=5s y rollback. SQL y resultados resumidos en preflight.json. Sin seed, migración, observación ni embedding generado.

- Destino cliente localhost:5432/team360; servidor 172.18.0.2/32, PostgreSQL 18.4 (Debian), no recovery.
- pgvector 0.8.2. Ocho tablas business_concept presentes; RLS desactivado en todas. Rol efectivo rolsuper=true y rolbypassrls=true.
- Nueve conceptos publicados; corporativas versión 2, otros versión 1. Dos conceptos stock propuestos sin current_version.
- Existen tres organizaciones: telchi (workspace telchi_dev, dos usuarios activos), team360_live (dos activos), team360_platform (uno activo). Existencia no acredita permisos ni sesiones autenticadas.
- TEAM360_ENV ausente; TEAM360_SEMANTICS_DEV_SYSTEM_IDENTIFIER ausente. No se acreditó separación frente a producción. Escrituras y reinicios bloqueados.
- Archivos 028/029 presentes y estructura compatible; no se verificó registro histórico/checksum de aplicación. No se reaplicaron.

## Diferencias frente al baseline informado

La evidencia anterior sigue siendo histórica, no un PASS nuevo. Se corrigió únicamente resolver.py y se agregó test_operational_closure.py dentro de business_semantics.

Nombre canónico sin alias duplicado ahora resuelve como coincidencia exacta usando el contrato alias existente. Evidencia estructurada de candidatos y referencias conversacionales ahora llega a luna_context, limitada a cinco entidades/reglas por concepto autorizado.

No se levantó Srv05. No hay listener observado en puertos 8000/8005. El montaje y habilitación efectiva deben acreditarse en una sesión autorizada; el código composition.py requiere TEAM360_BUSINESS_SEMANTICS=1.

## Comandos y límites

La consulta de catálogo agrupó semantic_code/status/current_version/versiones; la consulta de identidad sólo agrupó organización/workspace/cantidad activa. No se publicaron usuarios, credenciales ni tokens.

Regresión: uv run --no-sync pytest modules/business_semantics/tests modules/telchi/assistant/tests tests/test_telchi_assistant_srv05.py -q. Resultado final en tests.log. No se ejecutó live_evidence.py: escribe seed y embeddings.
