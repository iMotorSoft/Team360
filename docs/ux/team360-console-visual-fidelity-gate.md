# Team360 Console visual fidelity gate

Este informe registra el gate visual ejecutado el 2026-08-11 contra las capturas entregadas, la rama técnica de diseño y la implementación funcional vigente.

## Resultado

El resultado es `TEAM360_CONSOLE_VISUAL_FIDELITY_BLOCKED`: las 15 capturas finales muestran Home pública y Vera, no Team360 Console. No existe una referencia visual final de Console en el directorio indicado.

La rama UX aporta dos capturas técnicas de dashboard y permite confirmar una fidelidad estructural alta, pero su propio handoff las declara pendientes de revisión. No sustituyen una captura final aprobada.

## Fuentes y prioridad

La auditoría respetó la siguiente jerarquía sin cambiar de rama ni copiar lógica desde el handoff.

| Fuente | Uso efectivo |
| --- | --- |
| `feature/console-backend-core` | Fuente de verdad funcional y único worktree de escritura. |
| `ux/team360-console-design-handoff` | Referencia técnica consultada mediante `git show`, `git diff` y `git archive`. |
| `/home/issajar/Downloads/WhatsApp Unknown 2026-08-11 at 10.14.22 AM (3)` | Referencia visual final; contiene únicamente Home/Vera móvil. |

## Estado Git

La validación comenzó desde el commit que incorporó los probes Gmail y sin cambios pendientes.

| Campo | Valor |
| --- | --- |
| Rama | `feature/console-backend-core` |
| HEAD inicial | `681b5a03ddd772e2ee9ce0d3e8f095607207a6e3` |
| Worktree inicial | Limpio |
| Push | No |
| Deploy | No |

## Inventario de capturas finales

Las 15 referencias son JPEG verticales comprimidos, en español, sin sidebar de Console. La resolución sugiere un viewport móvil cercano a 320 px.

| Captura | Resolución | Pantalla probable | Ruta equivalente | Estado UI | Confianza |
| --- | ---: | --- | --- | --- | --- |
| `WhatsApp Image 2026-08-10 at 4.17.08 PM.jpeg` | 320×548 | Home, hero | `/` | Header sticky, hero y CTA | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.09 PM.jpeg` | 321×545 | Home, entrada a Vera | `/#vera` | Presentación y ejemplos | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.09 PM (1).jpeg` | 313×546 | Vera | `/#vera` | Ejemplo seleccionado en formulario | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.10 PM.jpeg` | 319×521 | Vera | `/#vera` | Conversación con estado de error | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.10 PM (1).jpeg` | 315×536 | Home, antes/después | `/` | Card comparativa | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.10 PM (2).jpeg` | 318×536 | Home, lógica | `/` | Introducción y card 01 | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.11 PM.jpeg` | 323×532 | Home, lógica | `/` | Cards 02–04 | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.11 PM (1).jpeg` | 317×546 | Home, tareas | `/` | Primer grupo de cards | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.11 PM (2).jpeg` | 319×537 | Home, tareas/método | `/` | Fin de tareas e inicio de método | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.12 PM.jpeg` | 322×548 | Home, método | `/` | CTA y pasos 01–04 | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.12 PM (1).jpeg` | 317×549 | Home, soluciones | `/` | Título y primera solución | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.13 PM.jpeg` | 311×554 | Home, soluciones | `/` | Cards Social, Sales y Knowledge | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.13 PM (1).jpeg` | 315×547 | Home, equipos | `/` | Operación, ventas y partners | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.14 PM.jpeg` | 314×545 | Home, FAQ/CTA | `/` | Acordeón y comienzo del CTA | Alta |
| `WhatsApp Image 2026-08-10 at 4.17.14 PM (1).jpeg` | 319×530 | Home, CTA/footer | `/` | CTA final y comienzo del footer | Alta |

Los timestamps del filesystem son `2026-08-11 10:14:20 -0300`; los nombres indican una captura original del 2026-08-10 entre 16:17:08 y 16:17:14.

## Mapeo captura a código

El contenido visible y el texto se validaron contra el código funcional, no solo contra los nombres de archivo.

| Grupo de capturas | Ruta | Componente principal | Superficie | Test existente |
| --- | --- | --- | --- | --- |
| Hero, secciones, soluciones, método, equipos, FAQ y CTA | `/` | `src/pages/index.astro` y `PublicMarketingLayout.astro` | Home pública protegida | `public-home-vera-protection.spec.ts` |
| Entrada, formulario y conversación Vera | `/#vera` | `PublicVeraEntry.svelte` y `DiagnosticadorCore.svelte` | Vera/Diagnosticador protegidos | `public-home-vera-protection.spec.ts`, `public-vera.spec.ts` |
| Team360 Console | Sin captura entregada | `ConsoleAppLayout.astro` y `components/console/**` | Alcance solicitado | Suites `console-*.spec.ts` |

No se asignó ninguna captura a shell, dashboard, Clients, Services, Tasks, Runs, Workers, Organizations, Partners, Workspaces, Team, Settings, Support, Results o ServiceDetail.

## Inventario técnico de Console

Las rutas reales se inventariaron para dejar preparado el gate cuando exista una referencia visual final de Console.

| Pantalla | Ruta | Componente | Stage | Test existente |
| --- | --- | --- | --- | --- |
| Shell | `/w/[workspaceId]/` | `ConsoleAppLayout.astro`, `AppShell.svelte` | Shell/Stage 3 | `console-shell.spec.ts` |
| Dashboard | `/w/[workspaceId]/` | `ConsoleDashboard.svelte` | Stage 4 | `console-shared-components-stage3.spec.ts` |
| Clients | `/w/[workspaceId]/clients` | `ConsoleSectionPage.svelte` | Stage 4 | Regresión consolidada de Console |
| Services | `/w/[workspaceId]/services` | `ServicesList.svelte` | Stage 5 | `console-operation-stage5.spec.ts` |
| Tasks | `/w/[workspaceId]/tasks` | `TasksList.svelte` | Stage 5 | `console-operation-stage5.spec.ts` |
| Runs | `/w/[workspaceId]/runs` | `RunsList.svelte` | Stage 5 | `console-operation-stage5.spec.ts` |
| Workers | `/w/[workspaceId]/workers` | `WorkersList.svelte` | Stage 5 | `console-operation-stage5.spec.ts` |
| Organizations | `/w/[workspaceId]/organizations` | `ConsoleSectionPage.svelte` | Stage 6 | `console-organization-stage6.spec.ts` |
| Partners | `/w/[workspaceId]/partners` | `ConsoleSectionPage.svelte` | Stage 6 | `console-organization-stage6.spec.ts` |
| Workspaces | `/w/[workspaceId]/workspaces` | `ConsoleSectionPage.svelte` | Stage 6 | `console-organization-stage6.spec.ts` |
| Team | `/w/[workspaceId]/team` | `TeamList.svelte` | Stage 6 | `console-organization-stage6.spec.ts` |
| Settings | `/w/[workspaceId]/settings` | `WorkspaceSettings.svelte` | Stage 7 | `console-settings-support-stage7.spec.ts` |
| Support | `/w/[workspaceId]/support` | `ConsoleSectionPage.svelte` | Stage 7 | `console-settings-support-stage7.spec.ts` |
| Results | `/w/[workspaceId]/results` | `ConsoleSectionPage.svelte` | Stage 8 | `console-results-service-detail-stage8.spec.ts` |
| ServiceDetail | `/w/[workspaceId]/services/[serviceId]` | `ServiceDetail.svelte` | Stage 8 | `console-results-service-detail-stage8.spec.ts` |

ServiceDetail conserva ocho tabs para audiencias técnicas: Resumen, Resultados, Reportes, Alertas, Tareas, Historial, Configuración y Técnico. La audiencia cliente oculta los dos tabs técnicos por seguridad funcional.

## Comparación con la rama UX

La consulta selectiva confirmó que la implementación funcional conserva la composición técnica del handoff sin adoptar sus divergencias de lógica.

| Área | Referencia UX | Implementación funcional | Clasificación |
| --- | --- | --- | --- |
| Shell | Sidebar fijo, topbar, breadcrumbs y content grid | Misma composición y responsive | A — coincidencia técnica |
| Dashboard desktop | Métricas, servicios, prioridades, actividad y resultados | Misma jerarquía; datos y densidad actualizados | D — diferencia funcional preservada |
| Dashboard mobile | Stacking de métricas y cards | Mismo orden semántico y stacking | A — coincidencia técnica |
| Branding | `Team360Logo.astro` con isotipo T turquesa y wordmark Team/360 | El gate original solo comprobó carga del asset del Sidebar y no auditó `MockAccessLayout` | Diferencia confirmada y corregida en el gate específico de branding |
| Métricas | Valores mock históricos 4/1/1/7 | Datos funcionales actuales 5/1/2/8 | D — diferencia funcional preservada |
| Cliente | Netzaj Racing en handoff | Perfil cliente vigente Team360.live | D — diferencia funcional preservada |
| Diagnosis | La rama UX elimina `ConsoleDiagnosis` | La rama funcional conserva Diagnosis y su ruta | D — `DIFFERENCE PRESERVED FOR FUNCTIONAL SAFETY` |
| Cards | Variantes históricas blancas y dark | Pasteles semánticos y prioridades claras | E — requiere captura final de Console |

Se revisaron selectivamente `AppShell.svelte`, `Sidebar.svelte`, `Topbar.svelte`, `ContextBanner.svelte` y `ConsoleDashboard.svelte`. No se copió `CustomSelect`, markup completo, stores, mocks ni navegación desde UX.

### Corrección del gate de branding

La revisión específica posterior determinó que el gate original no cubrió la identidad completa de marca de Console. Las capturas finales disponibles eran de Home/Vera, y la comparación técnica de Console se concentró en estructura y carga de assets.

La prueba anterior aceptaba cualquier URL que contuviera `team360_logo`, tuviera HTTP 200 y dimensiones válidas. No distinguía `team360_logo_t.png`, colores del wordmark ni el `BrandMark` alternativo usado por `MockAccessLayout.astro` en login y select-workspace.

La causa raíz fue una cobertura incompleta: se validó disponibilidad, no identidad. El gate de branding corrige esa omisión con un identificador estable de variante, el asset fuente exacto, colores diferenciados Team/360 y cobertura desktop, mobile y RTL.

## Comparación de las capturas protegidas

Las capturas finales sí presentan diferencias reales contra Home/Vera actuales, pero estas superficies quedaron explícitamente fuera del alcance de modificación.

| Grupo | Diferencias iniciales | Clasificación | Decisión |
| --- | --- | --- | --- |
| Header | Logo, CTA “Comenzar” y proporciones distintas | B visual + D copy | Preservado: Home protegida |
| Hero | Fondo claro sin foto frente a hero oscuro con imagen; copy secundario distinto | B visual + D contenido | Preservado: Home protegida |
| Antes/después | Título, bullets, fondos y radios distintos | B visual + D contenido | Preservado: Home protegida |
| Lógica/método | Agrupación y textos distintos | C estructural + D contenido | Preservado: Home protegida |
| Soluciones/tareas | Cards y taxonomía distintas | C estructural + D contenido | Preservado: Home protegida |
| Vera | Paleta, layout, formulario y estado de error distintos | C estructural + D funcional | Preservado: Vera/Diagnosticador protegidos |
| Equipos/FAQ/CTA | Copy, fondos y jerarquía distintos | B visual + D contenido | Preservado: Home protegida |

La implementación pública no se modificó. Copiar estas referencias dentro de este gate habría violado la protección de Home, Vera y Diagnosticador.

## Revisión de interfaz

La auditoría aplicó las reglas vigentes de Web Interface Guidelines y verificó foco, teclado, targets, semántica, responsive y estados mediante código y E2E.

Hallazgos preexistentes fuera del cambio visual:

- `src/components/console/Topbar.svelte:46`: el control Buscar es visual y no tiene acción; requiere una decisión funcional, no un ajuste de fidelidad.
- `src/components/console/reports/ReportsList.svelte:67`: Astro DEV advierte `a11y_no_noninteractive_tabindex`; el test vigente usa foco explícito para la región scrollable y este gate no alteró ese contrato.
- `src/components/console/diagnosis/ConsoleDiagnosis.svelte:234`: el placeholder usa tres puntos en lugar del carácter `…`; no se tocó porque Diagnosticador está protegido.
- `src/lib/t360/diagnosticador/DiagnosticadorCore.svelte:61` y `VeraEmbedWrapper.svelte:26`: Astro DEV emitió hints preexistentes sobre referencias al valor inicial; las suites protegidas pasan y no se modificó Diagnosticador.
- `src/styles/global.css:76`: las reglas globales existentes de `touch-action` y foco son deliberadas; este gate no agregó selectores globales.

## Cambios realizados

No hubo cambios de CSS, markup ni componentes. El único archivo versionable creado es este informe.

| Archivo | Pantalla | Diferencia | Cambio | Impacto funcional |
| --- | --- | --- | --- | --- |
| `docs/ux/team360-console-visual-fidelity-gate.md` | Gate transversal | Faltaba evidencia consolidada | Informe de validación | Ninguno |

## Evidencia visual

La evidencia pesada se conserva localmente bajo una ruta ignorada por Git y no forma parte del commit.

| Evidencia | Ruta local | Resultado |
| --- | --- | --- |
| Referencias finales | Directorio externo informado por diseño | 15 JPEG Home/Vera |
| Referencia UX desktop | `ux/team360-console-design-handoff:SrvRestAstroLS_v1/docs/design-review/screenshots/desktop-console-dashboard-team360.png` | 1440×1615 |
| Referencia UX mobile | `ux/team360-console-design-handoff:SrvRestAstroLS_v1/docs/design-review/screenshots/mobile-console-dashboard.png` | 390×2538 |
| Baseline actual | `SrvRestAstroLS_v1/astro/screenshots/ux-fidelity/baseline/` | Home por secciones y Console 1440/390 |
| Final actual | `SrvRestAstroLS_v1/astro/screenshots/ux-fidelity/final/` | Recaptura sin cambios funcionales |

Las capturas baseline/final de Console y ocho secciones públicas fueron byte-idénticas. El hero y full-page públicos variaron por render dinámico, sin diferencias humanas nuevas ni cambios de código.

## Validación por pantalla

La siguiente ficha resume el único screen de Console con referencia técnica y el alcance real de las referencias finales.

```text
SCREEN: Console Dashboard
ROUTE: /w/ws-team360-control/
REFERENCE: rama UX, captura técnica desktop/mobile
VIEWPORT: 1440 y 390

LAYOUT: PASS
TYPOGRAPHY: PASS
CARDS: DIFFERENCE (sin captura final aprobada)
CONTROLS: PASS
TABLES: N/A
RESPONSIVE: PASS
FUNCTIONALITY: PASS

VISUAL FIDELITY: HIGH contra referencia técnica UX
FINAL VISUAL FIDELITY: NO EVALUABLE contra capturas finales
```

```text
SCREEN: Home pública y Vera
ROUTE: / y /#vera
REFERENCE: 15 capturas finales
VIEWPORT: aproximadamente 320

LAYOUT: DIFFERENCE
TYPOGRAPHY: DIFFERENCE
CARDS: DIFFERENCE
CONTROLS: DIFFERENCE
TABLES: N/A
RESPONSIVE: PASS
FUNCTIONALITY: PASS

VISUAL FIDELITY: MEDIUM
FINAL VISUAL FIDELITY: PRESERVADA SIN CAMBIOS POR SUPERFICIE PROTEGIDA
```

## Matriz final

La matriz separa salud funcional de fidelidad final evaluable.

| Pantalla | Captura | Viewport | Baseline | Final | Funcional | Estado |
| --- | --- | ---: | --- | --- | --- | --- |
| Dashboard owner | UX técnica desktop | 1440 | High | High | PASS | `BLOCKED_REFERENCE_AMBIGUOUS` |
| Dashboard cliente | UX técnica mobile histórica | 390 | High | High | PASS | `PASS_WITH_FUNCTIONAL_DIFFERENCE` |
| Shell y rutas Stages 4–8 | Sin captura final | 390/768/1280 | No evaluable | No evaluable | PASS | `BLOCKED_REFERENCE_AMBIGUOUS` |
| Home pública | 13 capturas finales | ≈320 | Medium | Sin cambios | PASS | `PASS_WITH_FUNCTIONAL_DIFFERENCE` |
| Vera | 2 capturas finales | ≈320 | Medium | Sin cambios | PASS | `PASS_WITH_FUNCTIONAL_DIFFERENCE` |

## Pruebas y resultados

Las pruebas se ejecutaron contra el runtime oficial local, con Playwright como automatizador y sin `webServer` alternativo.

| Gate | Resultado |
| --- | --- |
| Console shell + Stages 3, 5, 6, 7 y 8 | 27/27 PASS |
| Home + Vera aisladas | 21/21 PASS |
| Embed, loader, manifest, entry, SRI, cross-origin, mount y Mamamia360 | 20/20 PASS |
| Corrida protegida combinada inicial | 40 PASS / 1 fallo por 404 de orden de suite |
| Repetición aislada del caso fallido | 1/1 PASS; no reproducible |
| `pnpm check` | 0 errores, 0 warnings, 7 hints preexistentes |
| `pnpm build` | PASS; 146 páginas |
| Consola y requests durante capturas | 0 errores y 0 requests fallidos |

La corrida dividida estable cubre 41/41 casos protegidos. El 404 de la corrida combinada no se reprodujo solo ni en el grupo Home/Vera y no motivó un cambio en superficies protegidas.

## Funcionalidad preservada

La validación confirmó navegación, rutas, acciones cubiertas, tablas, formularios, tabs, shell, responsive, teclado y RTL mediante las suites existentes.

Home intacta. Vera intacta. Diagnosticador intacto. Embed intacto. Loader intacto. Manifest intacto. Entry intacto. SRI intacto. CORS intacto. Allowed origins intactos. Mamamia360 no tocado.

## Servicios y entorno

Backend y Astro se levantaron únicamente mediante `backend-dev.sh` y `astro-dev.sh`. El launcher verificó los servicios permanentes sin administrarlos.

PostgreSQL no fue iniciado, detenido ni reiniciado. Milvus no fue iniciado, detenido ni reiniciado. LiteLLM no fue iniciado, detenido ni reiniciado.

`agent-browser` no estaba instalado y no se agregó ninguna dependencia. La evidencia reproducible se generó con Playwright + Chromium, el gate oficial del proyecto.

## Conclusión

La implementación de Console coincide estructuralmente con la referencia técnica UX y conserva toda la funcionalidad, pero no puede aprobarse contra las capturas finales porque esas capturas corresponden exclusivamente a Home/Vera.

Para cerrar el gate hace falta un set aprobado de capturas de Team360 Console. No se avanzó a producción, deploy ni push.
