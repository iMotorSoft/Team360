<script lang="ts">
  /**
   * CustomSelect — Dropdown estilizado reutilizable.
   *
   * Props:
   *   options      — array de { value, label }
   *   value        — valor actualmente seleccionado
   *   ariaLabel    — texto accesible del control
   *   centered     — centra el dropdown y aplica estilo uppercase (locale picker)
   *   onchange     — callback (value: string) => void
   */

  type Option = { value: string; label: string };

  let {
    options,
    value,
    ariaLabel = "Seleccionar opción",
    centered = false,
    isUppercase = "uppercase",
    textSize = "0.9rem",
    onchange,
  }: {
    options: Option[];
    value: string;
    ariaLabel?: string;
    centered?: boolean;
    isUppercase?: "uppercase" | "capitalize";
    textSize?: string;
    onchange: (value: string) => void;
  } = $props();

  let open = $state(false);

  const selected = $derived(options.find((o) => o.value === value));

  function select(opt: Option) {
    onchange(opt.value);
    open = false;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") open = false;
  }

  function closeOnOutside(node: HTMLElement) {
    function handler(e: MouseEvent) {
      if (!node.contains(e.target as Node)) open = false;
    }
    document.addEventListener("mousedown", handler);
    return {
      destroy() {
        document.removeEventListener("mousedown", handler);
      },
    };
  }
</script>

<div
  class="custom-select-wrap"
  use:closeOnOutside
  onkeydown={handleKeydown}
  role="none"
>
  <button
    type="button"
    class="custom-select-trigger"
    class:compact={centered}
    class:open
    style:text-transform={isUppercase}
    style:font-size={textSize}
    aria-haspopup="listbox"
    aria-expanded={open}
    aria-label={ariaLabel}
    onclick={() => (open = !open)}
  >
    <span class="custom-select-label">{selected?.label ?? value}</span>
    <svg
      class="custom-select-chevron"
      class:rotated={open}
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  </button>

  {#if open}
    <ul
      class="custom-select-dropdown"
      class:centered
      role="listbox"
      aria-label={ariaLabel}
    >
      {#each options as opt}
        <li role="none">
          <button
            type="button"
            role="option"
            aria-selected={value === opt.value}
            class="custom-select-option"
            class:active={value === opt.value}
            onclick={() => select(opt)}
          >
            {opt.label}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
