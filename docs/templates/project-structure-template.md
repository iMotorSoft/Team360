# Project Structure Template

Plantilla base para crear proyectos nuevos usando el patron operativo validado
en Team360.

Esta plantilla es un punto de partida. Antes de usarla, reemplazar:

```text
{PROJECT_NAME}
{PROJECT_SLUG}
{APP_DIR}
{PROJECT_SKILL}
{LOCAL_BASE_URL}
{PROD_BASE_URL}
{BACKEND_PORT}
{FRONTEND_PORT}
{DB_STACK}
{AI_GATEWAY}
{DEPLOY_TARGET}
{PYTHON_ENTRYPOINT}  # default iMotorSoft: ls_iMotorSoft_Srv01.py
```

## Estructura base

```text
{PROJECT_NAME}/
├── AGENTS.md
├── .agents/
│   └── skills/
│       └── {PROJECT_SKILL}/
│           └── SKILL.md
├── lat.md/
│   ├── lat.md
│   ├── status_actual.md
│   ├── global-orchestration.md
│   ├── mermaid-diagram-policy.md
│   ├── root-cause-debugging-policy.md
│   ├── browser-validation-policy.md
│   ├── service-preflight-methodology.md
│   ├── evidence-pass-fail-policy.md
│   ├── secrets-policy.md
│   ├── dependency-policy.md
│   └── lab-policy.md
├── {APP_DIR}/
│   ├── backend/
│   │   ├── ls_iMotorSoft_Srv01.py
│   │   ├── modules/
│   │   ├── routes/
│   │   ├── tests/
│   │   ├── scripts/
│   │   └── db/
│   │       └── migrations/
│   ├── frontend/
│   │   ├── src/
│   │   ├── e2e/
│   │   └── docs/
│   ├── docs/
│   │   └── status_actual.md
│   └── lab/
├── docs/
│   ├── README.md
│   ├── status_actual.md
│   ├── negocio/
│   ├── estrategia/
│   ├── ux/
│   ├── analisis-tecnico/
│   ├── adr/
│   ├── frontend/
│   └── templates/
└── data/
    └── reports/
        ├── snapshots/
        └── validation/
```

## Separacion documental

| Tipo de contenido | Ubicacion |
|---|---|
| Arquitectura viva, invariantes, contratos transversales | `lat.md/` |
| Tecnico runtime: backend, frontend, migraciones, validacion de desarrollo | `{APP_DIR}/docs/` |
| Negocio, producto, estrategia, UX, ADRs, plantillas | `docs/` |
| Evidencias, reportes, snapshots, exports | `data/reports/` |

Regla:

```text
No duplicar el mismo contenido entre capas.
Mover o enlazar.
```

## ADR vs arquitectura viva

Mantener separadas estas dos capas:

| Capa | Uso |
|---|---|
| `docs/adr/` | decision tomada, contexto, rationale historico y consecuencias |
| `lat.md/` | regla viva e invariante que agentes/codigo deben obedecer |

Regla:

```text
ADR decide.
lat.md gobierna.
status_actual.md registra estado.
```

No duplicar un documento completo entre ADR y `lat.md`. El ADR debe apuntar al
invariante vivo cuando la decision tenga impacto operativo.

## Archivos minimos

### `AGENTS.md`

Debe declarar:

- raiz del proyecto;
- skill local obligatorio;
- protocolo de arranque;
- mapa de ramas;
- separacion documental;
- reglas tecnicas no negociables;
- politicas de browser, root cause, Mermaid, deploy, preflight, secretos,
  dependencias y evidencia;
- formato de cierre de tareas.

### `.agents/skills/{PROJECT_SKILL}/SKILL.md`

Debe contener:

- proposito del proyecto;
- ubicacion del skill;
- protocolo obligatorio al iniciar sesion;
- mapa rapido de ramas;
- estructura relevante;
- reglas de trabajo;
- convenciones para `lat.md`;
- convenciones para labs;
- convenciones de resultado.

### `lat.md/lat.md`

Indice raiz de arquitectura viva.

Formato recomendado:

```markdown
# {PROJECT_NAME}

This directory defines high-level concepts, architecture decisions and stable
invariants for {PROJECT_NAME}.

- [[global-orchestration]] — branch ownership, active fronts and coordination.
- [[browser-validation-policy]] — Playwright as E2E gate, browser tools as exploratory.
- [[service-preflight-methodology]] — service checks before real tests.
- [[mermaid-diagram-policy]] — Mermaid source as canonical diagrams.
- [[root-cause-debugging-policy]] — no fixes without verified root cause.
- [[evidence-pass-fail-policy]] — minimum evidence before declaring PASS/FAIL.
- [[secrets-policy]] — secrets handling and redaction rules.
- [[dependency-policy]] — global tools vs versioned project dependencies.
```

### `status_actual.md`

Cada directorio documental activo debe tener uno.

Plantilla:

```markdown
# Status actual - {AREA}

Objetivo: `{OBJETIVO}`

Ultima actualizacion: YYYY-MM-DD

## Estado general

## Acciones realizadas

### YYYY-MM-DD - Titulo

- Que se hizo.
- Que no se toco.
- Validacion.
- Riesgos o notas.

## Validacion

## Pendientes recomendados

## Notas de seguridad
```

## Ramas recomendadas

Adaptar nombres, pero conservar semantica:

| Rama | Uso |
|---|---|
| `main` | snapshot estable / produccion |
| `feature/product-core` | producto funcional vivo |
| `feature/knowledge-ingestion` | ingestion, RAG, embeddings, retrieval |
| `ux/design-handoff` | mock visual, handoff UX, sin runtime real |
| `docs/knowledge-foundation` | contenido knowledge, manuales, authoring |

Regla:

```text
"desarrollo", "dev" o "backend" apuntan a la rama funcional viva.
No crear una rama local llamada desarrollo.
```

## Backend Python por defecto

Para proyectos nuevos de iMotorSoft, el servidor Python por defecto es
LiteStar/Litestar.

Regla:

```text
Framework backend Python default: LiteStar.
Archivo principal backend default: ls_iMotorSoft_Srv01.py.
No usar app.py como entrypoint principal del proyecto.
```

El nombre `app` puede usarse como objeto ASGI interno porque mantiene
compatibilidad con Uvicorn, tooling ASGI y ejemplos del ecosistema:

```python
from litestar import Litestar, get


@get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "{PROJECT_SLUG}",
    }


app = Litestar(route_handlers=[health])
```

Launcher local conceptual:

```bash
uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port {BACKEND_PORT}
```

Reglas:

- `ls_iMotorSoft_Srv01.py` es el entrypoint canonico para proyectos nuevos
  iMotorSoft salvo ADR explicito que defina otro nombre.
- `app.py` no debe crearse como archivo principal ni como fuente de verdad del
  servidor.
- Un wrapper de compatibilidad `app.py` solo es aceptable si una herramienta
  externa lo exige, y debe delegar sin duplicar rutas ni configuracion.
- FastAPI no es el default de proyectos nuevos; solo se usa si un ADR propio
  justifica la excepcion.

## Politicas a crear en `lat.md/`

Crear como minimo:

```text
browser-validation-policy.md
service-preflight-methodology.md
mermaid-diagram-policy.md
root-cause-debugging-policy.md
evidence-pass-fail-policy.md
secrets-policy.md
dependency-policy.md
lab-policy.md
```

Agregar politicas especificas cuando existan:

```text
frontend-deploy-policy.md
backend-deploy-policy.md
database-driver-policy.md
model-routing-policy.md
security-hitl-policy.md
frontend-url-source-of-truth.md
```

## Herramientas externas adoptadas como conceptos

No instalar herramientas externas completas solo porque una idea sea util.

Cuando se toma una idea de otro proyecto, documentar:

- herramienta o repo de origen;
- que se adopta;
- que no se adopta;
- archivo `lat.md/` resultante;
- riesgos evitados;
- si requiere dependencia local versionada.

### gstack `/diagram`

Adoptar solo el criterio documental:

- Mermaid como fuente canonica versionable en Git;
- diagramas embebidos en Markdown o `.mmd`;
- SVG/PNG/Excalidraw como derivados opcionales.

No adoptar:

- gstack como dependencia;
- skill `/diagram` completo;
- `.gstack`;
- telemetry;
- browse daemon;
- hooks;
- commits automaticos;
- triplet obligatorio.

Regla:

```text
Mermaid es fuente.
Los renders son salida.
gstack no es dependencia.
```

Esta es una regla central de la plantilla, no una preferencia estetica:

```text
Mermaid como fuente canonica versionable en Git.
SVG/PNG/Excalidraw solo como derivados opcionales.
No instalar /diagram completo.
No depender de gstack.
```

### gstack `/investigate`

Adoptar solo el metodo:

- no corregir sin causa raiz verificable;
- reproduccion exacta;
- hipotesis verificable;
- evidencia antes del fix;
- regla de tres hipotesis;
- debug report;
- regresion backend/Playwright cuando corresponda.

No adoptar:

- skill `/investigate` completo;
- `.gstack`;
- learnings cross-project;
- freeze hooks;
- telemetry;
- commits automaticos.

## Browser validation

Regla base:

```text
Playwright + Chromium = gate E2E oficial.
Browser MCP / browser automation = exploracion y diagnostico visual.
```

Una fase browser no queda cerrada solo con inspeccion visual. Debe terminar,
cuando corresponda, en test reproducible.

## Evidencia PASS/FAIL

Ninguna validacion relevante debe cerrarse solo con "funciona" o "tests pasan".

Evidencia minima:

```text
branch
HEAD
worktree relevante
entorno
base URL
comandos ejecutados
resultado exacto
cantidad de tests
errores 5xx
errores criticos de consola
requests duplicados
modelo/fallback si aplica IA
trace/screenshot/video si aplica browser
```

Para deploys, agregar:

```text
build
artifact publicado
destino remoto
backup
dry-run
verificacion post-deploy
smoke productivo
rollback disponible
```

## Root cause debugging

Cadena obligatoria para bugs no triviales:

```text
sintoma observado
→ reproduccion exacta
→ hipotesis de causa raiz
→ evidencia
→ fix minimo
→ test de regresion
→ validacion final
```

Especialmente cuando:

- la prueba manual falla aunque los tests pasen;
- local y produccion difieren;
- hay bugs mobile/touch;
- hay requests duplicados;
- hay estado persistido inconsistente;
- hay fallback de modelo inesperado;
- un deploy responde pero parece servir build viejo.

## Mermaid

Mermaid debe ser una regla de primer nivel para proyectos nuevos, no un detalle
de tooling.

Regla base:

```text
Mermaid source in Git.
Rendered artifacts only when needed.
```

Los renders SVG/PNG/Excalidraw son derivados opcionales.

No instalar Mermaid globalmente como requisito del proyecto.

Si se requiere render reproducible, agregar dependencia local versionada.

No adoptar gstack `/diagram` completo ni depender de gstack para mantener
diagramas.

## Preflight de servicios

Antes de tests, smokes o benchmarks que dependan de servicios reales, validar:

- DB activa;
- vector store o search index activo;
- gateway de modelos activo;
- variables de entorno accesibles;
- modelo/alias registrado;
- llamada real minima sin fallback silencioso;
- health checks relevantes.

Si el preflight falla, no interpretar el resultado como calidad del modulo.

## Secretos y datos sensibles

Reglas minimas:

- no commitear credenciales;
- no imprimir secrets en logs ni reportes;
- no leer `.env` salvo pedido explicito y necesidad justificada;
- no sincronizar `.env*` ni `.venv/` en deploys por archivos;
- sanitizar DSN, API keys, tokens y hostnames sensibles en evidencias;
- verificar existencia de sensibles sin mostrar valores.

Ejemplo de representacion:

```text
postgresql://user:***@host:5432/db
API_KEY=present
```

## Dependencias globales vs locales

Regla:

```text
Herramientas globales = diagnostico personal.
Dependencias versionadas = gates del proyecto.
```

No declarar PASS con una herramienta global como unica dependencia si el gate
debe ser reproducible.

Instalar localmente y versionar cuando la herramienta sea parte de:

- CI;
- build;
- test permanente;
- render reproducible;
- deploy;
- generacion de artefactos oficiales.

## Laboratorio tecnico

Crear `lab/` solo para experimentos reproducibles y aislados.

Reglas:

- cada experimento en su propia carpeta;
- cada experimento con `README.md`;
- resultados auditables en JSON/Markdown y, si aporta, HTML;
- no tocar configuracion productiva desde `lab/`;
- si se adopta, migrar a codigo productivo, test automatizado o documento
  formal;
- no dejar `lab/` como segunda implementacion paralela.

## DB runtime

Elegir y documentar una politica de acceso a datos desde el inicio.

Debe definir:

- schema truth;
- migraciones;
- driver runtime;
- pool/conexion;
- repository pattern;
- ubicacion del SQL;
- frontera de DTO/Pydantic/serializacion;
- drivers/ORMs prohibidos o condicionados.

Ejemplo Team360:

```text
SQL migrations as source of truth.
psycopg 3 async direct.
Pydantic only at HTTP/API borders.
SQL inside repositories, not endpoints.
```

## Modelos AI y fallback

Si el proyecto usa IA, definir:

- aliases de modelo en vez de slugs hardcodeados;
- proveedor efectivo;
- gateway o router;
- modelo esperado por flujo;
- fallback permitido/prohibido;
- smoke real minimo;
- evidencia de auth/credito/provider;
- respuesta no vacia;
- metadatos de modelo usados.

Regla:

```text
No aprobar calidad si el modelo real no fue validado.
No aceptar fallback silencioso como PASS salvo que sea explicitamente esperado.
```

## Conectividad frontend/backend

Definir una unica fuente de verdad para URLs del frontend.

Ejemplo:

```text
frontend/src/components/global.js
```

Debe centralizar:

- modo local vs productivo;
- URL REST dev;
- URL REST prod;
- URL publica del sitio;
- SSE o streaming endpoints si aplica.

No corregir conectividad dispersando URLs hardcodeadas en componentes o API
clients.

## Deploy

Antes del primer deploy, crear una politica explicita para el mecanismo real:

- rsync;
- Vercel;
- Docker;
- GitHub Actions;
- servidor manual;
- plataforma gestionada.

La politica debe cubrir:

```text
branch/HEAD
worktree
build limpio
tests
backup o rollback
dry-run si aplica
destino
secretos preservados
verificacion post-deploy
smoke productivo
evidencia final
```

Un deploy exitoso no demuestra que el build correcto este sirviendo.

## Comandos iniciales sugeridos

```bash
mkdir -p .agents/skills/{PROJECT_SKILL}
mkdir -p lat.md
mkdir -p {APP_DIR}/docs
mkdir -p {APP_DIR}/lab
mkdir -p docs/{negocio,estrategia,ux,analisis-tecnico,adr,frontend,templates}
mkdir -p data/reports/{snapshots,validation}
```

Luego crear:

```text
AGENTS.md
.agents/skills/{PROJECT_SKILL}/SKILL.md
lat.md/lat.md
lat.md/status_actual.md
{APP_DIR}/docs/status_actual.md
docs/status_actual.md
docs/adr/status_actual.md
docs/templates/status_actual_template.md
data/reports/README.md
```

## Primer checklist

1. Definir nombre y objetivo del proyecto.
2. Definir ramas activas.
3. Definir directorio productivo principal.
4. Crear `AGENTS.md`.
5. Crear skill local del proyecto.
6. Crear `lat.md/lat.md` y politicas minimas.
7. Crear status locales.
8. Definir Mermaid como fuente canonica de diagramas.
9. Definir root cause debugging para bugs manuales/no triviales.
10. Definir politica PASS/FAIL y evidencia minima.
11. Definir politica de secretos.
12. Definir politica de dependencias globales/locales.
13. Definir stack DB y documentarlo.
14. Definir servicios reales y preflight.
15. Definir modelo/alias/fallback si hay IA.
16. Agregar Playwright desde el inicio si hay frontend.
17. Definir LiteStar/Litestar como backend Python default o documentar ADR de excepcion.
18. Definir `ls_iMotorSoft_Srv01.py` como entrypoint backend default o documentar ADR de excepcion.
19. Definir comandos oficiales de backend y frontend.
20. Definir politica de deploy antes del primer despliegue.
21. Crear `lab/` con reglas de experimentos reproducibles.

## Criterio de cierre del bootstrap

El bootstrap queda listo cuando:

```text
AGENTS.md existe
skill local existe
lat.md/lat.md existe
status_actual.md principales existen
separacion documental esta definida
preflight esta definido
browser validation esta definida
root cause debugging esta definido
Mermaid policy esta definida
evidence/pass-fail policy esta definida
secrets policy esta definida
dependency policy esta definida
lab policy esta definida
deploy policy esta definida o explicitamente diferida
```
