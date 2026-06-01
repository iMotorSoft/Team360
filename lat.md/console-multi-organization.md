# Team360 Console Multi-organization

Team360 separates its public commercial website from its private operational console.

## Domain Boundary

```text
team360.live
  -> public commercial website

console.team360.live
  -> Team360 Console
  -> private operational platform
```

The public website explains value and converts prospects. Team360 Console manages organizations, workspaces, services, packages, workers, runs, results and permissions.

Do not merge both information architectures into a single generic application experience.

## Organization Hierarchy

Team360 is the root organization.

Initial organization types:

```text
team360_root
partner
direct_client
partner_client
```

Initial allowed hierarchy:

```text
Team360
|-- direct_client
`-- partner
    `-- partner_client
```

A partner can administer its own organization and its authorized descendants. It cannot see direct Team360 clients, other partners or sibling subtrees.

`Mamá Mía 360` is the first concrete `partner` instance for region `Israel`. It must remain configuration data, never hardcoded product logic.

## Organization vs Workspace

`organization` is the commercial, contractual and hierarchical entity.

`workspace` is an operational context owned by an organization. Services, configurations, runs and visible results are scoped to a workspace.

A user belongs to an organization and can receive explicit access to one or more workspaces.

## Authorization Invariant

Every private request must resolve:

```text
authenticated_user_id
organization_id
workspace_id
granted_permissions
allowed_organization_scope
```

UI filtering is not authorization. Backend checks must enforce membership, workspace access, atomic permission, resource ownership and allowed organization subtree.

## Navigation Invariant

Team360 Console uses one adaptable App Shell. Visible navigation and service tabs are derived from organization type, effective permissions, active workspace, contracted services, available modules and allowed organization scope.

Roles are initial permission profiles, not the only authorization source. The UI must always display the active organization, workspace and access mode.

See `docs/ux/team360-console-navigation-model.md` and `docs/adr/ADR-002-team360-console-navigation-by-role.md`.

## App Shell Invariant

Team360 Console uses one reusable App Shell and shared layout patterns. Role and organization context adapt visibility and depth; they do not create separate consoles.

Private data must not render before session and active context validation. Workspace changes must discard stale UI state.

See `docs/ux/team360-console-app-shell-and-layout-system.md` and `docs/adr/ADR-003-team360-console-app-shell-and-layout-system.md`.

## Product Vocabulary

```text
package
  -> commercial offer

service
  -> contracted outcome visible to the customer

worker
  -> internal technical execution capability

dashboard / report
  -> visible result for an authorized customer or partner
```

Customers do not interact directly with workers. See [[multi-package-workers]].

## Current Schema Gap

Current migrations model `core_workspaces`, `core_users`, RBAC, packages and workers. They do not yet fully model organizations, parent-child hierarchy, regions, multi-workspace user access, customer-visible services or delegated partner scope.

Implement this target model through a future explicit and auditable migration. Do not retrofit old migrations silently.

## Product and UX Reference

See `docs/ux/team360-domains-and-console-strategy.md` and `docs/adr/ADR-001-team360-domain-separation-and-console.md`.
