<script lang="ts">
  import { Card, EmptyState, SectionHeader, StatusBadge } from "../../ui";
  import { organizations, users, workspaces } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const accessibleOrganizationIds = $derived(new Set(consoleContext.bootstrap.accessibleOrganizations.map(({ id }) => id)));
  const accessibleWorkspaceIds = $derived(new Set(consoleContext.bootstrap.accessibleWorkspaces.map(({ id }) => id)));
  const visibleUsers = $derived(
    users.filter(
      ({ organizationId, workspaceIds }) =>
        accessibleOrganizationIds.has(organizationId) || workspaceIds.some((workspaceId) => accessibleWorkspaceIds.has(workspaceId)),
    ),
  );

  function organizationName(organizationId: string) {
    return organizations.find(({ id }) => id === organizationId)?.name ?? "Organización no disponible";
  }

  function workspaceNames(workspaceIds: string[]) {
    return workspaces.filter(({ id }) => workspaceIds.includes(id) && accessibleWorkspaceIds.has(id)).map(({ name }) => name);
  }
</script>

<section>
  <SectionHeader
    eyebrow="Personas y accesos visibles"
    title={consoleContext.bootstrap.uiHints.technicalDepth === "full" ? "Usuarios" : "Equipo"}
    description="Consulta roles, organización, workspaces visibles y permisos resumidos. La creación y edición quedan fuera de esta fase mock."
  />

  <div class="mt-7 grid gap-4 xl:grid-cols-2">
    {#each visibleUsers as user}
      <Card variant="flat">
        <div class="flex items-start gap-4">
          <span class="grid size-12 shrink-0 place-items-center rounded-xl bg-[#153b5b] text-xs font-bold text-white">{user.avatarInitials}</span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 class="text-sm font-bold text-[#31536b]">{user.name}</h2>
                <p class="mt-1 text-xs text-[#8396a2]">{user.email}</p>
              </div>
              <StatusBadge status={user.status} />
            </div>
            <p class="mt-3 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-[#168b88]">{user.role}</p>
            <p class="mt-2 text-xs leading-5 text-[#78909f]">{organizationName(user.organizationId)}</p>
          </div>
        </div>
        <div class="mt-4 border-t border-[#edf1f2] pt-4">
          <p class="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-[#91a2ad]">Workspaces visibles</p>
          <p class="mt-2 text-xs leading-5 text-[#668092]">{workspaceNames(user.workspaceIds).join(" · ") || "Sin workspace visible en este alcance"}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            {#each user.permissionSummary as permission}
              <span class="rounded-full bg-[#eef6f5] px-2.5 py-1 text-[0.66rem] font-bold text-[#47716f]">{permission}</span>
            {/each}
          </div>
        </div>
      </Card>
    {/each}
    {#if visibleUsers.length === 0}
      <EmptyState
        title="Todavía no hay integrantes visibles."
        description="El equipo aparecerá cuando existan personas asignadas al alcance seleccionado."
        nextStep="Revisar el workspace o esperar la próxima asignación."
      />
    {/if}
  </div>
</section>
