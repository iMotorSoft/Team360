# Contrato de protección — Home pública y Vera

Gate: `TEAM360_PUBLIC_HOME_VERA_PROTECTION_GATE`.
Cierre: 2026-08-06.
Rama: `feature/console-backend-core` (HEAD `1b3d4f2` al inicio).
Resultado: `TEAM360_PUBLIC_HOME_VERA_PROTECTION_PASS`.

Este documento define gates de regresión para la superficie pública de Team360.
Cualquier módulo futuro (Team360 Flow, Stage 10, nuevos embeds, etc.) debe
respetar estas reglas sin excepción.

En la política de ownership, `PRODUCTION_PROTECTED` se limita actualmente a
Vera / Diagnosticador y al componente/embed productivo. La Home conserva este
contrato y sus tests de regresión, pero no queda íntegramente clasificada como
`PRODUCTION_PROTECTED`; tampoco Console adquiere esa clasificación por deploy.

## 1. Superficie cubierta por regresión

Los siguientes puntos públicos permanecen cubiertos por los gates existentes, independientemente de su categoría de ownership.

- Home pública: `https://team360.live/`
- Vera / Diagnosticador público: `https://team360.live/#vera`
- Equivalente DEV: `http://127.0.0.1:3050/` y `http://127.0.0.1:3050/#vera`
- Ruta alternativa de contenido idéntico: `/t360` (misma página, canonical
  propio) — usada por la suite E2E de Vera.

## 2. Contrato de la home

| Elemento | Archivo | Regla |
| --- | --- | --- |
| Ruta `/` | `astro/src/pages/index.astro` | Debe cargar sin errores de consola ni overflow horizontal en 390/768/1280 |
| Layout | `astro/src/layouts/PublicMarketingLayout.astro` | Header sticky + main `#contenido` + footer; skip-link a `#contenido` |
| Header | `astro/src/components/marketing/MarketingHeader.astro` | Navegación por anclas (`#solucion`, `#casos`, `#metodo`, `#partners`); CTA a `#vera`; "Acceso clientes" a `CONSOLE_SITE_URL/login` |
| Footer | `astro/src/components/marketing/MarketingFooter.astro` | Enlaces internos por ancla, `mailto:contacto@team360.live`, acceso clientes |
| Hero | `index.astro` (sección inicial) | CTA "Empezar diagnóstico" → `#vera`; "Ver soluciones" → `#solucion` |
| Secciones | `index.astro` | `#diagnostico`, `#solucion`, `#casos`, `#metodo`, `#partners`, `#faq`, `#contacto` con `scroll-mt-24` |
| Sección Vera | `astro/src/components/diagnosis/PublicVeraEntry.svelte` | Elemento `id="vera"` con `scroll-mt-24` (no queda oculto tras el header sticky) |
| SEO / OG | `PublicMarketingLayout.astro` | Title, description, canonical `https://team360.live/`, OG/Twitter con imagen `team360-social-preview.png` |
| URLs | `astro/src/components/global.js` | Única fuente de verdad DEV/PRO (`IS_REST_PRO`, `URL_REST_DEV`); no hardcodear URLs en componentes |

Idiomas: la home es ES estática; Vera detecta idioma por mensaje y devuelve
diagnóstico localizado (ES/EN/HE) con `lang`/`dir` correctos.

## 3. Contrato de Vera pública

Flujo: `/#vera → PublicVeraEntry → DiagnosticadorCore → sendPublicTurn →
POST /api/diagnosis/turn → normalizeT360DiagnosisTurn → render`.

| Regla | Comportamiento |
| --- | --- |
| Inicio | Formulario inicial `public-vera-text` + `public-vera-submit` |
| Turnos | `public-vera-chat-input` + `public-vera-chat-submit`; `canSend` requiere texto y no-loading |
| Interaction blocks | `public-vera-interaction-block` con `data-valid`; renderizado por `T360InteractionRenderer` |
| Consumo de acciones | Un `t360action` marca el bloque como consumido (`consumedByMsgIdx`); no duplica bubble de usuario (`appendUserMessage=false` es intencional) |
| Prioridad de bloques | Un solo bloque operativo por turno cuando corresponde; opciones elegidas no reaparecen como acciones activas |
| Nueva conversación | `public-vera-new-conversation` limpia mensajes y `session_id`, conserva idioma |
| Persistencia | `team360.vera.session.v1` (sessionStorage) via `DEFAULT_SESSION_STORAGE_KEY` |
| Errores | `public-vera-error` localizado; retry disponible; sin secretos |
| Mobile | Sin overflow; entrada y chat dentro del ancho visible |
| RTL/HE | `DiagnosisResult` con `lang="he"` y `dir="rtl"` |

## 4. Contrato del embed productivo

| Elemento | URL pública | Integridad (manifest productivo) |
| --- | --- | --- |
| Manifest | `/embed/team360-diagnosticador.manifest.json` | `entrySha256`, `entryIntegrity`, `loaderSha256`, `loaderIntegrity` |
| Loader | `/embed/team360-diagnosticador-loader.js` | versionado `experimental-9e` |
| Entry | `/embed/team360-diagnosticador.js` | global `Team360Diagnosticador` |
| Auth | `POST /api/diagnosis/embed/auth` | HMAC request-bound; `client_id`, `timestamp`, `signature` |
| Turn | `POST /api/diagnosis/turn` | `X-T360-Signature`; contexto resuelto server-side |

Reglas:

- `clientId` público; `hmac_secret`, tenant/scope y `allowed_origins` solo
  server-side.
- CORS productivo permite los origins de la seed `embed_clients` (incluye
  `team360.live`, `mamamia360.com`, `www.mamamia360.com`).
- SRI: `loaderIntegrity` y `entryIntegrity` del manifest se verifican
  (`verifyEntryIntegrity` opt-in); integridad negativa bloquea antes de mount.
- Assets DEV (`astro.config.dev.mjs` + `scripts/embed-dev-assets.mjs`) sirven
  el grafo allowlisted sin tocar artefactos productivos.
- Los hashes productivos NO se regeneran por builds locales; el runtime DEV
  resuelve su propio manifest en memoria.

## 5. Pruebas de protección (cobertura vigente)

| Spec | Cubre |
| --- | --- |
| `e2e/public-home-vera-protection.spec.ts` | Home `/`, navegación directa `/#vera`, hash tras reload, sección bajo el header, interacción mock sin duplicación, nueva conversación, mobile 390, HE/RTL, matriz 390/768/1280 sin overflow ni errores |
| `e2e/public-home-social-meta.spec.ts` | SEO, OG, canonical `/` y `/t360` |
| `e2e/public-vera.spec.ts` | Vera estructurada mock (12) + 2 skips preexistentes + smoke real (con `T360_REAL_E2E=1`) |
| `e2e/public-vera-*.spec.ts` (family) | Feasibility, adversarial, email orders/postsale, kommo, salesforce, phone problems, mobile sequential, new conversation |
| `e2e/diagnosticador-dev-serving.spec.ts` | Serving DEV vs. artefacto productivo |
| `e2e/diagnosticador-loader-manifest.spec.ts` | Manifest, loader, SRI positivo/negativo |
| `e2e/diagnosticador-{mount,loader,asset,embed,external,script}-demo.spec.ts` | Mount/destroy/remount, contrato `auth → turn` |
| `e2e/diagnosticador-{browser-loader,cross-origin,cross-origin-integrity}-fixture.spec.ts` | Cross-origin allow/deny, integrity |
| `e2e/public-vera-embed-mamamia360.spec.ts` | Cliente externo real |

## 6. Reglas para futuros módulos (protección estructural)

1. Namespaces separados: frontend, backend, eventos y storage por módulo.
2. Stores separados; la home/Vera no comparten estado con Console.
3. Rutas propias: los módulos standalone entran por rutas propias, nunca
   reemplazando `/`, `/#vera` o `/t360`.
4. CSS encapsulado: no introducir estilos globales sin revisión; no usar
   selectores globales destructivos.
5. No reutilizar componentes específicos de Vera (`DiagnosticadorCore`,
   `PublicVeraEntry`) para otros módulos.
6. No modificar `global.js` sin validar URLs públicas (única fuente de verdad).
7. No modificar loaders existentes al agregar loaders nuevos; cada módulo
   tiene su propio manifest, entry y namespace.
8. Eventos nuevos (`t360:*`) no deben colisionar con los de Vera.
9. El registro de navegación de Console no altera la home.
10. El build de un módulo nuevo no debe sobrescribir artefactos embed
    existentes en `public/embed/` ni `dist/embed/`.
11. Permisos y datos aislados por workspace y módulo.
12. Componentes embebibles con contratos propios (manifest + entry + auth).

## 7. Reserva conceptual para Team360 Flow (no implementar en este gate)

- Página standalone propia (no `/` ni `/#vera`).
- Namespace backend, frontend, loader, manifest, entry, eventos y APIs propios.

## 8. Referencias

- `docs/ux/team360-console-ux-stages-1-8-consolidated.md` (migración UX, sin
  cambios públicos).
- `docs/diagnosticador_embed_installation_guide_v1.md` (integración cliente).
- `docs/diagnosticador_loader_manifest_v1.md`, `..._loader_integrity_v1.md`,
  `..._loader_integrity_enforcement_v1.md`, `..._loader_distribution_v1.md`.
- `docs/diagnosticador_cross_origin_fixture_v1.md`,
  `docs/diagnosticador_embed_dev_serving_v1.md`.
- `lat.md/team360-runtime-operational-policy.md`,
  `lat.md/diagnosticador-embeddable-component-architecture.md`.
- `SrvRestAstroLS_v1/docs/status_actual.md` (sección del gate).
