# Team360

This directory defines high-level concepts, business logic, architecture decisions and test specifications for Team360.

It is managed as a `lat.md` documentation layer: source code can anchor to these definitions with `@lat` comments and `[[...]]` references.

- [[team360-platform]] — Product thesis, control plane, auditability and ERP AI Workflow Layer positioning.
- [[multi-package-workers]] — Workspace, automation packages, package workers, worker configs, credentials and customer interaction boundaries.
- [[knowledge-rag-graphrag]] — Knowledge scopes, RAG/GraphRAG retrieval modes, document/chunk model and future graph model.
- [[ai-litellm]] — LiteLLM as OpenAI-compatible AI gateway, adapter boundary, model aliases, usage metadata and fallback rules.
- [[security-hitl-mfa]] — MFA, HITL, remote mirroring, hardware proximity, blocked actions and no-bypass security rules.
- [[automation-diagnosis]] — Guided automation diagnosis assistant, deterministic classification and Phase 1 implementation invariants.
- [[postgres-ai-persistence]] - PostgreSQL 18 as transactional core, pgvector and LangGraph persistence roadmap, checkpoint boundaries.
