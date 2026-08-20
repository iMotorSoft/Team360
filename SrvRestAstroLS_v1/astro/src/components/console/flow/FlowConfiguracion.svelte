<script lang="ts">
  import { onMount } from "svelte";
  import {
    cloneFlowConfiguration,
    configurationFingerprint,
    FLOW_CONFIGURATION_DEMO,
    validateFlowEmail,
    type FlowConfigurationSaveHandler,
    type FlowSectorConfiguration,
  } from "../../../lib/t360/flow/configuration";
  import {
    fetchFlowConfigurations,
    fetchOperationalSettings,
    fetchSchedulerStatus,
    mapFlowSectors,
    updateFlowConfiguration,
    updateOperationalSettings,
    type FlowConfigurationError,
    type FlowOperationalSettings,
    type FlowSchedulerState,
  } from "../../../lib/api/flowConfiguration";
  import FlowClosureSupervisorEditor from "./FlowClosureSupervisorEditor.svelte";
  import FlowLevelEditor from "./FlowLevelEditor.svelte";
  import FlowSectorSelector from "./FlowSectorSelector.svelte";

  let {
    configurations = FLOW_CONFIGURATION_DEMO,
    persistenceEnabled = false,
    onSave = () => undefined,
    onCancel = () => undefined,
    token = null,
    apiEnabled = true,
  }: {
    configurations?: FlowSectorConfiguration[];
    persistenceEnabled?: boolean;
    onSave?: FlowConfigurationSaveHandler;
    onCancel?: () => void;
    token?: string | null;
    apiEnabled?: boolean;
  } = $props();

  let savedConfigurations = $state(cloneFlowConfiguration(configurations));
  let draftConfigurations = $state<FlowSectorConfiguration[] | null>(null);
  let selectedSectorId = $state<string | null>(savedConfigurations[0]?.sectorId ?? null);
  let pendingSectorId = $state<string | null>(null);
  let touched = $state<Record<string, boolean>>({});
  let attemptedSave = $state(false);
  let saveState = $state<"idle" | "saving" | "saved" | "error" | "cancelled">("idle");
  let saveMessage = $state("");
  let loading = $state(false);
  let loadError = $state<FlowConfigurationError | null>(null);
  let operationalSettings = $state<FlowOperationalSettings | null>(null);
  let opsDraft = $state<Partial<FlowOperationalSettings> | null>(null);
  let schedulerState = $state<FlowSchedulerState | null>(null);
  let opsSaving = $state(false);
  let opsSaveMessage = $state("");

  // MVP: la ruta productiva usa la API real (default_admin) sin requerir token.
  // `apiEnabled={false}` se usa en fixtures controlados.
  const useRealApi = $derived(apiEnabled);
  const canPersist = $derived(useRealApi || persistenceEnabled);

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
    if (!selectedSector) return { levels: {}, closure: null, sla: {} };
    const slaErrors: Record<string, string | null> = {};
    for (const level of selectedSector.levels) {
      const sla = level.firstResponseSlaSeconds;
      if (sla !== null && sla !== undefined) {
        if (!Number.isInteger(sla) || sla <= 0) {
          slaErrors[level.id] = "El SLA debe ser un entero positivo";
        } else {
          slaErrors[level.id] = null;
        }
      } else {
        slaErrors[level.id] = null;
      }
    }
    return {
      levels: Object.fromEntries(selectedSector.levels.map((level) => [level.id, validationErrors[level.id]])),
      closure: validationErrors[`closure:${selectedSector.sectorId}`] ?? null,
      sla: slaErrors,
    };
  });
  const hasValidationErrors = $derived(Object.values(validationErrors).some(Boolean));
  const visibleValidationErrorCount = $derived(
    Object.entries(validationErrors).filter(([key, value]) => value && (touched[key] || attemptedSave)).length,
  );

  const loadErrorCopy = $derived.by(() => {
    switch (loadError) {
      case "unauthorized":
        return { title: "Sesión requerida", detail: "Necesitás autenticarte para ver la configuración de Flow." };
      case "forbidden":
        return { title: "Sin permiso", detail: "Tu rol no tiene acceso de configuración de Flow (flow.configuration.read)." };
      case "not_found":
        return { title: "Configuración no encontrada", detail: "El sector solicitado no existe en el catálogo de Flow." };
      case "validation":
        return { title: "Datos inválidos", detail: "El backend rechazó la configuración enviada." };
      default:
        return { title: "No se pudo cargar", detail: "El servicio de configuración de Flow no está disponible en este momento." };
    }
  });

  async function loadRealConfiguration() {
    if (!useRealApi) return;
    loading = true;
    loadError = null;
    const result = await fetchFlowConfigurations(token ?? undefined);
    loading = false;
    if (result.error) {
      loadError = result.error;
      return;
    }
    if (!result.data) {
      loadError = "unavailable";
      return;
    }
    const loaded = mapFlowSectors(result.data);
    savedConfigurations = loaded;
    selectedSectorId = loaded[0]?.sectorId ?? null;
  }

  async function loadOperationalSettings() {
    if (!useRealApi) return;
    const result = await fetchOperationalSettings(token ?? undefined);
    if (result.data) {
      operationalSettings = result.data;
      opsDraft = null;
    }
  }

  async function loadSchedulerStatus() {
    if (!useRealApi) return;
    const result = await fetchSchedulerStatus(token ?? undefined);
    if (result.data) {
      schedulerState = result.data;
    }
  }

  onMount(() => {
    if (useRealApi) {
      void loadRealConfiguration();
      void loadOperationalSettings();
      void loadSchedulerStatus();
    }
  });

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
    if (level) {
      level.destination = value;
      if (sector && level.level === sector.closureApprovalLevel) {
        sector.closureSupervisorDestination = value;
      }
    }
    draftConfigurations = next;
    saveState = "idle";
    saveMessage = "";
  }

  function updateLevelSla(levelId: string, value: string) {
    if (!draftConfigurations) return;
    const next = cloneFlowConfiguration(draftConfigurations);
    const sector = next.find((item) => item.sectorId === selectedSectorId);
    const level = sector?.levels.find((item) => item.id === levelId);
    if (level) {
      const trimmed = value.trim();
      level.firstResponseSlaSeconds = trimmed === "" ? null : parseInt(trimmed, 10);
    }
    draftConfigurations = next;
    saveState = "idle";
    saveMessage = "";
  }

  // Operational settings functions
  function beginOpsEdit() {
    if (!operationalSettings) return;
    opsDraft = { ...operationalSettings };
    opsSaveMessage = "";
  }

  function cancelOpsEdit() {
    opsDraft = null;
    opsSaveMessage = "";
  }

  function updateOpsField<K extends keyof FlowOperationalSettings>(field: K, value: FlowOperationalSettings[K]) {
    if (!opsDraft) return;
    opsDraft = { ...opsDraft, [field]: value };
    opsSaveMessage = "";
  }

  // Safe defaults for template access (TypeScript can't see Svelte if-block scoping)
  const opsAutomation = $derived(opsDraft?.automation_enabled ?? operationalSettings?.automation_enabled ?? false);
  const opsIntake = $derived(opsDraft?.mail_intake_enabled ?? operationalSettings?.mail_intake_enabled ?? true);
  const opsCutoff = $derived(opsDraft?.mail_after_cutoff ?? operationalSettings?.mail_after_cutoff ?? true);

  async function saveOpsSettings() {
    if (!opsDraft || !useRealApi) return;
    opsSaving = true;
    opsSaveMessage = "";
    const result = await updateOperationalSettings(opsDraft, token ?? undefined);
    opsSaving = false;
    if (result.error) {
      opsSaveMessage = "No se pudieron guardar los ajustes operacionales.";
      return;
    }
    if (result.data) {
      operationalSettings = result.data;
      opsDraft = null;
      opsSaveMessage = "Ajustes operacionales guardados.";
    }
  }

  function updateClosureDestination(value: string) {
    if (!draftConfigurations || !selectedSectorId) return;
    const next = cloneFlowConfiguration(draftConfigurations);
    const sector = next.find((item) => item.sectorId === selectedSectorId);
    if (sector) {
      sector.closureSupervisorDestination = value;
      const closureLevel = sector.levels.find((item) => item.level === sector.closureApprovalLevel);
      if (closureLevel) closureLevel.destination = value;
    }
    draftConfigurations = next;
    saveState = "idle";
    saveMessage = "";
  }

  function updateClosureApprovalLevel(level: number) {
    if (!draftConfigurations || !selectedSectorId) return;
    const next = cloneFlowConfiguration(draftConfigurations);
    const sector = next.find((item) => item.sectorId === selectedSectorId);
    if (sector && sector.levels.some((item) => item.level === level)) {
      sector.closureApprovalLevel = level;
      // El supervisor es una proyección del nivel que aprueba: el destino
      // mostrado sigue al nivel elegido (el email que se persiste es el del
      // nivel; no hay una dirección de supervisor separada).
      const closureLevel = sector.levels.find((item) => item.level === level);
      if (closureLevel) {
        sector.closureSupervisorDestination = closureLevel.destination;
      }
    }
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
    if (!canPersist) {
      saveState = "error";
      saveMessage = "La persistencia todavía no está conectada. Tus cambios siguen siendo un borrador local de esta pantalla.";
      return;
    }

    if (useRealApi) {
      const sectorId = selectedSectorId;
      if (!sectorId) return;
      const sector = draftConfigurations.find((item) => item.sectorId === sectorId);
      if (!sector) return;
      saveState = "saving";
      saveMessage = "Guardando cambios...";
      const result = await updateFlowConfiguration(
        sectorId,
        {
          levels: sector.levels.map((level) => ({
            level: level.level,
            destination: level.destination,
            first_response_sla_seconds: level.firstResponseSlaSeconds,
          })),
          closure_approval_level: sector.closureApprovalLevel,
        },
        token ?? undefined,
      );
      if (result.error || !result.data) {
        if (result.error === "unauthorized") {
          saveState = "error";
          saveMessage = "Tu sesión expiró. Volvé a iniciar sesión para guardar.";
        } else if (result.error === "forbidden") {
          saveState = "error";
          saveMessage = "Tu rol no tiene permiso para modificar la configuración de Flow.";
        } else if (result.error === "validation") {
          saveState = "error";
          saveMessage = "El backend rechazó los cambios. Revisá los destinatarios e intentá nuevamente.";
        } else {
          saveState = "error";
          saveMessage = "No se pudieron guardar los cambios. Intentá nuevamente en unos instantes.";
        }
        return;
      }
      const canonical = mapFlowSectors({ sectors: [result.data] })[0];
      savedConfigurations = savedConfigurations.map((item) =>
        item.sectorId === canonical.sectorId ? canonical : item,
      );
      draftConfigurations = null;
      touched = {};
      attemptedSave = false;
      saveState = "saved";
      saveMessage = "Cambios guardados.";
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
      {:else if useRealApi}
        <span class="rounded-full border border-[#b9e7cc] bg-[#e8f8ef] px-3 py-1.5 text-xs font-bold text-[#17663d]">Configuración persistente</span>
      {:else}
        <span class="rounded-full border border-[#f1dfa2] bg-[#fff7d9] px-3 py-1.5 text-xs font-bold text-[#765d00]">Modo demo · solo lectura</span>
      {/if}
    </div>
  </header>

  {#if useRealApi && loadError}
    <div class="rounded-2xl border border-[#f1c7c2] bg-[#fdf0ee] p-4" role="alert">
      <div class="flex items-start gap-3">
        <span class="mt-0.5 text-base text-[#9b3328]" aria-hidden="true">●</span>
        <div>
          <p class="text-xs font-bold uppercase tracking-[0.1em] text-[#9b3328]">{loadErrorCopy.title}</p>
          <p class="mt-1 text-xs leading-5 text-[#9b3328]">{loadErrorCopy.detail}</p>
        </div>
      </div>
    </div>
  {:else if useRealApi && !loading}
    <div class="rounded-2xl border border-[#b9e7cc] bg-[#e8f8ef] p-4" role="status">
      <div class="flex items-start gap-3">
        <span class="mt-0.5 text-base text-[#17663d]" aria-hidden="true">✓</span>
        <div>
          <p class="text-xs font-bold uppercase tracking-[0.1em] text-[#17663d]">Configuración persistente</p>
          <p class="mt-1 text-xs leading-5 text-[#17663d]">
            La configuración se lee y guarda a través de PostgreSQL. Los cambios aplican a los próximos casos y autorizaciones de cierre.
          </p>
        </div>
      </div>
    </div>
  {:else if !useRealApi}
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
  {/if}

  <div class="grid min-w-0 gap-6 xl:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)]">
    {#if useRealApi && loadError}
      <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-8 text-center xl:col-span-2" role="alert" data-flow-config-error>
        <p class="text-sm font-bold text-[#31536b]">{loadErrorCopy.title}</p>
        <p class="mt-2 text-xs leading-5 text-[#78909f]">{loadErrorCopy.detail}</p>
        <p class="mt-4 text-xs text-[#91a2ad]">La configuración de Flow no está disponible en este momento. No se muestran datos de demostración.</p>
      </section>
    {:else if loading}
      <aside class="animate-pulse rounded-2xl border border-card-border bg-card-bg p-4" aria-label="Cargando configuración">
        <div class="h-3 w-24 rounded bg-base-200"></div>
        <div class="mt-4 space-y-2">
          <div class="h-14 rounded-xl bg-base-200"></div>
          <div class="h-14 rounded-xl bg-base-200"></div>
        </div>
      </aside>
      <section class="min-w-0 space-y-6 animate-pulse" aria-label="Cargando configuración">
        <div class="h-36 rounded-2xl border border-card-border bg-card-bg p-5">
          <div class="h-4 w-40 rounded bg-base-200"></div>
          <div class="mt-3 h-6 w-56 rounded bg-base-200"></div>
        </div>
        <div class="h-24 rounded-2xl bg-base-200"></div>
        <div class="h-32 rounded-2xl bg-base-200"></div>
      </section>
    {:else}
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
                  disabled={!canPersist || !isDirty || hasValidationErrors || saveState === "saving"}
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
              {#if canPersist}
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
          disabled={saveState === "saving"}
          errors={selectedValidationErrors.levels}
          touched={touched}
          onDestinationInput={updateLevelDestination}
          onDestinationBlur={markTouched}
          onSlaInput={updateLevelSla}
          onSlaBlur={markTouched}
          slaErrors={selectedValidationErrors.sla ?? {}}
        />

        <FlowClosureSupervisorEditor
          approvalLevel={selectedSector.closureApprovalLevel}
          destination={selectedSector.closureSupervisorDestination}
          levels={selectedSector.levels.map((level) => ({ level: level.level, label: level.label }))}
          editing={isEditing}
          disabled={saveState === "saving"}
          error={selectedValidationErrors.closure}
          touched={Boolean(touched[`closure:${selectedSector.sectorId}`])}
          onDestinationInput={updateClosureDestination}
          onDestinationBlur={() => markTouched(`closure:${selectedSector.sectorId}`)}
          onApprovalLevelChange={updateClosureApprovalLevel}
        />
      {:else}
        <section class="rounded-2xl border border-dashed border-[#d7e3e5] bg-white/70 p-8 text-center">
          <p class="text-sm font-bold text-[#31536b]">Seleccioná un sector</p>
          <p class="mt-1 text-xs leading-5 text-[#78909f]">La configuración del circuito aparecerá cuando el catálogo tenga un sector disponible.</p>
        </section>
      {/if}
    </section>
    {/if}
  </div>

  <!-- Operational Settings Section -->
  {#if useRealApi && operationalSettings}
  <div class="mt-8">
    <section class="rounded-2xl border border-card-border bg-card-bg p-5 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)] sm:p-6">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="min-w-0">
          <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#168b88]">Operación de Flow</p>
          <h2 class="mt-1 text-2xl font-bold tracking-[-0.035em] text-[#173b5b]">Configuración del scheduler</h2>
          <p class="mt-1 text-sm text-[#78909f]">Controlá la automatización, frecuencia e intake de correo.</p>
        </div>
        {#if !opsDraft}
          <button type="button" class="inline-flex min-h-11 items-center justify-center rounded-full border border-[#168b88] bg-[#168b88] px-5 py-2.5 text-sm font-bold text-white transition hover:border-[#126d6b] hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]" onclick={beginOpsEdit}>
            Editar operación
          </button>
        {:else}
          <div class="flex flex-wrap gap-2">
            <button type="button" class="inline-flex min-h-11 items-center justify-center rounded-full border border-[#cddbdd] bg-white px-5 py-2.5 text-sm font-bold text-[#47657b] transition hover:border-[#9fb6bb] hover:bg-[#f4f8f8] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88]" onclick={cancelOpsEdit}>
              Cancelar
            </button>
            <button type="button" class="inline-flex min-h-11 items-center justify-center rounded-full border border-[#168b88] bg-[#168b88] px-5 py-2.5 text-sm font-bold text-white transition hover:border-[#126d6b] hover:bg-[#126d6b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] disabled:cursor-not-allowed disabled:opacity-50" disabled={opsSaving} onclick={saveOpsSettings}>
              {opsSaving ? "Guardando..." : "Guardar operación"}
            </button>
          </div>
        {/if}
      </div>

      {#if opsSaveMessage}
        <div class="mt-4 rounded-2xl border border-[#b9e7cc] bg-[#e8f8ef] p-4" role="status">
          <p class="text-sm font-semibold text-[#17663d]">{opsSaveMessage}</p>
        </div>
      {/if}

      <div class="mt-5 space-y-4">
        <!-- Automation Toggle -->
        <div class="flex items-center justify-between rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] px-4 py-3">
          <div>
            <p class="text-sm font-bold text-[#31536b]">Automatización habilitada</p>
            <p class="text-xs text-[#78909f]">Activa el scheduler que ejecuta ciclos automáticos de Flow.</p>
          </div>
          {#if opsDraft}
            <button type="button" role="switch" aria-checked={opsDraft.automation_enabled ?? operationalSettings?.automation_enabled}
              onclick={() => updateOpsField("automation_enabled", !(opsDraft?.automation_enabled ?? operationalSettings?.automation_enabled))}
              class={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${(opsDraft?.automation_enabled ?? operationalSettings?.automation_enabled) ? "bg-[#168b88]" : "bg-[#bccdd0]"}`}
            >
              <span class="pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform duration-200 ease-in-out ${(opsDraft?.automation_enabled ?? operationalSettings?.automation_enabled) ? "translate-x-5" : "translate-x-0"}" aria-hidden="true"></span>
            </button>
          {:else}
            <span class={`rounded-full px-3 py-1.5 text-xs font-bold ${operationalSettings?.automation_enabled ? "border border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]" : "border border-[#dce6e8] bg-white text-[#587184]"}`}>
              {operationalSettings?.automation_enabled ? "ACTIVA" : "INACTIVA"}
            </span>
          {/if}
        </div>

        <!-- Scheduler Interval -->
        <div class="flex items-center justify-between rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] px-4 py-3">
          <div>
            <p class="text-sm font-bold text-[#31536b]">Frecuencia del scheduler</p>
            <p class="text-xs text-[#78909f]">Segundos entre ciclos automáticos.</p>
          </div>
          {#if opsDraft}
            <div class="flex items-center gap-2">
              <input type="number" min="5" max="3600" step="1" value={opsDraft.scheduler_interval_seconds ?? operationalSettings?.scheduler_interval_seconds}
                oninput={(e) => updateOpsField("scheduler_interval_seconds", parseInt(e.currentTarget.value, 10))}
                class="w-24 rounded-xl border border-[#d5e0e2] bg-white px-3 py-2 text-sm text-[#31536b] outline-none focus-visible:border-[#168b88] focus-visible:ring-2 focus-visible:ring-[#168b88]/20"
              />
              <span class="text-xs font-bold text-[#78909f]">seg</span>
            </div>
          {:else}
            <span class="text-sm font-bold text-[#31536b]">{operationalSettings?.scheduler_interval_seconds}s</span>
          {/if}
        </div>

        <!-- Mail Intake Toggle -->
        <div class="flex items-center justify-between rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] px-4 py-3">
          <div>
            <p class="text-sm font-bold text-[#31536b]">Intake de correo habilitado</p>
            <p class="text-xs text-[#78909f]">Procesa emails entrantes del buzón configurado.</p>
          </div>
          {#if opsDraft}
            <button type="button" role="switch" aria-checked={opsDraft.mail_intake_enabled ?? operationalSettings?.mail_intake_enabled}
              onclick={() => updateOpsField("mail_intake_enabled", !(opsDraft?.mail_intake_enabled ?? operationalSettings?.mail_intake_enabled))}
              class={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${(opsDraft?.mail_intake_enabled ?? operationalSettings?.mail_intake_enabled) ? "bg-[#168b88]" : "bg-[#bccdd0]"}`}
            >
              <span class="pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform duration-200 ease-in-out ${(opsDraft?.mail_intake_enabled ?? operationalSettings?.mail_intake_enabled) ? "translate-x-5" : "translate-x-0"}" aria-hidden="true"></span>
            </button>
          {:else}
            <span class={`rounded-full px-3 py-1.5 text-xs font-bold ${operationalSettings?.mail_intake_enabled ? "border border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]" : "border border-[#dce6e8] bg-white text-[#587184]"}`}>
              {operationalSettings?.mail_intake_enabled ? "ACTIVO" : "INACTIVO"}
            </span>
          {/if}
        </div>

        <!-- Batch Limit -->
        <div class="flex items-center justify-between rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] px-4 py-3">
          <div>
            <p class="text-sm font-bold text-[#31536b]">Lote máximo de correo</p>
            <p class="text-xs text-[#78909f]">Máximo de mensajes procesados por ciclo.</p>
          </div>
          {#if opsDraft}
            <input type="number" min="1" max="10000" step="1" value={opsDraft.mail_batch_limit ?? operationalSettings?.mail_batch_limit}
              oninput={(e) => updateOpsField("mail_batch_limit", parseInt(e.currentTarget.value, 10))}
              class="w-24 rounded-xl border border-[#d5e0e2] bg-white px-3 py-2 text-sm text-[#31536b] outline-none focus-visible:border-[#168b88] focus-visible:ring-2 focus-visible:ring-[#168b88]/20"
            />
          {:else}
            <span class="text-sm font-bold text-[#31536b]">{operationalSettings?.mail_batch_limit}</span>
          {/if}
        </div>

        <!-- Historical Cutoff -->
        <div class="flex items-center justify-between rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] px-4 py-3">
          <div>
            <p class="text-sm font-bold text-[#31536b]">Protección histórica</p>
            <p class="text-xs text-[#78909f]">Evita procesar emails anteriores al corte productivo.</p>
          </div>
          {#if opsDraft}
            <button type="button" role="switch" aria-checked={opsDraft.mail_after_cutoff ?? operationalSettings?.mail_after_cutoff}
              onclick={() => updateOpsField("mail_after_cutoff", !(opsDraft?.mail_after_cutoff ?? operationalSettings?.mail_after_cutoff))}
              class={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#168b88] ${(opsDraft?.mail_after_cutoff ?? operationalSettings?.mail_after_cutoff) ? "bg-[#168b88]" : "bg-[#bccdd0]"}`}
            >
              <span class="pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform duration-200 ease-in-out ${(opsDraft?.mail_after_cutoff ?? operationalSettings?.mail_after_cutoff) ? "translate-x-5" : "translate-x-0"}" aria-hidden="true"></span>
            </button>
          {:else}
            <span class={`rounded-full px-3 py-1.5 text-xs font-bold ${operationalSettings?.mail_after_cutoff ? "border border-[#b9e7cc] bg-[#e8f8ef] text-[#17663d]" : "border border-[#dce6e8] bg-white text-[#587184]"}`}>
              {operationalSettings?.mail_after_cutoff ? "ACTIVA" : "INACTIVA"}
            </span>
          {/if}
        </div>
      </div>
    </section>

    <!-- Scheduler Status -->
    {#if schedulerState}
    <section class="mt-6 rounded-2xl border border-card-border bg-card-bg p-5 shadow-[0_18px_45px_-42px_rgba(16,45,79,0.7)] sm:p-6">
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-[#78909f]">Estado del scheduler</p>
      <h2 class="mt-1 text-xl font-bold tracking-[-0.025em] text-[#173b5b]">Último ciclo ejecutado</h2>

      <div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] p-3">
          <p class="text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[#78909f]">Resultado</p>
          <p class="mt-1 text-sm font-bold {schedulerState.last_result === 'PASS' ? 'text-[#17663d]' : schedulerState.last_result === 'ERROR' ? 'text-[#9b3328]' : 'text-[#587184]'}">
            {schedulerState.last_result ?? "Sin ciclos"}
          </p>
        </div>
        <div class="rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] p-3">
          <p class="text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[#78909f]">Ciclos totales</p>
          <p class="mt-1 text-sm font-bold text-[#31536b]">{schedulerState.cycle_count}</p>
        </div>
        <div class="rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] p-3">
          <p class="text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[#78909f]">Procesados</p>
          <p class="mt-1 text-sm font-bold text-[#31536b]">{schedulerState.processed_count}</p>
        </div>
        <div class="rounded-xl border border-[#e3eaeb] bg-[#f8fbfa] p-3">
          <p class="text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[#78909f]">Último ciclo</p>
          <p class="mt-1 text-xs font-bold text-[#31536b]">
            {schedulerState.last_finished_at_utc ? new Date(schedulerState.last_finished_at_utc).toLocaleString() : "Nunca"}
          </p>
        </div>
      </div>

      {#if schedulerState.last_error_class}
        <div class="mt-3 rounded-xl border border-[#f1c7c2] bg-[#fdf0ee] p-3">
          <p class="text-xs font-bold text-[#9b3328]">Error: {schedulerState.last_error_class}</p>
        </div>
      {/if}
    </section>
    {/if}
  </div>
  {/if}
</div>
