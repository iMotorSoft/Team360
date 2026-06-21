<script lang="ts">
  import { Card, SectionHeader, StatusBadge } from "../../ui";
  import { integrations } from "../../../lib/mock";
  import { consoleContext } from "../../../stores/consoleContext.svelte";

  const workspaceIntegrations = $derived(
    integrations.filter(
      ({ workspaceId }) => workspaceId === consoleContext.activeWorkspace.id,
    ),
  );
</script>

<section>
  <SectionHeader
    eyebrow="Preferencias del contexto"
    title="Configuración"
    description="Resumen de organización, workspace, módulos e integraciones previstas. La edición real queda deshabilitada en esta fase."
  />

  <div class="mt-7 grid gap-5 xl:grid-cols-2">
    <Card variant="flat-large">
      <p class="top-badge">Contexto operativo</p>
      <dl class="mt-5 space-y-3 text-lg">
        <div class="flex justify-between gap-3 border-b border-[#edf1f2] pb-3">
          <dt class="text-[#78909f]">Organización</dt>
          <dd class="font-bold text-[#31536b]">
            {consoleContext.activeOrganization.name}
          </dd>
        </div>
        <div class="flex justify-between gap-3 border-b border-[#edf1f2] pb-3">
          <dt class="text-[#78909f]">Workspace</dt>
          <dd class="font-bold text-[#31536b]">
            {consoleContext.activeWorkspace.name}
          </dd>
        </div>
        <div class="flex justify-between gap-3 border-b border-[#edf1f2] pb-3">
          <dt class="text-[#78909f]">Región</dt>
          <dd class="font-bold text-[#31536b]">
            {consoleContext.activeOrganization.region}
          </dd>
        </div>
        <div class="flex justify-between gap-3 border-b border-[#edf1f2] pb-3">
          <dt class="text-[#78909f]">Idioma</dt>
          <dd class="font-bold uppercase text-[#31536b]">
            {consoleContext.locale}
          </dd>
        </div>
        <div class="flex justify-between gap-3">
          <dt class="text-[#78909f]">Dirección</dt>
          <dd class="font-bold uppercase text-[#31536b]">
            {consoleContext.direction}
          </dd>
        </div>
      </dl>
    </Card>

    <Card variant="flat-large">
      <p class="top-badge">Módulos habilitados</p>
      <div class="mt-4 flex flex-wrap gap-2">
        {#each consoleContext.bootstrap.enabledModules as module}
          <span
            class="rounded-full bg-[#eef6f5] px-2.5 py-1 text-base font-bold text-[#47716f] capitalize"
            >{module}</span
          >
        {/each}
      </div>
      <p class="mt-5 text-lg leading-5 text-[#78909f]">
        Visibilidad mock para diseño. El backend deberá calcular módulos y
        permisos efectivos.
      </p>
    </Card>

    <Card variant="flat-large">
      <p class="top-badge">Servicios contratados</p>
      <div class="mt-4 space-y-3">
        {#each consoleContext.contractedServices as service}
          <div
            class="flex items-center justify-between gap-3 rounded-xl bg-[#f8fbfa] px-3 py-3"
          >
            <div>
              <p class="text-lg font-bold text-[#47657b]">{service.name}</p>
              <p class="mt-1 text-lg text-[#91a2ad]">
                {service.packageName}
              </p>
            </div>
            <StatusBadge status={service.health} />
          </div>
        {:else}
          <p class="rounded-xl bg-[#f8fbfa] p-4 text-lg text-[#78909f]">
            No hay servicios contratados en este workspace.
          </p>
        {/each}
      </div>
    </Card>

    <Card variant="flat-large">
      <p class="top-badge">Integraciones previstas</p>
      <div class="mt-4 space-y-3">
        {#each workspaceIntegrations as integration}
          <div class="rounded-xl bg-[#f8fbfa] px-3 py-3">
            <div class="flex items-center justify-between gap-3">
              <p class="text-xs font-bold text-[#47657b]">{integration.name}</p>
              <StatusBadge status={integration.status} />
            </div>
            <p class="mt-2 text-lg leading-5 text-[#91a2ad]">
              {integration.note}
            </p>
          </div>
        {:else}
          <p class="rounded-xl bg-[#f8fbfa] p-4 text-lg text-[#78909f]">
            Todavía no hay integraciones previstas para este workspace.
          </p>
        {/each}
      </div>
    </Card>
  </div>
</section>
