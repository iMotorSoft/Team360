# Team360 Runtime Operational Policy

This document defines the validated operational policy for the public Vera
experience in Team360.

It is an architecture invariant. Agents must read and follow it before changing
or validating the public diagnosis runtime, backend startup, frontend startup,
LiteLLM model routing, Milvus retrieval or PostgreSQL state persistence.

## Active Architecture

The validated public Vera flow is:

```text
/t360
-> Astro / Svelte
-> POST /api/diagnosis/turn
-> Backend Litestar
-> PostgreSQL 18
-> Milvus 2.6
-> LiteLLM
-> GPT-5.4 Nano
```

Main stack:

- Frontend: Astro 6 + Svelte 5.
- Backend: Litestar.
- Conversational state: PostgreSQL 18.
- Vector retrieval: Milvus 2.6.
- LLM gateway: LiteLLM.
- Team360 alias: `openai_gpt-5-nano`.
- Real upstream: `openai/gpt-5.4-nano`.
- Observed snapshot: `gpt-5.4-nano-2026-03-17`.
- LiteLLM API mode: Chat Completions.
- OpenAI direct: technical bypass only, not the main route.

## Services And Ports

| Service | Port |
| --- | ---: |
| PostgreSQL 18 | 5432 |
| Milvus 2.6 | 19530 |
| Milvus health | 9091 |
| LiteLLM | 4000 |
| Team360 backend | 7050 |
| Astro frontend | 3050 |

Before starting backend and frontend, PostgreSQL 18, Milvus 2.6 and LiteLLM
must already be available.

## PostgreSQL 18

The runtime database is:

```text
team360
```

The conversational state table is:

```text
sales_diagnosis_conversation_states
```

Policy:

- PostgreSQL is the source of truth for conversational state.
- The real public runtime must not use `InMemory` state.
- Do not use databases or URLs from other projects.
- Do not print or document the database password.
- The DSN must be resolved from private backend configuration.

Sanitized representation:

```text
postgresql://administrator:***@localhost:5432/team360
```

Conceptual environment:

```bash
AUTOMATION_DIAGNOSIS_REPOSITORY=postgres
TEAM360_DB_URL_PSQL='postgresql://administrator:***@localhost:5432/team360'
```

The real password must come from the runtime environment or existing private
configuration.

## Milvus 2.6

Production collection:

```text
team360_sales_diagnosis_knowledge_v1
```

Validated configuration:

- Dimension: `1536`.
- Metric: `COSINE`.
- Real retrieval.
- Real embeddings.
- Knowledge scope filters.
- Approved documents and chunks.

Environment:

```bash
TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus
TEAM360_MILVUS_HOST=127.0.0.1
TEAM360_MILVUS_PORT=19530
TEAM360_MILVUS_COLLECTION=team360_sales_diagnosis_knowledge_v1
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b
TEAM360_EMBEDDING_MODEL=openai_text_embedding_3_small
```

Do not use on the real public route:

- `NullRetrievalProvider`.
- Fake retrieval.
- Static benchmark chunks.
- Fake embeddings.
- Zero vectors.
- pgvector.

## LiteLLM

Base endpoint:

```text
http://localhost:4000/v1
```

Team360 alias:

```text
openai_gpt-5-nano
```

The alias resolves internally to:

```text
openai/gpt-5.4-nano
```

Validated API mode:

```text
chat
```

Used endpoints:

```text
POST /v1/chat/completions
POST /v1/embeddings
```

Backend configuration:

```bash
TEAM360_AI_PROVIDER=litellm
TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano
TEAM360_LITELLM_API_MODE=chat
```

Authentication policy:

- LiteLLM is protected by `LITELLM_MASTER_KEY`.
- The backend may resolve the key through private configuration.
- Do not write the master key in commands, code, tests or documentation.
- Do not expose the upstream OpenAI key.
- Do not enable silent fallback to OpenAI direct.

If a specific client variable is required, define it only in the execution
environment:

```bash
TEAM360_LITELLM_API_KEY="$LITELLM_MASTER_KEY"
```

## Model And Parameters

| Concept | Value |
| --- | --- |
| LiteLLM alias | `openai_gpt-5-nano` |
| Upstream | `openai/gpt-5.4-nano` |
| API | Chat Completions |
| Temperature | `0.2` |
| Additional reasoning | disabled / not required |
| Responses API lab reasoning | `low` when explicitly testing `openai/gpt-5.4-nano` |
| Current public streaming | no |
| State | PostgreSQL |
| Retrieval | Milvus |

Do not use as main configuration:

- `gpt-5-nano`.
- OpenAI direct.
- Responses API.
- `reasoning_effort`.
- Alternative models without explicit decision.

LiteLLM may have `drop_params: true`, but the backend must still send
compatible parameters and must not depend on the proxy silently discarding
incorrect parameters.

Responses API is allowed only for explicit compatibility checks, labs or
controlled model evaluation outside the public Vera main runtime. In that
case, when the effective OpenAI upstream is `openai/gpt-5.4-nano`, send:

```json
{"reasoning": {"effort": "low"}}
```

Do not use `minimal` for that upstream. This exception does not change the
validated public `/t360` route: Vera remains on Chat Completions with no
additional reasoning parameter unless a new runtime decision is documented.

## Private Backend Configuration

Secrets and private values must be resolved through:

- Environment variables.
- Existing private configuration.
- `globalVar.py` when Team360 already uses it as the central adapter.

Do not duplicate secrets inside:

- Routes.
- Runtime modules.
- Tests.
- Scripts.
- Versioned YAML.
- Documented commands.
- Frontend code.

Never print these values:

- `OpenAI_Key_JAI_query`.
- `LITELLM_MASTER_KEY`.
- `OPENROUTER_API_KEY`.
- `REQUESTY_API_KEY`.
- PostgreSQL password.

## Frontend Configuration

Central file:

```text
SrvRestAstroLS_v1/astro/src/components/global.js
```

The public backend URL must resolve from that file.

Current relevant configuration:

```javascript
URL_REST_DEV = "http://localhost:7050"
API_BASE_URL = `${URL_REST}/api`
```

Policy:

- Svelte components must not invent URLs.
- `publicDiagnosis.ts` must consume central frontend configuration.
- Do not duplicate `http://localhost:7050` across files.
- `/t360` currently calls the backend configured in `global.js` directly.
- For the current public experience, the critical backend port is `7050`.

Frontend flow:

```text
t360.astro
-> PublicVeraEntry.svelte
-> publicDiagnosis.ts
-> API_BASE_URL
-> http://localhost:7050/api/diagnosis/turn
```

## Known Astro Proxy Inconsistency

`astro.config.mjs` still keeps a development proxy from `/api` to:

```text
http://127.0.0.1:8000
```

However, `/t360` does not currently depend on that proxy because it uses the
absolute URL from `global.js`:

```text
http://localhost:7050/api
```

Therefore:

- `/t360` works with backend on `7050`.
- The proxy to `8000` may affect other views that use relative `/api` routes.
- Do not change it during a conversation validation.
- It must be unified later to avoid two configuration sources.
- Until that cleanup, `global.js` is the effective source for `/t360`.

## Backend Startup

Production directory on the remote host:

```bash
cd /home/administrator/project/iMotorSoft/ai/Team360/SrvRestAstroLS_v1/backend
```

Canonical production startup for the current public Vera runtime:

```bash
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
uv run uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port 7050
```

Important runtime notes:

- Use `ls_iMotorSoft_Srv01:app` for the deployed production command. `app.py`
  may exist as a compatibility wrapper, but production currently launches the
  explicit module above.
- Do not set `TEAM360_BACKEND_DEBUG` in production. Litestar debug stays off by
  default; normal scanner paths such as `/api/env` and `/api/config` must return
  controlled `404 Not Found` responses without traceback noise.
- `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres` is the effective variable read by
  the public diagnosis state repository bootstrap. `TEAM360_DIAGNOSIS_STATE_PROVIDER=postgres`
  is kept as an operational marker/compatibility variable but is not the state
  switch used by `routes/diagnosis.py`.
- `TEAM360_EMBEDDING_VERSION` is the effective Milvus embedding-version filter.
  Do not use `TEAM360_MILVUS_EMBEDDING_VERSION` unless code is changed to read
  it.
- `TEAM360_PUBLIC_*` values document the intended public context. The current
  public turn route still uses the canonical constants and resolver path for
  `team360_live`, `team360_public_site`, `pkg_sales_diagnosis` and
  `ks_team360_sales_diagnosis`.

Older conceptual commands may show:

```bash
AUTOMATION_DIAGNOSIS_REPOSITORY=postgres \
TEAM360_AI_PROVIDER=litellm \
TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1 \
TEAM360_LITELLM_MODEL_ALIAS=openai_gpt-5-nano \
TEAM360_LITELLM_API_MODE=chat \
TEAM360_DIAGNOSIS_RETRIEVAL_PROVIDER=milvus \
TEAM360_MILVUS_HOST=127.0.0.1 \
TEAM360_MILVUS_PORT=19530 \
TEAM360_MILVUS_COLLECTION=team360_sales_diagnosis_knowledge_v1 \
TEAM360_KNOWLEDGE_SCOPE_ID=8b071443-5bd6-4fe4-bbc3-fc2dca179a5b \
TEAM360_EMBEDDING_MODEL=openai_text_embedding_3_small \
uv run uvicorn app:app --host 127.0.0.1 --port 7050
```

Treat those as historical unless the code and deployment command are explicitly
changed. The DSN and keys must not be written literally in docs or shell
history when they are already resolved by the environment or `globalVar.py`.

## Frontend Startup

Directory:

```bash
cd SrvRestAstroLS_v1/astro
```

Expected versions:

- Node.js `>=22.12.0`.
- pnpm `>=11.5.0`.

Start:

```bash
pnpm dev -- --host 127.0.0.1 --port 3050
```

Validated equivalent:

```bash
npx astro dev --host 127.0.0.1 --port 3050
```

Public URL:

```text
http://127.0.0.1:3050/t360
```

Use `tmux`, `screen`, `setsid` or the available operational process manager for
persistent processes. A temporary shell may terminate Astro when closed.

## Relevant Endpoints

| Route | Use |
| --- | --- |
| `POST /api/diagnosis/turn` | Public multi-turn conversation |
| `/health` | Backend health |
| `http://localhost:4000/health` | LiteLLM health |
| `POST /v1/chat/completions` | Generation through LiteLLM |
| `POST /v1/embeddings` | Embeddings through LiteLLM |
| `/t360` | Public experience |

Conversation request contract:

```json
{
  "session_id": "conv_...",
  "message": "mensaje del usuario"
}
```

Conceptual response:

```json
{
  "session_id": "conv_...",
  "response_text": "...",
  "turn_count": 1,
  "is_new": true
}
```

## Conversational Policy

Current actions:

```text
reflect_and_ask
diagnose
```

The runtime, not the model, owns the decision.

### `reflect_and_ask`

Must:

- Answer briefly.
- Show understanding.
- Ask one main question.
- Not repeat answered information.
- Not request unnecessary implementation details.
- Not deliver final diagnosis.

### `diagnose`

Must:

- Deliver complete orientation or diagnosis.
- Avoid additional questions.
- Use confirmed facts.
- Declare assumptions.
- Include validation points.
- Give one concrete next step.

### Critical Data

Depending on the case, critical data may include:

- Objective.
- Process.
- Channel.
- System or source.
- Volume or frequency.
- Human approval.
- Security restriction.

### Non-Blocking Data

Examples:

- Exact discount rule.
- Thresholds.
- Schedules.
- File names.
- Final document format.
- Implementation details.

These data must not block an initial orientation. They must appear as:

```text
punto a validar
```

## Conversational Memory

PostgreSQL persists the full state.

Semantic memory may include:

- Business context.
- Current process.
- Problem.
- Objective.
- Channels.
- Volume.
- Systems.
- Data sources.
- Human approval.
- Exceptions.
- Contradictions.
- Diagnosis status.

Asked questions must preserve:

- Intent.
- Text.
- Turn.
- Answered state.
- Evidence of answer.

Clear corrections replace previous data.

Example:

```text
Before: stock and prices are in Excel
After: stock is in the system and prices are in the spreadsheet
```

Correct final state:

```text
stock_source = sistema
price_source = planilla
```

## Security

Vera must not:

- Ask for passwords.
- Ask for MFA codes.
- Ask for SMS codes.
- Ask for QR codes.
- Ask for biometrics.
- Suggest bypassing native controls.
- Promise integration with closed software without validation.
- Promise pricing, SLA or ROI.
- Activate extensions that are not available yet.

The user must complete native application security controls.

Team360 may automate the flow around those controls, but must not bypass them.

## Capabilities Not Enabled Yet

Do not present these as available:

- Step-to-Action.
- Lead capture.
- `diagnostic_code`.
- Automatic WhatsApp handoff.
- Automatic pricing.
- SLA.
- Guaranteed ROI.

The first productive stage offers:

- Conversation.
- Minimal questions.
- Useful diagnosis.
- Concrete orientation.

## Minimum Validation After Startup

Backend:

```bash
curl http://127.0.0.1:7050/health
```

LiteLLM:

```bash
curl http://localhost:4000/health
```

Frontend:

```text
http://127.0.0.1:3050/t360
```

HTTP 200 is not enough. Real validation must happen from a browser and confirm:

- Message sending.
- Visible response.
- Stable session ID.
- Incrementing `turn_count`.
- PostgreSQL persistence.
- Milvus retrieval.
- LiteLLM call.
- No fallback.
- Input re-enabled.
- No mixed sessions.

## Troubleshooting

### LiteLLM returns 401

Check:

- `LITELLM_MASTER_KEY`.
- Key sent by the backend.
- `TEAM360_LITELLM_API_KEY`.
- No different key was written in files.

Do not switch to OpenAI direct to hide the problem.

### LiteLLM returns reasoning-related errors

Confirm:

```bash
TEAM360_LITELLM_API_MODE=chat
```

Do not send:

```text
reasoning_effort
```

If the task is an explicit Responses API lab or compatibility check for
`openai/gpt-5.4-nano`, use `reasoning.effort=low`. Do not use `minimal`.

### Embeddings fail

Confirm:

- Alias `openai_text_embedding_3_small`.
- Endpoint `/v1/embeddings`.
- Scope ID.
- Milvus collection.
- Dimension `1536`.

Do not use fake embeddings.

### CORS on `/t360`

Confirm:

- Frontend on `127.0.0.1:3050` or `localhost:3050`.
- Backend on `7050`.
- Allowed origins.
- URL defined in `global.js`.

### `/t360` uses the wrong port

Check first:

```text
src/components/global.js
```

Then check:

```text
publicDiagnosis.ts
```

The Astro proxy to `8000` is not currently the effective source for `/t360`.

### Backend dies when the terminal closes

Use a persistent process:

- `tmux`.
- `screen`.
- `setsid`.
- System service.

### Frontend dies when the terminal closes

Same cause: Astro must run in a persistent session.

## Final Operation Rule

The main Team360 runtime configuration is:

```text
State:
PostgreSQL 18

Retrieval:
Milvus 2.6

Gateway:
LiteLLM

Alias:
openai_gpt-5-nano

Upstream:
openai/gpt-5.4-nano

API:
Chat Completions

Backend:
127.0.0.1:7050

Frontend:
127.0.0.1:3050

Public URL:
http://127.0.0.1:3050/t360
```

Configuration sources:

```text
Public frontend:
src/components/global.js

Backend and secrets:
environment variables + private config / globalVar.py

Development proxy:
astro.config.mjs
```

Do not duplicate responsibilities across these three layers.
