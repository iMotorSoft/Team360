<script lang="ts">
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import { Select } from "../ui";

  let { view }: { view: ConsoleView } = $props();

  function changeWorkspace(event: Event) {
    const workspaceId = (event.currentTarget as HTMLSelectElement).value;
    window.location.assign(buildConsoleRoute(workspaceId, view, consoleContext.activeProfile));
  }
</script>

<label class="block">
  <span class="mb-1.5 block text-[0.63rem] font-bold uppercase tracking-[0.18em] text-[#78909f]">Workspace activo</span>
  <Select
    aria-label="Cambiar workspace activo"
    controlSize="sm"
    onchange={changeWorkspace}
    value={consoleContext.activeWorkspace.id}
  >
    {#each consoleContext.bootstrap.accessibleWorkspaces as workspace}
      <option value={workspace.id}>{workspace.name}</option>
    {/each}
  </Select>
</label>
