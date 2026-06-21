<script lang="ts">
  import { t } from "../../lib/i18n";
  import { getViewLabelKey } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";

  let { view }: { view: ConsoleView } = $props();
</script>

<nav
  aria-label="Breadcrumbs"
  class="flex flex-wrap items-center gap-2 text-sm font-semibold text-[#8396a2]"
>
  <span>{consoleContext.activeOrganization.name}</span>
  <span class="text-[#c4ced3]">/</span>
  <span>{consoleContext.activeWorkspace.name}</span>
  <span class="text-[#c4ced3]">/</span>
  <span class="text-[#47657b]"
    >{t(getViewLabelKey(view), consoleContext.locale)}</span
  >
</nav>
