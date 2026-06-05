<script lang="ts">
  import { buildConsoleRoute } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";

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

  function changeProfile(event: Event) {
    const profile = (event.currentTarget as HTMLSelectElement).value as
      | "team360_admin"
      | "team360_operator"
      | "partner_admin"
      | "client_admin";
    const selected = designProfiles.find(({ id }) => id === profile);

    if (selected) {
      window.location.assign(
        buildConsoleRoute(selected.defaultWorkspaceId, view, selected.id),
      );
    }
  }
</script>

<label class="block">
  <span
    class="mb-1.5 block text-xs font-bold uppercase tracking-[0.18em] text-[#78909f]"
    >Perfil mock / diseño</span
  >
  <select
    aria-label="Cambiar perfil mock de diseño"
    class="w-full rounded-xl border border-[#dbe5e7] bg-white px-3 py-2 text-sm font-semibold text-[#21415e] transition focus-visible:border-[#71cfc6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
    onchange={changeProfile}
    value={consoleContext.activeProfile}
  >
    {#each designProfiles as profile}
      <option value={profile.id}>{profile.label}</option>
    {/each}
  </select>
</label>
