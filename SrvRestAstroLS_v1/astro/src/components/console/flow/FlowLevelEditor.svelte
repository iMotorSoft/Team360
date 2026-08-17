<script lang="ts">
  import { flowChannelLabel, type FlowConfigurationLevel } from "../../../lib/t360/flow/configuration";

  let {
    levels,
    editing = false,
    errors = {},
    touched = {},
    onDestinationInput = () => undefined,
    onDestinationBlur = () => undefined,
  }: {
    levels: FlowConfigurationLevel[];
    editing?: boolean;
    errors?: Record<string, string | null>;
    touched?: Record<string, boolean>;
    onDestinationInput?: (levelId: string, value: string) => void;
    onDestinationBlur?: (levelId: string) => void;
  } = $props();
</script>

<section aria-labelledby="flow-circuit-title">
  <div class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Circuito operativo</p>
      <h2 id="flow-circuit-title" class="mt-1 text-xl font-bold tracking-[-0.025em] text-[#173b5b]">Niveles de atención</h2>
      <p class="mt-1 text-sm leading-5 text-[#78909f]">Cada nivel recibe el caso en el orden definido por el circuito.</p>
    </div>
    <span class="rounded-full border border-[#dce6e8] bg-white px-3 py-1.5 text-xs font-bold text-[#587184]">
      {levels.length} {levels.length === 1 ? "nivel" : "niveles"}
    </span>
  </div>

  {#if levels.length === 0}
    <div class="mt-5 rounded-2xl border border-dashed border-[#d7e3e5] bg-[#f8fbfa] p-6">
      <p class="text-sm font-bold text-[#31536b]">Este sector todavía no tiene niveles</p>
      <p class="mt-1 text-xs leading-5 text-[#78909f]">La creación de niveles quedará disponible cuando exista la política de configuración del backend.</p>
    </div>
  {:else}
    <div class="mt-5 space-y-0">
      {#each levels as level, index (level.id)}
        <article class="relative rounded-2xl border border-card-border bg-white p-4 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)] sm:p-5">
          <div class="flex items-start gap-3">
            <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[#e4f5f3] text-sm font-bold text-[#126d6b]">N{level.level}</span>
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="text-base font-bold text-[#173b5b]">{level.label}</h3>
                <span class="rounded-full bg-[#f1f5f5] px-2 py-1 text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[#78909f]">{level.role}</span>
              </div>
              <p class="mt-1 text-xs text-[#78909f]">Canal de atención · {flowChannelLabel(level.channel)}</p>

              {#if editing}
                {@const error = errors[level.id]}
                <label class="mt-4 block" for={`flow-destination-${level.id}`}>
                  <span class="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-[#587184]">Destinatario</span>
                  <input
                    id={`flow-destination-${level.id}`}
                    name={`destination-${level.id}`}
                    type="email"
                    value={level.destination}
                    aria-invalid={Boolean(error && touched[level.id])}
                    aria-describedby={error && touched[level.id] ? `flow-error-${level.id}` : undefined}
                    oninput={(event) => onDestinationInput(level.id, event.currentTarget.value)}
                    onblur={() => onDestinationBlur(level.id)}
                    class="w-full min-w-0 rounded-xl border border-[#d5e0e2] bg-white px-3.5 py-3 text-sm text-[#31536b] outline-none transition placeholder:text-[#91a2ad] focus-visible:border-[#168b88] focus-visible:ring-2 focus-visible:ring-[#168b88]/20 aria-[invalid=true]:border-[#b54a3d] aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-[#b54a3d]/15"
                  />
                  {#if error && touched[level.id]}
                    <span id={`flow-error-${level.id}`} class="mt-1.5 block text-xs font-semibold text-[#9b3328]">{error}</span>
                  {/if}
                </label>
              {:else}
                <div class="mt-4 flex min-w-0 items-center gap-2 rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] px-3.5 py-3">
                  <span class="min-w-0 flex-1 truncate font-mono text-sm text-[#31536b]" title={level.destination}>{level.destination}</span>
                  <span class="shrink-0 text-xs text-[#91a2ad]" aria-hidden="true">✉</span>
                </div>
              {/if}
            </div>
          </div>
        </article>
        {#if index < levels.length - 1}
          <div class="flex h-8 items-center justify-center" aria-hidden="true">
            <span class="h-full border-s border-dashed border-[#9bcac6]"></span>
            <span class="absolute ms-2 mt-7 text-[#168b88]">⌄</span>
          </div>
        {/if}
      {/each}
    </div>
  {/if}
</section>
