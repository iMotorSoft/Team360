# ADR-006 - Plantilla base replicable para nuevos proyectos

Estado: aprobado.

Fecha: 2026-06-24.

## Contexto

Team360 consolido una forma de trabajar que combina codigo productivo,
arquitectura viva, bitacoras tecnicas, documentacion de negocio, evidencia
auditable, skills locales de agentes, Playwright como gate E2E y politicas
operativas explicitas.

Esa estructura redujo ambiguedad sobre:

- donde vive cada tipo de decision;
- como arrancan los agentes de codigo;
- que rama corresponde a cada tipo de trabajo;
- que evidencia hace falta para declarar PASS;
- como evitar fixes a ciegas cuando una prueba manual encuentra bugs aunque los
  tests existentes pasen.

La misma base conviene reutilizar en proyectos nuevos para evitar volver a
decidir la estructura documental, la separacion de responsabilidades y las
reglas minimas de validacion desde cero.

## Decision

Team360 adopta una plantilla replicable para nuevos proyectos basada en:

1. `AGENTS.md` como contrato obligatorio para agentes.
2. `.agents/skills/<project-name>/SKILL.md` como skill local principal.
3. `lat.md/` como arquitectura viva e invariantes estables.
4. `docs/` para material narrativo de negocio, producto, estrategia, UX,
   ADRs y plantillas.
5. `data/reports/` para evidencias, snapshots, relevamientos y reportes
   exportables.
6. `<app-dir>/docs/status_actual.md` como bitacora tecnica principal del
   runtime.
7. `status_actual.md` por directorio documental activo.
8. Separacion estricta entre:
   - arquitectura viva;
   - documentacion tecnica runtime;
   - documentacion negocio/producto;
   - evidencia generada.
9. Mermaid como fuente canonica versionable para diagramas tecnicos.
10. Renders SVG/PNG/Excalidraw solo como artefactos derivados opcionales.
11. Politica de root cause debugging para bugs no triviales.
12. Playwright + Chromium como gate E2E oficial.
13. Browser MCP como herramienta exploratoria y de diagnostico visual.
14. Preflight de servicios reales antes de pruebas que dependan de DB, vector
    store, gateway de modelos o proveedores externos.
15. Evidencia minima PASS/FAIL para validaciones y despliegues.
16. Politica de secretos y sanitizacion de credenciales.
17. Politica de dependencias globales vs locales.
18. Politica de laboratorio tecnico reproducible.
19. Politicas de deploy explicitas antes de automatizar despliegues.
20. Politica de modelo/alias/fallback cuando el proyecto use IA.
21. LiteStar/Litestar como servidor Python por defecto para nuevos proyectos
    iMotorSoft.
22. `ls_iMotorSoft_Srv01.py` como entrypoint backend canonico; `app.py` no es
    el archivo principal por defecto.

La plantilla ejecutable vive en:

```text
docs/templates/project-structure-template.md
```

## Herramientas externas como fuente de conceptos

La plantilla permite extraer conceptos de herramientas externas, pero no
adoptarlas automaticamente como dependencia.

Decision especifica tomada desde `https://github.com/garrytan/gstack`:

| Herramienta gstack | Que se adopta | Que no se adopta |
|---|---|---|
| `/diagram` | Mermaid como fuente canonica versionable en Git; renders derivados opcionales | skill completo, `.gstack`, telemetry, browse daemon, hooks, commits automaticos, triplet obligatorio, dependencia de gstack |
| `/investigate` | no corregir sin causa raiz, reproduccion exacta, hipotesis verificable, evidencia, regla de tres hipotesis, debug report y regresion | skill completo, `.gstack`, learnings cross-project, freeze hooks, telemetry, commits automaticos |

Regla:

```text
Extraer criterio operativo.
No incorporar automatismos externos sin decision propia.
```

## ADR vs lat.md

La plantilla conserva dos niveles distintos:

| Capa | Uso |
|---|---|
| `docs/adr/` | decision tomada, contexto, rationale y consecuencias historicas |
| `lat.md/` | invariante vivo que agentes y codigo deben obedecer |

Un ADR puede apuntar a un documento `lat.md/`, pero no debe duplicarlo
completamente. Si la regla es operativa y debe ser obedecida por agentes,
pertenece a `lat.md/`.

## Consecuencias

- Los nuevos proyectos arrancan con una estructura documental y operativa
  conocida.
- Las decisiones estables quedan en `lat.md/`, no dispersas en chats o
  bitacoras.
- Las evidencias y snapshots no contaminan la documentacion narrativa.
- Los agentes tienen un protocolo de arranque uniforme.
- Los bugs manuales dejan de cerrarse con "tests pasan" si no existe
  reproduccion, causa raiz y regresion.
- Los diagramas tecnicos quedan mantenibles porque Mermaid vive en Git y los
  renders no son fuente de verdad.
- Las dependencias globales no se convierten en requisito oculto para declarar
  PASS.
- Los deploys no se consideran aprobados por el solo hecho de haber sincronizado
  archivos o terminado un build.
- Las politicas se pueden adaptar por proyecto sin copiar reglas especificas de
  Team360 que no apliquen.

## Adaptacion requerida

Cada proyecto nuevo debe reemplazar:

- nombre del proyecto;
- ramas activas;
- directorio productivo principal;
- stack frontend/backend;
- politica de DB;
- servicios reales del preflight;
- comandos oficiales de backend/frontend;
- politicas de deploy;
- URL base local y productiva;
- skills locales;
- herramienta de deploy;
- politica de secretos;
- politica de dependencias;
- framework backend Python;
- entrypoint backend;
- aliases/modelos AI si aplica;
- criterios PASS/FAIL propios.

No se deben copiar rutas, dominios, secrets, nombres comerciales ni decisiones
de Team360 que pertenezcan solo a este producto.

Para proyectos iMotorSoft nuevos, el default recomendado es:

```text
Backend Python: LiteStar/Litestar
Entrypoint: backend/ls_iMotorSoft_Srv01.py
Objeto ASGI interno: app
Launcher: uvicorn ls_iMotorSoft_Srv01:app
```

FastAPI o `backend/app.py` solo deben aparecer como excepcion documentada por
un ADR propio del proyecto.

## Referencias

- Plantilla ejecutable: `../templates/project-structure-template.md`
- Arquitectura viva: `../../lat.md/lat.md`
- Diagramas: `../../lat.md/team360-mermaid-diagram-policy.md`
- Root cause debugging: `../../lat.md/team360-root-cause-debugging-policy.md`
- Browser validation: `../../lat.md/browser-mcp-validation-policy.md`
- Service preflight: `../../lat.md/service-preflight-methodology.md`
