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
          : (currentIndex +
              (event.key === "ArrowRight" ? 1 : -1) +
              tabs.length) %
            tabs.length;
    const nextTab = tabs[nextIndex];

    onChange(nextTab.id);
    (event.currentTarget as HTMLElement).parentElement
      ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
      [nextIndex]?.focus();
  }

  const pastelColors = [
    {
      inactive: "bg-green-50/70 text-[#147d79]/70 border-transparent",
      active: "bg-green-100 text-[#147d79] border-green-200",
      hover: "hover:bg-green-100 hover:text-[#147d79]",
    },
    {
      inactive: "bg-pink-50/70 text-[#9d2460]/70 border-transparent",
      active: "bg-pink-100 text-[#9d2460] border-pink-200",
      hover: "hover:bg-pink-100 hover:text-[#9d2460]",
    },
    {
      inactive: "bg-blue-50/70 text-[#1a5ba8]/70 border-transparent",
      active: "bg-blue-100 text-[#1a5ba8] border-blue-200",
      hover: "hover:bg-blue-100 hover:text-[#1a5ba8]",
    },
    {
      inactive: "bg-orange-50/70 text-[#b36b00]/70 border-transparent",
      active: "bg-orange-100 text-[#b36b00] border-orange-200",
      hover: "hover:bg-orange-100 hover:text-[#b36b00]",
    },
    {
      inactive: "bg-purple-50/70 text-[#5527a0]/70 border-transparent",
      active: "bg-purple-100 text-[#5527a0] border-purple-200",
      hover: "hover:bg-purple-100 hover:text-[#5527a0]",
    },
    {
      inactive: "bg-teal-50/70 text-[#0f5e5b]/70 border-transparent",
      active: "bg-teal-100 text-[#0f5e5b] border-teal-200",
      hover: "hover:bg-teal-100 hover:text-[#0f5e5b]",
    },
    {
      inactive: "bg-red-50/70 text-[#9b1f1f]/70 border-transparent",
      active: "bg-red-100 text-[#9b1f1f] border-red-200",
      hover: "hover:bg-red-100 hover:text-[#9b1f1f]",
    },
  ];

  function getTabColors(index: number, isActive: boolean) {
    const color = pastelColors[index % pastelColors.length];
    return isActive ? color.active : `${color.inactive} ${color.hover}`;
  }
</script>

<div class="overflow-x-auto">
  <div
    class="flex min-w-max gap-2 rounded-2xl border border-[#e0e8ea] bg-white p-3"
    role="tablist"
    aria-label={label}
  >
    {#each tabs as tab, i}
      <button
        aria-selected={activeTab === tab.id}
        class={`rounded-xl px-3 py-2 text-lg font-semibold border transition 
        focus-visible:outline-2 focus-visible:outline-offset-2 
        focus-visible:outline-[#168b88] cursor-pointer ${getTabColors(i, activeTab === tab.id)}`}
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
