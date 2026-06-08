# Knowledge Runtime Target

A knowledge package lives at the platform / package level within
the `team360` organization and `team360_platform` workspace.
Its `knowledge-scope-mapping.yaml` declares `organization_code` and
`workspace_code` for this package-level context.

A document approved for ingestion may additionally declare an
`organization_code` and `workspace_code` that correspond to a
**runtime target** — the actual client deployment (e.g. Team360.live
running in `team360_live` / `team360_public_site`).

This is not a mismatch; it is a valid target declaration.

## Invariant

- `knowledge-scope-mapping.yaml` MAY declare
  `default_runtime_organization_code` and
  `default_runtime_workspace_code` to make runtime targets explicit.
- The scanner MUST accept documents whose `organization_code` +
  `workspace_code` match a declared runtime target without emitting
  a workspace_code warning.
- A document pointing to a workspace that is neither the package
  workspace nor a declared runtime target SHALL still generate a
  warning.

## Motivation

Separating the package/platform workspace from the runtime target
allows a single package to define knowledge at the platform level
while documents declare which specific client deployment they feed.
This avoids false positives in validation and keeps the platform →
tenant mapping explicit in metadata rather than hardcoded.
