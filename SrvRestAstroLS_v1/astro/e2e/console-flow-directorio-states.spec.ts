import { test, expect, type Page } from "@playwright/test";

// Team360 Flow — Directorio: estados de autorización y errores (UI).
// No requiere backend real: interfiere el endpoint de listado para simular
// 401/403/404/500 y verifica que la UI trata cada estado de forma diferenciada
// y segura. La autorización real está cubierta por los tests de ruta.

const DIRECTORIO_URL = "/w/ws-team360-control/flow";
const EXEC_LIST_API = /\/api\/team360-flow\/executive(?:\?.*)?$/;
const EXEC_DETAIL_API = /\/api\/team360-flow\/executive\/[0-9a-f-]{36}/;

async function openFlow(page: Page) {
  await page.goto(DIRECTORIO_URL);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
}

function trackErrors(page: Page, errors: string[]) {
  page.on("console", (msg) => {
    // Los estados simulados producen mensajes del navegador
    // "Failed to load resource: the server responded with a status of NNN";
    // son el efecto esperado de interrumpir el API, no errores de la app.
    if (msg.type() !== "error") return;
    if (msg.text().startsWith("Failed to load resource:")) return;
    if (!msg.text().includes("favicon")) errors.push(`console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
}

async function interceptExecutiveList(page: Page, status: number, body: unknown) {
  await page.route(EXEC_LIST_API, (route) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }),
  );
}

test.describe("Flow Directorio — autorización", () => {
  test("401: conduce al flujo de acceso y no muestra datos", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutiveList(page, 401, { detail: "unauthorized" });
    await openFlow(page);

    await expect(page.getByText("Sesión requerida", { exact: true })).toBeVisible();
    const login = page.getByRole("link", { name: "Ir al acceso" });
    await expect(login).toBeVisible();
    await expect(login).toHaveAttribute("href", "/login");

    await expect(page.locator("ul li button")).toHaveCount(0);
    await expect(page.getByText("Datos de demostración", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("403: comunica acceso no autorizado sin exponer datos del caso", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutiveList(page, 403, { detail: "Forbidden" });
    await openFlow(page);

    await expect(page.getByText("Sin permiso de Directorio", { exact: true })).toBeVisible();
    await expect(page.getByText(/flow\.executive\.read/)).toBeVisible();

    // No se muestran KPIs, listado ni evidencias de casos.
    await expect(page.locator("main article")).toHaveCount(0);
    await expect(page.locator("ul li button")).toHaveCount(0);
    await expect(page.getByText("Datos de demostración", { exact: true })).toHaveCount(0);
    await expect(page.getByText("SLA por nivel", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("reintento tras 403 vuelve a consultar y recupera", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);

    let calls = 0;
    await page.route(EXEC_LIST_API, (route) => {
      calls += 1;
      return calls === 1
        ? route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Forbidden" }) })
        : route.continue();
    });
    await openFlow(page);

    await expect(page.getByText("Sin permiso de Directorio", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reintentar" }).click();
    await expect(page.getByText("Backend Flow · datos reales", { exact: true })).toBeVisible();
    await expect(page.locator("ul li button").first()).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio — errores y degradación", () => {
  test("404 del detalle entre listado y selección: conserva el listado y muestra recovery", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await page.route(EXEC_DETAIL_API, (route) =>
      route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) }),
    );
    await openFlow(page);
    await page.locator("ul li button").first().click();

    await expect(page.getByText("Caso no encontrado", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Volver al listado" })).toBeVisible();
    await page.getByRole("button", { name: "Volver al listado" }).click();
    await expect(page.locator("ul li button").first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("404 del listado: error seguro sin datos de demostración", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutiveList(page, 404, { detail: "not found" });
    await openFlow(page);

    await expect(page.getByText("No se pudo cargar el listado", { exact: true })).toBeVisible();
    await expect(page.getByText("Datos de demostración", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("500 del listado: no expone el error crudo ni fabrica datos", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutiveList(page, 500, { detail: "internal error" });
    await openFlow(page);

    await expect(page.getByText("No se pudo cargar el listado", { exact: true })).toBeVisible();
    await expect(page.getByText("Datos de demostración", { exact: true })).toHaveCount(0);
    await expect(page.getByText("internal error", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("red caída: error de listado sin congelamiento", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await page.route(EXEC_LIST_API, (route) => route.abort("failed"));
    await openFlow(page);

    await expect(page.getByText("No se pudo cargar el listado", { exact: true })).toBeVisible();
    await expect(page.getByText("Datos de demostración", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

});
