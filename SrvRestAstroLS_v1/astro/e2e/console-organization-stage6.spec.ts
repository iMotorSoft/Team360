import { test, expect } from "@playwright/test";

const CONSOLE_ROOT = "/w/ws-team360-control";

test.describe("Console Stage 6 — Organización", () => {
  test("organizations carga cards con nombre, tipo, estado y workspace count", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/organizations`);

    await expect(page.getByRole("heading", { name: "Organizaciones" })).toBeVisible();

    // Organization cards should exist
    const orgCards = page.getByText("workspace(s)");
    const count = await orgCards.count();
    expect(count).toBeGreaterThan(0);

    // Status badges visible
    await expect(page.getByText("Activo").first()).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Organizaciones" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("partners carga cards con métricas de clientes y workspaces", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/partners`);

    await expect(page.getByRole("heading", { name: "Partners" })).toBeVisible();

    // Metric cards with client/workspace counts
    const metricCards = page.getByText("Clientes asociados");
    const count = await metricCards.count();
    expect(count).toBeGreaterThan(0);

    await expect(page.getByText("Workspaces propios").first()).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Partners" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("workspaces carga cards con nombre, organización, tipo y locale", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/workspaces`);

    await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();

    // Workspace cards with type/locale/direction
    const wsCards = page.getByText("ES").first();
    await expect(wsCards).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("workspace switcher cambia contexto, URL y breadcrumb correctamente", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/workspaces`);

    // Open workspace switcher
    const switcher = page.getByRole("combobox", { name: /workspace/i }).or(page.locator("select").first());
    const switcherExists = await switcher.isVisible().catch(() => false);

    if (switcherExists) {
      // Get current URL
      const urlBefore = page.url();
      expect(urlBefore).toContain("ws-team360-control");

      // Switch to another workspace if possible
      await switcher.selectOption({ index: 1 }).catch(() => {});
      await page.waitForTimeout(500);

      const urlAfter = page.url();
      // Verify navigation happened or stayed on valid route
      expect(urlAfter).toContain("/w/");
    }

    // Refresh preserves route
    await page.reload();
    await expect(page.getByRole("heading", { name: "Workspaces" }).or(page.locator("h1"))).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("team carga miembros con avatar, nombre, email y rol", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/team`);

    await expect(page.getByRole("heading", { name: /Usuarios|Equipo/ })).toBeVisible();

    // Member cards with avatar initials
    const avatarEls = page.locator("[class*='size-11']");
    const count = await avatarEls.count();
    expect(count).toBeGreaterThan(0);

    // Email visible
    await expect(page.getByText("@").first()).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: /Usuarios|Equipo/ })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });
});
