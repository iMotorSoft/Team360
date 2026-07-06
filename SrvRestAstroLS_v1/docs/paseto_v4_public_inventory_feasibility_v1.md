# PASETO v4.public — Inventario y factibilidad

**Fecha:** 2026-07-05
**Rama:** `feature/console-backend-core`
**HEAD:** `48b3c21`
**Estado del worktree:** 3 archivos modificados (docs), 2 untracked (docs). Sin cambios en código productivo. `git diff --check`: PASS.

---

## A. Resumen ejecutivo

Team360 **no usa JWT en ningún punto del código productivo**. La autenticación actual es **HMAC-SHA256 request-bound** para el embed (`X-T360-Signature`) y no hay auth de usuarios/console implementada. No existen dependencias JWT ni criptográficas (no hay `cryptography`, `PyNaCl`, `PyJWT`, `jose`, `jsonwebtoken`).

**Decisión recomendada:**
```
PASETO v4.public RECOMENDADO PARA NUEVA AUTH, NO MIGRAR EMBED HMAC TODAVÍA
```

- PASETO v4.public sí aplica para futuros tokens de Console, service-to-service, magic links e invitaciones.
- PASETO v4.public **no debe reemplazar** el HMAC request-bound del embed, que está atado a mensaje/sesión/timestamp y no necesita token portable.
- No hay JWT real que migrar hoy.

---

## B. Inventario completo

### B.1 Tabla de hallazgos

| Área | Archivo | Línea/Referencia | Hallazgo | Clasificación | Impacto PASETO | Acción recomendada |
| ---- | ------- | ---------------: | -------- | ------------- | -------------- | ------------------ |
| Backend embed | `modules/embed_clients/hmac.py` | 1-49 | HMAC-SHA256 canonical string `client_id.timestamp.session_id.message`. Firma en header `X-T360-Signature: sha256=<hex>`. | **E — HMAC embed actual** | Ninguno. HMAC está atado a mensaje. No reemplazar. | Mantener HMAC request-bound |
| Backend embed | `modules/embed_clients/auth.py` | 1-169 | `authorize_request()` y `issue_signature()` con validación de origin, timestamp tolerance (±300s), HMAC verify | **E — HMAC embed actual** | Ninguno. No es reemplazable por token portable sin cambiar el contrato. | Mantener |
| Backend embed | `modules/embed_clients/models.py` | 8-36 | `EmbedClient` dataclass con `hmac_secret` plaintext + contexto fijo | **E — HMAC embed actual** | PASETO no aplica aquí. HMAC secret storage es deuda separada. | Deuda: vault/rotación, no PASETO |
| Backend embed | `modules/embed_clients/repository.py` | 1-59 | Carga desde PostgreSQL con SQL directo, pool de conexiones | **E — HMAC embed actual** | No aplica. | Mantener |
| Backend routes | `routes/diagnosis.py` | 699-792 | `POST /api/diagnosis/embed/auth` genera firma server-side | **E — HMAC embed actual** | No aplica. | Mantener |
| Backend routes | `routes/diagnosis.py` | 795-910 | `POST /api/diagnosis/turn` con client_id opcional, firma HMAC | **E — HMAC embed actual** | No aplica. | Mantener |
| Backend routes | `routes/diagnosis.py` | 517-548 | `ALLOWED_PUBLIC_DIAGNOSIS_CONTEXTS` allowlist backend | **F — Config backend** | No aplica. | Mantener |
| Backend console | `modules/console/service.py` | 43-140 | `ConsoleBootstrapService.build_bootstrap()` recibe `user_id` y `workspace_id` sin verificar token | **C — Token genérico futuro** | Alto. PASETO v4.public como access token de Console. | Implementar en Fase P3 |
| Backend console | `modules/console/types.py` | 27-34 | `CurrentUserDTO` con `user_id`, roles, profiles | **C — Token genérico futuro** | Los claims de PASETO incluirán `sub`, roles, org. | Adoptar en nuevo auth |
| Backend console | `modules/console/errors.py` | 1-14 | `WorkspaceNotFoundError`, `UserNotFoundError`, `ConsolePermissionError` | **C — Token genérico futuro** | Errores compatibles con middleware de tokens. | Mantener |
| Backend DB | `db/migrations/008_create_embed_clients.sql` | 1-71 | Tabla `embed_clients` con `hmac_secret`, `allowed_origins`, contexto fijo | **E — HMAC embed actual** | No migrar. PASETO no requiere esta tabla. | Mantener |
| Backend DB | `db/migrations/001_team360_core_schema.sql` | 349, 357-358 | `auth_type` en `llm_providers`: `bearer`, `api_key`, `none` | **H — Dep potencial** | Solo para LLM upstream, unrelated. | Sin acción |
| Backend DB | `db/migrations/001_team360_core_schema.sql` | 24-35 | `core_users` con `workspace_id`, `role`, `status`, `email`, `display_name` | **C — Token genérico futuro** | PASETO servirá para sesiones de estos usuarios. | Adoptar en Console auth |
| Backend DB | `db/migrations/001_team360_core_schema.sql` | 158 | `verify_token_ref text` en `core_events` | **H — Dep potencial** | Campo para token de verificación de eventos. Evaluar PASETO. | Posible migración futura |
| Backend DB | `db/migrations/001_team360_core_schema.sql` | 134 | `verification_status` en `core_events` | **H — Dep potencial** | Relacionado con verificación. | Sin acción inmediata |
| Backend tests | `tests/test_embed_clients_contract.py` | 48-57 | Tests HMAC sign/verify | **E — HMAC embed actual** | No aplicar PASETO aquí. | Mantener |
| Backend tests | `tests/test_diagnosis_public_router.py` | 60/60 + 83/83 | Tests de router embed auth + turn | **E — HMAC embed actual** | Tests existentes deben seguir pasando. | Mantener |
| Backend deps | `pyproject.toml` | 1-35 | **Sin JWT, sin PASETO, sin cryptography, sin PyNaCl** | **H — Dep potencial** | Se necesitará nueva dependencia. | Agregar en Fase P1 |
| Frontend embed | `src/lib/t360/embed/` | `mount.ts`, `browser-global.ts` | Interfaz mount con `clientId`, `apiBaseUrl`, sin secreto | **D — Session local frontend** | No cambiar. El frontend nunca debe manejar claves. | Mantener |
| Frontend embed | `public/embed/team360-diagnosticador-loader.js` | completo | Loader externo con `load()`, `mount()`, `verifyEntryIntegrity` | **D — Session local frontend** | No cambiar. No debe manejar tokens. | Mantener |
| Frontend E2E | `e2e/diagnosticador-embed-demo.spec.ts` | 24-112 | Valida auth `POST /api/diagnosis/embed/auth` → respuesta `client_id, timestamp, signature` | **E — HMAC embed actual** | Tests HMAC existentes deben seguir pasando. | Mantener |
| Frontend E2E | `e2e/diagnosticador-external-host-demo.spec.ts` | 29-136 | Valida contrato embed auth | **E — HMAC embed actual** | Idem. | Mantener |
| Frontend E2E | `e2e/diagnosticador-cross-origin-integrity-loader-fixture.spec.ts` | 190-360 | Valida loader con integrity | **E — HMAC embed actual** | Idem. | Mantener |
| Frontend E2E | `e2e/public-vera.spec.ts` | 4, 50-550 | Session keys en `sessionStorage`, tests de nueva conversación | **D — Session local frontend** | PASETO no reemplaza sessionStorage frontend. | Mantener |
| Frontend session | `src/lib/t360/diagnosticador/state/session.ts` | Referencia en lat.md | Manejo de `sessionStorage` con keys aisladas | **D — Session local frontend** | No aplicar PASETO. SessionStorage es del navegador. | Mantener |
| Frontend deps | `package.json` | 1-32 | **Sin JWT, sin PASETO, sin crypto** | **H — Dep potencial** | PASETO verification pública podría hacerse en frontend con `tweetnacl` o similar. Evaluar si es necesario. | Opcional, post-Fase P3 |
| Docs | `docs/diagnosticador_embed_auth_v1.md` | 1-395 | Documentación del contrato embed auth v1. Menciona "no JWT" explícito en línea 11. | **B — Docs solamente** | PASETO no aplica aquí. | Actualizar doc si se cambia algo |
| Docs | `docs/status_actual.md`, `lat.md/status_actual.md` | Múltiples | Bitácoras de fases embed. Sin JWT en ninguna. | **B — Docs solamente** | Sin impacto. | Sin acción |
| Docs UX | `docs/ux/team360-console-app-shell-and-layout-system.md` | 506-524 | Mención de "Sesión expirada", "reautenticación" | **C — Token genérico futuro** | PASETO se ajusta al modelo de sesión descrito. | Adoptar en diseño |
| Docs UX | `docs/ux/team360-domains-and-console-strategy.md` | 340, 387 | `session`, `authenticated_user_id` en contexto UX | **C — Token genérico futuro** | PASETO sirve estos claims. | Adoptar |
| Frontend base | `docs/frontend/team360-frontend-technical-base-from-vertice360.md` | 223, 302-304 | Mención de `src/auth/` con `session.svelte.ts` y `token.ts` como estructura planeada | **C — Token genérico futuro** | PASETO encaja como token implementation. | Implementar con PASETO |
| Infra | `docs/frontend/team360-frontend-technical-base-from-vertice360.md` | 152 | "Sin autenticación token/session en los demos" | **C — Token genérico futuro** | Confirmación de que no hay auth hoy. | Sin acción |
| Backend console | `modules/console/service.py` | 43-51 | `profile` reserved para "future authenticated HTTP boundary" | **C — Token genérico futuro** | PASETO debería ser ese boundary. | Implementar en Fase P3 |
| Estrategia | `docs/estrategia/capacidades_reutilizables_inventario_2026-05-06.md` | 68, 102-103 | Menciones de HMAC/signature en proveedores Gupshup/Bird (stubs) | **H — Dep potencial** | Canales externos usan sus propias firmas. Sin impacto. | Sin acción |
| All | `AGENTS.md`, `lat.md/*` | Múltiples | No hay referencia a JWT, PASETO, tokens de sesión ni auth de usuarios | **B — Docs solamente** | Sin impacto. | Sin acción |

### B.2 Clasificación resumida

| Clase | Cantidad | Descripción |
| ----- | -------- | ----------- |
| **A — JWT real actual** | **0** | No existe JWT en producción, tests, docs de diseño ni migraciones. |
| **B — JWT mencionado en docs** | **0** | Solo aparece en `diagnosticador_embed_auth_v1.md` como "no se introduce JWT". |
| **C — Token genérico futuro** | **~6** | Console bootstrap apunta a auth futura; UX docs mencionan sesión; migración 001 tiene `core_users`. |
| **D — Session local frontend** | **~4** | SessionStorage por sesión aislada. No es reemplazable por PASETO. |
| **E — HMAC embed actual** | **~8** | HMAC-SHA256 request-bound. No reemplazar por PASETO. |
| **F — Config backend** | **1** | Allowlist de contextos públicos. No relacionado. |
| **H — Dep potencial** | **~4** | No hay dependencias JWT/crypto. Se necesitarán nuevas. |
| **I — Falso positivo** | **Varios** | `session_id` conversacional (no auth), `token` como metadato de LLM, etc. |

---

## C. Hallazgos principales

### C.1 JWT real
**No existe.** Cero referencias a JWT en código productivo, tests, configuraciones o dependencias.

### C.2 Token genérico
El módulo `modules/console/` implementa `ConsoleBootstrapService` que recibe `user_id` y `workspace_id` sin verificar ningún token. El comentario en `service.py:50` dice: *"profile is reserved for a future authenticated HTTP boundary"*. No hay routes de console todavía.

### C.3 HMAC embed
El embed usa HMAC-SHA256 request-bound con canonical string `client_id.timestamp.session_id.message`. La firma viaja en `X-T360-Signature`. El backend valida origin, timestamp window (±300s), y session_id obligatorio. No hay token portable.

### C.4 Sesiones frontend
`sessionStorage` con keys aisladas (`team360.vera.session.v1`, `team360.embed.demo.session.v1`, etc.). Contienen datos de sesión conversacional, no tokens de auth.

### C.5 Docs
La documentación de embed auth dice explícitamente "no se introduce token efímero ni JWT" (decisión 8B). Las bitácoras de estado no mencionan JWT ni PASETO.

### C.6 Dependencias
**No hay** `cryptography`, `PyNaCl`, `PyJWT`, `python-jose`, `pypaseto`, `paseto`, `jsonwebtoken`, `jose` ni similares en Python ni JS. El backend usa `hashlib` + `hmac` (stdlib). El frontend no usa crypto.

---

## D. Reemplazos potenciales

| Caso | Hoy | PASETO propuesto | Prioridad | Riesgo |
| ---- | --- | ---------------- | --------: | ------ |
| Console access token | No existe (solo `user_id` plano en service) | PASETO v4.public con claims `sub`, `org`, `workspace`, `roles` | **Alta** | Bajo — es nuevo, no hay legado |
| Console refresh token | No existe | PASETO v4.public con TTL más largo + revocación vía DB | **Media** | Bajo — nuevo |
| Service-to-service | No existe | PASETO v4.public con `typ: service` | **Media** | Bajo — nuevo |
| Magic links / invitaciones | No existe | PASETO v4.public con `typ: invitation` | **Media** | Bajo — nuevo |
| Embed auth (`/embed/auth`) | HMAC-SHA256 request-bound | **No reemplazar** | — | Alto — cambiaría contrato público |
| Embed turn (`/diagnosis/turn`) | HMAC-SHA256 header `X-T360-Signature` | **No reemplazar** | — | Alto — rompería todos los clientes |
| SessionStorage frontend | Keys aisladas | **No reemplazar** | — | No aplica — storage del navegador |
| LLM upstream auth | Bearer token API key | **No reemplazar** | — | No aplica — es auth de proveedor externo |

---

## E. No reemplazar todavía

1. **HMAC embed (`/embed/auth`, `/turn`, `X-T360-Signature`)** — contrato público validado con clientes HTML/PHP/WordPress. PASETO no mejora el request-binding actual.
2. **SessionStorage frontend** — no es auth, es estado conversacional.
3. **LLM provider auth** — Bearer token para LiteLLM es externo.
4. **Milvus token** — token de acceso a Milvus, unrelated.
5. **Allowlist de contextos** — no es auth, es validación de tenant.

---

## F. Diseño recomendado

### F.1 Para Console/admin (nuevo)

```
POST /api/console/auth/login
  → valida credentials (email + password, OAuth, etc.)
  → emite PASETO v4.public access token
  → emite PASETO v4.public refresh token (opcional)

GET /api/console/bootstrap
  → header Authorization: Bearer <paseto_token>
  → verifica firma con public key
  → extrae claims user_id, workspace_id, roles
  → llama a ConsoleBootstrapService
  → responde bootstrap del workspace
```

Claims del access token:
```json
{
  "sub": "user:<uuid>",
  "org": "team360_live",
  "workspace": "<workspace_id>",
  "roles": ["admin", "operator"],
  "iat": 1710000000,
  "exp": 1710003600,
  "jti": "unique-token-id",
  "typ": "console_access"
}
```

### F.2 Para embed (mantener HMAC)

- `/embed/auth` sigue generando firma HMAC server-side.
- `/turn` sigue verificando `X-T360-Signature`.
- No introducir PASETO en el flujo embed.

Opción B (PASETO en embed) se descarta por ahora porque:
- El HMAC está atado al mensaje exacto (no replay).
- El embed no necesita token portable.
- Cambiar el snippet público para clientes WordPress/PHP tiene alto costo.

### F.3 Para magic links / invitaciones

PASETO v4.public es apto con TTLs de horas/días. Claims sugeridos:

```json
{
  "sub": "email:user@example.com",
  "org": "org_code",
  "workspace": "workspace_code",
  "iat": 1710000000,
  "exp": 1710086400,
  "jti": "unique-token-id",
  "typ": "invitation"
}
```

---

## G. Variables/env sugeridas

```text
# Path-based (recomendado para producción con secret manager)
TEAM360_PASETO_V4_PRIVATE_KEY_PATH=/etc/team360/keys/paseto_private.pem
TEAM360_PASETO_V4_PUBLIC_KEY_PATH=/etc/team360/keys/paseto_public.pem
TEAM360_PASETO_KEY_ID=k1
TEAM360_PASETO_ISSUER=team360.live
TEAM360_PASETO_DEFAULT_TTL_SECONDS=3600

# O base64 (para entornos sin filesystem persistente)
TEAM360_PASETO_V4_PRIVATE_KEY_B64=<base64_encoded_ed25519_private>
TEAM360_PASETO_V4_PUBLIC_KEY_B64=<base64_encoded_ed25519_public>
```

NO inline en código. NO en repositorio.

---

## H. Claims sugeridos por tipo de token

| Tipo | Claims obligatorios | TTL sugerido |
| ---- | ------------------- | -----------: |
| `console_access` | `sub`, `org`, `workspace`, `roles`, `iat`, `exp`, `jti`, `typ` | 1 hora |
| `console_refresh` | `sub`, `iat`, `exp`, `jti`, `typ` | 30 días |
| `service` | `sub` (service name), `iat`, `exp`, `jti`, `typ` | 5 minutos |
| `invitation` | `sub` (email), `org`, `workspace`, `iat`, `exp`, `jti`, `typ` | 48 horas |
| `magic_link` | `sub` (email), `iat`, `exp`, `jti`, `typ` | 15 minutos |

---

## I. Fases propuestas

### Fase P1 — ADR PASETO + selección de librería
- Crear ADR documentando la decisión.
- Evaluar `PyPASETO` y `paseto` (Python) para v4.public + Ed25519.
- Evaluar `tweetnacl` o similar para frontend si se necesita verificación pública.
- Definir formato de key (PEM, base64).
- **Sin implementación de runtime.**

### Fase P2 — Módulo crypto/tokens read-only + tests
- Crear `modules/crypto/tokens.py` (o `modules/auth/`) con:
  - `PasetoTokenService` con `sign()` y `verify()`.
  - Lectura de claves desde env/path.
  - Soporte de `kid` para rotación.
  - Tests unitarios de firma/verificación/expiracion/clock skew.
- Dependencia nueva: agregar `pypaseto` o `paseto` a `pyproject.toml`.
- **No integrar con Console ni rutas todavía.**

### Fase P3 — Console access token con PASETO
- Endpoint `POST /api/console/auth/login` (o el que corresponda).
- Middleware/guard que verifica `Authorization: Bearer <paseto>`.
- Integrar con `ConsoleBootstrapService` existente.
- Claims: `sub`, `org`, `workspace`, `roles`.
- **Console auth funcional mínima.**

### Fase P4 — Evaluar embed auth PASETO vs mantener HMAC
- Reevaluar si conviene emitir PASETO desde `/embed/auth` en lugar de HMAC.
- Si se decide cambiar, afecta: snippet público, clientes existentes, tests E2E.
- **Decisión documentada, no necesariamente implementada.**

### Fase P5 — Rotación/kid/revocación
- Endpoint de revocación o blacklist en DB.
- Soporte `kid` para rotate de keys sin downtime.
- Script de rotación de claves.
- Documentación operativa.

---

## J. Tests requeridos

Cuando se implemente:

| Test | Descripción |
| ---- | ----------- |
| Firma/verificación | `sign()` produce token verificable por `verify()` |
| Expiración | Token expirado → rechazo |
| Issuer/audience | Validación de `iss` esperado |
| Kid | Rotación de keys, token firmado con key anterior aún verificable si kid está en allowlist |
| Token malformado | String random → error controlado |
| Clock skew | Tolerancia configurable (±30s default) |
| Claims faltantes | Token sin `sub` → rechazo |
| No logging de token | `repr()` del token no muestra payload completo |
| No secrets en frontend | La public key en frontend es OK, private key nunca |
| Revocación | Token revocado → rechazo |

---

## K. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
| ------ | ------------ | ------- | ---------- |
| Madurez de librería PASETO Python | Media | Alto | Probar `PyPASETO` contra test vectors oficiales. Tener fallback a `cryptography` + implementación manual Ed25519. |
| Soporte v4.public | Baja | Alto | v4.public está especificado y tiene implementaciones. Verificar. |
| Manejo de Ed25519 (claves no estándar para algunos equipos) | Baja | Medio | Documentar generación de claves y formato PEM. |
| Almacenamiento de private key | Medio | Alto | Usar secret manager (infraestructura existente) + env path. No inline. |
| Rotación de claves | Media | Medio | Diseñar con `kid` desde el inicio. Script de rotación. |
| Clock skew entre servicios | Baja | Medio | Tolerancia configurable (±30s). |
| Revocación (tokens emitidos no revocables sin blacklist) | Media | Medio | Blacklist en DB o TTL corto + refresh token. |
| Replay de token | Baja | Medio | `jti` + `exp` + binding a origin/IP en casos sensibles. |
| Token leakage en frontend | Media | Alto | No poner private key en frontend. Solo public key si se verifica. TTL corto. |
| Logs accidentales con token | Media | Medio | `__repr__` sanitizado. Filtro en logging middleware. |
| WordPress/HTML copiando tokens | Baja | Bajo | Embed no usará PASETO (se mantiene HMAC). |
| CORS/origin | Baja | Medio | PASETO no reemplaza validación CORS. |
| Menor familiaridad que JWT | Media | Bajo | Documentación clara. PASETO es más simple que JOSE. |
| Interoperabilidad externa | Baja | Medio | Para console es interno; para embed se mantiene HMAC. |

---

## L. Preguntas de factibilidad (respuestas)

1. **¿Hay JWT real hoy en el repo?** No.
2. **¿Hay dependencias JWT hoy?** No.
3. **¿Hay auth real de usuarios hoy?** No. `ConsoleBootstrapService` recibe `user_id` sin verificar.
4. **¿Hay solo auth de embed?** Sí. HMAC-SHA256 request-bound.
5. **¿El HMAC actual del embed debe mantenerse?** Sí. Es un contrato público validado.
6. **¿Qué parte tendría sentido reemplazar con PASETO?** Console auth, service-to-service, magic links, invitaciones. Todo nuevo.
7. **¿PASETO v4.public encaja mejor para?**
   - Sesiones de Console: **Sí**, es el caso principal.
   - Tokens de embed: **No**, mantener HMAC.
   - Invitaciones: **Sí**.
   - Magic links: **Sí**.
   - API admin: **Sí**.
   - Service-to-service: **Sí**.
8. **¿Qué partes NO conviene migrar a PASETO?** Embed HMAC, sessionStorage frontend, LLM upstream auth, Milvus token.
9. **¿Qué claims mínimos?** `sub`, `iat`, `exp`, `jti`, `typ`. Según tipo: `org`, `workspace`, `roles`.
10. **¿Dónde guardar claves?** Secret manager o filesystem protegido (env `TEAM360_PASETO_V4_PRIVATE_KEY_PATH`).
11. **¿Cómo rotar claves?** `kid` en token + allowlist de public keys activas.
12. **¿Cómo versionar `kid`?** `kid` en footer del PASETO. Rotación: nueva key con nuevo `kid`, mantener viejas en allowlist para verificación hasta expirar tokens.
13. **¿Qué TTL?** Console access: 1h. Refresh: 30d. Invitaciones: 48h. Magic links: 15min. Service: 5min.
14. **¿Qué librería Python?** `PyPASETO` (recomendada para v4.public) o implementar con `cryptography` + Ed25519 si PyPASETO no madura suficiente.
15. **¿Qué impacto frontend?** Mínimo. Solo si se verifica public key en frontend (no necesario para v1). Console recibirá token y lo enviará en `Authorization` header.
16. **¿Qué impacto tests?** Tests nuevos para crypto + auth. Tests existentes de embed HMAC no se tocan.
17. **¿Qué migraciones DB?** Posible tabla de refresh tokens / revocación (`auth_tokens` con `jti`, `user_id`, `expires_at`, `revoked_at`).
18. **¿Qué cambios de env?** Las vars de keys (`TEAM360_PASETO_V4_*`).
19. **¿Qué riesgos con WordPress/PHP/embed?** Ninguno. El embed no usará PASETO.
20. **¿Conviene implementar ahora o documentar ADR primero?** **ADR primero** (Fase P1), luego implementación (P2-P5).

---

## M. Validaciones finales

```
git diff --check: PASS
git status --short: 3 modified, 2 untracked (solo docs)
```

No se tocó código productivo, rutas, frontend, servicios, dependencias ni configuraciones.

---

## N. Informe final

### A. Resultado

```
PASETO INVENTORY COMPLETADO — DOC CREADO SIN COMMIT
```

### B. Estado Git

- **Rama:** `feature/console-backend-core`
- **HEAD:** `48b3c21` — `test(diagnosticador): sync external integrity snippet`
- **Worktree inicial:** 3 modified (docs), 2 untracked (docs)
- **Worktree final:** 4 modified (3 preexisting + este doc), 2 untracked (docs)

### C. Inventario resumido

- **JWT real encontrado:** No
- **Dependencias JWT:** No
- **Auth real de usuarios:** No (solo `ConsoleBootstrapService` sin verificación)
- **Embed HMAC:** Sí (HMAC-SHA256 request-bound)
- **Tokens frontend/session:** Sí (sessionStorage conversacional, no auth)

### D. Factibilidad

- **Factible:** Sí
- **Dónde conviene:** Console admin, service-to-service, invitaciones, magic links
- **Dónde no conviene:** Embed HMAC, sessionStorage frontend, LLM upstream auth

### E. Recomendación

```
PASETO v4.public RECOMENDADO PARA NUEVA AUTH, NO MIGRAR EMBED HMAC TODAVÍA
```

### F. Archivos revisados

- `SrvRestAstroLS_v1/backend/routes/diagnosis.py`
- `SrvRestAstroLS_v1/backend/modules/embed_clients/` (6 archivos)
- `SrvRestAstroLS_v1/backend/modules/console/` (4 archivos)
- `SrvRestAstroLS_v1/backend/pyproject.toml`
- `SrvRestAstroLS_v1/backend/db/migrations/001_*.sql`
- `SrvRestAstroLS_v1/backend/db/migrations/008_*.sql`
- `SrvRestAstroLS_v1/backend/tests/test_embed_clients_contract.py`
- `SrvRestAstroLS_v1/backend/tests/test_diagnosis_public_router.py`
- `SrvRestAstroLS_v1/astro/package.json`
- `SrvRestAstroLS_v1/astro/src/lib/t360/embed/` (mount.ts, browser-global.ts)
- `SrvRestAstroLS_v1/astro/src/pages/` (Varias páginas demo)
- `SrvRestAstroLS_v1/astro/e2e/` (Varios tests E2E)
- `SrvRestAstroLS_v1/astro/public/embed/` (loader, manifest)
- `SrvRestAstroLS_v1/docs/diagnosticador_embed_auth_v1.md`
- `SrvRestAstroLS_v1/docs/status_actual.md` + varios docs embed
- `lat.md/` (varios archivos)
- `AGENTS.md`, `.agents/skills/` (SKILL.md)

### G. Archivos creados/modificados

- **Creado:** `SrvRestAstroLS_v1/docs/paseto_v4_public_inventory_feasibility_v1.md`

### H. Riesgos resumidos

- Madurez de librería PASETO en Python (mitigable con `cryptography`)
- Almacenamiento y rotación de private key (diseñar con `kid` desde inicio)
- Token leakage en logs (repr sanitizado)
- Romper embed existente si se mezcla (no mezclar: mantener HMAC)

### I. Próxima fase recomendada

**Fase P1 — ADR PASETO v4.public + selección de librería**

- Crear ADR documentando decisión.
- Evaluar `PyPASETO` vs implementación con `cryptography` + Ed25519.
- Definir formato de key, env vars, estructura de módulo.
- Sin implementación de runtime productivo.

### J. Veredicto final

```
PASETO v4.public RECOMENDADO PARA NUEVA AUTH, NO MIGRAR EMBED HMAC TODAVÍA
```
