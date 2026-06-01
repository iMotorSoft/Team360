<script lang="ts">
  import { Badge } from "../ui";
  import { deriveConsoleAudience } from "../../lib/navigation/derive";
  import { consoleContext } from "../../stores/consoleContext.svelte";

  const audience = $derived(deriveConsoleAudience(consoleContext.bootstrap));
</script>

<section
  class={`flex flex-col gap-3 rounded-2xl border px-4 py-3 sm:flex-row sm:items-center sm:justify-between ${
    consoleContext.bootstrap.uiHints.showDelegatedAccessNotice ? "border-[#f0d8a5] bg-[#fff9ec]" : "border-[#dce8e8] bg-white/76"
  }`}
>
  <div>
    <div class="flex flex-wrap items-center gap-2">
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#5c7788]">Contexto operativo</p>
      {#if consoleContext.bootstrap.uiHints.showDelegatedAccessNotice}
        <Badge variant="warning" class="h-auto px-2 py-1 text-[0.62rem]">Acceso delegado</Badge>
      {:else}
        <Badge variant="info" class="h-auto px-2 py-1 text-[0.62rem]">Contexto propio</Badge>
      {/if}
    </div>
    <p class="mt-1.5 text-sm font-semibold text-[#254b66]">
      {consoleContext.activeOrganization.name}
      <span class="mx-1.5 text-[#a1b0b8]">·</span>
      {consoleContext.activeWorkspace.name}
    </p>
  </div>
  <p class="max-w-xl text-xs leading-5 text-[#718793]">
    {#if consoleContext.bootstrap.uiHints.showDelegatedAccessNotice}
      Estás consultando una organización autorizada desde {audience === "owner" || audience === "operator" ? "Team360" : "tu red partner"}.
    {:else}
      La información visible corresponde al workspace seleccionado y a sus servicios habilitados.
    {/if}
  </p>
</section>
