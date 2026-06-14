# Knowledge Documents Foundation

Team360 separates source knowledge documents from runtime ingestion and from
the first concrete package.

This document defines the stable documentation boundary. Runtime entities and
retrieval contracts remain in [[knowledge-scope-contract]] and
[[knowledge-rag-graphrag]].

## Core Rule

```text
knowledge documentation foundation
  -> reusable structure, metadata, curation and authoring standards

knowledge package
  -> concrete corpus bound to package_code / knowledge_scope_code

case or assistant
  -> visible installation, channel or validation scenario
```

`pkg_sales_diagnosis` is the first concrete package. It must not define the
whole knowledge documentation architecture.

## Repository Boundary

The canonical source-document tree is:

```text
SrvRestAstroLS_v1/knowledge/
```

Within that tree:

- `_standards/` contains reusable authoring, metadata, curation and chunking
  preparation rules;
- `global/` contains future cross-package knowledge;
- `packages/{package_code}/` contains package-specific knowledge.

## Directory Lifecycle

Every global or package corpus uses the same lifecycle:

```text
drafts/    -> review only, not ingested
approved/  -> canonical source documents ready for ingestion
exports/   -> derived human-readable outputs, not canonical
archive/   -> replaced or deprecated documents, not active
```

Documents can move from `drafts/` to `approved/` only after metadata,
evidence, access tags, risk, scope and limits have been reviewed.

## Metadata Boundary

Every source document intended for ingestion must carry YAML frontmatter with
stable technical identifiers:

```text
knowledge_scope_code
scope_type
organization_code
workspace_code
package_code when applicable
assistant_instance_code when applicable
area_key
topic_key
document_type
visibility
access_tags
locale
version
source_type
node_path
status
ingestion_status
```

Package metadata lives under:

```text
knowledge/packages/{package_code}/_metadata/
```

The package metadata declares the package profile, scope mapping and access tag
catalog for that package. Global knowledge must not inherit package permissions
implicitly.

## L0, L1, L2

Source documents should be written for semantic retrieval:

- L0: compact document abstract with scope and limits;
- L1: major sections that can be retrieved independently;
- L2: granular rules, examples, matrices and exceptions.

This prepares documents for a future SemanticChunker without binding the
documentation structure to one implementation.

## Global vs Package vs Case

Global knowledge is reusable across packages and must use `scope_type: global`
unless an explicit exception is documented.

Package knowledge belongs under `packages/{package_code}/` and must not contain
unrelated package material.

A case, customer, channel, public assistant or validation scenario can use a
package, but it does not redefine package architecture.

## Sales Diagnosis Boundary

The first package uses:

```text
package_code: pkg_sales_diagnosis
knowledge_scope_code: ks_team360_sales_diagnosis
assistant_instance_code: team360_sales_diagnosis
service_code: svc_sales_diagnosis
template_code: team360_sales_automation_diagnosis
```

`Vera / Asistente Inteligente Vera` is a commercial visible name only. It must
not be used as a technical core identifier and must not create `vera_*`
identifiers in runtime, tests, migrations, workers, scopes or canonical source
documents.

## Diagnostic Feasibility Principle

Team360 diagnostic assistants must evaluate technical and operational
feasibility for user-proposed cases when possible, even when the case is not in
the immediate package catalog.

Feasibility diagnosis is not the same as immediate commercial availability,
implementation promise, quotation, lead capture or package creation.

The stable documentation standard lives in:

```text
SrvRestAstroLS_v1/knowledge/_standards/diagnostic-feasibility-principle.md
```

The standard separates:

- technical feasibility;
- operational feasibility;
- immediate commercial availability;
- need for more information;
- human review;
- future opportunity;
- not recommended or high-risk cases.

`pkg_sales_diagnosis` is the first concrete package where this principle
applies, but it does not define the general rule.

## Non-Goals

This foundation does not:

- implement SemanticChunker;
- run embeddings;
- write ArangoDB, Milvus, pgvector or PostgreSQL records;
- create ingestion endpoints;
- create a knowledge admin UI;
- promote draft package content to approved content.

## Decision

Team360 keeps knowledge source documentation generic and multi-package ready.
`pkg_sales_diagnosis` validates the structure as the first package, while the
foundation remains independent from sales and ready for future packages.
