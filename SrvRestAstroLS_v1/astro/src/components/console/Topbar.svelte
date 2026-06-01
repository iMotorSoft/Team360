<script lang="ts">
  import { SUPPORTED_LOCALES } from "../../lib/i18n";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";
  import NotificationCenter from "./NotificationCenter.svelte";

  let { onMenu = () => undefined }: { onMenu?: () => void } = $props();
</script>

<header class="sticky top-0 z-30 flex h-[4.75rem] items-center justify-between gap-4 border-b border-[#e1e9eb] bg-[#fbfcfa]/88 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
  <div class="flex min-w-0 items-center gap-3">
    <button
      aria-label="Abrir navegación"
      class="grid size-10 shrink-0 place-items-center rounded-xl border border-[#e0e8eb] bg-white text-[#526d81] lg:hidden"
      onclick={onMenu}
      type="button"
    >
      <ConsoleIcon name="menu" />
    </button>
    <div class="min-w-0">
      <p class="truncate text-xs font-bold uppercase tracking-[0.17em] text-[#168b88]">{consoleContext.bootstrap.uiHints.profileLabel}</p>
      <p class="mt-1 truncate text-sm font-semibold text-[#284c67]">
        {consoleContext.activeOrganization.name}
        <span class="mx-1.5 text-[#a5b3bb]">/</span>
        {consoleContext.activeWorkspace.name}
      </p>
    </div>
  </div>

  <div class="flex items-center gap-2 sm:gap-3">
    <label class="hidden sm:block">
      <span class="sr-only">Idioma de interfaz</span>
      <select
        aria-label="Idioma de interfaz"
        class="rounded-xl border border-[#e0e8eb] bg-white px-2.5 py-2 text-xs font-bold uppercase text-[#587184] transition focus-visible:border-[#71cfc6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
        onchange={(event) => consoleContext.setLocale((event.currentTarget as HTMLSelectElement).value)}
        value={consoleContext.locale}
      >
        {#each SUPPORTED_LOCALES as locale}
          <option value={locale}>{locale}</option>
        {/each}
      </select>
    </label>
    <button
      aria-label="Buscar"
      class="hidden size-10 place-items-center rounded-xl border border-[#e0e8eb] bg-white text-[#526d81] transition hover:border-[#badbd9] hover:text-[#167f7c] sm:grid"
      type="button"
    >
      <ConsoleIcon name="search" />
    </button>
    <NotificationCenter />
    <div class="ms-1 hidden items-center gap-2 border-s border-[#e0e8eb] ps-3 sm:flex">
      <span class="grid size-9 place-items-center rounded-xl bg-[#153b5b] text-xs font-bold text-white">
        {consoleContext.bootstrap.currentUser.avatarInitials}
      </span>
      <div class="hidden xl:block">
        <p class="text-xs font-bold text-[#31536b]">{consoleContext.bootstrap.currentUser.name}</p>
        <p class="mt-0.5 text-[0.68rem] text-[#8a9ba6]">{consoleContext.bootstrap.currentUser.role}</p>
      </div>
    </div>
  </div>
</header>
