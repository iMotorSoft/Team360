<script lang="ts">
  export interface TabItem {
    id: string;
    label: string;
  }

  let {
    tabs,
    activeTab,
    onChange,
    label = "Secciones del servicio",
  }: {
    tabs: TabItem[];
    activeTab: string;
    onChange: (tabId: string) => void;
    label?: string;
  } = $props();

  function handleKeydown(event: KeyboardEvent, tabId: string) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;

    event.preventDefault();
    const currentIndex = tabs.findIndex(({ id }) => id === tabId);
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    const nextTab = tabs[nextIndex];

    onChange(nextTab.id);
    (event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]?.focus();
  }
</script>

<div class="overflow-x-auto">
  <div class="flex min-w-max gap-1 rounded-2xl border border-[#e0e8ea] bg-white p-1.5" role="tablist" aria-label={label}>
    {#each tabs as tab}
      <button
        aria-selected={activeTab === tab.id}
        class={`rounded-xl px-3 py-2 text-xs font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${
          activeTab === tab.id ? "bg-[#e4f5f3] text-[#147d79]" : "text-[#668092] hover:bg-[#f4f8f8] hover:text-[#31536b]"
        }`}
        onclick={() => onChange(tab.id)}
        onkeydown={(event) => handleKeydown(event, tab.id)}
        role="tab"
        tabindex={activeTab === tab.id ? 0 : -1}
        type="button"
      >
        {tab.label}
      </button>
    {/each}
  </div>
</div>
