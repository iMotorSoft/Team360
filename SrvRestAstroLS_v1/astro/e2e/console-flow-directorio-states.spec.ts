import { test, expect, type Page } from "@playwright/test";

// Team360 Flow — Directorio: estados de autorización y errores (UI).
// No requiere backend real: interfiere /api/team360-flow/executive/* para
// simular 401/403/404/500 y verifica que la UI trata cada estado de forma
// diferenciada y segura. La autorización real del backend está cubierta por
// los tests de ruta (test_flow_director_authorization.py).

const DIRECTORIO_URL = "/w/ws-team360-control/flow";
const EXEC_API = /\/api\/team360-flow\/executive\/[0-9a-f-]{36}/;

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

async function interceptExecutive(page: Page, status: number, body: unknown) {
  await page.route(EXEC_API, (route) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }),
  );
}

test.describe("Flow Directorio — autorización", () => {
  test("401: conduce al flujo de acceso y no muestra datos", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutive(page, 401, { detail: "unauthorized" });
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
    await interceptExecutive(page, 403, { detail: "Forbidden" });
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
    await page.route(EXEC_API, (route) => {
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
  test("404 en todos los casos conocidos: cae a modo demostración explícito", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutive(page, 404, { detail: "not found" });
    await openFlow(page);

    await expect(page.getByText("Datos de demostración", { exact: true })).toBeVisible();
    await expect(page.locator("ul li button").first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("500 en todos los casos: fallback de demostración sin error crudo", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await interceptExecutive(page, 500, { detail: "internal error" });
    await openFlow(page);

    await expect(page.getByText("Datos de demostración", { exact: true })).toBeVisible();
    await expect(page.getByText("internal error", { exact: true })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("red caída (network error): fallback de demostración y sin congelamiento", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await page.route(EXEC_API, (route) => route.abort("failed"));
    await openFlow(page);

    await expect(page.getByText("Datos de demostración", { exact: true })).toBeVisible();
    // La UI sigue operable en modo demo: se puede seleccionar un caso.
    await page.locator("ul li button").first().click();
    await expect(page.locator('[data-selected="yes"]')).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("carga parcial: casos cargados + aviso de fallos sin romper el listado", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);

    let served = 0;
    await page.route(EXEC_API, (route) => {
      served += 1;
      return served <= 5
        ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({}) })
        : route.continue();
    });
    await openFlow(page);

    await expect(page.getByText("Backend Flow · datos reales", { exact: true })).toBeVisible();
    await expect(page.getByText(/casos no pudieron cargarse/)).toBeVisible();
    await expect(page.locator("ul li button").first()).toBeVisible();
    expect(errors).toEqual([]);
  });
});
