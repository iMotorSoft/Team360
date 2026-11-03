# HUMAN_ACTION_REQUIRED

Se necesitan cuentas existentes autorizadas U1/U2 Telchi distintos, U3 de otra organización real y U4 administrador Telchi. U4 puede coincidir con U1/U2 si la política lo permite. No hay cuentas activadas ni sesiones disponibles.

## Condición antes de ejecutar

Operador y personas confirman consentimiento DEV y los IDs/workspace/email reales por canal privado. No proporcionar contraseñas, tokens ni issuer.json por chat. No usar credenciales productivas ni ampliar roles.

Comandos literales del [runbook](../../../../../SrvRestAstroLS_v1/docs/team360_console_dev_password_login_v1.md). Variables AUTHORIZED_* representan designaciones humanas pendientes, no valores inventados. Repetir enrollment/login para cada identidad designada, usando un token-output NUEVO por cuenta/login.

## Preparar terminal

Ejecutar desde la raíz del repositorio en terminal interactiva. La configuración privada ya existe; NO ejecutar prepare ni regenerar claves/rol.

```bash
cd SrvRestAstroLS_v1/backend
export TEAM360_ENV=dev
AUTH_DIR=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z
AUTH_CONFIG="$AUTH_DIR/issuer.json"
```

## Activar una cuenta consentida

El operador autorizado selecciona usuario/workspace existentes y activos. getpass pide la contraseña dos veces, mínimo 12 caracteres; no emite sesión ni concede permisos.

```bash
uv run --no-sync python -m modules.console.login_cli set-password \
  --config "$AUTH_CONFIG" --user-id "$AUTHORIZED_USER_ID" \
  --workspace-id "$AUTHORIZED_WORKSPACE_ID" --apply --local-owner-enrollment
```

La conexión de enrollment utiliza configuración global del operador y se compara con el pin. No continuar si cambió el destino acreditado. Un reset invalida sesiones anteriores; no resetear cuentas ajenas.

## Iniciar sesión legítima

La persona autentica su workspace/email por contraseña en getpass. El token va a archivo privado 0600 nuevo y vence en 900 segundos, sin aparecer en stdout.

```bash
uv run --no-sync python -m modules.console.login_cli login \
  --config "$AUTH_CONFIG" --workspace "$AUTHORIZED_WORKSPACE_SLUG" \
  --email "$AUTHORIZED_EMAIL" --token-output "$AUTH_DIR/session-user-a.paseto"
```

El nombre mostrado es el literal del runbook. Para otra cuenta/login elegir otro nombre privado nuevo; no sobrescribir ni reutilizar sesión entre personas. Custodiarlo localmente, nunca pegarlo en chat/log/evidencia.

## Comprobar autorización administrativa

Sólo U4 puede usar esta operación del runbook. Valida firma, expiración, sub/user_id, amr=pwd, credential_version, usuario/workspace/organización activos y rol organization_admin en DB.

```bash
uv run --no-sync python -m modules.business_semantics.cli list \
  --workspace "$AUTHORIZED_WORKSPACE_SLUG" --auth-config "$AUTH_CONFIG" \
  < "$AUTH_DIR/session-user-a.paseto"
```

IMPORTANTE: list llama BusinessConceptAdministration.execute(admin=True). Para U1/U2 estándar debe denegar; no es una consulta estándar ni whoami. No conceder admin para convertir esa denegación en PASS.

## Identidad y permisos sin secretos

No existe comando whoami/effective-permissions en este runbook/login CLI. No inventamos uno ni afirmamos que list muestre el principal autenticado.

Login verifica por workspace/email; la identidad efectiva se debe contrastar con el principal verificado y auditoría DB por el operador, sin imprimir token/hash/clave. El procedimiento de inspección autenticada y transporte U1/U2 de lectura/conversación aún no está acreditado. No reemplazarlo por bootstrap, header DEV o teléfono piloto fijo.

Tras enrollment/login, conservar archivos privados localmente y coordinar inmediatamente la ventana de pruebas dentro del TTL; reportar sólo identidades designadas/consentimiento y resultados no secretos. Los comandos anteriores habilitan la ceremonia existente, no completan por sí solos MU/MT/ADM ni el puente conversacional.
