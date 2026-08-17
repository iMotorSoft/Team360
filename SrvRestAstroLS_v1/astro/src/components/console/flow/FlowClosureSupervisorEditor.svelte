<script lang="ts">
  let {
    approvalLevel,
    destination,
    editing = false,
    error = null,
    touched = false,
    onDestinationInput = () => undefined,
    onDestinationBlur = () => undefined,
  }: {
    approvalLevel: number | null;
    destination: string;
    editing?: boolean;
    error?: string | null;
    touched?: boolean;
    onDestinationInput?: (value: string) => void;
    onDestinationBlur?: () => void;
  } = $props();
</script>

<section class="rounded-2xl border border-[#c5e5dc] bg-[#f4fbf8] p-4 sm:p-5" aria-labelledby="flow-closure-title">
  <div class="flex items-start gap-3">
    <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-[#dff3e9] text-lg text-[#17663d]" aria-hidden="true">✓</span>
    <div class="min-w-0 flex-1">
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#238454]">Autorización de cierre</p>
      <h2 id="flow-closure-title" class="mt-1 text-xl font-bold tracking-[-0.025em] text-[#173b5b]">Supervisor de cierre</h2>
      <p class="mt-1 max-w-2xl text-sm leading-5 text-[#587184]">
        Autoriza la resolución final del caso. Es una autoridad de cierre, no un nivel adicional de escalamiento.
      </p>

      {#if editing}
        <label class="mt-4 block" for="flow-closure-supervisor">
          <span class="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-[#587184]">Email del supervisor</span>
          <input
            id="flow-closure-supervisor"
            name="closure-supervisor"
            type="email"
            value={destination}
            aria-invalid={Boolean(error && touched)}
            aria-describedby={error && touched ? "flow-closure-error" : undefined}
            oninput={(event) => onDestinationInput(event.currentTarget.value)}
            onblur={onDestinationBlur}
            class="w-full min-w-0 rounded-xl border border-[#b9dfd0] bg-white px-3.5 py-3 text-sm text-[#31536b] outline-none transition focus-visible:border-[#238454] focus-visible:ring-2 focus-visible:ring-[#238454]/20 aria-[invalid=true]:border-[#b54a3d] aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-[#b54a3d]/15"
          />
          {#if error && touched}
            <span id="flow-closure-error" class="mt-1.5 block text-xs font-semibold text-[#9b3328]">{error}</span>
          {/if}
        </label>
      {:else}
        <div class="mt-4 flex min-w-0 flex-wrap items-center gap-2">
          <span class="min-w-0 max-w-full truncate rounded-xl border border-[#b9dfd0] bg-white px-3.5 py-3 font-mono text-sm text-[#17663d]" title={destination}>{destination || "Sin destinatario definido"}</span>
          {#if approvalLevel}
            <span class="rounded-full border border-[#b9dfd0] bg-[#e5f7ee] px-2.5 py-1 text-xs font-bold text-[#238454]">Autoridad N{approvalLevel}</span>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</section>
