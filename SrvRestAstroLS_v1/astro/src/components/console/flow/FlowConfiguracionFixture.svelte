<script lang="ts">
  import {
    flowLevelRole,
    type FlowConfigurationLevel,
    type FlowSectorConfiguration,
  } from "../../../lib/t360/flow/configuration";
  import FlowConfiguracion from "./FlowConfiguracion.svelte";

  type SaveMode = "success" | "error";

  let saveMode = $state<SaveMode>("success");
  let saveCount = $state(0);

  function levelsFor(sectorId: string, count: number): FlowConfigurationLevel[] {
    return Array.from({ length: count }, (_, index) => {
      const level = index + 1;
      return {
        id: `${sectorId}-level-${level}`,
        level,
        label: `Nivel ${level}`,
        channel: "email",
        destination: `nivel${level}@${sectorId}.demo.local`,
        active: true,
        role: flowLevelRole(level),
      };
    });
  }

  const configurations: FlowSectorConfiguration[] = [
    ...[1, 3, 5].map((count) => {
      const sectorId = `fixture-${count}`;
      const levels = levelsFor(sectorId, count);
      return {
        sectorId,
        displayName: `Prueba UX · ${count} ${count === 1 ? "nivel" : "niveles"}`,
        active: true,
        levels,
        closureApprovalLevel: count,
        closureSupervisorDestination: levels.at(-1)?.destination ?? "",
      } satisfies FlowSectorConfiguration;
    }),
    {
      sectorId: "fixture-empty",
      displayName: "Prueba UX · sin niveles",
      active: true,
      levels: [],
      closureApprovalLevel: null,
      closureSupervisorDestination: "",
    },
  ];

  async function simulateSave() {
    if (saveMode === "error") throw new Error("save fixture failed");
    saveCount += 1;
  }
</script>

<svelte:head>
  <title>Prueba UX | Configuración de Flow</title>
</svelte:head>

<div class="min-h-screen bg-[#f3f7f7] px-4 py-6 text-[#203c55] sm:px-6 lg:px-10">
  <div class="mx-auto max-w-6xl">
    <div class="mb-5 rounded-2xl border border-[#b9def0] bg-[#e9f6fc] p-4 text-[#1d6688]">
      <p class="text-xs font-bold uppercase tracking-[0.14em]">Prueba interna de validación UX</p>
      <p class="mt-1 text-xs leading-5">Los sectores y guardados de esta página son simulaciones de prueba. No representan catálogo productivo ni persisten datos.</p>
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-2 text-xs font-semibold" for="fixture-save-mode">
          Resultado del callback
          <select id="fixture-save-mode" bind:value={saveMode} class="rounded-lg border border-[#9ecde1] bg-white px-2 py-1.5 text-xs text-[#31536b]">
            <option value="success">Éxito simulado</option>
            <option value="error">Error simulado</option>
          </select>
        </label>
        <span class="text-xs font-semibold" data-save-count>Guardados simulados: {saveCount}</span>
      </div>
    </div>

    <FlowConfiguracion configurations={configurations} apiEnabled={false} persistenceEnabled={true} onSave={simulateSave} />
  </div>
</div>
