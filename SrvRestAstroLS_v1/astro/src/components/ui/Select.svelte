<script lang="ts">
  import type { Snippet } from "svelte";
  import type { HTMLSelectAttributes } from "svelte/elements";

  type Props = Omit<HTMLSelectAttributes, "children" | "size"> & {
    children?: Snippet;
    controlSize?: "sm" | "md";
  };

  let {
    children,
    controlSize = "md",
    class: className = "",
    onchange,
    ...rest
  }: Props = $props();

  const sizeClasses = {
    sm: "min-h-10 px-2.5 py-2 text-xs",
    md: "min-h-11 px-3 py-2.5 text-sm",
  } as const;
</script>

<select
  {...rest}
  class={`w-full rounded-xl border border-[#dbe5e7] bg-white font-semibold text-[#21415e] transition focus-visible:border-[#71cfc6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:bg-[#f1f5f5] disabled:text-[#91a2ad] ${sizeClasses[controlSize]} ${className}`}
  {onchange}
>
  {@render children?.()}
</select>
