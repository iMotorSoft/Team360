# Multi-package Workers

A workspace can contract multiple automation packages. Each package can be composed of one or more workers.

Do not model only global workers. The operational center is `package_worker`: the concrete use of a worker inside a package for a specific workspace.

## Conceptual Model

```text
workspace
  -> assistant_instance
  -> automation_package
      -> package_worker
          -> package_worker_config
          -> credential_reference
          -> knowledge_scope
```

## Worker Definition vs Package Worker

`worker_definition` describes a generic capability:

- `sap_b1_desktop_worker`;
- `meli_browser_worker`;
- `document_ocr_worker`;
- `diagnosis_ai_interpreter`;
- `workflow_classifier`;
- `approval_worker`.

`package_worker` describes the concrete use of that capability for a package in a workspace.

## Package Worker Config

A `package_worker` can need:

- private configuration;
- URLs or endpoints;
- dedicated users;
- credential references;
- API keys or tokens by reference;
- permissions;
- operational limits;
- `allowed_actions`;
- `blocked_actions`;
- mode: `read_only`, `assisted`, `approval_required`, `execution`, `blocked`;
- private operating data;
- `knowledge_scope_id`;
- audit and traceability rules.

## Interaction Boundary

Customers never interact directly with workers.

Allowed:

```text
Customer -> Team360 -> automation_package -> package_worker -> worker
```

Forbidden:

```text
Customer -> worker
```

## Phase 1 Rule

In Phase 1, workers can be internal backend modules.

They must still expose clear contracts so they can later become external processes, browser workers, desktop workers, queues, independent services or specialized agents.
