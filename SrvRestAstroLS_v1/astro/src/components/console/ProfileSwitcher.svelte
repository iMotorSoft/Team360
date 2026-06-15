<script lang="ts">
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import CustomSelect from "./CustomSelect.svelte";

  let { view }: { view: ConsoleView } = $props();

  const designProfiles = $derived(
    consoleContext.mockProfiles.filter(({ id }) =>
      [
        "team360_admin",
        "team360_operator",
        "partner_admin",
        "client_admin",
      ].includes(id),
    ),
  );

  const profileOptions = $derived(
    designProfiles.map((p) => ({ value: p.id, label: p.label })),
  );

  function changeProfile(profileId: string) {
    const selected = designProfiles.find(({ id }) => id === profileId);
    if (selected) {
      window.location.assign(
        buildConsoleRoute(selected.defaultWorkspaceId, view, selected.id),
      );
    }
  }
</script>

<div>
  <span class="mb-1.5 block top-badge-neutral">Perfil mock / diseño</span>
  <CustomSelect
    options={profileOptions}
    value={consoleContext.activeProfile}
    ariaLabel="Cambiar perfil mock de diseño"
    isUppercase="capitalize"
    textSize="1rem"
    onchange={changeProfile}
  />
</div>
