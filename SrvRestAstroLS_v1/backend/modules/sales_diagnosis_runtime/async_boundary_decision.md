# Async Boundary Decision — Sales Diagnosis Runtime

## Context

The `AssistantConversationRuntime` was built as a synchronous core. All
providers (`StateRepository`, `RetrievalProvider`, `LLMProvider`,
`MetricsRecorder`, `AuditTrail`) are sync protocols. Production PostgreSQL
persistence requires `psycopg_pool.AsyncConnectionPool` — a fundamentally
async resource.

## Decision

**Keep the runtime core sync. Add an async boundary for persistence only.**

### What stays sync

- `AssistantConversationRuntime.handle_turn()` — public API
- `StateRepository`, `RetrievalProvider`, `LLMProvider` — all protocols
- All existing mock/null providers, tests, smokes

### What becomes async

- `AsyncStateRepository` protocol in `providers.py`
- `AsyncPostgresConversationStateRepository` in `state_repository.py`
- Async smoke `scripts/smoke_sales_diagnosis_state_postgres_async.py`

### Why not convert the runtime to async today

1. **Scope creep**: Converting `handle_turn` to async would cascade through
   `retrieve`, `generate`, `record_turn`, `record` — all protocol methods.
2. **Test surface**: ~250 lines of sync tests across 5+ files would need
   async migration.
3. **No endpoint driver**: The first consumer of async state persistence is
   the future SSE/endpoint layer. That layer is not yet defined.
4. **Incremental safety**: The async repository is independently testable,
   smokable, and can be wired into an async endpoint without touching the
   runtime.

## Architecture

```
Endpoint (async)      ──→  AsyncStateRepository (protocol)
                                │
                    ┌───────────┴───────────┐
                    │                       │
     AsyncPostgres                AsyncInMemory (tests)
 ConversationStateRepo
     (psycopg 3 pool)
```

The sync runtime continues to use `StateRepository` (sync). When a future
async endpoint orchestrates a turn, it will:

1. Call `AsyncStateRepository.load()` to fetch prior state (async)
2. Call `runtime.handle_turn(input, state)` (sync — fast, no I/O)
3. Call `AsyncStateRepository.save(output.next_state)` (async)

## Files Changed

| File | Change |
|------|--------|
| `providers.py` | Added `AsyncStateRepository` protocol and `AsyncInMemoryStateRepository` |
| `state_repository.py` | Added `AsyncPostgresConversationStateRepository` |
| `scripts/smoke_sales_diagnosis_state_postgres_async.py` | New async smoke |
| `tests/test_sales_diagnosis_async_state_repository.py` | New 19 tests |

## Future Considerations

- When a real endpoint is introduced, it should use `AsyncStateRepository`
  and call `handle_turn` as a sync subroutine between async I/O operations.
- If `retrieve()` or `generate()` ever become async (Milvus gRPC, LLM
  streaming), the protocols would need async variants, and the runtime
  would need a separate async entry point.
- The sync `PostgresConversationStateRepository` skeleton is preserved for
  documentation/reference.
