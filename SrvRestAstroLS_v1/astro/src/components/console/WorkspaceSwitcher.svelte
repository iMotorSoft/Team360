<script lang="ts">
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";

  let { view }: { view: ConsoleView } = $props();

  function changeWorkspace(event: Event) {
    const workspaceId = (event.currentTarget as HTMLSelectElement).value;
    window.location.assign(buildConsoleRoute(workspaceId, view, consoleContext.activeProfile));
  }
</script>

<label class="block">
  <span class="mb-1.5 block text-[0.63rem] font-bold uppercase tracking-[0.18em] text-[#78909f]">Workspace activo</span>
  <select
    aria-label="Cambiar workspace activo"
    class="w-full rounded-xl border border-[#dbe5e7] bg-white px-3 py-2 text-xs font-semibold text-[#21415e] transition focus-visible:border-[#71cfc6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
    onchange={changeWorkspace}
    value={consoleContext.activeWorkspace.id}
  >
    {#each consoleContext.bootstrap.accessibleWorkspaces as workspace}
      <option value={workspace.id}>{workspace.name}</option>
    {/each}
  </select>
</label>
