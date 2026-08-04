<script lang="ts">
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import { Select } from "../ui";

  let { view }: { view: ConsoleView } = $props();

  const designProfiles = $derived(
    consoleContext.mockProfiles.filter(({ id }) => ["team360_admin", "team360_operator", "partner_admin", "client_admin"].includes(id)),
  );

  function changeProfile(event: Event) {
    const profile = (event.currentTarget as HTMLSelectElement).value as "team360_admin" | "team360_operator" | "partner_admin" | "client_admin";
    const selected = designProfiles.find(({ id }) => id === profile);

    if (selected) {
      window.location.assign(buildConsoleRoute(selected.defaultWorkspaceId, view, selected.id));
    }
  }
</script>

<label class="block">
  <span class="mb-1.5 block text-[0.63rem] font-bold uppercase tracking-[0.18em] text-[#78909f]">Perfil mock / diseño</span>
  <Select
    aria-label="Cambiar perfil mock de diseño"
    controlSize="sm"
    onchange={changeProfile}
    value={consoleContext.activeProfile}
  >
    {#each designProfiles as profile}
      <option value={profile.id}>{profile.label}</option>
    {/each}
  </Select>
</label>
