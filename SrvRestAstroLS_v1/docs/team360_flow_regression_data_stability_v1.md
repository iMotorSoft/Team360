# Team360 Flow — Regression Data Stability V1

La regresión de Flow separa dos objetivos:

## Deterministic Regression

Usa PostgreSQL real y el harness de dominio `modules.flow.demo.run`.
Cada corrida crea casos propios con una marca única (`LAMUNI-DEMO-*` o un
prefijo explícito), reloj controlado para SLA y transporte externo determinístico.
No usa UUIDs históricos, posiciones globales ni totales congelados.

Suite backend:

```bash
cd SrvRestAstroLS_v1/backend
TEAM360_FLOW_LAMUNI_DEMO_TEST=1 uv run pytest tests/test_flow_lamuni_demo.py -q
TEAM360_FLOW_AUDIT_EXEC_DIRECTORIO_TEST=1 uv run pytest tests/test_flow_audit_executive_directorio.py -q
```

Para una regresión browser determinística:

```bash
uv run python -m modules.flow.demo.run --prefix REGSTAB-RUN
TEAM360_FLOW_DEMO_MARKER='LAMUNI-DEMO-...' \
TEAM360_FLOW_DEMO_REQUEST_ID='...' \
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050 \
pnpm exec playwright test e2e/console-flow-directorio-deterministic.spec.ts
```

La paginación aislada usa un prefijo común para 25 fixtures propios y valida
10/10/5 por API, además de la navegación de página en Directorio:

```bash
TEAM360_FLOW_PAGE_SEARCH='REGSTAB-PAGE-<run-id>' \
TEAM360_FLOW_PAGE_COUNT=25 \
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050 \
pnpm exec playwright test e2e/console-flow-directorio-deterministic-pagination.spec.ts
```

Los fixtures quedan identificados en DEV para conservar evidencia y no se
eliminan mediante limpieza global. No hay `TRUNCATE`, reset de DB ni borrado de
casos ajenos.

## Real Data Smoke

`console-flow-directorio-live.spec.ts` consulta PostgreSQL real a través de la
Executive API y descubre dinámicamente los casos disponibles. Verifica:

- listados, IDs únicos, estados canónicos y fuentes `LIVE`/`AUDIT_SNAPSHOT`;
- búsqueda por identidad descubierta;
- filtros y paginación contra metadata de la API;
- un caso `RESOLVED` si existe, un caso abierto si existe, escalamiento y
  pending approval sin asumir que el dataset los contenga siempre;
- responsive, race de selección, errores de consola y requests fallidos.

No fija totales globales, UUIDs históricos, posiciones, estados SLA futuros ni
casos que puedan envejecer con el reloj real.

Comando:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050 \
pnpm exec playwright test e2e/console-flow-directorio-live.spec.ts
```

`NO_TEST_DATA` indica que el smoke no encontró una categoría opcional (por
ejemplo, ningún caso pending) y no se confunde con una regresión de producto.

## Servicios

Los E2E requieren los launchers oficiales:

```bash
./backend-dev.sh
./astro-dev.sh
```

PostgreSQL, Milvus y LiteLLM deben estar disponibles según el preflight del
backend. La suite no inicia, detiene ni recrea infraestructura global.
