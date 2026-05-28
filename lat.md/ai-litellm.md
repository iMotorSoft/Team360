# AI LiteLLM

Team360 should use LiteLLM through an adapter boundary, not directly from domain logic.

LiteLLM is an OpenAI-compatible gateway for model access, aliases, provider switching and usage metadata.

## Adapter Rule

Domain services should depend on ports such as:

```text
AIInterpreterPort
  -> LiteLLMAIInterpreter
  -> MockAIInterpreter
  -> NoopAIInterpreter
```

LiteLLM is the real AI path for modules that need AI in Phase 1.

Mock and Noop exist for tests, fallback and local deterministic execution.

## Configuration

Recommended variables:

```bash
TEAM360_AI_PROVIDER=litellm|mock|none
TEAM360_LITELLM_BASE_URL=http://localhost:4000/v1
TEAM360_LITELLM_API_KEY=...
LITELLM_MASTER_KEY=...
TEAM360_AUTOMATION_DIAGNOSIS_TEXT_MODEL=automation_diagnosis_text
TEAM360_AUTOMATION_DIAGNOSIS_EMBEDDING_MODEL=automation_diagnosis_embedding
```

Secrets must not be stored in repo files. Use references or environment variables.

## Usage Metadata

The AI layer should prepare or record:

- provider;
- model alias;
- model returned by provider;
- prompt tokens;
- completion tokens;
- total tokens;
- cost when available;
- latency;
- correlation_id;
- session_id;
- automation key or package context.

## Decision Boundary

AI can:

- interpret free text;
- extract signals;
- summarize;
- draft user-facing explanations;
- detect mentioned risks;
- suggest possible workers.

AI must not:

- decide final classification alone;
- bypass scoring;
- approve sensitive actions;
- bypass security controls;
- expose secrets.

Rule:

```text
LiteLLM interprets.
Team360 decides.
```
