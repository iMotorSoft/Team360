# Team360 - Configuracion local de desarrollo

Ultima actualizacion: 2026-06-21

## Proposito

Este documento registra la configuracion local validada para levantar Team360 en
desarrollo con frontend Astro, backend Litestar, PostgreSQL, Milvus y LiteLLM.

No debe contener secretos. Las credenciales se toman del entorno de la shell.

## Puertos locales

| Servicio | Puerto | Nota |
| --- | ---: | --- |
| Backend Team360 | `7050` | Litestar/Uvicorn |
| Astro | `3050` | Frontend dev server |
| LiteLLM | `4000` | Proxy OpenAI-compatible |
| Milvus | `19530` | Vector store local/remoto expuesto localmente |
| PostgreSQL | `5432` | DB `team360`, resuelta por `globalVar.py` |

## Fuente de verdad frontend

La configuracion frontend del endpoint REST esta centralizada en:

```text
SrvRestAstroLS_v1/astro/src/components/global.js
```

Valores relevantes:

```js
const URL_REST_DEV = "http://localhost:7050";
const URL_REST_PRO = "";
const IS_REST_PRO = true;

export const URL_REST = IS_REST_PRO ? URL_REST_PRO : URL_REST_DEV;
export const API_BASE_URL = `${getRestBaseUrl()}/api`;
export const AGUI_BASE_URL = `${getRestBaseUrl()}/api/agui`;
export const URL_SSE = `${getRestBaseUrl()}/api/agui/stream`;
```

Regla operativa:

- `URL_REST_DEV` debe apuntar al backend local en `http://localhost:7050`.
- `URL_REST_PRO=""` hace que el frontend use rutas relativas como `/api`.
- Los clientes frontend deben importar desde `components/global.js` y no
  hardcodear URLs.

Nota actual:

`astro.config.mjs` todavia tiene un proxy Vite de desarrollo `/api` hacia
`http://127.0.0.1:8000`. Si `IS_REST_PRO=true` en dev, el navegador usa `/api`
relativo y ese proxy entra en juego. Para una validacion local con backend en
`7050`, hay dos opciones:

1. Usar `URL_REST_DEV` con el toggle dev correspondiente.
2. Usar un forward temporal de sesion `8000 -> 7050`, sin persistirlo.

La validacion del 2026-06-21 uso la segunda opcion con `socat`.

## Resolucion de PostgreSQL

PostgreSQL se resuelve desde:

```text
SrvRestAstroLS_v1/backend/globalVar.py
```

Prioridad efectiva:

```text
1. TEAM360_DB_URL
2. TEAM360_DB_URL_PSQL
3. DB_PG_V360_URL, derivando el nombre de DB a TEAM360_DB_NAME
```

Valores relevantes:

```text
TEAM360_DB_NAME=team360
TEAM360_DB_SCHEMA=public
```

Si `DB_PG_V360_URL` existe y usa esquema PostgreSQL, `globalVar.py` reemplaza
el nombre de la base por `TEAM360_DB_NAME`. Por eso no hace falta declarar
`TEAM360_DB_URL_PSQL` en el comando local cuando el entorno ya tiene
`DB_PG_V360_URL` correctamente exportada.

## Resolucion de LiteLLM

Para llamadas a LiteLLM, la key se toma del entorno. La prioridad usada por los
flujos de diagnostico incluye:

```text
1. TEAM360_LITELLM_API_KEY
2. LITELLM_API_KEY
3. LITELLM_MASTER_KEY
```

En desarrollo local validado, `LITELLM_MASTER_KEY` estaba exportada desde la
shell del usuario y fue heredada por el proceso del backend.

Variables de LiteLLM:

```bash
TEAM360_AI_PROVIDER=litellm
TEAM360_LITELLM_BASE_URL=http://127.0.0.1:4000
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano
```

## Resolucion de Milvus

Variables validadas:

```bash
TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus
TEAM360_MILVUS_HOST=127.0.0.1
TEAM360_MILVUS_PORT=19530
TEAM360_MILVUS_COLLECTION=team360_sales_diagnosis_knowledge_v1
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1
```

`TEAM360_MILVUS_TOKEN` solo es necesario si la instancia de Milvus requiere
autenticacion.

## Comando backend validado

Ejecutar desde:

```bash
cd SrvRestAstroLS_v1/backend
```

Comando:

```bash
TEAM360_BACKEND_DEBUG=1 \
AUTOMATION_DIAGNOSIS_REPOSITORY=postgres \
TEAM360_EMBEDDING_VERSION=team360-openai-small-1536-v1 \
TEAM360_AI_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://127.0.0.1:4000 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_PORT=19530 \
TEAM360_MILVUS_COLLECTION=team360_sales_diagnosis_knowledge_v1 \
TEAM360_DIAGNOSIS_STATE_PROVIDER=postgres \
TEAM360_PUBLIC_ORGANIZATION_CODE=team360_live \
TEAM360_PUBLIC_WORKSPACE_CODE=team360_public_site \
TEAM360_PUBLIC_PACKAGE_CODE=pkg_sales_diagnosis \
TEAM360_PUBLIC_KNOWLEDGE_SCOPE_CODE=ks_team360_sales_diagnosis \
uv run uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port 7050 --reload
```

Notas:

- `TEAM360_BACKEND_DEBUG=1` es solo para desarrollo local.
- `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres` activa estado persistido para el
  diagnostico publico.
- Las credenciales de PostgreSQL y LiteLLM no se pasan en este comando si ya
  estan exportadas en el entorno.
- Las variables `TEAM360_PUBLIC_*` quedan declaradas para paridad operativa del
  diagnostico publico. El runtime actual tambien conserva codigos canonicos en
  sus contratos internos.

## Comando Astro validado

Ejecutar desde:

```bash
cd SrvRestAstroLS_v1/astro
```

Comando:

```bash
corepack pnpm dev --host 127.0.0.1 --port 3050
```

Si el frontend esta usando rutas relativas `/api` por `URL_REST_PRO=""` y no se
cambia el toggle local, usar solo para la sesion:

```bash
socat TCP-LISTEN:8000,fork,reuseaddr TCP:127.0.0.1:7050
```

Ese forward no debe persistirse como configuracion del proyecto.

## Preflight recomendado

Verificar variables sin imprimir secretos:

```bash
python3 - <<'PY'
import os

for name in [
    "DB_PG_V360_URL",
    "TEAM360_DB_URL",
    "TEAM360_DB_URL_PSQL",
    "LITELLM_MASTER_KEY",
    "LITELLM_API_KEY",
    "TEAM360_LITELLM_API_KEY",
]:
    print(f"{name}: {'set' if os.environ.get(name, '').strip() else 'missing'}")
PY
```

Verificar DSN resuelto por `globalVar.py` sin exponer password:

```bash
cd SrvRestAstroLS_v1/backend

uv run python - <<'PY'
from globalVar import get_team360_db_url_psql
from urllib.parse import urlparse

dsn = get_team360_db_url_psql()
print("globalVar DSN:", "set" if dsn else "missing")
if dsn:
    parsed = urlparse(dsn)
    print("database:", parsed.path.lstrip("/") or "unknown")
    print("host:", parsed.hostname or "unknown")
    print("port:", parsed.port or "default")
PY
```

## Validaciones HTTP

Health backend:

```bash
curl http://127.0.0.1:7050/api/health
```

Turno real de diagnostico:

```bash
curl -sS -X POST http://127.0.0.1:7050/api/diagnosis/turn \
  -H 'Content-Type: application/json' \
  --data '{
    "message": "Hola, quiero evaluar si Team360 puede ayudarme a ordenar consultas de clientes y derivarlas al equipo correcto.",
    "locale": "es",
    "assistant_instance_id": "team360_sales_diagnosis",
    "client_context": {
      "source_channel": "team360_public_site",
      "site_channel": "public_web",
      "assistant_display_name": "Vera",
      "lead_owner": "Team360",
      "service_code": "sales_diagnosis",
      "package_code": "pkg_sales_diagnosis",
      "knowledge_scope_code": "ks_team360_sales_diagnosis",
      "template_code": "public_site"
    }
  }'
```

Astro:

```bash
curl -I http://127.0.0.1:3050/t360
curl -I http://127.0.0.1:3050/t360-interaction-lab
curl http://127.0.0.1:3050/api/health
```

## Validaciones frontend

Desde:

```bash
cd SrvRestAstroLS_v1/astro
```

Comandos:

```bash
corepack pnpm check
corepack pnpm build
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050 \
T360_REAL_E2E=1 \
corepack pnpm exec playwright test \
  e2e/t360-interaction-lab.spec.ts \
  e2e/public-vera.spec.ts \
  --project=chromium
```

Resultado validado el 2026-06-21:

```text
git diff --check: OK
pnpm check: OK, con hint preexistente por parametro page no usado en test skipped
pnpm build: OK
Playwright: 14 passed, 1 skipped
```

## Estado final esperado

Al finalizar una validacion local, apagar procesos levantados para la prueba:

- backend Uvicorn `7050`;
- Astro `3050`;
- forward temporal `8000 -> 7050`, si se uso.

Los servicios externos que ya estaban vivos antes de la prueba, como LiteLLM o
Milvus, no se apagan salvo que la tarea lo pida explicitamente.
