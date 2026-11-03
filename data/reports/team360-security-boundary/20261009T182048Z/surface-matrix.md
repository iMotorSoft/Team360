# Matriz de exposición

| Surface | DEV | PROD | Auth / authenticity | Side effects |
|---|---:|---:|---|---|
| Diagnosis DEV adapter | Sólo `TEAM360_ENV=dev|development`; 201 en flujo válido | 404 | Aislamiento por entorno; no identidad de usuario porque es herramienta DEV | Memoria/fakes default; PG/Milvus/LiteLLM sólo opt-in; rechazo antes de construir runtime |
| Console bootstrap experimental | Sólo `TEAM360_ENV=dev|development`; emite PASETO opcional | 404 | Sin login nuevo; el endpoint final autenticado queda pendiente | Lecturas PG y emisión token sólo tras guard; rechazo antes de DB/token |
| Gupshup webhook | Habilitable con token | Habilitable con token | `x-team360-webhook-token` contra secret existente; config ausente 503, inválido 401; no firma provider-native documentada | Auth antes de body; claim PG atómico; Flow sólo para ID nuevo |
| Evolution DEV webhook (scan) | Sólo entorno DEV explícito + enable/config/token | 503 | Token Messaging existente | Persistencia/service sólo después de configuración/auth |

## Clasificación final

- DEV surface in production: `DENY`.
- Bootstrap anonymous escalation in production: `DENY`.
- Bootstrap legitimate DEV flow: `PASS`; claims/capabilities/TTL sin expansión.
- Gupshup source authenticity boundary: `PASS` fail-closed.
- Gupshup destination compatibility/configuration: `NOT_TESTED / EXTERNAL_EVIDENCE`.
- Gupshup idempotency: `IDEMPOTENT` para inbound message ID estable.
