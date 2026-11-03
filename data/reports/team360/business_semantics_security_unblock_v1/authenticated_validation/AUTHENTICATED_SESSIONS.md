# Sesiones autenticadas

REAL_USER_AUTH=BLOCKED. Lectura real: console_password_credentials enrolled=0/enabled=0; console_login_attempts=0; archivos privados *.paseto=0. No se ejecutó enrollment/login ni se fabricaron sesiones.

## Identidades requeridas

Existencia de usuarios/roles en DB no concede consentimiento para activarlos o impersonarlos. Las designaciones concretas son humanas y siguen pendientes.

| Identidad | Contrato | Resultado real |
| --- | --- | --- |
| U1 | Telchi consulta estándar | BLOCKED: sin credencial/sesión consentida |
| U2 | Otro usuario Telchi | BLOCKED: sin credencial/sesión consentida |
| U3 | Otra organización real | BLOCKED: sin designación/sesión consentida |
| U4 | organization_admin Telchi | BLOCKED: sin sesión consentida |

[HUMAN_ACTION_REQUIRED.md](HUMAN_ACTION_REQUIRED.md) contiene sólo comandos soportados. No hay tokens/contraseñas/hashes/key material en estos informes.

## Evidencia reutilizada

Auth source/runbook/tests/migración conservan sus hashes de auth_window: [auth_baseline_integrity.json](auth_baseline_integrity.json). No se repitieron 221 tests, KDF ni PG descartable.

[auth_window/GATES.md](../auth_window/GATES.md) acredita login, lockout, reset/disabled, rol y CLI con sujetos sintéticos descartables. No acredita U1–U4 reales; negativas MU-01 reales siguen pendientes. Conexión DB del rol dedicado en esta corrida NO es sesión Console de persona.
