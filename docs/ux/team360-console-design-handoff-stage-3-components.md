# Etapa 3 — Adaptación visual progresiva de componentes compartidos

Este documento registra el alcance, las decisiones y la evidencia de la Etapa 3 sobre la rama funcional de Team360 Console.

Fecha: 2026-08-04.

Base funcional inicial: `feature/console-backend-core` @ `c2ccf975669c964605d4eed0790544e2db7d2202`.

Referencia visual: `ux/team360-console-design-handoff` @ `a75909d`.

## 1. Baseline

El HEAD esperado de Etapa 2 era `546e945`; el HEAD real incluía seis commits legítimos posteriores, limitados a correcciones y documentación del embed.

| Validación inicial | Resultado |
| --- | --- |
| Rama | `feature/console-backend-core` |
| Worktree | limpio |
| `pnpm check` | PASS: 0 errores, 0 warnings, 6 hints preexistentes |
| `pnpm build` | PASS: 146 páginas |
| Scripts disponibles | `dev`, `build`, `preview`, `check`, `test:e2e`, `test:e2e:headed` |
| Scripts ausentes | `test`, `lint` |

Los tres errores históricos de `src/lib/t360/embed/mount.ts` ya no existen en el HEAD actual: fueron corregidos legítimamente en `907ed8e`. Esta etapa no modificó ese archivo.

## 2. Inventario funcional

El relevamiento encontró una capa UI inicial y varias composiciones repetidas en consola. La tabla identifica usos, contratos y riesgo antes de la adaptación.

| Componente | Archivo | Pantallas que lo usan | Lógica, props o eventos | Riesgo |
| --- | --- | --- | --- | --- |
| `Card` | `src/components/ui/Card.svelte` | Diagnosticador, dashboard | `children`, `title`, clases | medio: semántica y padding |
| `SectionHeader` | `src/components/ui/SectionHeader.svelte` | servicios, reportes, alertas, tareas, equipo, settings | eyebrow, title, description, actions | bajo |
| `StatCard` | `src/components/ui/StatCard.svelte` | servicios, detalle, dashboard | label, value, description, trend | bajo |
| `Badge` / `StatusBadge` | `src/components/ui/*.svelte` | shell y todas las listas | estado → variante semántica | medio: no cambiar significado |
| `Alert` | `src/components/ui/Alert.svelte` | estados de error | variante y contenido | medio: `role=alert` |
| `EmptyState` | `src/components/ui/EmptyState.svelte` | listas y detalle | título, descripción, próximo paso, acciones | bajo |
| `Loading` | `src/components/ui/Loading.svelte` | Diagnosticador | label y `role=status` | bajo |
| `Button` | `src/components/ui/Button.svelte` | detalle de servicio; acciones del Diagnosticador | type, disabled, loading y atributos nativos | alto dentro de formularios |
| Selects nativos | `Topbar`, `ProfileSwitcher`, `WorkspaceSwitcher` | shell | `onchange`, value, navegación, locale | alto si se reemplazan |
| Textarea nativo | `ConsoleDiagnosis.svelte` | Diagnosticador de consola | `bind:value`, teclado, submit por acción | alto |
| Tablas | `ReportsList`, `ConsoleSectionPage` | reportes y clientes | columnas, acciones, responsive | medio |
| Dropdown | `NotificationCenter.svelte` | topbar | open, close, alertas filtradas | alto: foco y overlays |
| Modal | no existe en consola | ninguna | sin contrato real | no crear |
| Filtros y paginación | no existen en las pantallas elegidas | ninguna | sin contrato real | no crear |

Las duplicaciones principales eran superficies de cards, encabezados, botones deshabilitados, tablas con overflow y cards de alerta repetidas entre la página de alertas y NotificationCenter.

## 3. Matriz de riesgo UX

La comparación se realizó con `git show a75909d:<ruta>` y `git diff feature/console-backend-core..a75909d -- <ruta>` sin merge, rebase ni cambio de rama.

| Propuesta | Clase | Decisión | Motivo |
| --- | --- | --- | --- |
| Variantes visuales de `Card` | A, visual segura | reinterpretada | conserva tag semántico y `title` funcional |
| Tokens de badges, botones y estados | A, visual segura | adoptada | usa tokens de Etapa 1 y foco visible |
| `AlertCard` del handoff | B, estructural adaptable | reinterpretada | se limita al tipo `Alert` real; no une tasks/reportes |
| `CustomSelect` | C, funcional peligrosa | descartada | no demuestra flechas, Enter, foco activo ni typeahead equivalentes |
| Select nativo con wrapper visual | A, visual segura | adoptada | preserva teclado, labels, mobile y eventos |
| Tabla → cards en mobile | B, estructural adaptable | conservada | ya existía y no elimina información ni acciones |
| Modal genérico sin consumidor | C, abstracción sin uso | descartada | no existe un flujo real compatible |
| Mocks, opciones o handlers del handoff | C, funcional peligrosa | descartada | la rama funcional sigue siendo fuente de verdad |

## 4. Pantallas representativas

Se eligieron cuatro superficies para cubrir el sistema compartido sin migrar todas las rutas de la consola.

| Ruta | Cobertura | Datos | Funciones críticas | Resultado |
| --- | --- | --- | --- | --- |
| `/w/ws-team360-control/` | dashboard, métricas, cards, badges | mock preexistente de consola | audiencia, links, estados | adaptada y validada |
| `/w/ws-team360-control/reports` | tabla, filas, mobile, acción disabled | mock preexistente | columnas, estado, responsive | adaptada y validada |
| `/w/ws-team360-control/diagnosis` | textarea, botones, loading, error, resultado | backend real | binding, pasos, submit, clasificación | adaptada y validada |
| `/w/ws-team360-control/alerts` | alertas, empty state, dropdown | mock preexistente | severidad, estado, acción sugerida, overlay | adaptada y validada |

No se sustituyeron datos reales ni se agregaron mocks. La presencia de mocks de consola es anterior a esta etapa y permanece explícita en la interfaz.

## 5. Implementación por bloque

Los cambios se hicieron en bloques pequeños con `check`, `build`, diff y smoke visual entre bloques.

### 5.1 Cards y contenedores

Se centralizaron variantes visuales sin unificar responsabilidades funcionales distintas.

- `Card` agrega variantes `default`, `large`, `flat`, `light`, `dark` y `mini`, conserva `title` y permite tags semánticos acotados.
- `SectionHeader` agrega nivel y actions responsive.
- `StatCard` usa tokens de Etapa 1.
- El dashboard consume `SectionHeader`, `StatCard` y `Card` sin cambiar datos, links ni condiciones por audiencia.

### 5.2 Badges, alertas y estados

Los estados conservan texto y significado; el color es un refuerzo y no la única señal.

- `Badge` y `Alert` dejan de depender de clases DaisyUI genéricas y usan variantes Team360.
- `EmptyState` agrega una presentación compacta.
- `AlertCard` acepta sólo el contrato `Alert` existente y se reutiliza en alertas y notificaciones.
- Loading conserva `role=status`; error conserva `role=alert`.

### 5.3 Botones y acciones

El wrapper reenvía atributos y eventos nativos y mantiene un default seguro.

- `Button` conserva `type="button"` por defecto, disabled, loading y `aria-busy`.
- Se agregan tamaños y variantes con targets táctiles mínimos.
- Se migran acciones compatibles del Diagnosticador y reportes.
- Los botones de opciones permanecen específicos y reciben `type="button"` explícito.

### 5.4 Formularios

La adaptación evita reemplazos interactivos de riesgo.

- `Select` envuelve el control nativo y se usa en locale, perfil y workspace con los mismos handlers y values.
- `Textarea` conserva `bind:value` y atributos nativos.
- La pregunta y descripción del Diagnosticador quedan asociadas con `aria-labelledby` y `aria-describedby`.
- Se corrigió el orden bidi del contador numérico con aislamiento LTR local.
- No se crean `Input`, `FilterBar` ni filtros ficticios porque no existen dos usos compatibles en el alcance.

### 5.5 Tablas y listados

Las tablas conservan estructura, contenido y acciones.

- `DataTable` aporta superficie, overflow horizontal controlado y región con etiqueta accesible; los controles reales de cada fila conservan la navegación por teclado.
- Se usa en reportes y clientes.
- La vista mobile preexistente en cards se conserva íntegra.
- No se agregan sorting ni paginación inexistentes.

### 5.6 Dropdowns y modales

NotificationCenter es el único overlay real compatible encontrado.

- Se agrega Escape, click externo, `aria-controls`, `aria-expanded`, región etiquetada y retorno de foco.
- Se corrige el badge posicional a `inset-inline-end` mediante `end` para RTL.
- No se crea un modal genérico sin consumidor real; queda diferido hasta una pantalla que demuestre el contrato.

## 6. Accesibilidad, idiomas y responsive

Los gates cubren teclado, foco, controles nativos, estados y layout en los tamaños requeridos.

| Área | Evidencia |
| --- | --- |
| Teclado | textarea por keyboard, controles de tabla en el orden nativo, Escape del dropdown |
| Foco | outlines visibles y retorno al trigger tras Escape |
| Labels | selects con nombre accesible; textarea asociada a pregunta y ayuda |
| Disabled | botones disabled reales, no sólo visuales |
| Color | badges mantienen labels de estado visibles |
| Touch | botones compartidos con mínimo 40–48 px según tamaño |
| ES / EN / HE | selector nativo y navegación validados por E2E |
| RTL | `dir=rtl`, contador bidi y badge lógico del dropdown |
| Responsive | screenshots y métricas en 390, 768 y 1280 px; sin overflow de documento |

El contenido interno del Diagnosticador de consola continúa en español, igual que antes de esta etapa; no se alteraron claves ni contratos de i18n. La localización completa de pantallas internas queda fuera del alcance visual.

## 7. Validaciones ejecutadas

Las pruebas se ejecutaron con backend y Astro levantados sólo mediante `backend-dev.sh` y `astro-dev.sh`.

| Comando o gate | Resultado |
| --- | --- |
| `pnpm check` inicial y por bloque | PASS: 0 errores, 0 warnings, 6 hints preexistentes |
| `pnpm build` inicial y por bloque | PASS: 146 páginas |
| Etapa 3 + shell E2E | PASS: 11/11 |
| `e2e/diagnosis.spec.ts` | PASS: 1 passed, 1 skip preexistente para backend apagado |
| `e2e/public-vera.spec.ts` dentro de suite protegida | pruebas ejecutables PASS; 2 skips preexistentes/condicionales en el conjunto |
| Manifest, loader, SRI y cross-origin | PASS después de Gate 3B: 20/20 en serving, loader, integrity, fixtures y superficies embed |
| Smoke visual Playwright | dashboard, alertas y formulario inspeccionados; 390/768/1280 sin overflow |
| Consola y red | único error observado: 404 preexistente del logo `[object Object]` en Sidebar |
| `git diff --check` | PASS en cada bloque |
| `agent-browser` | no disponible en el entorno; se usó Playwright + Chromium |

## 8. Bloqueos ambientales y errores

La etapa no introduce errores conocidos. El bloqueo detectado durante su validación quedó resuelto por el Gate 3B en un commit separado.

### 8.1 Entry del embed servido en desarrollo

La causa raíz era que el build genera `dist/embed/team360-diagnosticador.js`, pero `astro-dev.sh` no exponía `dist`.

- el Gate 3B prepara el build y sirve sólo el grafo allowlisted mediante configuración DEV;
- manifest, loader y entry: HTTP 200;
- SHA-256, SRI, CORS local y cross-origin: PASS;
- loader, manifest y entry productivos permanecen intactos;
- no se usó `astro preview`, proxy ni servidor paralelo.

### 8.2 Logo del sidebar

El smoke visual detectó `background-image: url('[object Object]')`, que genera un 404 relativo en todas las rutas de consola.

El problema es preexistente en `Sidebar.svelte`, no fue causado por los componentes compartidos y no se corrigió para evitar ampliar la etapa.

### 8.3 Herramienta exploratoria

El binario `agent-browser` no está instalado. No se instalaron dependencias; Playwright + Chromium cubrió la validación reproducible y visual.

## 9. Protección de la fuente funcional

El diff no incluye backend, stores, rutas, auth, permisos ni artefactos públicos del embed.

- Vera y `/t360`: sin cambios; pruebas ejecutables PASS.
- Diagnosticador embebible: sin cambios.
- `PublicVeraEntry`, loader, manifest, mount, entry, SRI, CORS y allowed origins: sin cambios.
- Contratos frontend-backend y DEV/PRO: sin cambios.
- PostgreSQL, Milvus y LiteLLM: verificados por preflight; no iniciados, detenidos ni reiniciados por esta tarea.

## 10. Diferencias pendientes

Las diferencias se difieren para proteger funcionalidad o porque no existe todavía un contrato real.

- CustomSelect completo del handoff.
- Modales compartidos sin consumidor real.
- Inputs, filtros, sorting y paginación inexistentes en las pantallas elegidas.
- Migración visual de las restantes rutas y listas.
- Localización integral del contenido interno de consola.
- Corrección aislada del asset del logo de Sidebar.

## 11. Estado de cierre

El código de la Etapa 3 está implementado y sus pruebas focalizadas y protegidas pasan sobre el runtime oficial.

Resultado: `STAGE 3 SHARED COMPONENTS PASS`.

El Gate 3B quedó aislado en su propio commit; corresponde crear el commit atómico de Etapa 3 por separado.

## 12. Próxima etapa recomendada

Etapa 4: migración visual pantalla por pantalla de las secciones principales de la consola, reutilizando el sistema compartido validado en la Etapa 3. La corrección aislada del logo de Sidebar puede tratarse como una regresión técnica acotada sin mezclarla con esa migración.
