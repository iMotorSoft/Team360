# PASETO Console Auth Verifier — v1

## Objetivo

Fase P4B — Verificador PASETO reutilizable para endpoints Console protegidos.
Cierra el circuito: P4A emite `access_token`, P4B lo verifica.

## Relación con P4A

- P4A: `POST /api/console/bootstrap` → emite `access_token` (PASETO v4.public, `typ=console_access`)
- P4B: `GET /api/console/me` → lee `Authorization: Bearer <token>` y verifica

El token emitido por P4A puede ser aceptado por P4B (circuito cerrado, ver
`test_token_from_bootstrap_verifies_via_console_auth`).

## Header esperado

```
Authorization: Bearer <paseto_v4_public_token>
```

## Claims requeridos

| Claim | Requerido | Validado |
| ----- | :-------: | :------: |
| `typ` | Sí | `console_access` |
| `iss` | Sí | `team360` |
| `sub` | Sí | debe empezar con `user:` |
| `user_id` | Sí | presente y no vacío |
| `exp` | Sí (implícito via `verify_paseto_v4_public`) |
| `iat` | Sí (implícito via `verify_paseto_v4_public`) |
| `jti` | Sí (implícito via `verify_paseto_v4_public`) |
| `kid` (footer) | Sí (implícito via `verify_paseto_v4_public`) |

## Errores 401

| Condición | detail |
| --------- | ------ |
| Authorization ausente | `Authorization header is required` |
| Scheme no Bearer | `Authorization scheme must be Bearer` |
| Token vacío | `Bearer token is empty` |
| `typ` incorrecto | Propaga desde PASETO: `Expected typ=...` |
| `iss` incorrecto | Propaga desde PASETO: `Expected iss=...` |
| `kid` desconocido | Propaga desde PASETO: `Unknown key_id` |
| Token expirado | Propaga desde PASETO: `Token expired` |
| `sub` sin prefijo `user:` | `Invalid subject: must start with 'user:'` |
| `user_id` ausente | `Missing user_id claim` |
| Token malformado | Propaga desde PASETO: `Malformed PASETO` |

## Endpoint protegido

```
GET /api/console/me
```

Response (200):
```json
{
  "user_id": "<user_id>",
  "subject": "user:<user_id>",
  "token_type": "paseto_v4_public"
}
```

No devuelve `access_token`, ni keys, ni claims completos.

## Componentes

- `modules/console/auth.py` — `ConsolePrincipal`, `extract_bearer_token()`, `verify_console_access_token()`, `ConsoleAuthError`
- `routes/console_me.py` — `GET /api/console/me` handler
- `modules/security/paseto_tokens.py` — `get_dev_public_keys_by_id()` (helper público para dev)

## Qué valida

- Formato Bearer token
- Firma Ed25519 v4.public
- `typ=console_access`
- `iss=team360`
- `sub=user:<id>` con prefijo
- `user_id` presente
- `kid` en footer selecciona la key correcta
- Expiración (con leeway configurable)

## Qué no valida todavía

- Revocación (no hay DB table `paseto_tokens` ni blacklist jti)
- Scope/permisos del usuario
- Refresh token
- Multi-tenancy

## No toca

- Embed/HMAC (sin cambios en `embed_clients/`, `diagnosis.py`)
- `/t360`, `PublicVeraEntry.svelte`, `global.js`
- Runtime, Milvus, LiteLLM, PostgreSQL

## Próximos pasos

- P4C: aplicar verificador PASETO al primer endpoint Console real
- DB table para jti revocation
- Refresh token
