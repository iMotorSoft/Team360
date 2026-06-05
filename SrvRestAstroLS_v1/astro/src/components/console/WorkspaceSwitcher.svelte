<script lang="ts">
  import { ROUTES } from "../global.js";
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";

  let { view }: { view: ConsoleView } = $props();
  const selectWorkspaceHref = $derived(
    consoleContext.activeProfile === "team360_admin"
      ? ROUTES.selectWorkspace
      : `${ROUTES.selectWorkspace}?profile=${consoleContext.activeProfile}`,
  );

  function changeWorkspace(event: Event) {
    const workspaceId = (event.currentTarget as HTMLSelectElement).value;
    window.location.assign(
      buildConsoleRoute(workspaceId, view, consoleContext.activeProfile),
    );
  }
</script>

<div>
  <label class="block">
    <span
      class="mb-1.5 block text-xs font-bold uppercase tracking-[0.18em] text-[#78909f]"
      >Workspace activo</span
    >
    <select
      aria-label="Cambiar workspace activo"
      class="w-full rounded-xl border border-[#dbe5e7] bg-white px-3 py-2 text-sm font-semibold text-[#21415e] transition focus-visible:border-[#71cfc6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
      onchange={changeWorkspace}
      value={consoleContext.activeWorkspace.id}
    >
      {#each consoleContext.bootstrap.accessibleWorkspaces as workspace}
        <option value={workspace.id}>{workspace.name}</option>
      {/each}
    </select>
  </label>
  <a
    class="mt-5 flex min-h-10 w-full items-center justify-center gap-2 rounded-xl
    border border-[#bcdedb] bg-[#eef9f7] px-3 py-2 text-sm font-bold text-[#147d79]
    shadow-[0_8px_18px_-16px_rgba(16,45,79,0.85)] transition hover:border-[#8fcfc9]
    hover:bg-[#E9F5F3] focus-visible:outline-2
    focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
    data-design-action="change-workspace"
    href={selectWorkspaceHref}
  >
    <ConsoleIcon class="size-5" name="workspace" />
    Cambiar workspace
  </a>
</div>
