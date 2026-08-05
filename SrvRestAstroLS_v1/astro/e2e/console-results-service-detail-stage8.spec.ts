import { test, expect } from "@playwright/test";

const CONSOLE_ROOT = "/w/ws-team360-control";

test.describe("Console Stage 8 — Results y ServiceDetail", () => {
  test("results carga métricas de servicios con nombre, valor y label", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/results`);

    await expect(page.getByRole("heading", { name: "Resultados" })).toBeVisible();

    // Metric cards with numeric values
    const metricCards = page.locator("[class*='text-3xl']");
    const count = await metricCards.count();
    expect(count).toBeGreaterThan(0);

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Resultados" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("service detail navega desde services y carga con tabs, estado y métricas", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/services`);

    // Click first "Ver servicio" link
    const firstLink = page.getByRole("link", { name: "Ver servicio" }).first();
    await expect(firstLink).toBeVisible();
    await firstLink.click();

    // Verify we're on a service detail page
    const url = page.url();
    expect(url).toContain("/services/");

    // Header shows service name and back link
    await expect(page.getByRole("link", { name: /Volver a servicios/ })).toBeVisible();
    await expect(page.getByText("Próximo paso")).toBeVisible();

    // Status badges visible (Activo, Saludable, etc.) in main content
    const main = page.locator("#contenido-consola");
    await expect(main.getByText(/Activo|Saludable|saludable|Pendiente/).first()).toBeVisible();

    // Tabs exist
    await expect(page.getByRole("tab", { name: "Resumen" })).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("link", { name: /Volver/ })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("service detail conserva servicio tras refresh", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/services`);
    await page.getByRole("link", { name: "Ver servicio" }).first().click();

    const urlBefore = page.url();
    expect(urlBefore).toContain("/services/");

    // Service name before refresh
    const headingBefore = await page.getByRole("heading", { level: 1 }).textContent();

    await page.reload();
    await expect(page.getByText("Próximo paso")).toBeVisible();

    const urlAfter = page.url();
    expect(urlAfter).toBe(urlBefore);

    // Service name preserved
    const headingAfter = await page.getByRole("heading", { level: 1 }).textContent();
    expect(headingAfter).toBe(headingBefore);

    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });
});
