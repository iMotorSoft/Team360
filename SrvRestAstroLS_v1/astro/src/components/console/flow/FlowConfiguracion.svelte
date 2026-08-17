<script lang="ts">
  import {
    cloneFlowConfiguration,
    configurationFingerprint,
    FLOW_CONFIGURATION_DEMO,
    validateFlowEmail,
    type FlowConfigurationSaveHandler,
    type FlowSectorConfiguration,
  } from "../../../lib/t360/flow/configuration";
  import FlowClosureSupervisorEditor from "./FlowClosureSupervisorEditor.svelte";
  import FlowLevelEditor from "./FlowLevelEditor.svelte";
  import FlowSectorSelector from "./FlowSectorSelector.svelte";

  let {
    configurations = FLOW_CONFIGURATION_DEMO,
    persistenceEnabled = false,
    onSave = () => undefined,
    onCancel = () => undefined,
  }: {
    configurations?: FlowSectorConfiguration[];
    persistenceEnabled?: boolean;
    onSave?: FlowConfigurationSaveHandler;
    onCancel?: () => void;
  } = $props();

  let savedConfigurations = $state(cloneFlowConfiguration(configurations));
  let draftConfigurations = $state<FlowSectorConfiguration[] | null>(null);
  let selectedSectorId = $state<string | null>(savedConfigurations[0]?.sectorId ?? null);
  let pendingSectorId = $state<string | null>(null);
  let touched = $state<Record<string, boolean>>({});
  let attemptedSave = $state(false);
  let saveState = $state<"idle" | "saving" | "saved" | "error" | "cancelled">("idle");
  let saveMessage = $state("");

  const activeConfigurations = $derived(draftConfigurations ?? savedConfigurations);
  const selectedSector = $derived(activeConfigurations.find((sector) => sector.sectorId === selectedSectorId) ?? null);
  const isEditing = $derived(draftConfigurations !== null);
  const isDirty = $derived(
    draftConfigurations !== null && configurationFingerprint(draftConfigurations) !== configurationFingerprint(savedConfigurations),
  );
  const validationErrors = $derived.by(() => {
    const errors: Record<string, string | null> = {};
    for (const sector of activeConfigurations) {
      for (const level of sector.levels) {
        errors[level.id] = validateFlowEmail(level.destination);
      }
      errors[`closure:${sector.sectorId}`] =
        sector.closureApprovalLevel === null && !sector.closureSupervisorDestination.trim()
          ? null
          : validateFlowEmail(sector.closureSupervisorDestination);
    }
    return errors;
  });
  const selectedValidationErrors = $derived.by(() => {
    if (!selectedSector) return { levels: {}, closure: null };
    return {
      levels: Object.fromEntries(selectedSector.levels.map((level) => [level.id, validationErrors[level.id]])),
      closure: validationErrors[`closure:${selectedSector.sectorId}`] ?? null,
    };
  });
  const hasValidationErrors = $derived(Object.values(validationErrors).some(Boolean));
  const visibleValidationErrorCount = $derived(
    Object.entries(validationErrors).filter(([key, value]) => value && (touched[key] || attemptedSave)).length,
  );

  function beginEdit() {
    draftConfigurations = cloneFlowConfiguration(savedConfigurations);
    touched = {};
    attemptedSave = false;
    saveState = "idle";
    saveMessage = "";
  }

  function cancelEdit() {
    draftConfigurations = null;
    pendingSectorId = null;
    touched = {};
    attemptedSave = false;
    saveState = "cancelled";
    saveMessage = "Los cambios se descartaron. La configuración guardada no fue modificada.";
    onCancel();
  }

  function requestSectorChange(sectorId: string) {
    if (sectorId === selectedSectorId) return;
    if (isEditing && isDirty) {
      pendingSectorId = sectorId;
      return;
    }
    selectedSectorId = sectorId;
  }

  function discardAndChangeSector() {
    if (!pendingSectorId) return;
    const nextSectorId = pendingSectorId;
    cancelEdit();
    selectedSectorId = nextSectorId;
    pendingSectorId = null;
  }

  function updateLevelDestination(levelId: string, value: string) {
    if (!draftConfigurations) return;
    const next = cloneFlowConfiguration(draftConfigurations);
    const sector = next.find((item) => item.sectorId === selectedSectorId);
    const level = sector?.levels.find((item) => item.id === levelId);
    if (level) level.destination = value;
    draftConfigurations = next;
    saveState = "idle";
    saveMessage = "";
  }

  function updateClosureDestination(value: string) {
    if (!draftConfigurations || !selectedSectorId) return;
    const next = cloneFlowConfiguration(draftConfigurations);
    const sector = next.find((item) => item.sectorId === selectedSectorId);
    if (sector) sector.closureSupervisorDestination = value;
    draftConfigurations = next;
    saveState = "idle";
    saveMessage = "";
  }

  function markTouched(key: string) {
    touched = { ...touched, [key]: true };
  }

  async function saveDraft() {
    attemptedSave = true;
    if (!draftConfigurations || hasValidationErrors || !isDirty) return;
    if (!persistenceEnabled) {
      saveState = "error";
      saveMessage = "La persistencia todavía no está conectada. Tus cambios siguen siendo un borrador local de esta pantalla.";
      return;
    }

    saveState = "saving";
    saveMessage = "Guardando cambios...";
    try {
      await onSave(cloneFlowConfiguration(draftConfigurations));
      savedConfigurations = cloneFlowConfiguration(draftConfigurations);
      draftConfigurations = null;
      touched = {};
      attemptedSave = false;
      saveState = "saved";
      saveMessage = "Cambios guardados.";
    } catch {
      saveState = "error";
      saveMessage = "No se pudieron guardar los cambios. Revisá el formulario e intentá nuevamente.";
    }
  }
</script>

<div class="space-y-6">
  <header class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
    <div class="min-w-0">
      <p class="text-xs font-bold uppercase tracking-[0.2em] text-console-brand">Configuración de Flow</p>
      <h1 class="mt-2 text-3xl font-bold tracking-[-0.055em] text-console-title sm:text-4xl">Sectores y niveles</h1>
      <p class="mt-3 max-w-3xl text-sm leading-6 text-console-muted">
        Definí quién recibe cada caso, en qué orden avanza y quién autoriza la resolución final.
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      {#if isEditing && isDirty}
        <span class="rounded-full border border-[#f1dfa2] bg-[#fff7d9] px-3 py-1.5 text-xs font-bold text-[#765d00]">Cambios sin guardar</span>
      {:else if isEditing}
        <span class="rounded-full border border-[#dce6e8] bg-white px-3 py-1.5 text-xs font-bold text-[#587184]">Sin cambios</span>
      {:else}
        <span class="rounded-full border border-[#f1dfa2] bg-[#fff7d9] px-3 py-1.5 text-xs font-bold text-[#765d00]">Modo demo · solo lectura</span>
      {/if}
    </div>
  </header>

  <div class="rounded-2xl border border-[#f1dfa2] bg-[#fff7d9] p-4" role="status">
    <div class="flex items-start gap-3">
      <span class="mt-0.5 text-base text-[#765d00]" aria-hidden="true">●</span>
      <div>
        <p class="text-xs font-bold uppercase tracking-[0.1em] text-[#765d00]">Configuración preparada</p>
        <p class="mt-1 text-xs leading-5 text-[#765d00]">
          Podés revisar y validar un borrador visual. La persistencia real se habilitará cuando exista el backend mutativo de Flow.
        </p>
      </div>
    </div>
  </div>

  <div class="grid min-w-0 gap-6 xl:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)]">
    <FlowSectorSelector sectors={activeConfigurations} selectedId={selectedSectorId} onSelect={requestSectorChange} />

    <section class="min-w-0 space-y-6" aria-label="Editor de configuración" data-flow-config-editor>
      {#if selectedSector}
        <section class="rounded-2xl border border-card-border bg-card-bg p-5 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)] sm:p-6">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#78909f]">Sector activo</p>
              <h2 class="mt-1 truncate text-2xl font-bold tracking-[-0.035em] text-[#173b5b]">{selectedSector.displayName}</h2>
              <p class="mt-1 text-sm text-[#78909f]">Circuito de atención y autoridad de cierre.</p>
            </div>
            {#if !isEditing}
              <button
                type="button"
                class="inline-flex min-h-11 items-center justify-center rounded-full border border-[#168b88] bg-[#168b88] px-5 py-2.5 text-sm font-bold text-white transition hover:border-[#126d6b] hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
                onclick={beginEdit}
              >
                Editar configuración
              </button>
            {:else}
              <div class="flex flex-wrap gap-2">
                <button
                  type="button"
                  class="inline-flex min-h-11 items-center justify-center rounded-full border border-[#cddbdd] bg-white px-5 py-2.5 text-sm font-bold text-[#47657b] transition hover:border-[#9fb6bb] hover:bg-[#f4f8f8] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]"
                  onclick={cancelEdit}
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  class="inline-flex min-h-11 items-center justify-center rounded-full border border-[#168b88] bg-[#168b88] px-5 py-2.5 text-sm font-bold text-white transition hover:border-[#126d6b] hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={!persistenceEnabled || !isDirty || hasValidationErrors || saveState === "saving"}
                  aria-describedby="flow-save-help"
                  onclick={saveDraft}
                >
                  {saveState === "saving" ? "Guardando..." : "Guardar cambios"}
                </button>
              </div>
            {/if}
          </div>

          {#if isEditing}
            <p id="flow-save-help" class="mt-4 text-xs leading-5 text-[#78909f]">
              {#if persistenceEnabled}
                Validá todos los destinatarios antes de preparar el guardado.
              {:else}
                Guardar cambios estará disponible cuando el backend mutativo de Flow esté conectado.
              {/if}
            </p>
          {/if}
        </section>

        {#if pendingSectorId}
          <div class="rounded-2xl border border-[#f1dfa2] bg-[#fffaf0] p-4" role="alertdialog" aria-labelledby="flow-sector-change-title">
            <p id="flow-sector-change-title" class="text-sm font-bold text-[#765d00]">Tenés cambios sin guardar</p>
            <p class="mt-1 text-xs leading-5 text-[#765d00]">Si cambiás de sector, el borrador actual se va a descartar.</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <button type="button" class="rounded-full border border-[#d6ae12] bg-[#f1cf45] px-3.5 py-2 text-xs font-bold text-[#4f4108] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]" onclick={discardAndChangeSector}>Descartar y cambiar</button>
              <button type="button" class="rounded-full border border-transparent px-3.5 py-2 text-xs font-bold text-[#765d00] hover:bg-[#fff2c7] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]" onclick={() => (pendingSectorId = null)}>Seguir editando</button>
            </div>
          </div>
        {/if}

        {#if saveState !== "idle" && saveMessage}
        <div class={`rounded-2xl border p-4 ${saveState === "error" ? "border-[#f1c7c2] bg-[#fdf0ee] text-[#9b3328]" : saveState === "saved" || saveState === "cancelled" ? "border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]" : "border-[#b9def0] bg-[#e9f6fc] text-[#1d6688]"}`} role="status">
            <p class="text-sm font-semibold">{saveMessage}</p>
            {#if visibleValidationErrorCount > 0}
              <p class="mt-1 text-xs">Revisá {visibleValidationErrorCount} campo{visibleValidationErrorCount === 1 ? "" : "s"} antes de continuar.</p>
            {/if}
          </div>
        {/if}

        <FlowLevelEditor
          levels={selectedSector.levels}
          editing={isEditing}
          errors={selectedValidationErrors.levels}
          touched={touched}
          onDestinationInput={updateLevelDestination}
          onDestinationBlur={markTouched}
        />

        <FlowClosureSupervisorEditor
          approvalLevel={selectedSector.closureApprovalLevel}
          destination={selectedSector.closureSupervisorDestination}
          editing={isEditing}
          error={selectedValidationErrors.closure}
          touched={Boolean(touched[`closure:${selectedSector.sectorId}`])}
          onDestinationInput={updateClosureDestination}
          onDestinationBlur={() => markTouched(`closure:${selectedSector.sectorId}`)}
        />
      {:else}
        <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-8 text-center">
          <p class="text-sm font-bold text-[#31536b]">Seleccioná un sector</p>
          <p class="mt-1 text-xs leading-5 text-[#78909f]">La configuración del circuito aparecerá cuando el catálogo tenga un sector disponible.</p>
        </section>
      {/if}
    </section>
  </div>
</div>
