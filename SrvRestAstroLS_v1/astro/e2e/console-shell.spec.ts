import { test, expect } from "@playwright/test";

const CONSOLE_URL = "/w/ws-team360-control/";
const SERVICES_URL = "/w/ws-team360-control/services";

async function openConsole(page: import("@playwright/test").Page, url = CONSOLE_URL) {
  await page.goto(url);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
}

test.describe("Console shell E2E - shell funcional", () => {
  test("carga el shell con sidebar, topbar, breadcrumbs y dashboard", async ({ page }) => {
    await openConsole(page);

    await expect(page.getByRole("complementary", { name: "Navegación contextual" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Navegación de consola" })).toBeVisible();
    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Breadcrumbs" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Estado general de la red" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Idioma de interfaz" })).toHaveValue("es");
  });

  test("navegación por secciones y estado activo", async ({ page }) => {
    await openConsole(page);

    const nav = page.getByRole("navigation", { name: "Navegación de consola" });
    await nav.getByRole("link", { name: "Servicios" }).click();

    await expect(page).toHaveURL(/\/services$/);
    await expect(page.getByRole("heading", { name: "Servicios" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Servicios" })).toHaveClass(/bg-\[#e4f5f3\]/);
  });

  test("refresh directo conserva la ruta y el shell", async ({ page }) => {
    await openConsole(page, SERVICES_URL);
    await expect(page.getByRole("heading", { name: "Servicios" })).toBeVisible();

    await page.reload();
    await expect(page.locator('[data-hydrated="true"]')).toBeVisible();

    await expect(page.getByRole("complementary", { name: "Navegación contextual" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Servicios" })).toBeVisible();
  });

  test("cambio de locale ES/EN/HE con RTL", async ({ page }) => {
    await openConsole(page);

    const locale = page.getByRole("combobox", { name: "Idioma de interfaz" });
    const firstLink = page
      .getByRole("navigation", { name: "Navegación de consola" })
      .getByRole("link")
      .first();

    await expect(firstLink).toHaveText("Inicio");
    await locale.selectOption("en");
    await expect(firstLink).toHaveText("Home");
    await locale.selectOption("he");
    await expect(firstLink).toHaveText("ראשי");

    const shellDir = await page.locator('[data-hydrated="true"]').getAttribute("dir");
    expect(shellDir).toBe("rtl");
  });

  test("selector de workspace navega al workspace elegido", async ({ page }) => {
    await openConsole(page);

    await page.getByRole("combobox", { name: "Cambiar workspace activo" }).selectOption("ws-carmel-retail");

    await expect(page).toHaveURL(/\/w\/ws-carmel-retail/);
  });

  test("branding del sidebar usa el isotipo y wordmark aprobados", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
    page.on("requestfailed", (req) => { if (req.url().includes("object%20Object")) errors.push(`Failed: ${req.url()}`); });

    await openConsole(page, "/w/ws-team360-control/team");

    const brand = page.locator("aside").getByRole("link", { name: "Team360 Console, inicio" });
    await expect(brand).toHaveAttribute("data-team360-logo-variant", "design-handoff");
    await expect(brand.locator('[data-team360-wordmark="team"]')).toHaveCSS("color", "rgb(16, 45, 79)");
    await expect(brand.locator('[data-team360-wordmark="360"]')).toHaveCSS("color", "rgb(22, 139, 136)");

    const logo = brand.locator('[data-team360-logo-icon="t360"]');
    await expect(logo).toBeVisible();

    const bgImage = await logo.evaluate((el) => el.style.backgroundImage);
    expect(bgImage).toContain("url(");
    expect(bgImage).not.toContain("[object Object]");
    expect(bgImage).not.toContain("undefined");
    expect(bgImage).not.toContain("null");
    expect(bgImage).toMatch(/team360_logo_t/);

    const urlMatch = bgImage.match(/url\(["']?([^"')]+)["']?\)/);
    expect(urlMatch).toBeTruthy();
    const imageUrl = urlMatch![1];

    const response = await page.request.get(imageUrl);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toMatch(/^image\//);

    const loaded = await page.evaluate((imgUrl) => {
      const img = new Image();
      return new Promise<{ w: number; h: number }>((res, rej) => {
        img.onload = () => res({ w: img.naturalWidth, h: img.naturalHeight });
        img.onerror = () => rej(new Error("Image load failed"));
        img.src = imgUrl;
      });
    }, imageUrl);
    expect(loaded.w).toBeGreaterThan(0);
    expect(loaded.h).toBeGreaterThan(0);

    expect(errors.filter((e) => !e.includes("favicon"))).toHaveLength(0);
  });

  test("branding de acceso usa Team360Logo y excluye el isotipo alternativo", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("requestfailed", (request) => errors.push(`Failed: ${request.url()}`));

    for (const route of ["/login", "/select-workspace"]) {
      await page.goto(route);

      const brand = page.locator("header").getByRole("link", { name: "Team360, inicio" });
      await expect(brand).toHaveAttribute("data-team360-logo-variant", "design-handoff");
      await expect(brand.locator('[data-team360-wordmark="team"]')).toHaveText("Team");
      await expect(brand.locator('[data-team360-wordmark="team"]')).toHaveCSS("color", "rgb(16, 45, 79)");
      await expect(brand.locator('[data-team360-wordmark="360"]')).toHaveText("360");
      await expect(brand.locator('[data-team360-wordmark="360"]')).toHaveCSS("color", "rgb(22, 139, 136)");

      const icon = brand.locator('[data-team360-logo-icon="t360"]');
      const bgImage = await icon.evaluate((element) => element.style.backgroundImage);
      expect(bgImage).toMatch(/team360_logo_t/);

      const urlMatch = bgImage.match(/url\(["']?([^"')]+)["']?\)/);
      expect(urlMatch).toBeTruthy();
      const response = await page.request.get(urlMatch![1]);
      expect(response.status()).toBe(200);
      expect(response.headers()["content-type"]).toMatch(/^image\/png/);
    }

    expect(errors.filter((error) => !error.includes("favicon"))).toEqual([]);
  });

  test("drawer mobile abre y cierra con overlay", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConsole(page);

    const drawer = page.getByRole("complementary", { name: "Navegación contextual" });
    await expect(drawer).toHaveCSS("translate", "-100%");

    await page.getByRole("button", { name: "Abrir navegación" }).click();
    await expect(drawer).toHaveCSS("translate", "0px");
    await expect(page.getByRole("button", { name: "Cerrar navegación" })).toHaveCount(2);
    const mobileBrand = drawer.getByRole("link", { name: "Team360 Console, inicio" });
    await expect(mobileBrand).toHaveAttribute("data-team360-logo-variant", "design-handoff");
    await expect(mobileBrand.locator('[data-team360-wordmark="360"]')).toHaveCSS("color", "rgb(22, 139, 136)");

    await drawer.getByRole("button", { name: "Cerrar navegación" }).click();
    await expect(drawer).toHaveCSS("translate", "-100%");
    await expect(page.getByRole("button", { name: "Cerrar navegación" })).toHaveCount(1);
  });
});
