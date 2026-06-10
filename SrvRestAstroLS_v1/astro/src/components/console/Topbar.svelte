<script lang="ts">
  import { SUPPORTED_LOCALES } from "../../lib/i18n";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";
  import NotificationCenter from "./NotificationCenter.svelte";
  import CustomSelect from "./CustomSelect.svelte";

  let { onMenu = () => undefined }: { onMenu?: () => void } = $props();

  const localeOptions = $derived(
    SUPPORTED_LOCALES.map((l) => ({ value: l, label: l })),
  );
</script>

<header
  class="sticky top-0 z-30 flex h-24 items-center justify-between gap-4 border-b border-[#e1e9eb] bg-[#fbfcfa]/88 px-4 backdrop-blur-xl sm:px-6 lg:px-8"
>
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
      <p
        class="truncate text-some font-bold uppercase tracking-[0.17em] text-[#168b88]"
      >
        {consoleContext.bootstrap.uiHints.profileLabel}
      </p>
      <div class="details-text flex items-center gap-3 mt-1 truncate">
        {consoleContext.activeOrganization.name}
        <div class="w-1.5 h-1.5 rounded-full bg-slate-400 pulse"></div>
        {consoleContext.activeWorkspace.name}
      </div>
    </div>
  </div>

  <div class="flex items-center gap-2 sm:gap-3">
    <!-- Locale picker -->
    <div class="hidden sm:block">
      <CustomSelect
        options={localeOptions}
        value={consoleContext.locale}
        ariaLabel="Idioma de interfaz"
        centered={true}
        onchange={(v) => consoleContext.setLocale(v)}
      />
    </div>

    <button
      aria-label="Buscar"
      class="text-[#526d81] cursor-pointer size-11 grid place-items-center rounded-full
      transition hover:bg-slate-100"
      type="button"
    >
      <ConsoleIcon name="search" class="size-7.5" />
    </button>
    <NotificationCenter />
    <div
      class="ms-1 hidden items-center gap-2 border-s border-[#e0e8eb] ps-3 sm:flex"
    >
      <span
        class="grid size-12 mx-2 items-center rounded-full text-center
        tracking-[0.1em] bg-base-content/80 text-base font-bold text-white"
      >
        {consoleContext.bootstrap.currentUser.avatarInitials}
      </span>
      <div class="hidden xl:block">
        <p class="text-base font-bold text-[#31536b]">
          {consoleContext.bootstrap.currentUser.name}
        </p>
        <p class="mt-0.5 text-sm text-[#8a9ba6]">
          {consoleContext.bootstrap.currentUser.role}
        </p>
      </div>
    </div>
  </div>
</header>
