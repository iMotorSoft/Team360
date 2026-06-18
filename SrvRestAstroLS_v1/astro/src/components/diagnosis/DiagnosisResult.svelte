<script lang="ts">
  import type { StructuredDiagnosis } from "../../lib/api/publicDiagnosis";
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

  let {
    diagnosis,
    isFallback,
    locale = "es",
  }: {
    diagnosis: StructuredDiagnosis;
    isFallback?: boolean;
    locale?: string;
  } = $props();

  const dir = $derived(directionForLocale(locale));
  const lang = $derived(langAttr(locale));

  const entityLinks = $derived(formatEntitySources(diagnosis.entity_sources, locale));
  const hasEntitySources = $derived(Object.keys(diagnosis.entity_sources).length > 0);
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
</div>
