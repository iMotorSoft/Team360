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

  test("drawer mobile abre y cierra con overlay", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConsole(page);

    const drawer = page.getByRole("complementary", { name: "Navegación contextual" });
    await expect(drawer).toHaveCSS("translate", "-100%");

    await page.getByRole("button", { name: "Abrir navegación" }).click();
    await expect(drawer).toHaveCSS("translate", "0px");
    await expect(page.getByRole("button", { name: "Cerrar navegación" })).toHaveCount(2);

    await drawer.getByRole("button", { name: "Cerrar navegación" }).click();
    await expect(drawer).toHaveCSS("translate", "-100%");
    await expect(page.getByRole("button", { name: "Cerrar navegación" })).toHaveCount(1);
  });
});
