import { expect, test, type Page } from "@playwright/test";

const CONFIG_URL = "/w/ws-team360-control/flow/configuracion";
const FIXTURE_URL = "/demo/flow/configuracion-fixtures";
const REAL_LIST_URL = "**/api/team360-flow/configuration";
const OPERATIONAL_SETTINGS_URL = "**/api/team360-flow/operational-settings";
const SCHEDULER_STATUS_URL = "**/api/team360-flow/scheduler/status";

function schedulerStatus(cycleCount: number, overrides: Record<string, unknown> = {}) {
  return {
    last_started_at_utc: "2026-08-23T22:28:12.333278Z",
    last_finished_at_utc: "2026-08-23T22:28:13.575496Z",
    last_result: "PASS",
    last_error_class: null,
    processed_count: 3,
    cycle_count: cycleCount,
    ...overrides,
  };
}

function schedulerStatusPanel(page: Page) {
  return page.locator("section").filter({
    has: page.getByRole("heading", { name: "Último ciclo ejecutado" }),
  });
}

async function openConfiguration(page: Page, url = CONFIG_URL) {
  await page.goto(url);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible().catch(async () => {
    await expect(page.getByRole("heading", { name: /Sectores y niveles/ })).toBeVisible();
  });
}

async function waitForRealConfig(page: Page) {
  await expect(page.getByText("Configuración persistente", { exact: true }).first()).toBeVisible();
}

function trackErrors(page: Page, errors: string[]) {
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("favicon")) errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => errors.push(`requestfailed: ${request.url()}`));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `overflow horizontal: ${overflow}`).toBeLessThanOrEqual(1);
}

async function expectEditableConfigurationFields(page: Page) {
  const editor = page.locator('[data-flow-config-editor]');
  await expect(editor.getByLabel("Destinatario", { exact: true })).toHaveCount(3);
  await expect(editor.getByRole("spinbutton", { name: /Tiempo máximo de primera respuesta/ })).toHaveCount(3);
  await expect(editor.getByRole("textbox", { name: /Email del supervisor/ })).toHaveCount(1);
}

test.describe("Flow Configuración — MVP sin login (datos reales)", () => {
  test("sin token carga la configuración real de PostgreSQL", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    const apiResponses: number[] = [];
    page.on("response", (response) => {
      if (response.url().includes("/api/team360-flow/configuration")) apiResponses.push(response.status());
    });

    await openConfiguration(page);
    await waitForRealConfig(page);

    await expect(page.getByRole("heading", { name: "Sectores y niveles" })).toBeVisible();
    await expect(page.getByRole("listbox", { name: "Seleccionar sector" }).getByRole("option", { name: /Alumbrado Público/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Niveles de atención" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Supervisor de cierre" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();

    expect(apiResponses.length).toBeGreaterThan(0);
    expect(apiResponses.every((status) => status === 200), `statuses: ${apiResponses}`).toBe(true);
    expect(errors).toEqual([]);
  });

  test("refresh directo conserva la configuración real sin login", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.reload();
    await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
    await waitForRealConfig(page);
    await expect(page.getByText("alumbrado.n1@alquimiablue.com", { exact: true }).first()).toBeVisible();
  });

  test("sin token: editar, guardar, recargar persiste y restaurar original", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    // ORIGINAL desde la vista real.
    const original = "alumbrado.n1@alquimiablue.com";
    const temporary = "mvp.temporal.n1@alquimiablue.com";

    // Editar -> cambiar N1 -> Guardar.
    await page.getByRole("button", { name: "Editar configuración" }).click();
    const first = page.locator('#flow-destination-alumbrado-level-1');
    await expect(first).toHaveValue(original);
    await first.fill(temporary);
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByText("Cambios guardados.", { exact: true })).toBeVisible();

    // Reload: el valor persistido permanece (no fake persistence).
    await page.reload();
    await waitForRealConfig(page);
    await expect(page.getByText(temporary, { exact: true }).first()).toBeVisible();

    // Restaurar ORIGINAL por la UI.
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-alumbrado-level-1').fill(original);
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByText("Cambios guardados.", { exact: true })).toBeVisible();
    await page.reload();
    await waitForRealConfig(page);
    await expect(page.getByText(original, { exact: true }).first()).toBeVisible();
    await expect(page.getByText(temporary, { exact: true })).toHaveCount(0);
  });

  test("error del backend no reemplaza por datos demo", async ({ page }) => {
    await page.route(REAL_LIST_URL, (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
    );
    await openConfiguration(page);
    await expect(page.getByText("No se pudo cargar", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Configuración preparada", { exact: true })).toHaveCount(0);
    await expect(page.getByText("alumbrado.n1@alquimiablue.com", { exact: true })).toHaveCount(0);
  });

  test("persist operational settings and render scheduler status", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    const endpoint = "/api/team360-flow/operational-settings";
    const beforeResponse = await page.request.get(endpoint);
    expect(beforeResponse.ok()).toBe(true);
    const original = await beforeResponse.json();
    const temporaryCutoff = Math.min(original.mail_cutoff_epoch + 45, 1893456000);
    const temporary = {
      automation_enabled: false,
      scheduler_interval_seconds: 20,
      mail_intake_enabled: false,
      mail_batch_limit: 17,
      mail_after_cutoff: true,
      mail_cutoff_epoch: temporaryCutoff,
    };

    try {
      await page.getByRole("button", { name: "Editar operación" }).click();

      async function setSwitch(name: string, expected: boolean) {
        const control = page.getByRole("switch", { name });
        const current = (await control.getAttribute("aria-checked")) === "true";
        if (current !== expected) await control.click();
      }

      await setSwitch("Automatización habilitada", temporary.automation_enabled);
      await setSwitch("Intake de correo habilitado", temporary.mail_intake_enabled);
      await setSwitch("Protección histórica", temporary.mail_after_cutoff);
      await page.getByRole("spinbutton", { name: "Frecuencia del scheduler" }).fill("20");
      await page.getByRole("spinbutton", { name: "Lote máximo de correo" }).fill("17");
      await page.getByRole("spinbutton", { name: "Corte histórico epoch UTC" }).fill(String(temporaryCutoff));
      await page.getByRole("button", { name: "Guardar operación" }).click();
      await expect(page.getByText("Ajustes operacionales guardados.", { exact: true })).toBeVisible();

      await page.reload();
      await waitForRealConfig(page);

      const scheduler = page.locator("section").filter({
        has: page.getByRole("heading", { name: "Configuración del scheduler" }),
      });
      await expect(scheduler.getByText("INACTIVA", { exact: true })).toBeVisible();
      await expect(scheduler.getByText("20s", { exact: true })).toBeVisible();
      await expect(scheduler.getByText("INACTIVO", { exact: true })).toBeVisible();
      await expect(scheduler.getByText("17", { exact: true })).toBeVisible();
      await expect(scheduler.getByText(String(temporaryCutoff), { exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Último ciclo ejecutado" })).toBeVisible();

      const persistedResponse = await page.request.get(endpoint);
      expect(await persistedResponse.json()).toEqual(temporary);
    } finally {
      const restoreResponse = await page.request.patch(endpoint, { data: original });
      expect(restoreResponse.ok()).toBe(true);
    }
  });

  test("cutoff inválido bloquea el guardado operacional", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar operación" }).click();
    const cutoff = page.getByRole("spinbutton", { name: "Corte histórico epoch UTC" });
    await cutoff.fill("0");
    await expect(page.getByText("El corte debe ser un epoch UTC válido entre 2020 y 2030.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar operación" })).toBeDisabled();
    await page.getByRole("button", { name: "Cancelar" }).last().click();
  });
});

test.describe("Flow Configuración — estado vivo del scheduler", () => {
  test("carga el estado inicial y actualiza ciclos, resultado y último ciclo sin reload", async ({ page }) => {
    await page.clock.install();
    let statusRequests = 0;
    await page.route(SCHEDULER_STATUS_URL, async (route) => {
      statusRequests += 1;
      const response = statusRequests === 1
        ? schedulerStatus(42)
        : schedulerStatus(43, {
            last_started_at_utc: "2026-08-23T22:28:22.333278Z",
            last_finished_at_utc: "2026-08-23T22:28:23.575496Z",
            last_result: "DEGRADED",
            processed_count: 4,
          });
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
    });

    await openConfiguration(page);
    await waitForRealConfig(page);
    const panel = schedulerStatusPanel(page);
    await expect(panel.getByText("42", { exact: true })).toBeVisible();
    await expect(panel.getByText("PASS", { exact: true })).toBeVisible();
    const initialLastCycle = await panel.locator("div").filter({ hasText: "Último ciclo" }).last().innerText();

    await page.clock.fastForward(10_000);

    await expect.poll(() => statusRequests).toBe(2);
    await expect(panel.getByText("43", { exact: true })).toBeVisible();
    await expect(panel.getByText("DEGRADED", { exact: true })).toBeVisible();
    await expect(panel.getByText("4", { exact: true })).toBeVisible();
    await expect.poll(async () => panel.locator("div").filter({ hasText: "Último ciclo" }).last().innerText())
      .not.toBe(initialLastCycle);
  });

  test("conserva el último estado válido y se recupera de un error temporal", async ({ page }) => {
    await page.clock.install();
    let statusRequests = 0;
    await page.route(SCHEDULER_STATUS_URL, async (route) => {
      statusRequests += 1;
      if (statusRequests === 2) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "temporary" }) });
        return;
      }
      const response = statusRequests === 1
        ? schedulerStatus(42)
        : schedulerStatus(44, { processed_count: 5 });
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
    });

    await openConfiguration(page);
    await waitForRealConfig(page);
    const panel = schedulerStatusPanel(page);
    await expect(panel.getByText("42", { exact: true })).toBeVisible();

    await page.clock.fastForward(10_000);
    await expect.poll(() => statusRequests).toBe(2);
    await expect(panel.getByText("42", { exact: true })).toBeVisible();

    await page.clock.fastForward(10_000);
    await expect.poll(() => statusRequests).toBe(3);
    await expect(panel.getByText("44", { exact: true })).toBeVisible();
    await expect(panel.getByText("5", { exact: true })).toBeVisible();
  });

  test("refresca el status inmediatamente después de guardar operación", async ({ page }) => {
    await page.clock.install();
    const requestOrder: string[] = [];
    let statusRequests = 0;
    let operationalSettings = {
      automation_enabled: false,
      scheduler_interval_seconds: 15,
      mail_intake_enabled: true,
      mail_batch_limit: 500,
      mail_after_cutoff: true,
      mail_cutoff_epoch: 1787239323,
    };

    await page.route(SCHEDULER_STATUS_URL, async (route) => {
      statusRequests += 1;
      requestOrder.push("status");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(schedulerStatus(statusRequests === 1 ? 42 : 43)),
      });
    });
    await page.route(OPERATIONAL_SETTINGS_URL, async (route) => {
      if (route.request().method() === "PATCH") {
        requestOrder.push("patch");
        operationalSettings = { ...operationalSettings, ...(route.request().postDataJSON() as object) };
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(operationalSettings),
      });
    });

    await openConfiguration(page);
    await waitForRealConfig(page);
    const panel = schedulerStatusPanel(page);
    await expect(panel.getByText("42", { exact: true })).toBeVisible();
    expect(statusRequests).toBe(1);

    await page.getByRole("button", { name: "Editar operación" }).click();
    await page.getByRole("switch", { name: "Automatización habilitada" }).click();
    await page.getByRole("button", { name: "Guardar operación" }).click();

    await expect(page.getByText("Ajustes operacionales guardados.", { exact: true })).toBeVisible();
    await expect.poll(() => statusRequests).toBe(2);
    expect(requestOrder.slice(-2)).toEqual(["patch", "status"]);
    await expect(panel.getByText("43", { exact: true })).toBeVisible();
  });

  test("evita fetches superpuestos y cancela el polling al desmontar", async ({ page }) => {
    await page.clock.install();
    let statusRequests = 0;
    let releasePendingRequest: (() => void) | undefined;
    await page.route(SCHEDULER_STATUS_URL, async (route) => {
      statusRequests += 1;
      if (statusRequests === 2) {
        await new Promise<void>((resolve) => {
          releasePendingRequest = resolve;
        });
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(schedulerStatus(statusRequests === 1 ? 42 : 43)),
      });
    });

    await openConfiguration(page);
    await waitForRealConfig(page);
    await expect(schedulerStatusPanel(page).getByText("42", { exact: true })).toBeVisible();

    await page.clock.fastForward(10_000);
    await expect.poll(() => statusRequests).toBe(2);
    await page.clock.fastForward(20_000);
    expect(statusRequests).toBe(2);

    releasePendingRequest?.();
    await expect(schedulerStatusPanel(page).getByText("43", { exact: true })).toBeVisible();
    await page.getByRole("navigation", { name: "Navegación de consola" }).getByRole("link", { name: "Directorio" }).click();
    await expect(page).toHaveURL(/\/flow\/?$/);
    await page.clock.fastForward(30_000);
    expect(statusRequests).toBe(2);
  });
});

test.describe("Flow Configuración — vista y navegación", () => {
  test("muestra sector, circuito operativo y supervisor separado", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openConfiguration(page);
    await waitForRealConfig(page);

    await expect(page.getByRole("heading", { name: "Sectores y niveles" })).toBeVisible();
    await expect(page.getByRole("listbox", { name: "Seleccionar sector" }).getByRole("option", { name: /Alumbrado Público/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Niveles de atención" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Supervisor de cierre" })).toBeVisible();
    await expect(page.getByText("Autoriza la resolución final del caso.")).toBeVisible();
    await expect(page.getByText("no un nivel adicional de escalamiento.")).toBeVisible();
    await expect(page.getByText("Configuración persistente", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("preserva la navegación Flow y no agrega controles a otros módulos", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    const nav = page.getByRole("navigation", { name: "Navegación de consola" });
    await expect(nav.locator('a[href*="/flow/configuracion"]')).toBeVisible();
    await nav.getByRole("link", { name: "Directorio" }).click();
    await expect(page).toHaveURL(/\/flow\/?$/);
    await expect(page.getByRole("heading", { name: "Vista Ejecutiva" })).toBeVisible();
  });
});

test.describe("Flow Configuración — draft y validación", () => {
  test("Editar sin cambios mantiene Guardar deshabilitado", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();

    await expect(page.getByText("Sin cambios", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeVisible();
    await expectEditableConfigurationFields(page);
  });

  test("cambio válido activa dirty y un email inválido queda asociado al campo", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();

    const first = page.locator('#flow-destination-alumbrado-level-1');
    await first.fill("alumbrado.n1");
    await first.blur();
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
    await expect(first).toHaveAttribute("aria-invalid", "true");
    await expect(first).toHaveAttribute("aria-describedby", "flow-error-alumbrado-level-1");
    await expect(page.getByText("Ingresá un email válido", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeDisabled();

    await first.fill("  alumbrado.nuevo@alquimiablue.com  ");
    await first.blur();
    await expect(first).toHaveAttribute("aria-invalid", "false");
    await expect(page.getByText("Ingresá un email válido", { exact: true })).toHaveCount(0);
  });

  test("vacío y formato sin dominio muestran mensajes de producto", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();
    const first = page.locator('#flow-destination-alumbrado-level-1');

    await first.fill("");
    await first.blur();
    await expect(page.getByText("El destinatario es obligatorio", { exact: true })).toBeVisible();
    await first.fill("@alquimiablue.com");
    await first.blur();
    await expect(page.getByText("Ingresá un email válido", { exact: true })).toBeVisible();
  });

  test("SLA inválido muestra validación y no habilita Guardar", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();

    const firstSla = page.getByRole("spinbutton", { name: /Tiempo máximo de primera respuesta/ }).first();
    await firstSla.fill("0");
    await firstSla.blur();
    await expect(page.getByText("El SLA debe ser un entero positivo", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeDisabled();

    await firstSla.fill("45");
    await firstSla.blur();
    await expect(page.getByText("El SLA debe ser un entero positivo", { exact: true })).toHaveCount(0);
  });

  test("Cancelar descarta el draft y restaura la configuración guardada", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();
    const first = page.locator('#flow-destination-alumbrado-level-1');
    const original = await first.inputValue();
    await first.fill("cambio.temporal@alquimiablue.com");
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancelar" }).click();

    await expect(page.getByText("Los cambios se descartaron. La configuración guardada no fue modificada.")).toBeVisible();
    await expect(page.getByText(original, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();
    await expect(page.locator('[data-flow-config-editor] input')).toHaveCount(0);
  });

  test("focus visible y teclado llegan al campo y a las acciones", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConfiguration(page);
    await waitForRealConfig(page);
    await page.getByRole("button", { name: "Editar configuración" }).focus();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator('#flow-destination-alumbrado-level-1')).toBeVisible();
    await page.locator('#flow-destination-alumbrado-level-1').focus();
    await expect(page.locator('#flow-destination-alumbrado-level-1')).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeFocused();
  });
});

test.describe("Flow Configuración — callbacks y niveles dinámicos (fixture)", () => {
  test("representa 1, 3 y 5 niveles sin selectores rígidos", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await expect(page.getByText("Prueba interna de validación UX")).toBeVisible();
    const selector = page.getByRole("listbox", { name: "Seleccionar sector" });
    const editor = page.locator('[data-flow-config-editor]');

    await selector.getByRole("option", { name: /Prueba UX · 1 nivel/ }).click();
    await expect(editor.locator("article")).toHaveCount(1);
    await selector.getByRole("option", { name: /Prueba UX · 3 niveles/ }).click();
    await expect(editor.locator("article")).toHaveCount(3);
    await selector.getByRole("option", { name: /Prueba UX · 5 niveles/ }).click();
    await expect(editor.locator("article")).toHaveCount(5);
    await expect(editor.getByRole("heading", { name: "Supervisor de cierre" })).toBeVisible();
    await selector.getByRole("option", { name: /Prueba UX · sin niveles/ }).click();
    await expect(editor.getByText("Este sector todavía no tiene niveles")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("cambiar de sector con draft no descarta cambios en silencio", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    const selector = page.getByRole("listbox", { name: "Seleccionar sector" });
    await selector.getByRole("option", { name: /Prueba UX · 3 niveles/ }).click();
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-fixture-3-level-1').fill("pendiente@fixture.demo.local");
    await selector.getByRole("option", { name: /Prueba UX · 5 niveles/ }).click();

    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("button", { name: "Seguir editando" }).click();
    await expect(page.getByRole("heading", { name: /3 niveles/ })).toBeVisible();
    await selector.getByRole("option", { name: /Prueba UX · 5 niveles/ }).click();
    await page.getByRole("button", { name: "Descartar y cambiar" }).click();
    await expect(page.getByRole("heading", { name: /5 niveles/ })).toBeVisible();
    await expect(page.locator('[data-flow-config-editor] input')).toHaveCount(0);
  });

  test("callback simulado exitoso muestra feedback y no usa persistencia", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    const selector = page.getByRole("listbox", { name: "Seleccionar sector" });
    await selector.getByRole("option", { name: /Prueba UX · 3 niveles/ }).click();
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-fixture-3-level-1').fill("nuevo@fixture.demo.local");
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("Cambios guardados.", { exact: true })).toBeVisible();
    await expect(page.locator("[data-save-count]")).toHaveText("Guardados simulados: 1");
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();
  });

  test("callback simulado fallido conserva el draft y muestra error", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await page.locator("#fixture-save-mode").selectOption("error");
    await page.getByRole("listbox", { name: "Seleccionar sector" }).getByRole("option", { name: /Prueba UX · 1 nivel/ }).click();
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-fixture-1-level-1').fill("otro@fixture.demo.local");
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("No se pudieron guardar los cambios. Revisá el formulario e intentá nuevamente.")).toBeVisible();
    await expect(page.locator('#flow-destination-fixture-1-level-1')).toHaveValue("otro@fixture.demo.local");
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeVisible();
  });
});

test.describe("Flow Configuración — supervisor de cierre (nivel que aprueba)", () => {
  test("cambiar el nivel de aprobación persiste y reaparece tras reload", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    // Estado inicial real: N2 aprueba (vista de solo lectura).
    await expect(page.getByText("Autoridad N2", { exact: true })).toBeVisible();

    // Editar -> aprobar desde N3 -> el destino del supervisor sigue a N3.
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await expect(page.getByRole("radio", { name: "Nivel 2 aprueba el cierre" })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("radio", { name: "Nivel 3 aprueba el cierre" }).click();
    await expect(page.getByRole("radio", { name: "Nivel 3 aprueba el cierre" })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "Nivel 2 aprueba el cierre" })).toHaveAttribute("aria-checked", "false");
    await expect(page.locator("#flow-closure-supervisor")).toHaveValue("alumbrado.n3@alquimiablue.com");
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByText("Cambios guardados.", { exact: true })).toBeVisible();

    await page.reload();
    await waitForRealConfig(page);
    await expect(page.getByText("Autoridad N3", { exact: true })).toBeVisible();

    // Restaurar el ORIGINAL (N2) por la UI.
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.getByRole("radio", { name: "Nivel 2 aprueba el cierre" }).click();
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByText("Cambios guardados.", { exact: true })).toBeVisible();
    await page.reload();
    await waitForRealConfig(page);
    await expect(page.getByText("Autoridad N2", { exact: true })).toBeVisible();
  });

  test("cambiar el email de N2 actualiza el destino del supervisor", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator("#flow-destination-alumbrado-level-2").fill("supervisor.temporal.n2@alquimiablue.com");
    await expect(page.locator("#flow-closure-supervisor")).toHaveValue("supervisor.temporal.n2@alquimiablue.com");

    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByText("Los cambios se descartaron. La configuración guardada no fue modificada.")).toBeVisible();
  });
});

test.describe("Flow Configuración — fallos de guardado (backend)", () => {
  test("PATCH 403: no muestra Guardado, conserva el draft y permite reintentar", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator("#flow-destination-alumbrado-level-1").fill("fallo403.n1@alquimiablue.com");

    await page.route("**/api/team360-flow/configuration/alumbrado", (route) =>
      route.request().method() === "PATCH"
        ? route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Forbidden" }) })
        : route.continue(),
    );
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("Tu rol no tiene permiso para modificar la configuración de Flow.")).toBeVisible();
    await expect(page.getByText("Cambios guardados.", { exact: true })).toHaveCount(0);
    // El draft se conserva para reintento.
    await expect(page.locator("#flow-destination-alumbrado-level-1")).toHaveValue("fallo403.n1@alquimiablue.com");
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeVisible();
  });

  test("PATCH 422: el backend rechaza y el draft queda intacto", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator("#flow-destination-alumbrado-level-1").fill("fallo422.n1@alquimiablue.com");

    await page.route("**/api/team360-flow/configuration/alumbrado", (route) =>
      route.request().method() === "PATCH"
        ? route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: "destination no es un email válido" }) })
        : route.continue(),
    );
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("El backend rechazó los cambios. Revisá los destinatarios e intentá nuevamente.")).toBeVisible();
    await expect(page.locator("#flow-destination-alumbrado-level-1")).toHaveValue("fallo422.n1@alquimiablue.com");
  });

  test("PATCH 500: error de servicio sin estado Guardado y con reintento posible", async ({ page }) => {
    await openConfiguration(page);
    await waitForRealConfig(page);

    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator("#flow-destination-alumbrado-level-1").fill("fallo500.n1@alquimiablue.com");

    await page.route("**/api/team360-flow/configuration/alumbrado", (route) =>
      route.request().method() === "PATCH"
        ? route.fulfill({ status: 500, contentType: "application/json", body: "{}" })
        : route.continue(),
    );
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("No se pudieron guardar los cambios. Intentá nuevamente en unos instantes.")).toBeVisible();
    await expect(page.getByText("Cambios guardados.", { exact: true })).toHaveCount(0);
    await expect(page.locator("#flow-destination-alumbrado-level-1")).toHaveValue("fallo500.n1@alquimiablue.com");
  });
});

test.describe("Flow Configuración — responsive y consola", () => {
  for (const [name, width, height] of [["390", 390, 844], ["768", 768, 1024], ["1024", 1024, 768], ["1280", 1280, 900]] as const) {
    test(`view y edit sin overflow en ${name}px`, async ({ page }) => {
      const errors: string[] = [];
      trackErrors(page, errors);
      await page.setViewportSize({ width, height });
      await openConfiguration(page);
      await waitForRealConfig(page);
      await expectNoHorizontalOverflow(page);
      await page.getByRole("button", { name: "Editar configuración" }).click();
      await expectEditableConfigurationFields(page);
      await expectNoHorizontalOverflow(page);
      await page.locator('#flow-destination-alumbrado-level-1').fill("direccion.muy.larga.para.validar.el.layout@alquimiablue.com");
      await page.locator('#flow-destination-alumbrado-level-1').blur();
      await expectNoHorizontalOverflow(page);
      await page.getByRole("button", { name: "Cancelar" }).click();
      expect(errors).toEqual([]);
    });
  }
});
