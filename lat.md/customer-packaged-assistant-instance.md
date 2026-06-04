# Customer Packaged Assistant Instance

Team360 must ship its first intelligent sales and automation diagnosis assistant as a real customer package installation, not as an internal demo or hardcoded special case.

This extends [[team360-platform]], [[console-multi-organization]], [[multi-package-workers]], [[automation-diagnosis]], [[knowledge-rag-graphrag]] and [[ai-diagnosis-rag-runtime]].

## Core Rule

```text
A customer buys a package.
The package creates/configures an assistant instance.
The assistant instance uses package workers.
Knowledge is scoped to the customer/workspace/assistant.
PostgreSQL records truth.
ArangoDB and Milvus provide scoped knowledge/retrieval runtime.
```

The canonical knowledge contract is [[knowledge-scope-contract]].

The first installation is Team360's own direct sales site:

```text
customer_organization: Team360
workspace: team360_public_site
automation_package: pkg_sales_diagnosis
assistant_instance: team360_sales_diagnosis
knowledge_scope: ks_team360_sales_diagnosis
lead_owner: Team360
market: direct
site_channel: team360.live
```

This is a self-customer installation. Team360 remains the platform/control-plane owner, but the public sales assistant must still be modeled as a customer-facing package instance with the same contracts that future customers and partners use.

## Why This Matters

Do not build a disposable Team360 sales assistant.

The first Team360 assistant must validate:

- organization and workspace scoping;
- package purchase/activation shape;
- assistant instance configuration;
- worker binding through `package_worker`;
- knowledge scope ownership;
- ArangoDB graph/document scoping;
- Milvus retrieval scoping;
- lead ownership;
- cost attribution;
- events and audit;
- AG-UI/SSE rendering from structured output.

If Team360 direct sales works as a package installation, Mamá Mía 360 and future partners can reuse the same pattern.

## Package Shape

The sales and diagnosis package should expose a customer-facing service:

```text
Asistente de venta y diagnostico
```

Internally, it can bind workers such as:

```text
guided_intake_worker
lead_qualification_worker
knowledge_retrieval_worker
diagnosis_scoring_worker
package_recommendation_worker
proposal_outline_worker
crm_handoff_worker
calendar_handoff_worker
agui_render_worker
```

Workers remain internal execution capabilities. The customer never contracts or calls workers directly.

## Required Runtime Context

Every session, event, model call, retrieval query and final lead card must carry:

```text
organization_id
workspace_id
assistant_instance_id
automation_package_id
knowledge_scope_id
site_channel
lead_owner
correlation_id
locale
```

For partner channels, also carry:

```text
partner_id
market_country
partner_lead_owner
```

## PostgreSQL Boundary

PostgreSQL remains the source of truth for:

- customer organization/workspace;
- package activation;
- assistant instance configuration;
- worker bindings and configs;
- credential references;
- diagnosis sessions;
- final diagnosis results;
- leads;
- events;
- audit;
- cost ledger and billing attribution.

ArangoDB and Milvus must not become the commercial or operational source of truth.

## ArangoDB Scope Rule

Do not create one physical collection per customer as the default.

Default model:

```text
shared domain collections
  + mandatory tenant/scope fields
  + logical graph per knowledge_scope or assistant_instance
```

Required fields on ArangoDB documents/edges:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_type
source_kind
version
status
```

Recommended initial collections:

```text
diagnosis_vertices
diagnosis_edges
diagnosis_documents
diagnosis_playbooks
```

The Team360 direct sales assistant uses:

```text
knowledge_scope_id = ks_team360_sales_diagnosis
assistant_instance_id = team360_sales_diagnosis
```

Physical collection/database isolation is reserved for explicit cases:

- enterprise/compliance requirement;
- high volume;
- legal isolation;
- operational performance proof;
- dedicated deployment contract.

## Milvus Scope Rule

Milvus stores embeddings and retrieval metadata, not truth.

Default model:

```text
shared collection or controlled partition
  + mandatory metadata filters
```

Required metadata:

```text
organization_id
workspace_id
assistant_instance_id
knowledge_scope_id
document_id
chunk_id
source_kind
version
status
```

Retrieval must always filter by `knowledge_scope_id` and should also filter by organization/workspace/assistant when available. Cross-customer retrieval is not allowed unless a future explicit shared/global knowledge scope permits it.

## Team360 Direct Installation

The Team360 direct assistant should be treated exactly like a sold package:

```text
Team360 as customer
  -> public website workspace
  -> sales diagnosis package
  -> assistant instance
  -> package workers
  -> Team360 sales knowledge scope
  -> ArangoDB graph/doc runtime
  -> Milvus semantic retrieval
  -> LiteLLM interpretation
  -> PostgreSQL final lead/result/audit
```

No code should branch on "if Team360 then special assistant." It should resolve the same package/assistant configuration path a normal customer uses.

## Partner Reuse

Mamá Mía 360 reuses the same package pattern:

```text
partner: Mamá Mía 360
market_country: Israel
supported_locales: es, en, he
assistant_instance: mamamia360_sales_diagnosis
knowledge_scope: ks_mamamia360_sales_diagnosis
```

The partner instance differs by brand, market, locale policy, catalog visibility, lead routing, cost attribution and knowledge scope. It does not fork the engine.
