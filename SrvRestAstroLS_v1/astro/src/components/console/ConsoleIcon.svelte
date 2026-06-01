<script lang="ts">
  let {
    name,
    class: className = "size-5",
  }: {
    name: string;
    class?: string;
  } = $props();
</script>

<svg
  aria-hidden="true"
  class={className}
  fill="none"
  stroke="currentColor"
  stroke-linecap="round"
  stroke-linejoin="round"
  stroke-width="1.8"
  viewBox="0 0 24 24"
>
  {#if name === "home"}
    <path d="m4 11 8-7 8 7"></path><path d="M6 10v10h12V10"></path><path d="M10 20v-6h4v6"></path>
  {:else if name === "network"}
    <circle cx="12" cy="5" r="2.5"></circle><circle cx="6" cy="18" r="2.5"></circle><circle cx="18" cy="18" r="2.5"></circle><path d="m10.8 7.2-3.6 8.3M13.2 7.2l3.6 8.3M8.5 18h7"></path>
  {:else if name === "partner"}
    <path d="M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"></path><path d="M3 21v-2a6 6 0 0 1 12 0v2M16 8h5M18.5 5.5v5"></path>
  {:else if name === "clients" || name === "team"}
    <path d="M16 20a6 6 0 0 0-12 0"></path><circle cx="10" cy="8" r="4"></circle><path d="M20 20a5 5 0 0 0-4-4.58M16 4.58a4 4 0 0 1 0 6.84"></path>
  {:else if name === "workspace"}
    <rect height="16" rx="2" width="18" x="3" y="4"></rect><path d="M3 9h18M8 4v5"></path>
  {:else if name === "services"}
    <rect height="7" rx="2" width="7" x="3" y="3"></rect><rect height="7" rx="2" width="7" x="14" y="3"></rect><rect height="7" rx="2" width="7" x="3" y="14"></rect><rect height="7" rx="2" width="7" x="14" y="14"></rect>
  {:else if name === "automation"}
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"></path><circle cx="12" cy="12" r="4"></circle>
  {:else if name === "activity"}
    <path d="M3 12h4l3-7 4 14 3-7h4"></path>
  {:else if name === "chart"}
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2"></path>
  {:else if name === "report"}
    <path d="M6 3h9l3 3v15H6z"></path><path d="M14 3v4h4M9 12h6M9 16h6M9 8h1"></path>
  {:else if name === "alert"}
    <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"></path>
  {:else if name === "tasks"}
    <path d="M9 5h11M9 12h11M9 19h11M4 5h.01M4 12h.01M4 19h.01"></path>
  {:else if name === "support"}
    <circle cx="12" cy="12" r="9"></circle><path d="M9.5 9a2.5 2.5 0 1 1 4.2 1.8c-.9.8-1.7 1.1-1.7 2.7M12 17h.01"></path>
  {:else if name === "settings"}
    <circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.1h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H3v-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3h.1A1.7 1.7 0 0 0 10 3V3h4v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1A1.7 1.7 0 0 0 21 10h.1v4H21a1.7 1.7 0 0 0-1.6 1Z"></path>
  {:else if name === "menu"}
    <path d="M4 6h16M4 12h16M4 18h16"></path>
  {:else if name === "search"}
    <circle cx="11" cy="11" r="6"></circle><path d="m16 16 4 4"></path>
  {:else if name === "close"}
    <path d="M18 6 6 18M6 6l12 12"></path>
  {:else}
    <circle cx="12" cy="12" r="8"></circle><path d="M12 8v4l3 2"></path>
  {/if}
</svg>
