<script lang="ts">
  import { onMount, type Snippet } from "svelte";
  import { Badge } from "../ui";
  import { formatDate } from "../../lib/formatters";
  import { getMockWorkspaceContext, type MockProfileId } from "../../lib/mock";
  import { deriveNavigation } from "../../lib/navigation/derive";
  import type { ConsoleView } from "../../lib/navigation/registry";
  import { consoleContext } from "../../stores/consoleContext.svelte";
  import Breadcrumbs from "./Breadcrumbs.svelte";
  import AlertsList from "./alerts/AlertsList.svelte";
  import ConsoleSectionPage from "./ConsoleSectionPage.svelte";
  import ContextBanner from "./ContextBanner.svelte";
  import ReportsList from "./reports/ReportsList.svelte";
  import RunsList from "./runs/RunsList.svelte";
  import ServiceDetail from "./services/ServiceDetail.svelte";
  import ServicesList from "./services/ServicesList.svelte";
  import WorkspaceSettings from "./settings/WorkspaceSettings.svelte";
  import Sidebar from "./Sidebar.svelte";
  import TasksList from "./tasks/TasksList.svelte";
  import TeamList from "./team/TeamList.svelte";
  import Topbar from "./Topbar.svelte";
  import WorkersList from "./workers/WorkersList.svelte";
  import ConsoleDashboard from "./dashboard/ConsoleDashboard.svelte";
  import ConsoleDiagnosis from "./diagnosis/ConsoleDiagnosis.svelte";

  let {
    view,
    initialWorkspaceId,
    serviceId,
    children,
  }: {
    view: ConsoleView;
    initialWorkspaceId: string;
    serviceId?: string;
    children?: Snippet;
  } = $props();

  let mobileOpen = $state(false);

  function initializeForRoute() {
    consoleContext.initialize("team360_admin", initialWorkspaceId);
  }

  initializeForRoute();

  const navigationGroups = $derived(deriveNavigation(consoleContext.bootstrap));
  const workspaceContext = $derived(getMockWorkspaceContext(consoleContext.activeWorkspace.id));
  const pendingTasks = $derived(workspaceContext.tasks.filter(({ status }) => status !== "completed"));
  const recentReports = $derived(workspaceContext.reports.slice(0, 3));

  onMount(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedProfile = params.get("profile") as MockProfileId | null;
    const profile = consoleContext.mockProfiles.some(({ id }) => id === requestedProfile) ? requestedProfile! : "team360_admin";

    consoleContext.initialize(profile, initialWorkspaceId);

    const locale = params.get("locale");
    if (locale) {
      consoleContext.setLocale(locale);
    }
  });
</script>

<div class="min-h-screen bg-[#f3f7f7] text-[#203c55]" dir={consoleContext.direction}>
  <Sidebar groups={navigationGroups} {view} {mobileOpen} onClose={() => (mobileOpen = false)} />

  <div class="min-h-screen lg:ps-[18.5rem]">
    <Topbar onMenu={() => (mobileOpen = true)} />

    <div class="mx-auto max-w-[104rem] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
      <Breadcrumbs {view} />
      <div class="mt-4">
        <ContextBanner />
      </div>

      <div class="mt-6 grid gap-6 2xl:grid-cols-[minmax(0,1fr)_17rem]">
        <main id="contenido-consola" class="min-w-0">
          {#if children}
            {@render children()}
          {:else if serviceId}
            <ServiceDetail {serviceId} />
          {:else if view === "home"}
            <ConsoleDashboard />
          {:else if view === "services"}
            <ServicesList />
          {:else if view === "reports"}
            <ReportsList />
          {:else if view === "alerts"}
            <AlertsList />
          {:else if view === "tasks"}
            <TasksList />
          {:else if view === "team"}
            <TeamList />
          {:else if view === "settings"}
            <WorkspaceSettings />
          {:else if view === "workers"}
            <WorkersList />
          {:else if view === "runs"}
            <RunsList />
          {:else if view === "diagnosis"}
            <ConsoleDiagnosis />
          {:else}
            <ConsoleSectionPage {view} />
          {/if}
        </main>

        <aside class="hidden space-y-4 2xl:block">
          <section class="rounded-2xl border border-[#e0e8ea] bg-white p-4">
            <p class="text-[0.65rem] font-bold uppercase tracking-[0.17em] text-[#168b88]">Workspace activo</p>
            <p class="mt-2 text-sm font-bold text-[#31536b]">{consoleContext.activeWorkspace.name}</p>
            <p class="mt-1 text-xs leading-5 text-[#8396a2]">{consoleContext.activeOrganization.name}</p>
            <div class="mt-4 flex flex-wrap gap-2">
              <Badge variant="info" class="h-auto px-2 py-1 text-[0.6rem]">{consoleContext.activeWorkspace.locale}</Badge>
              <Badge variant="neutral" class="h-auto px-2 py-1 text-[0.6rem]">{consoleContext.activeWorkspace.direction}</Badge>
            </div>
          </section>

          <section class="rounded-2xl border border-[#e0e8ea] bg-white p-4">
            <p class="text-[0.65rem] font-bold uppercase tracking-[0.17em] text-[#168b88]">Pendientes</p>
            <div class="mt-3 space-y-3">
              {#each pendingTasks.slice(0, 3) as task}
                <article class="border-b border-[#edf1f2] pb-3 last:border-0 last:pb-0">
                  <p class="text-xs font-bold leading-5 text-[#47657b]">{task.title}</p>
                  <p class="mt-1 text-[0.67rem] text-[#91a2ad]">Vence {formatDate(task.dueDate, consoleContext.locale)}</p>
                </article>
              {:else}
                <p class="text-xs leading-5 text-[#8396a2]">No hay tareas pendientes.</p>
              {/each}
            </div>
          </section>

          <section class="rounded-2xl border border-[#e0e8ea] bg-white p-4">
            <p class="text-[0.65rem] font-bold uppercase tracking-[0.17em] text-[#168b88]">Reportes recientes</p>
            <div class="mt-3 space-y-3">
              {#each recentReports as report}
                <article class="border-b border-[#edf1f2] pb-3 last:border-0 last:pb-0">
                  <p class="text-xs font-bold leading-5 text-[#47657b]">{report.title}</p>
                  <p class="mt-1 text-[0.67rem] text-[#91a2ad]">{report.period}</p>
                </article>
              {:else}
                <p class="text-xs leading-5 text-[#8396a2]">Aún no hay reportes en este workspace.</p>
              {/each}
            </div>
          </section>
        </aside>
      </div>
    </div>
  </div>
</div>
