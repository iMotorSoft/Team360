# Team360 Gmail provider

## Alcance

Este modulo implementa la infraestructura minima `Team360 Messaging -> Gmail
provider -> Gmail API`. Es infraestructura comun de Messaging y no pertenece ni
depende de Team360 Flow.

La autenticacion usa una Service Account con Domain-Wide Delegation, impersona
un usuario delegado y solicita solamente el scope
`https://www.googleapis.com/auth/gmail.modify`. La delegacion y la autorizacion
del scope se configuran fuera del codigo, en Google Workspace.

## Configuracion

- `TEAM360_GMAIL_SERVICE_ACCOUNT_FILE` (requerida): ruta al JSON de Service
  Account.
- `TEAM360_GMAIL_DELEGATED_USER` (opcional): usuario delegado por defecto.

El JSON debe vivir fuera del repositorio. No debe copiarse a `runtime/`,
fixtures, logs ni documentacion, y su contenido nunca debe imprimirse.

## Smoke de lectura

Desde `SrvRestAstroLS_v1/backend`:

```bash
uv run python -m modules.messaging.providers.gmail.probes.smoke_read \
  --account mesaentrada@alquimiablue.com \
  --limit 10
```

El probe lista mensajes y pide exclusivamente metadata segura. No obtiene
cuerpos, no modifica mensajes y no los marca como leidos.

## Smoke de envio

Sin `--confirm-send`, el comando valida argumentos y credenciales, construye el
cliente y termina como dry run sin enviar:

```bash
uv run python -m modules.messaging.providers.gmail.probes.smoke_send \
  --account mesaentrada@alquimiablue.com \
  --to mario.rojas@alquimiablue.com \
  --subject "Team360 Gmail API smoke test" \
  --body "Prueba real de Team360 Messaging via Gmail API."
```

Agregar `--confirm-send` solamente cuando exista autorizacion explicita.
