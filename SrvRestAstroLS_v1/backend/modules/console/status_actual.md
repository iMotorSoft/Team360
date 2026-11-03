# Status actual - Console / Auth

Estado local actualizado el 2026-10-14 con la ventana Console/Auth DEV autorizada; conserva los cierres anteriores. No constituye otro estado GLOBAL ni validación productiva.

## Estado vigente

Separar publicación UX, autenticación PASETO y autorización PostgreSQL; ninguna sustituye el gate del consumidor ni la autenticación request-bound del embed.

- Console UX Stages 1–8 consolidada y publicada según release 2026-08-06; no deployment realizado en esta normalización.
- PASETO v4.public Ed25519 foundation, emisión bootstrap y verificador Console implementados/validados en sus cierres.
- `POST /api/console/bootstrap` experimental emite access token cuando está habilitado, pero acepta IDs elegidos por el caller y no implementa la sesión previa del contrato final. Por eso queda DEV-only: sólo `TEAM360_ENV=dev|development` explícito; production, ausente o desconocido → 404 antes de DB/token. `GET /api/console/me` permanece disponible y verifica PASETO; no certifica RBAC enterprise completo.
- Permisos efectivos y contexto operacional resueltos desde PostgreSQL. Claves privadas fuera del frontend/repositorio.
- HMAC embed continúa vigente; revocación jti, refresh, dual support y deprecación HMAC no se declaran completados por P4A/P4B.
- Flow configuración demo sin login/RBAC es una política de esa superficie; Directorio HTTP usa capability y PASETO. No extrapolar la política demo a toda Console.

## Autoridades y evidencia

Los contratos conservan payloads, límites y tests fechados. El estado GLOBAL mantiene solo el resumen transversal.

- [Bootstrap](../../../docs/console_bootstrap_contract.md), [P4A](../../../docs/paseto_console_bootstrap_access_token_v1.md), [P4B](../../../docs/paseto_console_auth_verifier_v1.md).
- [Plan de migración embed](../../../docs/paseto_embed_auth_migration_plan_v1.md), [invariantes Console](../../../../lat.md/console-multi-organization.md).
- [Release UX](../../../docs/releases/team360-console-ux-production-2026-08-06.md), [histórico](../../../docs/status_historico_hasta_normalizacion_2026-10-06.md), [estado GLOBAL](../../../docs/status_actual.md).

## Enrollment/login DEV autorizado — 2026-10-14

Ventana GLOBAL explícita del propietario: pieza mínima Console implementada, preparada sólo en DEV y probada con identidades sintéticas; no declara sesiones humanas ni despliegue productivo.

- [Runbook](../../../docs/team360_console_dev_password_login_v1.md): credenciales separadas, scrypt, intentos persistidos, PASETO después de contraseña válida y epoch de credential reset. CLI interactiva; sin login web nuevo.
- Migración 030 y rol dedicado sin SUPERUSER/BYPASSRLS aplicados en el cluster DEV 7630993354699489317; issuer/config privado 0600. Usuarios/grants humanos intactos, cero contraseñas activadas y pool global sin cambios.
- Business Semantics CLI exige issuer explícito, sesión password/workspace/version vigente y RBAC DB. Bootstrap experimental por UUID no satisface este camino; otros consumidores mantienen sus contratos, sin revocación DB implícita.
- [Evidencia y gates](../../../../data/reports/team360/business_semantics_security_unblock_v1/auth_window/GATES.md): 221 PASS / 1 skip focalizados, incluyendo PG18 descartable y transporte CLI. Falta enrollment legítimo en terminal de usuarios designados y pruebas autenticadas pendientes. RLS semántico sigue ausente.

## Próximo paso

Activar contraseñas mediante getpass y verificar sesiones legítimas de dos usuarios Telchi, otro tenant y admin Telchi; no pedir passwords por chat ni entregar issuer privado a clientes.

Después, contratos operacionales Business Semantics y E2E WhatsApp. No habilitar producción, login web ni modificar el pool común/RLS sin validación específica.
