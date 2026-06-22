<script lang="ts">
  import type { StructuredDiagnosis } from "../../lib/api/publicDiagnosis";
  import type { T360MissingRequirement, T360Action, T360InteractionKind, T360ProductFitCardBlock } from "../../lib/t360/interaction/types";
  import T360ActionButtons from "../../lib/t360/interaction/T360ActionButtons.svelte";
  import T360StatusBadge from "../../lib/t360/interaction/T360StatusBadge.svelte";
  import {
    formatFeasibility,
    formatAutomationMode,
    formatConfidence,
    formatAvailability,
    formatHumanApproval,
    formatRisk,
    formatEntity,
    formatSystem,
    formatChannel,
    formatEntitySources,
    formatAutomatableStep,
    formatHumanStep,
    formatAssumption,
    formatValidationPoint,
    formatNextStep,
    sectionTitle,
    directionForLocale,
    langAttr,
  } from "../../lib/api/diagnosisPresentation";

  const requiredForLabels: Record<T360MissingRequirement["required_for"], string> = {
    preliminary_diagnosis: "Diagnóstico preliminar",
    full_diagnosis: "Diagnóstico completo",
    implementation: "Implementación",
    pricing: "Pricing",
    handoff: "Handoff",
  };

  let {
    diagnosis,
    isFallback,
    locale = "es",
    compactMissingRequirements = [],
    actionButtons = [],
    actionBlockType = "diagnosis_action_card" as T360InteractionKind,
    actionSessionId = "",
    actionDisabled = false,
    productFitData = null,
  }: {
    diagnosis: StructuredDiagnosis;
    isFallback?: boolean;
    locale?: string;
    compactMissingRequirements?: T360MissingRequirement[];
    actionButtons?: T360Action[];
    actionBlockType?: T360InteractionKind;
    actionSessionId?: string;
    actionDisabled?: boolean;
    productFitData?: T360ProductFitCardBlock | null;
  } = $props();

  const dir = $derived(directionForLocale(locale));
  const lang = $derived(langAttr(locale));

  const entityLinks = $derived(formatEntitySources(diagnosis.entity_sources, locale));
  const hasEntitySources = $derived(Object.keys(diagnosis.entity_sources).length > 0);

  let expanded = $state(false);
  let productFitOpen = $state(false);

  const hasExpandableContent = $derived(
    diagnosis.automatable_steps.length > 0 ||
    diagnosis.human_steps.length > 0 ||
    diagnosis.human_approval === "required" ||
    diagnosis.human_approval === "conditional" ||
    diagnosis.risks.length > 0 ||
    diagnosis.assumptions.length > 0 ||
    diagnosis.validation_points.length > 0 ||
    compactMissingRequirements.length > 0
  );
</script>

{#if isFallback}
  <div
    class="mb-4 rounded-2xl border border-[#ffe0b2] bg-[#fff8e1] px-4 py-3 text-sm leading-5 text-[#8d6e00]"
    role="status"
    aria-live="polite"
    {dir}
    {lang}
  >
    {sectionTitle("fallback_note", locale)}
  </div>
{/if}

<div
  class="mt-6 space-y-5 rounded-[1.5rem] border border-[#cde0df] bg-[#f6fbfa] p-5 sm:p-6"
  data-testid="diagnosis-result"
  {dir}
  {lang}
>
  <!-- Heading -->
  <div>
    <p class="text-xs font-bold uppercase tracking-[0.18em] text-[#168b88]">
      {sectionTitle("diagnosis_heading", locale)}
    </p>
  </div>

  <!-- Feasibility / Mode / Confidence badges -->
  <div class="flex flex-wrap gap-3">
    <div class="rounded-xl border border-[#c0dcd7] bg-white px-4 py-2.5">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
        {sectionTitle("feasibility", locale)}
      </p>
      <p class="mt-0.5 text-sm font-semibold text-[#102d4f]">
        {formatFeasibility(diagnosis.feasibility, locale)}
      </p>
    </div>
    <div class="rounded-xl border border-[#c0dcd7] bg-white px-4 py-2.5">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
        {sectionTitle("automation_mode", locale)}
      </p>
      <p class="mt-0.5 text-sm font-semibold text-[#102d4f]">
        {formatAutomationMode(diagnosis.automation_mode, locale)}
      </p>
    </div>
    <div class="rounded-xl border border-[#c0dcd7] bg-white px-4 py-2.5">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
        {sectionTitle("confidence", locale)}
      </p>
      <p class="mt-0.5 text-sm font-semibold text-[#102d4f]">
        {formatConfidence(diagnosis.confidence, locale)}
      </p>
    </div>
  </div>

  <!-- Availability -->
  <div>
    <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
      {sectionTitle("availability", locale)}
    </p>
    <p class="mt-0.5 text-sm font-semibold text-[#102d4f]">
      {formatAvailability(diagnosis.availability, locale)}
    </p>
  </div>

  <!-- Channels and systems -->
  {#if diagnosis.channels.length > 0 || diagnosis.systems.length > 0 || hasEntitySources}
    <div>
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
        {sectionTitle("channels_systems", locale)}
      </p>
      {#if diagnosis.channels.length > 0}
        <div class="mt-2 flex flex-wrap gap-1.5">
          {#each diagnosis.channels as ch}
            <span class="rounded-full border border-[#cde0df] bg-white px-2.5 py-0.5 text-[0.7rem] font-semibold text-[#3b5d6a]">
              {formatChannel(ch, locale)}
            </span>
          {/each}
        </div>
      {/if}
      {#if diagnosis.systems.length > 0}
        <div class="mt-2 flex flex-wrap gap-1.5">
          {#each diagnosis.systems as sys}
            <span class="rounded-full border border-[#b8cfcf] bg-[#e8f5f2] px-2.5 py-0.5 text-[0.7rem] font-semibold text-[#236661]">
              {formatSystem(sys, locale)}
            </span>
          {/each}
        </div>
      {/if}
      {#if hasEntitySources}
        <div class="mt-3 space-y-1">
          {#each entityLinks as link}
            <div class="flex min-w-0 flex-wrap items-center gap-2 text-sm leading-5 text-[#203c55]">
              <span class="min-w-0 break-words font-medium">{link.entity}</span>
              <span class="text-[#78909f]">→</span>
              <span class="min-w-0 break-words font-medium text-[#168b88]">{link.source}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Expandable detail section -->
  {#if expanded}
    <!-- Automatable steps -->
    {#if diagnosis.automatable_steps.length > 0}
      <div>
        <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
          {sectionTitle("what_can_automate", locale)}
        </p>
        <ul class="mt-2 space-y-1.5">
          {#each diagnosis.automatable_steps as step}
            <li class="flex items-start gap-2 text-sm leading-5 text-[#203c55]">
              <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-[#168b88]/10 text-[0.55rem] font-bold text-[#168b88]">✓</span>
              <span class="min-w-0 break-words">{formatAutomatableStep(step, locale)}</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Human steps -->
    {#if diagnosis.human_steps.length > 0 || diagnosis.human_approval === "required" || diagnosis.human_approval === "conditional"}
      <div>
        <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
          {sectionTitle("human_intervention", locale)}
        </p>
        {#if diagnosis.human_approval === "required" || diagnosis.human_approval === "conditional"}
          <p class="mt-1 text-sm font-medium text-[#203c55]">
            {formatHumanApproval(diagnosis.human_approval, locale)}
          </p>
        {/if}
        {#if diagnosis.human_steps.length > 0}
          <ul class="mt-2 space-y-1.5">
            {#each diagnosis.human_steps as step}
              <li class="flex items-start gap-2 text-sm leading-5 text-[#203c55]">
                <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-[#e8c184]/20 text-[0.55rem] font-bold text-[#b87d2c]">!</span>
                <span class="min-w-0 break-words">{formatHumanStep(step, locale)}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}

    <!-- Risks -->
    {#if diagnosis.risks.length > 0}
      <div>
        <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#c07830]">
          {sectionTitle("risks", locale)}
        </p>
        <ul class="mt-2 space-y-1.5">
          {#each diagnosis.risks as risk}
            <li class="flex items-start gap-2 text-sm leading-5 text-[#5f4a28]">
              <span class="mt-0.5 shrink-0 text-[#c07830]">⚠</span>
              {formatRisk(risk, locale)}
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Assumptions -->
    {#if diagnosis.assumptions.length > 0}
      <div>
        <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#6d8290]">
          {sectionTitle("assumptions", locale)}
        </p>
        <ul class="mt-2 space-y-1.5">
          {#each diagnosis.assumptions as assumption}
            <li class="flex items-start gap-2 text-sm leading-5 italic text-[#5f7481]">
              <span class="mt-1.5 shrink-0 text-[#91a2ad]">·</span>
              <span class="min-w-0 break-words">{formatAssumption(assumption, locale)}</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Validation points -->
    {#if diagnosis.validation_points.length > 0}
      <div>
        <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
          {sectionTitle("validation_points", locale)}
        </p>
        <ul class="mt-2 space-y-1.5">
          {#each diagnosis.validation_points as vp}
            <li class="flex items-start gap-2 text-sm leading-5 text-[#203c55]">
              <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border border-[#168b88] text-[0.55rem] font-bold text-[#168b88]">?</span>
              <span class="min-w-0 break-words">{formatValidationPoint(vp, locale)}</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Compact missing requirements -->
    {#if compactMissingRequirements.length > 0}
      <div>
        <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
          {sectionTitle("validation_points", locale)}
        </p>
        <div class="mt-2 flex flex-col gap-2">
          {#each compactMissingRequirements as req}
            <div class="flex items-start gap-2 rounded-lg border border-[#d5e2e5] bg-white p-2.5">
              <span
                class="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase leading-4 {req.status === 'missing' ? 'bg-[#fce4e0] text-[#b84a2c]' : req.status === 'partial' ? 'bg-[#fff3d6] text-[#996e1a]' : 'bg-[#dff0ed] text-[#168b88]'}"
              >
                {req.status === "missing" ? "Falta" : req.status === "partial" ? "Parcial" : "Confirmado"}
              </span>
              <div class="min-w-0 flex-1">
                <p class="text-sm leading-5 text-[#203c55]">{req.label}</p>
                {#if req.description}
                  <p class="mt-0.5 text-xs leading-4 text-[#6d8290]">{req.description}</p>
                {/if}
              </div>
              <span class="mt-0.5 shrink-0 rounded border border-[#cde0df] px-1.5 py-0.5 text-[0.58rem] font-medium text-[#5b7283]">
                {requiredForLabels[req.required_for]}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}

  <!-- Expand toggle -->
  {#if hasExpandableContent}
    <div class="flex justify-center">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border border-[#c0dcd7] bg-white px-4 py-2 text-[0.68rem] font-semibold text-[#168b88] transition hover:bg-[#f0f8f7]"
        onclick={() => expanded = !expanded}
        aria-expanded={expanded}
      >
        {expanded ? "Cerrar detalle" : "Ver detalle"}
        <span class="text-[0.5rem]">{expanded ? "▲" : "▼"}</span>
      </button>
    </div>
  {/if}

  <!-- Compact product fit -->
  {#if productFitData}
    <div class="rounded-xl border border-[#cde0df] bg-white p-4">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs font-bold uppercase tracking-[0.18em] text-[#168b88]">Posible encaje</p>
          <h3 class="mt-1 text-sm font-semibold leading-5 text-[#102d4f]">{productFitData.product_name}</h3>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-1.5">
          <T360StatusBadge status={productFitData.status} compact />
          {#if typeof productFitData.fit_score === "number"}
            <span class="rounded border border-[#cde0df] px-1.5 py-0.5 text-[0.6rem] font-semibold text-[#168b88]">{productFitData.fit_score}%</span>
          {/if}
        </div>
      </div>
      <p class="mt-2 text-sm leading-5 text-[#5b7283]">{productFitData.summary}</p>

      {#if productFitOpen}
        {#if productFitData.good_fit_reasons?.length}
          <div class="mt-3 rounded-lg bg-[#dff0ed]/50 p-3">
            <p class="text-xs font-bold uppercase tracking-[0.12em] text-[#168b88]">Por qué encaja</p>
            <ul class="mt-1.5 space-y-1">
              {#each productFitData.good_fit_reasons as reason}
                <li class="flex items-start gap-1.5 text-sm leading-5 text-[#203c55]">
                  <span class="mt-0.5 shrink-0 text-[#168b88]">✓</span>
                  <span class="min-w-0 break-words">{reason}</span>
                </li>
              {/each}
            </ul>
          </div>
        {/if}
        {#if productFitData.limitations?.length}
          <div class="mt-2 rounded-lg bg-[#fff3d6]/50 p-3">
            <p class="text-xs font-bold uppercase tracking-[0.12em] text-[#996e1a]">Limitaciones a validar</p>
            <ul class="mt-1.5 space-y-1">
              {#each productFitData.limitations as limitation}
                <li class="flex items-start gap-1.5 text-sm leading-5 text-[#5f4a28]">
                  <span class="mt-0.5 shrink-0 text-[#996e1a]">!</span>
                  <span class="min-w-0 break-words">{limitation}</span>
                </li>
              {/each}
            </ul>
          </div>
        {/if}
        {#if productFitData.recommended_next_step}
          <div class="mt-2 rounded-lg border border-[#d5e2e5] bg-[#f6fbfa] p-3">
            <p class="text-xs font-bold uppercase tracking-[0.12em] text-[#168b88]">Siguiente paso</p>
            <p class="mt-1 text-sm leading-5 text-[#203c55]">{productFitData.recommended_next_step}</p>
          </div>
        {/if}
      {:else if productFitData.good_fit_reasons?.length}
        <button
          type="button"
          class="mt-2 text-xs font-semibold text-[#168b88] underline underline-offset-2 transition hover:text-[#126d6b]"
          onclick={() => productFitOpen = true}
        >
          Ver por qué encaja
        </button>
      {/if}

      {#if productFitOpen && (productFitData.good_fit_reasons?.length || productFitData.limitations?.length || productFitData.recommended_next_step)}
        <button
          type="button"
          class="mt-2 text-xs font-medium text-[#78909f] underline underline-offset-2 transition hover:text-[#476275]"
          onclick={() => productFitOpen = false}
        >
          Cerrar detalle
        </button>
      {/if}

      {#if productFitData.actions?.length}
        <div class="mt-3 border-t border-[#d5e2e5] pt-3">
          <T360ActionButtons
            actions={productFitData.actions}
            sessionId={actionSessionId}
            blockType="product_fit_card"
            disabled={actionDisabled}
          />
        </div>
      {/if}
    </div>
  {/if}

  <!-- Next step -->
  {#if diagnosis.next_step}
    <div class="rounded-xl border border-[#b3d5cf] bg-[#e8f7f4] p-4">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#168b88]">
        {sectionTitle("next_step", locale)}
      </p>
      <p class="mt-1.5 text-sm font-semibold leading-6 text-[#102d4f]">
        {formatNextStep(diagnosis.next_step, locale)}
      </p>
    </div>
  {/if}

  <!-- Unified action buttons -->
  {#if actionButtons.length > 0}
    <div class="border-t border-[#d5e2e5] pt-4">
      <T360ActionButtons
        actions={actionButtons}
        sessionId={actionSessionId}
        blockType={actionBlockType}
        disabled={actionDisabled}
      />
    </div>
  {/if}
</div>
