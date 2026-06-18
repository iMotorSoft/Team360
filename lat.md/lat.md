# Team360

This directory defines high-level concepts, business logic, architecture decisions and test specifications for Team360.

It is managed as a `lat.md` documentation layer: source code can anchor to these definitions with `@lat` comments and `[[...]]` references.

- [[team360-global-orchestration]] — mapa global de ramas, frentes activos, reglas de coordinación y estado transversal de Team360.
- [[team360-pack-task-diagnosis-model]] — modelo conceptual de T360 Packs, Tasks, Pack Flows, Pack Integrate y alcance del Diagnostico Team360.
- [[team360-platform]] — Product thesis, control plane, auditability and ERP AI Workflow Layer positioning.
- [[multi-package-workers]] — Workspace, automation packages, package workers, worker configs, credentials and customer interaction boundaries.
- [[knowledge-rag-graphrag]] — Knowledge scopes, RAG/GraphRAG retrieval modes, document/chunk model and future graph model.
- [[knowledge-scope-contract]] — Canonical KnowledgeScope / KnowledgeDocument / KnowledgeChunk / VectorEmbedding contract derived from JudaismoEnVivo Catalog/MD/Chunk, with multi-tenant filters, ArangoDB text/graph source, Milvus derived index and pgvector laboratory/fallback boundary.
- [[ai-litellm]] — LiteLLM as OpenAI-compatible AI gateway, adapter boundary, model aliases, usage metadata and fallback rules.
- [[ai-diagnosis-rag-runtime]] — Initial automation diagnosis RAG runtime: ArangoDB + Milvus + LiteLLM, with PostgreSQL as operational truth and pgvector as available but not primary for first release.
- [[customer-packaged-assistant-instance]] — Treat Team360's first sales/diagnosis assistant as a real customer package installation with assistant instance, package workers, scoped ArangoDB/Milvus knowledge and PostgreSQL truth.
- [[security-hitl-mfa]] — MFA, HITL, remote mirroring, hardware proximity, blocked actions and no-bypass security rules.
- [[automation-diagnosis]] — Guided automation diagnosis assistant, deterministic classification and Phase 1 implementation invariants.
- [[postgres-ai-persistence]] — PostgreSQL 18 as transactional core, pgvector and LangGraph persistence roadmap, checkpoint boundaries.
- [[postgres-driver-policy]] — `psycopg 3 async` as standard runtime DB driver, repository pattern, SQLAlchemy/asyncpg policy.
- [[console-multi-organization]] — Public website and Team360 Console boundary, organization hierarchy, delegated access, contextual navigation and reusable App Shell.
- [[team360-frontend-base]] — Vertice360 as technical/UX base for Team360 frontend. Stack: pnpm, Astro 6, Svelte 5 with Runes, Tailwind 4, DaisyUI 5 CSS-first, AG-UI. See `docs/frontend/team360-frontend-technical-base-from-vertice360.md` and `docs/adr/ADR-004-team360-frontend-base-vertice360-modern-stack.md`.
- [[team360-frontend-ui-policy]] — Frontend invariants: pnpm is mandatory; Tailwind CSS 4 + DaisyUI 5 CSS-first is the initial UI stack; business screens consume Team360 wrappers from `src/components/ui/`. See `docs/frontend/team360-package-manager-and-ui-policy.md` and `docs/adr/ADR-005-team360-pnpm-tailwind4-daisyui5-ui-policy.md`.
- [[model-selection-routing]] — Model tier architecture (nano/mini/medium/large), provider routing (OpenAI direct vs OpenRouter), per-automation-type routing policy (SAP B1, browser, diagnosis), aliases over hardcoded slugs, and cost/pricing invariants.
- [[deepseek-v4-flash-opencode-browser]] — Guia operativa para usar DeepSeek V4 Flash con OpenCode + `opencode-browser`: browser QA dirigido, snapshots, prompts atomicos, validacion frontend/backend y limites frente a GPT-5.5.
- [[service-preflight-methodology]] — Mandatory preflight methodology before development tests, smokes, benchmarks or quality conclusions that depend on PostgreSQL, Milvus, LiteLLM, model aliases, env vars or external providers.
- [[team360-frontend-url-source-of-truth]] — Frontend URL single source of truth: `global.js` as canonical endpoint resolver, no hardcoded URLs, dev/pro toggle, centralized helpers.
- [[team360-runtime-operational-policy]] — Validated public Vera runtime policy: `/t360` -> Litestar -> PostgreSQL 18 -> Milvus 2.6 -> LiteLLM Chat Completions -> `openai_gpt-5-nano`, including ports, env vars, frontend URL ownership, secrets policy and smoke validation rules.
