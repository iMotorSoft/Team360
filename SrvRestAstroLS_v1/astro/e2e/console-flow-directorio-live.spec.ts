import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

// Real-data smoke only. It intentionally discovers cases from PostgreSQL and
// asserts API/UI invariants, never global totals, row positions or historical IDs.

const DIRECTORIO_URL = "/w/ws-team360-control/flow";
type ListPayload = {
  items: Array<Record<string, any>>;
  sectors: Array<Record<string, any>>;
  pagination: { page: number; page_size: number; total: number; has_next: boolean };
};

async function openFlow(page: Page) {
  await page.goto(DIRECTORIO_URL);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
  await expect(page.getByText("Backend Flow · datos reales", { exact: true })).toBeVisible();
}

async function listCases(request: APIRequestContext, params = "") {
  const response = await request.get(`/api/team360-flow/executive${params}`);
  expect(response.ok(), `Executive list HTTP ${response.status()}`).toBeTruthy();
  return (await response.json()) as ListPayload;
}

async function selectCaseById(page: Page, requestId: string) {
  // The API probe may use page_size=100 while the rendered list intentionally
  // stays paginated at 20. Search by the API-discovered identity before
  // clicking so a valid case outside page one remains selectable.
  const token = requestId.slice(0, 8);
  const search = page.getByRole("searchbox", { name: "Buscar caso" });
  await search.fill(token);
  const item = page.locator("ul li button", { hasText: `#${token}` });
  await expect(item).toHaveCount(1);
  await item.click();
}

function trackErrors(page: Page, errors: string[]) {
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon")) errors.push(`console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("requestfailed", (req) => errors.push(`requestfailed: ${req.url()}`));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `overflow horizontal: ${overflow}`).toBeLessThanOrEqual(1);
}

test.describe("Flow Directorio LIVE smoke — list invariants", () => {
  test("loads real PostgreSQL data without global golden totals", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const payload = await listCases(page.request, "?page=1&page_size=20");
    expect(payload.items.length).toBeGreaterThan(0);
    expect(payload.pagination.total).toBeGreaterThanOrEqual(payload.items.length);
    expect(new Set(payload.items.map((item) => item.request_id)).size).toBe(payload.items.length);
    for (const item of payload.items) {
      expect(["ACTIVE", "CONFIRMED", "RESOLUTION_PENDING_APPROVAL", "RESOLVED"]).toContain(item.status);
      expect(["open", "pending_approval", "closed"]).toContain(item.status_fact);
      expect(["LIVE", "AUDIT_SNAPSHOT"]).toContain(item.data_source);
    }
    await expect(page.locator("ul li button")).toHaveCount(payload.items.length);
    await expect(page.locator("main article")).toHaveCount(5);
    expect(errors).toEqual([]);
  });

  test("search resolves an API-discovered request identity", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const payload = await listCases(page.request, "?page=1&page_size=100");
    const fixture = payload.items[0];
    const token = String(fixture.request_id).slice(0, 8);
    const search = page.getByRole("searchbox", { name: "Buscar caso" });
    await search.fill(token);
    await expect(page.locator("ul li button")).toHaveCount(1);
    await expect(page.locator("ul li button").first()).toContainText(`#${token}`);

    await search.fill(`NO-SUCH-FLOW-${Date.now()}`);
    await expect(page.getByText("No encontramos casos con estos filtros")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("status filters match their dynamic API result", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const tabs = page.getByRole("tablist", { name: "Filtrar casos" });

    const filters: Array<[string, string]> = [
      ["Activos", "open"],
      ["Pendientes", "pending_approval"],
      ["Resueltos", "resolved"],
    ];
    for (const [label, status] of filters) {
      const expected = await listCases(page.request, `?page=1&page_size=20&status=${status}`);
      await tabs.getByRole("tab", { name: label }).click();
      await expect(page.locator("ul li button")).toHaveCount(expected.items.length);
    }
    expect(errors).toEqual([]);
  });

  test("pagination follows API metadata and tolerates database growth", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const first = await listCases(page.request, "?page=1&page_size=20");
    const next = page.getByRole("button", { name: "Siguiente" });
    if (first.pagination.has_next) {
      await expect(next).toBeEnabled();
      await next.click({ force: true });
      await expect(page.getByText("Página 2", { exact: true })).toBeVisible();
      const second = await listCases(page.request, "?page=2&page_size=20");
      await expect(page.locator("ul li button")).toHaveCount(second.items.length);
      expect(second.items.length).toBeGreaterThan(0);
    } else {
      await expect(next).toBeDisabled();
    }
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio LIVE smoke — dynamic detail", () => {
  test("resolved case is AUDIT_SNAPSHOT with stable evidence", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const payload = await listCases(page.request, "?page=1&page_size=100&status=resolved");
    expect(payload.items.length).toBeGreaterThan(0);
    const fixture = payload.items[0];
    await selectCaseById(page, fixture.request_id);
    const detail = page.locator('[data-selected="yes"]');
    await expect(detail.getByText("Registro final auditado", { exact: true })).toBeVisible();
    await expect(detail.locator('[aria-label*="Resuelto"]')).toBeVisible();
    await expect(detail.getByText("Historia del caso", { exact: true })).toBeVisible();
    await expect(detail.getByText("Evidencia y trazabilidad", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("open case remains LIVE when available", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const payload = await listCases(page.request, "?page=1&page_size=100&status=open");
    const fixture = payload.items.find((item) => item.data_source === "LIVE");
    if (!fixture) {
      test.info().annotations.push({ type: "NO_TEST_DATA", description: "No open LIVE case available" });
      return;
    }
    await page.getByRole("tablist", { name: "Filtrar casos" }).getByRole("tab", { name: "Activos" }).click();
    await selectCaseById(page, fixture.request_id);
    const detail = page.locator('[data-selected="yes"]');
    await expect(detail.getByText("Estado actual en vivo", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("escalated case preserves dynamic routing history", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const payload = await listCases(page.request, "?page=1&page_size=100&escalated=true");
    const fixture = payload.items.find((item) => Number(item.escalation_count) > 0);
    if (!fixture) {
      test.info().annotations.push({ type: "NO_TEST_DATA", description: "No escalated case available" });
      return;
    }
    await page.getByRole("tablist", { name: "Filtrar casos" }).getByRole("tab", { name: "Escalados" }).click();
    await selectCaseById(page, fixture.request_id);
    const detail = page.locator('[data-selected="yes"]');
    await expect(detail.getByText("Escalamientos", { exact: true })).toBeVisible();
    await expect(detail.getByText(/Nivel \d+ → Nivel \d+/, { exact: false }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("pending approval is never presented as closed when available", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const payload = await listCases(page.request, "?page=1&page_size=100&status=pending_approval");
    const fixture = payload.items[0];
    if (!fixture) {
      test.info().annotations.push({ type: "NO_TEST_DATA", description: "No pending approval case available" });
      return;
    }
    await page.getByRole("tablist", { name: "Filtrar casos" }).getByRole("tab", { name: "Pendientes" }).click();
    await selectCaseById(page, fixture.request_id);
    const detail = page.locator('[data-selected="yes"]');
    await expect(detail.getByText("Estado actual en vivo", { exact: true })).toBeVisible();
    await expect(detail.getByText("Pendiente de decisión", { exact: true })).toBeVisible();
    await expect(detail.getByText("Registro final auditado", { exact: false })).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio LIVE smoke — responsive and races", () => {
  for (const [name, width, height] of [["mobile", 390, 844], ["tablet", 768, 1024], ["desktop", 1280, 900]] as const) {
    test(`no horizontal overflow at ${name}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await openFlow(page);
      await expectNoHorizontalOverflow(page);
    });
  }

  test("latest selected case wins the detail race", async ({ page }) => {
    await openFlow(page);
    const payload = await listCases(page.request, "?page=1&page_size=2");
    if (payload.items.length < 2) {
      test.info().annotations.push({ type: "NO_TEST_DATA", description: "Need two cases for detail race" });
      return;
    }
    await selectCaseById(page, payload.items[0].request_id);
    await selectCaseById(page, payload.items[1].request_id);
    const detail = page.locator('[data-selected="yes"]');
    await expect(detail.getByRole("heading", { name: payload.items[1].description })).toBeVisible();
  });

  test("full smoke has no console errors or failed executive requests", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);
    const payload = await listCases(page.request, "?page=1&page_size=2");
    if (payload.items.length > 0) await selectCaseById(page, payload.items[0].request_id);
    const failures = await page.evaluate(() => performance.getEntriesByType("resource")
      .filter((entry) => entry.name.includes("/api/team360-flow/executive/") && (entry as PerformanceResourceTiming).responseStatus >= 400).length);
    expect(failures).toBe(0);
    expect(errors).toEqual([]);
  });
});
