import { test, expect } from "@playwright/test";

const CONSOLE_ROOT = "/w/ws-team360-control";

test.describe("Console Stage 7 — Settings y Support", () => {
  test("support carga panel de solicitudes y escalamiento con email link", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/support`);

    await expect(page.getByRole("heading", { name: "Soporte", exact: true })).toBeVisible();

    // Left panel: "Solicitudes recientes"
    await expect(page.getByText("Solicitudes recientes")).toBeVisible();

    // Right panel: "Escalamiento" with email link
    await expect(page.getByText("Escalamiento", { exact: true })).toBeVisible();
    const emailLink = page.getByRole("link").filter({ hasText: /@/ });
    await expect(emailLink.first()).toBeVisible();

    // Email link is a mailto
    const href = await emailLink.first().getAttribute("href");
    expect(href).toContain("mailto:");

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByText("Escalamiento", { exact: true })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("settings carga contexto operativo con org, workspace, región, idioma y dirección", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/settings`);

    await expect(page.getByRole("heading", { name: "Configuración" })).toBeVisible();

    const main = page.locator("#contenido-consola");

    // Context card with key fields
    await expect(main.getByText("Contexto operativo", { exact: true })).toBeVisible();
    await expect(main.getByText("Organización", { exact: true })).toBeVisible();
    await expect(main.getByText("Workspace", { exact: true })).toBeVisible();
    await expect(main.getByText("Región", { exact: true })).toBeVisible();
    await expect(main.getByText("Idioma", { exact: true })).toBeVisible();
    await expect(main.getByText("Dirección", { exact: true })).toBeVisible();

    // Modules card
    await expect(main.getByText("Módulos habilitados", { exact: true })).toBeVisible();

    // Services card
    await expect(main.getByText("Servicios contratados", { exact: true })).toBeVisible();

    // Integrations card
    await expect(main.getByText("Integraciones previstas", { exact: true })).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(main.getByText("Contexto operativo", { exact: true })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("settings valores son coherentes con el workspace activo", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });

    await page.goto(`${CONSOLE_ROOT}/settings`);

    // Locale and direction show real values (not empty/hardcoded)
    const main = page.locator("#contenido-consola");
    const localeText = await main.getByText("Idioma", { exact: true }).locator("..").locator("dd").textContent();
    expect(localeText).toBeTruthy();
    expect(["ES", "EN", "HE"]).toContain((localeText?.trim() ?? "").toUpperCase());

    const dirText = await main.getByText("Dirección", { exact: true }).locator("..").locator("dd").textContent();
    expect(dirText).toBeTruthy();
    expect(["LTR", "RTL"]).toContain((dirText?.trim() ?? "").toUpperCase());

    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });
});
