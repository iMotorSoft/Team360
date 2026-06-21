<script lang="ts">
  import { onMount } from "svelte";
  import {
    t360DiagnosisFixture,
    t360InteractionBlockFixtures,
    t360InteractionFixtureSessionId,
  } from "./fixtures";
  import T360DiagnosisSummary from "./T360DiagnosisSummary.svelte";
  import T360InteractionRenderer from "./T360InteractionRenderer.svelte";

  type EventLogEntry = {
    id: number;
    name: string;
    detail: unknown;
  };

  let eventLog = $state<EventLogEntry[]>([]);
  let eventCounter = 0;

  function pushEvent(name: string, detail: unknown) {
    eventCounter += 1;
    eventLog = [
      {
        id: eventCounter,
        name,
        detail,
      },
      ...eventLog,
    ].slice(0, 6);
  }

  onMount(() => {
    const eventNames = ["t360action", "t360choice", "t360choices"];
    const handler = (event: Event) => {
      pushEvent(event.type, event instanceof CustomEvent ? event.detail : null);
    };

    eventNames.forEach((eventName) => window.addEventListener(eventName, handler));
    return () => eventNames.forEach((eventName) => window.removeEventListener(eventName, handler));
  });
</script>

<div class="mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8" data-testid="t360-interaction-lab">
  <header class="flex flex-col gap-2">
    <p class="text-xs font-bold uppercase text-primary">Team360 interaction lab</p>
    <h1 class="text-2xl font-bold leading-tight sm:text-3xl">Interaction blocks</h1>
    <p class="max-w-3xl text-sm leading-6 text-base-content/65">
      Fixtures locales para validar componentes seguros de diálogos operativos sin backend ni HTML dinámico.
    </p>
  </header>

  <section class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
    <div class="flex flex-col gap-3">
      {#each t360InteractionBlockFixtures as block}
        <T360InteractionRenderer block={block} sessionId={t360InteractionFixtureSessionId} />
      {/each}

      <T360DiagnosisSummary diagnosis={t360DiagnosisFixture} sessionId={t360InteractionFixtureSessionId} />
    </div>

    <aside class="card bg-base-100 border border-base-300 shadow-sm lg:sticky lg:top-4 lg:self-start" data-testid="t360-event-log">
      <div class="card-body p-4">
        <div class="flex items-center justify-between gap-3">
          <h2 class="text-base font-bold leading-6">Eventos</h2>
          <span class="badge badge-outline h-auto px-2 py-1 text-xs">{eventLog.length}</span>
        </div>

        {#if eventLog.length === 0}
          <p class="text-sm leading-6 text-base-content/60">Sin eventos emitidos todavía.</p>
        {:else}
          <div class="flex flex-col gap-2">
            {#each eventLog as entry}
              <article class="rounded-box border border-base-300 bg-base-200 p-2" data-testid="t360-event-log-entry">
                <p class="text-xs font-bold text-base-content">{entry.name}</p>
                <pre class="mt-1 max-h-28 overflow-auto whitespace-pre-wrap break-words text-[0.68rem] leading-5 text-base-content/65">{JSON.stringify(entry.detail, null, 2)}</pre>
              </article>
            {/each}
          </div>
        {/if}
      </div>
    </aside>
  </section>
</div>
