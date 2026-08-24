<script lang="ts">
  let {
    approvalLevel,
    destination,
    levels = [],
    editing = false,
    disabled = false,
    error = null,
    touched = false,
    onDestinationInput = () => undefined,
    onDestinationBlur = () => undefined,
    onApprovalLevelChange = () => undefined,
  }: {
    approvalLevel: number | null;
    destination: string;
    levels?: { level: number; label: string }[];
    editing?: boolean;
    disabled?: boolean;
    error?: string | null;
    touched?: boolean;
    onDestinationInput?: (value: string) => void;
    onDestinationBlur?: () => void;
    onApprovalLevelChange?: (level: number) => void;
  } = $props();

  const requiresApproval = $derived(approvalLevel !== null);
</script>

<section class="rounded-2xl border border-[#c5e5dc] bg-[#f4fbf8] p-4 sm:p-5" aria-labelledby="flow-closure-title">
  <div class="flex items-start gap-3">
    <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[#dff3e9] text-lg text-[#17663d]" aria-hidden="true">✓</span>
    <div class="min-w-0 flex-1">
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#238454]">Autorización de cierre</p>
      <h2 id="flow-closure-title" class="mt-1 text-xl font-bold tracking-[-0.025em] text-[#173b5b]">Supervisor de cierre</h2>
      <p class="mt-1 max-w-2xl text-sm leading-5 text-[#587184]">
        {#if requiresApproval}
          Autoriza la resolución final del caso. Es una autoridad de cierre, no un nivel adicional de escalamiento.
        {:else}
          Este sector opera con sus niveles configurados y no requiere aprobación de cierre.
        {/if}
      </p>

      {#if requiresApproval && editing}
        <fieldset class="mt-4" disabled={disabled}>
          <legend class="mb-2 block text-xs font-bold uppercase tracking-[0.1em] text-[#587184]">
            Nivel que aprueba el cierre
          </legend>
          <div class="flex flex-wrap gap-2">
            {#each levels as level (level.level)}
              {@const selected = approvalLevel === level.level}
              <button
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={`Nivel ${level.level} aprueba el cierre`}
                onclick={() => onApprovalLevelChange(level.level)}
                class={`inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#238454] ${
                  selected
                    ? "border-[#238454] bg-[#dff3e9] text-[#17663d]"
                    : "border-[#b9dfd0] bg-white text-[#47657b] hover:bg-[#eef9f4]"
                }`}
              >
                <span
                  class={`grid size-4 shrink-0 place-items-center rounded-full border-2 ${selected ? "border-[#238454]" : "border-[#9bcac6]"}`}
                  aria-hidden="true"
                >
                  {#if selected}
                    <span class="size-2 rounded-full bg-[#238454]"></span>
                  {/if}
                </span>
                {level.label}
              </button>
            {/each}
          </div>
        </fieldset>

        <label class="mt-4 block" for="flow-closure-supervisor">
          <span class="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-[#587184]">Email del supervisor</span>
          <input
            id="flow-closure-supervisor"
            name="closure-supervisor"
            type="email"
            value={destination}
            disabled={disabled}
            aria-invalid={Boolean(error && touched)}
            aria-describedby={error && touched ? "flow-closure-error" : undefined}
            oninput={(event) => onDestinationInput(event.currentTarget.value)}
            onblur={onDestinationBlur}
            class="w-full min-w-0 rounded-xl border border-[#b9dfd0] bg-white px-3.5 py-3 text-sm text-[#31536b] outline-none transition placeholder:text-[#91a2ad] disabled:opacity-60 focus-visible:border-[#238454] focus-visible:ring-2 focus-visible:ring-[#238454]/20 aria-[invalid=true]:border-[#b54a3d] aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-[#b54a3d]/15"
          />
          {#if error && touched}
            <span id="flow-closure-error" class="mt-1.5 block text-xs font-semibold text-[#9b3328]">{error}</span>
          {/if}
          <span class="mt-1.5 block text-[0.62rem] leading-4 text-[#78909f]">
            El supervisor usa el destino del nivel elegido. Si cambiás el email del nivel, el supervisor lo toma automáticamente.
          </span>
        </label>
      {:else if requiresApproval}
        <div class="mt-4 flex min-w-0 flex-wrap items-center gap-2">
          <span class="min-w-0 max-w-full truncate rounded-xl border border-[#b9dfd0] bg-white px-3.5 py-3 font-mono text-sm text-[#17663d]" title={destination}>{destination || "Sin destinatario definido"}</span>
          {#if approvalLevel}
            <span class="rounded-full border border-[#b9dfd0] bg-[#e5f7ee] px-2.5 py-1 text-xs font-bold text-[#238454]">Autoridad N{approvalLevel}</span>
          {/if}
        </div>
      {:else}
        <div class="mt-4 rounded-xl border border-[#b9dfd0] bg-white px-3.5 py-3 text-sm font-semibold text-[#17663d]" role="status">
          Sin aprobación de cierre configurada para este sector.
        </div>
      {/if}
    </div>
  </div>
</section>
