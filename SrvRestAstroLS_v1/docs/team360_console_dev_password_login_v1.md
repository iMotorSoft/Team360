# Console DEV: enrollment y login por contraseña

Ceremonia CLI dentro de Console que emite el PASETO existente después de verificar una contraseña. Sólo DEV, sin endpoint web nuevo, cambios productivos ni tokens emitidos por identidad elegida.

## Frontera y estado

La pieza está implementada y preparada en DEV; las sesiones humanas y el cierre Business Semantics siguen pendientes.

La migración 030 añade console_password_credentials y console_login_attempts. El rol team360_business_semantics_dev_runtime no es superusuario, propietario ni bypass RLS. El pool global de Srv05/Srv01 no fue cambiado.

El issuer persistente es exclusivo de esta ceremonia DEV. No usa claves efímeras ni fallback; **no exportar su clave privada al bootstrap experimental**. El nuevo camino Business Semantics exige --auth-config, amr=pwd, workspace concordante y credential_version vigente, además del RBAC existente.

No se configuró login HTTP, frontend, refresh ni recuperación autoservicio. /api/console/bootstrap no es login humano y no emite sesiones aceptadas por este nuevo camino. Otros consumidores PASETO no adquieren revocación DB automáticamente.

## Enrollment humano

El operador autorizado trabaja desde backend y recibe la contraseña exclusivamente en terminal interactiva, sin chat, argv, variables de entorno o logs.

Configuración DEV preparada, fuera de Git y owner-only:

```bash
cd SrvRestAstroLS_v1/backend
export TEAM360_ENV=dev
AUTH_DIR=/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi/console-auth-window-20261014T134648Z
AUTH_CONFIG="$AUTH_DIR/issuer.json"
```

Activar/resetear sólo una identidad existente y autorizada:

```bash
uv run --no-sync python -m modules.console.login_cli set-password \
  --config "$AUTH_CONFIG" --user-id "$AUTHORIZED_USER_ID" \
  --workspace-id "$AUTHORIZED_WORKSPACE_ID" --apply --local-owner-enrollment
```

El comando exige TTY, getpass dos veces, usuario/workspace/organización activos, destino pinneado y confirmación explícita. Mínimo 12 caracteres, máximo 256, sin reglas de composición. No crea usuarios, cambia membresías o concede permisos.

El evento enrollment registra operator_uid y subject_user_id; actor_user_id permanece NULL: el sujeto aún no está autenticado. No atribuye una sesión ficticia a la persona. Cada reset incrementa credential_version e invalida sesiones anteriores en el nuevo consumidor.

Necesitamos dos personas Telchi diferentes, una identidad legítima de tenant B y un administrador Telchi. El admin puede ser uno de los dos usuarios Telchi. No activar cuentas ajenas ni sustituir consentimiento por existencia en DB.

## Login y consumo autorizado

El login selecciona al sujeto por credenciales persistidas, no por un UUID proporcionado; el token se entrega a un archivo privado nuevo de modo 0600.

```bash
uv run --no-sync python -m modules.console.login_cli login \
  --config "$AUTH_CONFIG" --workspace "$AUTHORIZED_WORKSPACE_SLUG" \
  --email "$AUTHORIZED_EMAIL" --token-output "$AUTH_DIR/session-user-a.paseto"

uv run --no-sync python -m modules.business_semantics.cli list \
  --workspace "$AUTHORIZED_WORKSPACE_SLUG" --auth-config "$AUTH_CONFIG" \
  < "$AUTH_DIR/session-user-a.paseto"
```

La contraseña entra por getpass. Ni token ni clave se imprimen. No compartir issuer.json con usuarios/clientes: contiene secretos de servidor, no una configuración pública. Un archivo de token existente nunca se sobrescribe; usar nombres nuevos para logins posteriores.

Todos los rechazos de credenciales son genéricos. PostgreSQL serializa intentos por workspace/email normalizados; cinco fallos por 15 minutos bloquean incluso contraseña correcta hasta vencer la ventana. El caller confirma los contadores de fallo, no los pierde por rollback.

## Seguridad y límites

scrypt usa N=131072, r=8, p=1, salt aleatorio de 16 bytes y comparación constante; hashes versionados con límites de tamaño y work factor fijo.

Secretos/configuración/backups permanecen en PRIVATE_ROOT. Login usa rol runtime; enrollment y migración requieren operador privilegiado distinto. Runtime no puede modificar credenciales ni crear tablas en el entorno validado. Sin grants en bases de otros proyectos.

El rol puede leer datos semánticos de varios tenants a nivel SQL: **RLS sigue ausente**. La autorización de aplicación y las pruebas reales de todas las rutas siguen siendo obligatorias. No publicar su DSN ni certificar aislamiento multitenant sólo por haber retirado SUPERUSER.

La CLI es una ceremonia DEV controlada por el operador, no un endpoint expuesto a Internet. Rate limiting por IP/dispositivo, MFA, cookies/CSRF y enrollment autoservicio necesitan su contrato antes de una futura interfaz web.

## Preparación y retorno

La preparación ya se aplicó con backup previo; no repetirla ni sobrescribir claves, rol o configuración existentes.

prepare exige --apply, pin de cluster, backup custom privado y loopback/team360; rechaza schema/rol/config existentes. No importa aplicaciones ni reinicia servicios. La validación aislada precedió a su aplicación DEV.

Para retirar la capacidad: dejar de invocar la nueva CLI y custodiar/revocar el acceso al archivo privado. Una ventana DB autorizada puede retirar LOGIN/grants del rol dedicado después de revisar conexiones y dependencias. No restaurar toda team360, borrar usuarios o eliminar tablas/auditoría para deshacer esta tarea.

No hay variables globales persistidas que revertir. Preservar backup y claves como evidencia privada; futuras rotaciones/reset requieren operación explícita. El backup fue validado por TOC y extracción SQL, no mediante restore operacional completo.

## Evidencia

Los tests incluyen credenciales sintéticas en PG18 descartable, no contraseñas ni sesiones humanas de las cuentas reales.

[Reporte y gates](../../data/reports/team360/business_semantics_security_unblock_v1/auth_window/GATES.md): 221 PASS / 1 skip en regresión focalizada; preparación DEV y privilegios reales verificados read-only, cero passwords activadas. El cierre histórico BLOCKED permanece intacto.
