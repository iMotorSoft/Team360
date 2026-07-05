# Plan de migración — Embed Auth HMAC → PASETO v4.public

**Fecha:** 2026-07-05  
**Basado en:** ADR `adr_paseto_v4_public_standard_v1.md`  
**Rama:** `feature/console-backend-core`

---

## Fase 0 — Fundación (esta iteración) ✓

| Acción | Archivo | Estado |
| ------ | ------- | ------ |
| ADR: PASETO v4.public como estándar | `docs/adr_paseto_v4_public_standard_v1.md` | ✓ |
| Módulo `paseto_tokens.py` | `modules/security/paseto_tokens.py` | ✓ |
| Tests de módulo (12 casos) | `tests/test_paseto_tokens.py` | ✓ (12/12 pass) |
| Dependencia `pyseto` | `pyproject.toml` | ✓ (`uv add pyseto`) |

## Fase 1 — Integración en Console (próxima iteración)

Objetivo: ConsoleBootstrapService emite token PASETO en lugar de almacenar user_id plano.

```
POST /api/console/bootstrap → { "user_id": "..." }
Response → { "access_token": "v4.public..." }
```

**Cambios necesarios:**
- `modules/security/paseto_tokens.py` — agregar helper `load_private_key_from_env()` que lea `TEAM360_PASETO_V4_PRIVATE_KEY_PATH`
- `modules/console/service.py` — `ConsoleBootstrapService` emite `issue_paseto_v4_public()` con `typ="console_access"`
- Guardar `jti` + `user_id` + `exp` en tabla `paseto_tokens` (nueva migración)
- El endpoint devuelve `{"access_token": ..., "token_type": "v4.public", "expires_in": 3600}`

**Nuevos tests:**
- `test_console_bootstrap_service.py` — verificar emisión de token PASETO
- Test de expiración + refresh

## Fase 2 — Embed Auth Dual Support

Objetivo: Embed acepta ambos formatos (HMAC legado + PASETO) para dar tiempo a los clientes a migrar.

**Cambios necesarios:**
- `modules/embed_clients/auth.py` — en `verify_embed_signature()` detectar formato:
  - Si comienza con `v4.public.` → verificar con `verify_paseto_v4_public()`
  - Si no → usar HMAC actual
- `modules/embed_clients/hmac.py` — agregar `_sign_with_paseto()` alternativa para nuevos clientes
- Snippet público (`docs/embed_installation_guide_v1.md`):
  - Agregar ejemplo de token PASETO en comentario
  - No cambiar el snippet que los clientes copian todavía

**Nuevos tests:**
- `test_embed_clients_contract.py` — agregar test: "HMAC token still works" + "PASETO token works"
- Test de dual path: ambos formatos pasan `verify_embed_signature()`

## Fase 3 — Clientes nuevos solo PASETO

Objetivo: Nuevos clientes de embed reciben snippet que emite PASETO.

- Cambiar snippet público para emitir `v4.public` + `X-T360-Signature: Bearer <token>`
- HMAC sigue funcionando para clientes existentes
- Documentar fecha estimada de deprecación de HMAC (mínimo 6 meses desde Fase 2)

## Fase 4 — Deprecación HMAC

Objetivo: Retirar HMAC cuando todos los clientes conocidos hayan migrado.

- Agregar `X-T360-Deprecation: HMAC-SHA256 será removido el <fecha>` en responses HMAC
- Monitorear logs de clientes HMAC activos
- Una vez que HMAC quede en cero → eliminar código HMAC + migración

## Línea de tiempo estimada

| Fase | Duración | Dependencias |
| ---- | -------- | ------------ |
| Fase 0 (Fundación) | 1 iteración | Ninguna |
| Fase 1 (Console) | 1 iteración | Fase 0 |
| Fase 2 (Dual Support) | 1 iteración | Fase 1 |
| Fase 3 (Snippet nuevo) | 1 iteración | Fase 2 |
| Fase 4 (Deprecación) | ~6 meses después | Fase 3 |

## Riesgos

- Clientes embed existentes deben actualizar su backend para emitir PASETO. HMAC no puede eliminarse sin comunicación previa.
- Console aún no tiene auth de usuario real. PASETO en Console es foundation, no producto terminado.
- Sin refresh token definido. Evaluar necesidad en Fase 1.
