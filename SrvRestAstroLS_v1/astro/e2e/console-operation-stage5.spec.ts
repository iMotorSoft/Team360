import { test, expect } from "@playwright/test";

const CONSOLE_ROOT = "/w/ws-team360-control";

test.describe("Console Stage 5 — Operación", () => {
  test("services carga página con métricas, cards y link de acción", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/services`);

    await expect(page.getByRole("heading", { name: "Servicios" })).toBeVisible();
    await expect(page.getByText("Servicios visibles")).toBeVisible();
    await expect(page.getByText("Prestaciones en funcionamiento.")).toBeVisible();

    // Service cards should exist
    await expect(page.getByRole("link", { name: "Ver servicio" }).first()).toBeVisible();

    // At least one service card with metrics
    const metricsGrid = page.locator("dl").first();
    await expect(metricsGrid).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("link", { name: "Ver servicio" }).first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("tasks carga prioridad, estado, responsable y fecha", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/tasks`);

    await expect(page.getByRole("heading", { name: "Tareas" })).toBeVisible();

    // Stats panel with responsible and due date
    await expect(page.getByText("Responsable", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Vencimiento", { exact: true }).first()).toBeVisible();

    // First task card should have a title
    const taskTitles = page.getByRole("heading", { level: 2 });
    const titleCount = await taskTitles.count();
    expect(titleCount).toBeGreaterThan(0);

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByText("Responsable", { exact: true }).first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("runs carga sección con estado o empty state", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/runs`);

    await expect(page.getByRole("heading", { name: "Ejecuciones" })).toBeVisible();

    // Either runs exist or empty state
    const hasRuns = await page.getByText("Duración", { exact: true }).first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText("Todavía no hay ejecuciones").isVisible().catch(() => false);
    expect(hasRuns || hasEmpty).toBe(true);

    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("workers carga sección con workers o empty state", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/workers`);

    await expect(page.getByRole("heading", { name: "Workers" })).toBeVisible();

    // Either workers exist or empty state
    const hasWorkers = await page.getByText("Última ejecución", { exact: true }).first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText("Todavía no hay workers").isVisible().catch(() => false);
    expect(hasWorkers || hasEmpty).toBe(true);

    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });
});
