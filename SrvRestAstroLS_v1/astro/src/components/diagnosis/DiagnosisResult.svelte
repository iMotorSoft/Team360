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
    class="mb-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm leading-5 text-amber-300"
    role="status"
    aria-live="polite"
    {dir}
    {lang}
  >
    {sectionTitle("fallback_note", locale)}
  </div>
{/if}

<div
  class="mt-6 space-y-5 rounded-[1.5rem] border border-white/10 bg-white/[0.04] p-5 sm:p-6"
  data-testid="diagnosis-result"
  {dir}
  {lang}
>
  <!-- Heading -->
  <div>
    <p class="text-xs font-bold uppercase tracking-[0.18em] text-[#8be1d8]">
      {sectionTitle("diagnosis_heading", locale)}
    </p>
  </div>

  <!-- Feasibility / Mode / Confidence badges -->
  <div class="flex flex-wrap gap-3">
    <div class="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("feasibility", locale)}
      </p>
      <p class="mt-0.5 text-sm font-semibold text-white">
        {formatFeasibility(diagnosis.feasibility, locale)}
      </p>
    </div>
    <div class="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("automation_mode", locale)}
      </p>
      <p class="mt-0.5 text-sm font-semibold text-white">
        {formatAutomationMode(diagnosis.automation_mode, locale)}
      </p>
    </div>
    <div class="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("confidence", locale)}
      </p>
      <p class="mt-0.5 text-sm font-semibold text-white">
        {formatConfidence(diagnosis.confidence, locale)}
      </p>
    </div>
  </div>

  <!-- Availability -->
  <div>
    <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
      {sectionTitle("availability", locale)}
    </p>
    <p class="mt-0.5 text-sm font-semibold text-white">
      {formatAvailability(diagnosis.availability, locale)}
    </p>
  </div>

  <!-- Automatable steps -->
  {#if diagnosis.automatable_steps.length > 0}
    <div>
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("what_can_automate", locale)}
      </p>
      <ul class="mt-2 space-y-1.5">
        {#each diagnosis.automatable_steps as step}
          <li class="flex items-start gap-2 text-sm leading-5 text-white/80">
            <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-[#8be1d8]/10 text-[0.55rem] font-bold text-[#8be1d8]">✓</span>
            <span class="min-w-0 break-words">{formatAutomatableStep(step, locale)}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- Human steps -->
  {#if diagnosis.human_steps.length > 0 || diagnosis.human_approval === "required" || diagnosis.human_approval === "conditional"}
    <div>
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("human_intervention", locale)}
      </p>
      {#if diagnosis.human_approval === "required" || diagnosis.human_approval === "conditional"}
        <p class="mt-1 text-sm font-medium text-white/80">
          {formatHumanApproval(diagnosis.human_approval, locale)}
        </p>
      {/if}
      {#if diagnosis.human_steps.length > 0}
        <ul class="mt-2 space-y-1.5">
          {#each diagnosis.human_steps as step}
            <li class="flex items-start gap-2 text-sm leading-5 text-white/80">
              <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-amber-500/10 text-[0.55rem] font-bold text-amber-400">!</span>
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
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("channels_systems", locale)}
      </p>
      {#if diagnosis.channels.length > 0}
        <div class="mt-2 flex flex-wrap gap-1.5">
          {#each diagnosis.channels as ch}
            <span class="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[0.7rem] font-semibold text-white/70">
              {formatChannel(ch, locale)}
            </span>
          {/each}
        </div>
      {/if}
      {#if diagnosis.systems.length > 0}
        <div class="mt-2 flex flex-wrap gap-1.5">
          {#each diagnosis.systems as sys}
            <span class="rounded-full border border-[#8be1d8]/20 bg-[#8be1d8]/10 px-2.5 py-0.5 text-[0.7rem] font-semibold text-[#8be1d8]">
              {formatSystem(sys, locale)}
            </span>
          {/each}
        </div>
      {/if}
      {#if hasEntitySources}
        <div class="mt-3 space-y-1">
          {#each entityLinks as link}
            <div class="flex min-w-0 flex-wrap items-center gap-2 text-sm leading-5 text-white/80">
              <span class="min-w-0 break-words font-medium">{link.entity}</span>
              <span class="text-white/40">→</span>
              <span class="min-w-0 break-words font-medium text-[#8be1d8]">{link.source}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Risks -->
  {#if diagnosis.risks.length > 0}
    <div>
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-amber-500">
        {sectionTitle("risks", locale)}
      </p>
      <ul class="mt-2 space-y-1.5">
        {#each diagnosis.risks as risk}
          <li class="flex items-start gap-2 text-sm leading-5 text-amber-200/80">
            <span class="mt-0.5 shrink-0 text-amber-500">⚠</span>
            {formatRisk(risk, locale)}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- Assumptions -->
  {#if diagnosis.assumptions.length > 0}
    <div>
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-white/50">
        {sectionTitle("assumptions", locale)}
      </p>
      <ul class="mt-2 space-y-1.5">
        {#each diagnosis.assumptions as assumption}
          <li class="flex items-start gap-2 text-sm leading-5 italic text-white/60">
            <span class="mt-1.5 shrink-0 text-white/40">·</span>
            <span class="min-w-0 break-words">{formatAssumption(assumption, locale)}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- Validation points -->
  {#if diagnosis.validation_points.length > 0}
    <div>
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("validation_points", locale)}
      </p>
      <ul class="mt-2 space-y-1.5">
        {#each diagnosis.validation_points as vp}
          <li class="flex items-start gap-2 text-sm leading-5 text-white/80">
            <span class="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border border-[#8be1d8] text-[0.55rem] font-bold text-[#8be1d8]">?</span>
            <span class="min-w-0 break-words">{formatValidationPoint(vp, locale)}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- Next step -->
  {#if diagnosis.next_step}
    <div class="rounded-xl border border-[#8be1d8]/20 bg-[#8be1d8]/10 p-4">
      <p class="text-[0.6rem] font-bold uppercase tracking-[0.14em] text-[#8be1d8]">
        {sectionTitle("next_step", locale)}
      </p>
      <p class="mt-1.5 text-sm font-semibold leading-6 text-white">
        {formatNextStep(diagnosis.next_step, locale)}
      </p>
    </div>
  {/if}
</div>
