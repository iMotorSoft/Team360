<script lang="ts">
  import { ROUTES } from "../global.js";
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";
  import CustomSelect from "./CustomSelect.svelte";

  let { view }: { view: ConsoleView } = $props();

  const selectWorkspaceHref = $derived(
    consoleContext.activeProfile === "team360_admin"
      ? ROUTES.selectWorkspace
      : `${ROUTES.selectWorkspace}?profile=${consoleContext.activeProfile}`,
  );

  const workspaceOptions = $derived(
    consoleContext.bootstrap.accessibleWorkspaces.map((w) => ({
      value: w.id,
      label: w.name,
    })),
  );

  function changeWorkspace(workspaceId: string) {
    window.location.assign(
      buildConsoleRoute(workspaceId, view, consoleContext.activeProfile),
    );
  }
</script>

<div>
  <span class="mb-1.5 block top-badge-neutral">Workspace activo</span>
  <CustomSelect
    options={workspaceOptions}
    value={consoleContext.activeWorkspace.id}
    ariaLabel="Cambiar workspace activo"
    isUppercase="capitalize"
    textSize="1rem"
    onchange={changeWorkspace}
  />

  <a
    class="mt-5 flex min-h-10 w-full items-center justify-center gap-4 rounded-xl
    border border-[#bcdedb] bg-[#eef9f7] px-3 py-2 text-lg font-semibold text-[#147d79]
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
