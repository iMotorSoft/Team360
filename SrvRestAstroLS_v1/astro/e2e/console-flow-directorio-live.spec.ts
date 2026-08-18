import { test, expect, type Page } from "@playwright/test";

// Team360 Flow — Directorio Premium V1 (modo LIVE)
// Requiere el runtime oficial: backend-dev.sh (7050) + astro-dev.sh (3050).
// Ejecutar con PLAYWRIGHT_SKIP_WEBSERVER=1 y PLAYWRIGHT_BASE_URL=http://127.0.0.1:3050.
// Consume datos REALES de PostgreSQL vía GET /api/team360-flow/executive/{id};
// no envía emails y no muta el workflow.

const DIRECTORIO_URL = "/w/ws-team360-control/flow";

async function openFlow(page: Page) {
  await page.goto(DIRECTORIO_URL);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
  await expect(page.getByText("Backend Flow · datos reales", { exact: true })).toBeVisible();
}

function trackErrors(page: Page, errors: string[]) {
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon")) errors.push(`console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("requestfailed", (req) => errors.push(`requestfailed: ${req.url()}`));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflow, `overflow horizontal esperado <= 1, fue ${overflow}`).toBeLessThanOrEqual(1);
}

async function selectCaseByText(page: Page, text: string) {
  await page.locator("ul li button", { hasText: text }).click();
}

function detailSection(page: Page) {
  return page.locator('[data-selected="yes"]');
}

test.describe("Flow Directorio LIVE — listado y KPIs", () => {
  test("carga casos reales del backend con indicadores derivados", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const rows = page.locator("ul li button");
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    expect(count, "debe haber al menos 10 casos reales").toBeGreaterThanOrEqual(10);

    for (const prefix of ["#814f38ce", "#c92d739c", "#333a15d0", "#d16a0a08"]) {
      await expect(page.locator("ul li button", { hasText: prefix }).first()).toBeVisible();
    }

    // Ordenado por confirmación descendente: el caso más reciente primero.
    await expect(rows.first()).toContainText("#9285797d");

    const articles = page.locator("main article");
    await expect(articles).toHaveCount(5);

    async function kpiValue(label: string) {
      const text = await page.locator("article", { hasText: label }).first().innerText();
      const match = text.match(/\n(\d+)\n/);
      return match ? Number(match[1]) : null;
    }

    expect(await kpiValue("Resueltos")).toBeGreaterThanOrEqual(1);
    expect(await kpiValue("Pendientes de aprobación")).toBe(1);

    await expect(page.getByText(/Indicadores calculados sobre los \d+ casos disponibles/)).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("filtros y búsqueda funcionan sobre datos reales", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const tabs = page.getByRole("tablist", { name: "Filtrar casos" });
    const rows = page.locator("ul li button");

    await tabs.getByRole("tab", { name: "Pendientes" }).click();
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("#d16a0a08");

    await tabs.getByRole("tab", { name: "Resueltos" }).click();
    await expect(rows.first()).toBeVisible();
    await expect(rows.first()).toContainText("#9285797d");

    await tabs.getByRole("tab", { name: "Todos" }).click();
    const search = page.getByRole("searchbox", { name: "Buscar caso" });
    await search.fill("plaza central");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("#814f38ce");

    await search.fill("zzzz-inexistente");
    await expect(page.getByText("No hay casos que coincidan")).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio LIVE — detalle por estado", () => {
  test("caso ACTIVE con cierre rechazado: motivo visible y sin cierre falso", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria intermitente en la avenida");
    const detail = detailSection(page);

    await expect(detail.locator('[aria-label*="Activo"]')).toBeVisible();
    await expect(detail.getByText("Estado actual en vivo")).toBeVisible();
    await expect(detail.getByText("Rechazado", { exact: true })).toBeVisible();
    await expect(detail.getByText("falta verificar que la luminaria permanezca encendida.", { exact: true })).toBeVisible();
    await expect(detail.getByText("El caso continúa activo", { exact: true })).toBeVisible();

    // El timeline NO debe comunicar cierre: el request volvió a ACTIVE.
    await expect(detail.getByText("Cierre autorizado por supervisor", { exact: true })).toHaveCount(0);
    await expect(detail.getByText("Caso resuelto", { exact: true })).toHaveCount(0);
    await expect(detail.getByText("Registro final auditado", { exact: false })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("caso RESOLUTION_PENDING_APPROVAL: pendiente y nunca cerrado", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la esquina");
    const detail = detailSection(page);

    await expect(detail.locator('[aria-label*="Pendiente de aprobación"]')).toBeVisible();
    await expect(detail.getByText("Estado actual en vivo")).toBeVisible();
    await expect(detail.getByText("Pendiente de decisión", { exact: true })).toBeVisible();
    await expect(detail.getByText("El caso sigue abierto hasta la decisión del supervisor.", { exact: true })).toBeVisible();
    await expect(detail.getByText("Propuesta del técnico", { exact: true })).toBeVisible();

    await expect(detail.getByText("Resuelto", { exact: true })).toHaveCount(0);
    await expect(detail.getByText("Registro final auditado", { exact: false })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("caso RESOLVED: AUDIT_SNAPSHOT con cierre, autorizador y evidencia", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la plaza central");
    const detail = detailSection(page);

    await expect(detail.locator('[aria-label*="Resuelto"]')).toBeVisible();
    await expect(detail.getByText("Registro final auditado", { exact: false }).first()).toBeVisible();
    await expect(detail.getByText("Aprobado", { exact: true })).toBeVisible();
    await expect(detail.getByText(/Autorizado por mario\.rojas@alquimiablue\.com/)).toBeVisible();
    await expect(detail.getByText(/Cerrado el/)).toBeVisible();
    await expect(detail.getByText("Caso resuelto", { exact: true })).toBeVisible();

    // Trazabilidad: audit record y referencias reales.
    await detail.getByText("Evidencia y trazabilidad", { exact: true }).click();
    await expect(detail.getByText("Audit record", { exact: true })).toBeVisible();
    await expect(detail.getByText(/^a23aa1ec-/)).toBeVisible();
    await expect(detail.getByText("Routing N1", { exact: true })).toBeVisible();
    await expect(detail.getByText("ba03a320-51ce-48d4-b3f7-3af1b1817b54", { exact: true })).toBeVisible();
    await expect(detail.getByText("Propuesta de resolución", { exact: true })).toBeVisible();
    await expect(detail.getByText("Aprobación de cierre", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("caso escalado N1→N2→N3 con SLA por nivel", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Olleros");
    const detail = detailSection(page);

    await expect(detail.getByText("Estado actual en vivo")).toBeVisible();
    await expect(detail.getByText("Nivel 1 · Vencido", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 2 · Vencido", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 3 · Dentro de SLA", { exact: true })).toBeVisible();

    await expect(detail.getByText("Nivel 1 → Nivel 2", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 2 → Nivel 3", { exact: true })).toBeVisible();
    await expect(detail.getByText("Escalamiento de nivel", { exact: true })).toHaveCount(2);
    await expect(detail.getByText("Asignado a Nivel 3", { exact: true })).toBeVisible();

    // El historial previo no se oculta: N1 y N2 siguen visibles.
    await expect(detail.getByText("Asignado a Nivel 1", { exact: true })).toBeVisible();
    await expect(detail.getByText("Asignado a Nivel 2", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("cambio rápido de caso: el detalle final es el último seleccionado", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Olleros");
    await selectCaseByText(page, "Luminaria intermitente en la avenida");
    const detail = detailSection(page);

    await expect(detail.getByRole("heading", { name: "Luminaria intermitente en la avenida" })).toBeVisible();
    await expect(detail.getByRole("heading", { name: "Luminaria apagada en la calle Olleros" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("caso sin escalamientos: no se muestra sección vacía", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la esquina");
    const detail = detailSection(page);

    await expect(detail.getByText("Escalamientos", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio LIVE — responsive", () => {
  for (const [vp, width, height] of [["mobile", 390, 844], ["tablet", 768, 1024], ["desktop", 1280, 900]] as const) {
    test(`sin overflow horizontal en ${vp}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const errors: string[] = [];
      trackErrors(page, errors);
      await openFlow(page);
      await expectNoHorizontalOverflow(page);

      await selectCaseByText(page, "Luminaria intermitente en la avenida");
      await expect(detailSection(page).getByText("Rechazado", { exact: true })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      expect(errors).toEqual([]);
    });
  }
});

test.describe("Flow Directorio LIVE — consola limpia", () => {
  test("recorrido completo sin errores de consola ni requests fallidos", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la plaza central");
    await expect(detailSection(page).getByText("Registro final auditado", { exact: false }).first()).toBeVisible();
    await selectCaseByText(page, "Luminaria apagada en la calle Olleros");
    await expect(detailSection(page).getByText("Nivel 2 → Nivel 3", { exact: true })).toBeVisible();

    const failures = await page.evaluate(() => {
      const nav = performance.getEntriesByType("resource");
      const apis = nav.filter((e) => e.name.includes("/api/team360-flow/executive/"));
      const failed = apis.filter((e) => (e as PerformanceResourceTiming).responseStatus >= 400);
      return { total: apis.length, failed: failed.length };
    });
    expect(failures.total, "debe haber consultas ejecutivas").toBeGreaterThanOrEqual(2);
    expect(failures.failed, "ninguna consulta ejecutiva debe fallar").toBe(0);
    expect(errors).toEqual([]);
  });
});
