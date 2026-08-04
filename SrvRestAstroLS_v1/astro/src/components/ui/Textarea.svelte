<script lang="ts">
  import type { HTMLTextareaAttributes } from "svelte/elements";

  type Props = Omit<HTMLTextareaAttributes, "value"> & {
    value?: string;
  };

  let {
    value = $bindable(""),
    class: className = "",
    ...rest
  }: Props = $props();
</script>

<textarea
  {...rest}
  bind:value
  class={`w-full rounded-xl border border-[#d5e0e2] bg-white px-4 py-3 text-sm leading-6 text-[#203c55] outline-none transition placeholder:text-[#91a2ad] focus-visible:border-[#168b88] focus-visible:ring-2 focus-visible:ring-[#168b88]/20 disabled:cursor-not-allowed disabled:bg-[#f1f5f5] disabled:text-[#91a2ad] aria-invalid:border-[#b54a3d] aria-invalid:ring-[#b54a3d]/15 ${className}`}
></textarea>
