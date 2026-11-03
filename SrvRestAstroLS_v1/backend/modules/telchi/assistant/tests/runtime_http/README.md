# Telchi assistant — Real HTTP runtime battery

Reproducible `curl` battery that exercises the **real** Telchi conversational
pipeline (MessageDispatcher → TelchiHandler → State Engine → capabilities →
Foundation → PostgreSQL) over HTTP, without sending WhatsApp messages. It is the
gate to run before any manual phone validation.

## What is real vs. adapted

| Layer | Real in this battery | Adapted (DEV only) |
| --- | --- | --- |
| Intérprete | `gpt-5.6-luna` directo (OpenAI Responses) | — |
| State Engine / V2 | `modules/telchi/assistant/state_engine.py` | — |
| Identidad y permisos | `PostgresPhoneIdentityResolver` + Console sobre PG | — |
| Persistencia | `ConversationRepository` sobre `message_threads`/`message_events` | — |
| Capability / Foundation | `query_fixed_sales` → `FoundationReader` read-only | — |
| Ingress | — | endpoint DEV `POST /api/telchi/assistant/dev/turn` |
| Egress | — | sin transporte WhatsApp (no se envía nada) |

The DEV endpoint reuses `MessageDispatcher` and the same `TelchiHandler`
registration produced by `create_telchi_app`; it only replaces the transport
boundary (claims a scenario-scoped durable thread instead of the Evolution
webhook, and has no outbound sender). It is disabled by default, loopback-only,
token-gated and derives the identity from the approved phone binding — never from
the request body.

## Usage

```bash
cd SrvRestAstroLS_v1/backend

# Full battery (starts and reaps its own DEV server)
uv run python -m modules.telchi.assistant.tests.runtime_http.run_battery \
  --output ../../data/reports/telchi/whatsapp-assistant-dev-live-v1/runtime_http

# Focused subset
... run_battery --only C06_documentary,incident_20261011 --output /tmp/telchi-http

# Against an already running DEV server
... run_battery --base-url http://127.0.0.1:7090 \
  --token "$TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN" --output /tmp/telchi-http
```

Security probes and restart continuity:

```bash
uv run python -m modules.telchi.assistant.tests.runtime_http.security_probes --output <dir>
uv run python -m modules.telchi.assistant.tests.runtime_http.restart_continuity --output <dir>
```

Each run uses a fresh `run_id`-scoped conversation key, so every execution starts
from a clean durable thread while preserving one conversation across its turns.

## Environment

The runner loads `SrvRestAstroLS_v1/.env.backend-dev.local`, resolves the pilot
phone from the approved `messaging_phone_bindings` row and the Telchi channel
binding, then exports (no secret is embedded in the repo):

```
TEAM360_ENV=dev
TEAM360_SRV05_EVOLUTION_ENABLED=1
TEAM360_MESSAGING_DEV_ENABLED=1
TEAM360_MESSAGING_DISPATCH_MODE=horizontal_v1
TEAM360_MESSAGING_WORKSPACE_SLUG=telchi_dev
TEAM360_MESSAGING_CHANNEL_ALIAS=telchi_whatsapp_dev
TEAM360_TELCHI_ASSISTANT_DEV_HTTP=1
TEAM360_TELCHI_ASSISTANT_DEV_HTTP_TOKEN=<random per run, >= 32 chars>
TEAM360_TELCHI_ASSISTANT_DEV_PHONE=<from PG binding>
```

## Output

* `runtime_http_results.json` — per turn: user text, HTTP status, classification,
  State Engine decision, `committed`, capability category, persisted state,
  audit, timings and the effective `curl` command (token redacted).
* `dev-server.log` — DEV server stdout (no token/phone).
* `security/security_results.json` — token, payload, routing, isolation and
  concurrency probes.
* `restart/restart_results.json` — durable context recovered after a DEV restart.