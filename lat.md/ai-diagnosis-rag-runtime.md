# AI Diagnosis RAG Runtime

Team360 should accelerate the first automation diagnosis service by reusing the proven JudaismoenVivo RAG runtime pattern:

```text
ArangoDB + Milvus + LiteLLM
```

This is a runtime direction for automation diagnosis and sales assistant knowledge. It does not replace PostgreSQL as Team360's transactional core.

## Initial Commercial Scope

The first runtime users are intelligent sales and diagnosis assistants for:

- Team360's direct public website;
- Mamá Mía 360's site as distributor / regional partner in Israel.

Mamá Mía 360 must be modeled as partner configuration, not as forked product logic. Its assistant must support Spanish, English and Hebrew and preserve partner attribution for leads, costs and commercial follow-up.

Both assistants share the same diagnosis RAG runtime and differ by `assistant_instance`, organization/workspace context, market, locale policy, allowed packages and knowledge scope.

The Team360 direct assistant must be treated as the first customer package installation, with its own workspace, assistant instance, package workers, knowledge scope, ArangoDB/Milvus scope filters and PostgreSQL lead/audit records. See [[customer-packaged-assistant-instance]].

The knowledge entity contract for this runtime is [[knowledge-scope-contract]].

## Core Rule

```text
PostgreSQL records operational truth.
ArangoDB models diagnosis knowledge relationships.
Milvus retrieves semantic context.
LiteLLM routes model calls.
Team360 decides, audits and renders.
```

This extends [[knowledge-rag-graphrag]], [[ai-litellm]], [[postgres-ai-persistence]] and [[security-hitl-mfa]].

## Why This Runtime

The first Team360 automation diagnosis service should prioritize speed of delivery and reuse of known working patterns.

ArangoDB + Milvus has already been validated in JudaismoenVivo for assistant-style retrieval over structured knowledge plus semantic search.

Team360 should not spend its first release cycle rebuilding this capability on pgvector if ArangoDB + Milvus can provide faster delivery and better graph expressiveness for diagnosis.

## Persistence Boundaries

### PostgreSQL

PostgreSQL 18 remains the source of truth for:

- organizations;
- workspaces;
- users and permissions;
- automation packages;
- package workers;
- diagnosis sessions and final diagnosis records;
- events;
- audit;
- cost ledger;
- billing and commercial state.

### ArangoDB

ArangoDB is the graph/document knowledge runtime for diagnosis.

It can model:

- client types;
- industries;
- business processes;
- pains;
- systems;
- automation candidates;
- blocked or not-recommended automations;
- risk flags;
- HITL/MFA modes;
- package-worker applicability;
- dependencies and integration requirements.

### Milvus

Milvus is the initial vector runtime for:

- semantic retrieval;
- similar cases;
- playbooks;
- diagnosis fragments;
- automation catalog text;
- proposal templates;
- retrieved context for LLM interpretation.

Milvus stores vectors and retrieval metadata. It is not the source of truth for commercial or operational records.

### pgvector

Migration `003_team360_pgvector_knowledge_embeddings.sql` has materialized pgvector capability in PostgreSQL.

For the first automation diagnosis runtime:

```text
pgvector is available but not the primary RAG runtime.
```

pgvector may be used later for:

- small internal knowledge scopes;
- fallback retrieval;
- consolidation if external vector infrastructure is not justified;
- experiments with PostgreSQL-only deployments.

Do not design the initial diagnosis service around pgvector unless an explicit later decision changes this runtime boundary.

## LiteLLM Boundary

All model calls for this service should go through LiteLLM via a Team360 adapter/port.

Domain logic must not call OpenAI or OpenRouter directly.

Model slugs should be hidden behind aliases such as:

```text
automation_diagnosis_text
automation_diagnosis_classifier
automation_diagnosis_recommender
sales_assistant_text
cheap_classifier
```

Requests must include Team360 metadata for cost, audit and support:

```text
organization_id
workspace_id
assistant_instance_id
automation_package_id
package_worker_id
session_id
correlation_id
feature
phase
model_alias
```

LiteLLM tracks and routes. Team360 owns final authorization, scoring, billing and audit.

## AG-UI And SSE

The model should not return HTML as the primary UI contract.

The model should return semantic diagnosis structures such as:

```text
diagnosis_summary
automation_candidates
not_recommended_items
required_integrations
risk_flags
hitl_requirements
commercial_fit
suggested_packages
next_questions
proposal_outline
```

Litestar should stream progress with SSE and render AG-UI blocks from validated structures:

- cards;
- forms;
- tables;
- alerts;
- scores;
- timelines;
- recommendations.

## Security And Sales Boundary

Automation diagnosis can suggest opportunities, but it must not promise bypass of security controls.

If a requested process depends on MFA bypass, hardware keys, biometrics, strong signatures, anti-bot evasion or irreversible financial writes, the diagnosis must classify it as:

- blocked;
- not recommended;
- consulting only;
- assisted with HITL;
- official API required.

The diagnosis is a sales asset, but it must remain technically honest.

## Initial Model Direction

Preliminary model routing from JudaismoenVivo evaluations:

- `qwen/qwen3-30b-a3b-thinking-2507`: primary candidate for enriched consultative diagnosis.
- `gpt-4o-mini-2024-07-18`: OpenAI fallback.
- `deepseek/deepseek-v4-flash`: useful for offline/deep analysis, not default interactive if latency/format risks remain.
- `gpt-4.1-nano-2025-04-14`: cheap auxiliary classifier/extractor while available, not the main diagnosis brain.

These slugs must remain configuration behind aliases.

## Decision

For the first Team360 automation diagnosis and intelligent sales assistant:

```text
Use ArangoDB + Milvus + LiteLLM.
Keep PostgreSQL as operational truth.
Do not use pgvector as the primary RAG runtime for the first release.
Render AG-UI from structured diagnosis output, not model-generated HTML.
```
