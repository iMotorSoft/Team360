# PASETO Console Bootstrap Access Token — v1 (experimental)

## Resumen

Fase P4A del plan de migración HMAC→PASETO. `ConsoleBootstrapService` emite un
PASETO v4.public `access_token` firmado (Ed25519) como campo opcional de la
respuesta `POST /api/console/bootstrap`.

Controlado por variable de entorno `TEAM360_PASETO_ENABLED=true`. Cuando está
deshabilitado, el endpoint funciona exactamente como antes (sin token).

## Endpoint

| Método | Ruta |
| ------ | ---- |
| POST | `/api/console/bootstrap` |

### Request body (JSON)

```json
{
  "workspace_id": "...",
  "user_id": "..."
}
```

### Response (cuando PASETO habilitado)

```json
{
  "workspace": {...},
  "current_user": {...},
  "effective_permissions": [...],
  "capabilities": [...],
  "entitlements": {...},
  "navigation": [...],
  "services": [...],
  "tasks_summary": {...},
  "alerts": [...],
  "workspace_context": {...},
  "organization_context": {...},
  "debug": ...,
  "access_token": "v4.public.ey...",
  "token_type": "paseto_v4_public",
  "expires_in": 900
}
```

Cuando PASETO deshabilitado, `access_token`, `token_type` y `expires_in` son `null`.

## Claims del token

| Claim | Valor | Descripción |
| ----- | ----- | ----------- |
| `typ` | `"console_access"` | Tipo de token (verificado) |
| `iss` | `"team360"` | Emisor (verificado) |
| `sub` | `"user:<user_id>"` | Sujeto |
| `user_id` | `<user_id>` | ID de usuario (claim plano) |
| `iat` | unix timestamp | Emitido en |
| `exp` | unix timestamp | Expira en (default +900s) |
| `jti` | UUID v4 | ID único del token |

### Footer

```json
{"kid":"local-dev-key-1"}
```

## Configuración (env vars)

| Variable | Default | Descripción |
| -------- | ------- | ----------- |
| `TEAM360_PASETO_ENABLED` | `""` | `"1"`, `"true"`, `"yes"` para activar |
| `TEAM360_PASETO_ISSUER` | `"team360"` | Issuer claim |
| `TEAM360_PASETO_KEY_ID` | `"local-dev-key-1"` | Key ID en footer |
| `TEAM360_CONSOLE_PASETO_TTL_SECONDS` | `900` | TTL del token en segundos |
| `TEAM360_PASETO_PRIVATE_KEY_B64` | `""` | Private key PEM en base64 |
| `TEAM360_PASETO_PUBLIC_KEY_B64` | `""` | Public key PEM en base64 |

Si no se proveen `TEAM360_PASETO_PRIVATE_KEY_B64`/`PUBLIC_KEY_B64`, se genera
un par dinámico en memoria (`PasetoKeyPair.generate("local-dev-key-1")`).
Esto es seguro para desarrollo pero inválido en producción (cada reinicio
invalida tokens previos).

## Arquitectura

```
POST /api/console/bootstrap
  └─ routes/console_bootstrap.py
       └─ ConsoleBootstrapService.build_bootstrap(paseto_settings=...)
            ├─ repositorios (workspace, permission, package, task)
            └─ issue_console_access_token(user_id, settings)
                 └─ issue_paseto_v4_public(claims, ...)
                      └─ pyseto.encode()
```

La inyección es opcional: `ConsoleBootstrapService` recibe
`PasetoConsoleSettings | None`. Si `None` o `enabled=False`, no hay token.
El handler lee la configuración desde env vars cada request.

## Tests

`tests/test_console_bootstrap_service.py` — 12 tests total (6 originales + 6 P4A):

1. `test_build_bootstrap_maps_services_and_default_task_summary` — original
2. `test_debug_is_omitted_for_client_context` — original
3. `test_debug_is_included_for_internal_context` — original
4. `test_workers_are_hidden_without_worker_permission` — original
5. `test_capabilities_are_derived_from_permissions_and_entitlements` — original
6. `test_missing_workspace_raises_domain_error` — original
7. `test_missing_user_raises_domain_error` — original
8. `test_bootstrap_still_returns_user_id_without_paseto` — **P4A**: sin token = `access_token: None`
9. `test_bootstrap_returns_access_token_when_paseto_enabled` — **P4A**: token presente, formato `v4.public.`
10. `test_access_token_verifies_with_public_key` — **P4A**: token verifica contra public key
11. `test_no_access_token_when_paseto_disabled` — **P4A**: `enabled=False` → sin token
12. `test_bootstrap_user_id_preserved_with_paseto` — **P4A**: user_id preservado con token

## Próximos pasos (post-P4A)

- Fase P4B: DB table para jti revocation + token validation endpoint
- Fase P5: integración con frontend mock (consumir token desde console bootstrap)
- Producción: generar par de keys persistentes, configurar env vars reales
- Documentar rotación de keys y soporte multi-kid

## Sin cambios en esta fase

- `global.js`, `/t360`, `PublicVeraEntry.svelte` — intactos
- `modules/embed_clients/` — intacto (HMAC embed sigue siendo el contrato)
- `routes/diagnosis.py` — intacto
- Runtime, Milvus, LiteLLM, PostgreSQL — intactos
- No se agregó DB table para jti/revocation
