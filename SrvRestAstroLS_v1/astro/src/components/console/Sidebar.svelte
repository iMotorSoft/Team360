<script lang="ts">
  import { APP_PUBLIC_NAME, BRAND } from "../global.js";
  import { t } from "../../lib/i18n";
  import type { DerivedNavigationGroup } from "../../lib/navigation/derive";
  import { navigationGroupLabelKeys, type ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import ConsoleIcon from "./ConsoleIcon.svelte";
  import ProfileSwitcher from "./ProfileSwitcher.svelte";
  import WorkspaceSwitcher from "./WorkspaceSwitcher.svelte";

  let {
    groups,
    view,
    mobileOpen = false,
    onClose = () => undefined,
  }: {
    groups: DerivedNavigationGroup[];
    view: ConsoleView;
    mobileOpen?: boolean;
    onClose?: () => void;
  } = $props();
</script>

{#if mobileOpen}
  <button
    aria-label="Cerrar navegación"
    class="fixed inset-0 z-40 bg-[#0d2947]/35 backdrop-blur-sm lg:hidden"
    onclick={onClose}
    type="button"
  ></button>
{/if}

<aside
  aria-label="Navegación contextual"
  class={`console-drawer fixed inset-y-0 start-0 z-50 flex w-[18.5rem] flex-col border-e border-[#dce6e8] bg-[#f8fbfa] transition-transform duration-300 lg:translate-x-0 ${
    mobileOpen ? "translate-x-0" : consoleContext.direction === "rtl" ? "translate-x-full" : "-translate-x-full"
  }`}
>
  <div class="flex h-[4.75rem] items-center justify-between border-b border-[#e2eaec] px-5">
    <a class="flex items-center gap-3" href="/" translate="no">
      <span class="relative grid size-10 place-items-center overflow-hidden rounded-2xl bg-[#102d4f] shadow-sm" aria-hidden="true">
        <span class="absolute inset-[7px] rounded-full border border-[#6ed7cb]/80"></span>
        <span class="absolute left-[12px] top-[12px] size-2 rounded-full bg-[#6ed7cb]"></span>
        <span class="absolute bottom-[10px] right-[10px] size-2.5 rounded-full bg-white"></span>
        <span class="absolute h-px w-4 rotate-45 bg-white/70"></span>
      </span>
      <span>
        <span class="block text-lg font-bold tracking-[-0.05em] text-[#102d4f]">{APP_PUBLIC_NAME}</span>
        <span class="block text-[0.61rem] font-bold uppercase tracking-[0.2em] text-[#168b88]">{BRAND.tagline}</span>
      </span>
    </a>
    <button
      aria-label="Cerrar navegación"
      class="grid size-9 place-items-center rounded-xl text-[#668092] transition hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] lg:hidden"
      onclick={onClose}
      type="button"
    >
      <ConsoleIcon name="close" />
    </button>
  </div>

  <div class="space-y-3 border-b border-[#e2eaec] px-4 py-4">
    <ProfileSwitcher {view} />
    <WorkspaceSwitcher {view} />
  </div>

  <nav class="flex-1 space-y-5 overflow-y-auto px-3 py-5" aria-label="Navegación de consola">
    {#each groups as group}
      <div>
        <p class="px-3 text-[0.62rem] font-bold uppercase tracking-[0.2em] text-[#91a2ad]">
          {t(navigationGroupLabelKeys[group.id], consoleContext.locale)}
        </p>
        <ul class="mt-2 space-y-1">
          {#each group.items as item}
            <li>
              <a
                class={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${
                  item.view === view ? "bg-[#e4f5f3] text-[#147d79]" : "text-[#587184] hover:bg-white hover:text-[#214762]"
                }`}
                href={item.href}
                onclick={onClose}
              >
                <ConsoleIcon class="size-[1.05rem]" name={item.icon} />
                <span>{t(item.labelKey, consoleContext.locale)}</span>
                {#if item.view === "alerts" && consoleContext.notificationSummary.activeWorkspaceAlerts}
                  <span class="ms-auto grid min-w-5 place-items-center rounded-full bg-[#e86852] px-1.5 py-0.5 text-[0.62rem] font-bold text-white">
                    {consoleContext.notificationSummary.activeWorkspaceAlerts}
                  </span>
                {/if}
              </a>
            </li>
          {/each}
        </ul>
      </div>
    {/each}
  </nav>

  <div class="border-t border-[#e2eaec] p-4">
    <div class="rounded-2xl border border-[#d8e7e7] bg-white p-3">
      <p class="text-[0.62rem] font-bold uppercase tracking-[0.17em] text-[#168b88]">Modo diseño</p>
      <p class="mt-1.5 text-xs leading-5 text-[#6d8391]">Datos simulados. Sin autenticación ni operaciones reales.</p>
    </div>
  </div>
</aside>
