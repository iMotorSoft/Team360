# Backend Scripts

Scripts operativos y utilitarios del backend.

Si aparecen scripts de catalogo, pgvector o sync desde `v360`, deben tratarse como infraestructura futura opcional.
No forman parte del runtime central actual de Team360 ni de la prioridad principal del producto.

## automation_diagnosis

- `smoke_automation_diagnosis_litellm.py`: smoke HTTP controlado para validar que un backend ya levantado con `TEAM360_AI_PROVIDER=litellm` puede iniciar sesion, guardar 10 respuestas y clasificar usando el proxy LiteLLM real. Tambien sirve para modo combinado `TEAM360_AI_PROVIDER=litellm` + `AUTOMATION_DIAGNOSIS_REPOSITORY=postgres`; usar `--print-sql` para imprimir la query read-only de verificacion PostgreSQL por `session_id`.

Modo combinado LiteLLM + PostgreSQL:

```bash
cd backend
uv run python scripts/smoke_automation_diagnosis_litellm.py --backend-url http://127.0.0.1:8011 --timeout 120 --print-sql
```

Si PostgreSQL falla durante el snapshot, el backend debe responder HTTP 503 y el smoke imprime el cuerpo truncado del error.

## sales_diagnosis_runtime

- `smoke_sales_diagnosis_runtime_postgres.py`: smoke backend-only del runtime completo `AssistantConversationRuntime` contra PostgreSQL 18 real.
  - Usa fake RetrievalProvider (no Milvus), fake LLMProvider (no OpenAI), fake MetricsRecorder y fake AuditTrail.
  - Realiza 4 turnos: safe → safe → soft guardrail (too_many_questions) → hard guardrail (unsafe_claim / UnsafeResponseError).
  - Valida que state se guarda/carga entre turnos, turn_count incrementa, guardrails funcionan y cleanup se ejecuta.
  - Requiere `TEAM360_DB_URL` y migracion 007 aplicada.
  - No endpoint, no frontend, no LLM real, no Milvus real.

  ```bash
  cd backend
  TEAM360_DB_URL=postgresql://user:pass@localhost:5432/team360 \
    uv run python scripts/smoke_sales_diagnosis_runtime_postgres.py
  ```

- `smoke_sales_diagnosis_state_postgres_async.py`: smoke async de `AsyncPostgresConversationStateRepository` contra PostgreSQL 18 real.
  - Usa psycopg_pool.AsyncConnectionPool directamente.
  - Valida save → load → update → load non-existent → verify round-trip fidelity con ConversationStateSerializer y RetrievedChunks.
  - Requiere `TEAM360_DB_URL` (o `TEAM360_DB_URL_PSQL`) y migracion 007 aplicada.
  - No runtime, no endpoint, no LLM, no Milvus.

  ```bash
  cd backend
  TEAM360_DB_URL=postgresql://user:pass@localhost:5432/v360 \
    uv run python scripts/smoke_sales_diagnosis_state_postgres_async.py
  ```

## sync_conversation_states

- `smoke_sales_diagnosis_state_postgres.py`: smoke original (sync bridge) para validar tabla `sales_diagnosis_conversation_states` contra PostgreSQL real. Pre-1.8g, reemplazado por el smoke async.

- `smoke_sales_diagnosis_runtime_dev_endpoint.py`: smoke HTTP del endpoint interno/dev `POST /api/dev/sales-diagnosis-runtime/turn`. Requiere backend corriendo. Valida response contract, turn_count, guardrails, IDs prohibidos, runtime_mode, y que no se usen servicios reales. No requiere DB, no requiere LLM real, no requiere Milvus.

  ```bash
  cd backend
  # terminal 1: backend
  uv run uvicorn app:app --host 127.0.0.1 --port 8000
  # terminal 2: smoke
  uv run python scripts/smoke_sales_diagnosis_runtime_dev_endpoint.py
  ```
