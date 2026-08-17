import { expect, test, type Page } from "@playwright/test";

const CONFIG_URL = "/w/ws-team360-control/flow/configuracion";
const FIXTURE_URL = "/demo/flow/configuracion-fixtures";

async function openConfiguration(page: Page, url = CONFIG_URL) {
  await page.goto(url);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible().catch(async () => {
    await expect(page.getByRole("heading", { name: /Sectores y niveles/ })).toBeVisible();
  });
}

function trackErrors(page: Page, errors: string[]) {
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("favicon")) errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => errors.push(`requestfailed: ${request.url()}`));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `overflow horizontal: ${overflow}`).toBeLessThanOrEqual(1);
}

test.describe("Flow Configuración — vista y navegación", () => {
  test("muestra sector, circuito operativo y supervisor separado", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openConfiguration(page);

    await expect(page.getByRole("heading", { name: "Sectores y niveles" })).toBeVisible();
    await expect(page.getByRole("listbox", { name: "Seleccionar sector" }).getByRole("option", { name: /Alumbrado Público/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Niveles de atención" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Supervisor de cierre" })).toBeVisible();
    await expect(page.getByText("Autoriza la resolución final del caso.")).toBeVisible();
    await expect(page.getByText("no un nivel adicional de escalamiento.")).toBeVisible();
    await expect(page.getByText("Modo demo · solo lectura")).toBeVisible();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("preserva la navegación Flow y no agrega controles a otros módulos", async ({ page }) => {
    await openConfiguration(page);
    const nav = page.getByRole("navigation", { name: "Navegación de consola" });
    await expect(nav.locator('a[href*="/flow/configuracion"]')).toBeVisible();
    await nav.getByRole("link", { name: "Directorio" }).click();
    await expect(page).toHaveURL(/\/flow\/?$/);
    await expect(page.getByRole("heading", { name: "Vista Ejecutiva" })).toBeVisible();
  });
});

test.describe("Flow Configuración — draft y validación", () => {
  test("Editar sin cambios mantiene Guardar deshabilitado", async ({ page }) => {
    await openConfiguration(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();

    await expect(page.getByText("Sin cambios", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeVisible();
    await expect(page.locator('[data-flow-config-editor] input')).toHaveCount(4);
  });

  test("cambio válido activa dirty y un email inválido queda asociado al campo", async ({ page }) => {
    await openConfiguration(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();

    const first = page.locator('#flow-destination-alumbrado-level-1');
    await first.fill("alumbrado.n1");
    await first.blur();
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
    await expect(first).toHaveAttribute("aria-invalid", "true");
    await expect(first).toHaveAttribute("aria-describedby", "flow-error-alumbrado-level-1");
    await expect(page.getByText("Ingresá un email válido", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeDisabled();

    await first.fill("  alumbrado.nuevo@alquimiablue.com  ");
    await first.blur();
    await expect(first).toHaveAttribute("aria-invalid", "false");
    await expect(page.getByText("Ingresá un email válido", { exact: true })).toHaveCount(0);
  });

  test("vacío y formato sin dominio muestran mensajes de producto", async ({ page }) => {
    await openConfiguration(page);
    await page.getByRole("button", { name: "Editar configuración" }).click();
    const first = page.locator('#flow-destination-alumbrado-level-1');

    await first.fill("");
    await first.blur();
    await expect(page.getByText("El destinatario es obligatorio", { exact: true })).toBeVisible();
    await first.fill("@alquimiablue.com");
    await first.blur();
    await expect(page.getByText("Ingresá un email válido", { exact: true })).toBeVisible();
  });

  test("Cancelar descarta el draft y restaura la configuración guardada", async ({ page }) => {
    await openConfiguration(page);
    const original = "alumbrado.n1@alquimiablue.com";
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-alumbrado-level-1').fill("cambio.temporal@alquimiablue.com");
    await expect(page.getByText("Cambios sin guardar", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancelar" }).click();

    await expect(page.getByText("Los cambios se descartaron. La configuración guardada no fue modificada.")).toBeVisible();
    await expect(page.getByText(original, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();
    await expect(page.locator('[data-flow-config-editor] input')).toHaveCount(0);
  });

  test("focus visible y teclado llegan al campo y a las acciones", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openConfiguration(page);
    await page.getByRole("button", { name: "Editar configuración" }).focus();
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator('#flow-destination-alumbrado-level-1')).toBeVisible();
    await page.locator('#flow-destination-alumbrado-level-1').focus();
    await expect(page.locator('#flow-destination-alumbrado-level-1')).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeFocused();
  });
});

test.describe("Flow Configuración — callbacks y niveles dinámicos", () => {
  test("representa 1, 3 y 5 niveles sin selectores rígidos", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await expect(page.getByText("Prueba interna de validación UX")).toBeVisible();
    const selector = page.getByRole("listbox", { name: "Seleccionar sector" });
    const editor = page.locator('[data-flow-config-editor]');

    await selector.getByRole("option", { name: /Prueba UX · 1 nivel/ }).click();
    await expect(editor.locator("article")).toHaveCount(1);
    await selector.getByRole("option", { name: /Prueba UX · 3 niveles/ }).click();
    await expect(editor.locator("article")).toHaveCount(3);
    await selector.getByRole("option", { name: /Prueba UX · 5 niveles/ }).click();
    await expect(editor.locator("article")).toHaveCount(5);
    await expect(editor.getByRole("heading", { name: "Supervisor de cierre" })).toBeVisible();
    await selector.getByRole("option", { name: /Prueba UX · sin niveles/ }).click();
    await expect(editor.getByText("Este sector todavía no tiene niveles")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("cambiar de sector con draft no descarta cambios en silencio", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    const selector = page.getByRole("listbox", { name: "Seleccionar sector" });
    await selector.getByRole("option", { name: /Prueba UX · 3 niveles/ }).click();
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-fixture-3-level-1').fill("pendiente@fixture.demo.local");
    await selector.getByRole("option", { name: /Prueba UX · 5 niveles/ }).click();

    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("button", { name: "Seguir editando" }).click();
    await expect(page.getByRole("heading", { name: /3 niveles/ })).toBeVisible();
    await selector.getByRole("option", { name: /Prueba UX · 5 niveles/ }).click();
    await page.getByRole("button", { name: "Descartar y cambiar" }).click();
    await expect(page.getByRole("heading", { name: /5 niveles/ })).toBeVisible();
    await expect(page.locator('[data-flow-config-editor] input')).toHaveCount(0);
  });

  test("callback simulado exitoso muestra feedback y no usa persistencia", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    const selector = page.getByRole("listbox", { name: "Seleccionar sector" });
    await selector.getByRole("option", { name: /Prueba UX · 3 niveles/ }).click();
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-fixture-3-level-1').fill("nuevo@fixture.demo.local");
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("Cambios guardados.", { exact: true })).toBeVisible();
    await expect(page.locator("[data-save-count]")).toHaveText("Guardados simulados: 1");
    await expect(page.getByRole("button", { name: "Editar configuración" })).toBeVisible();
  });

  test("callback simulado fallido conserva el draft y muestra error", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await page.locator("#fixture-save-mode").selectOption("error");
    await page.getByRole("listbox", { name: "Seleccionar sector" }).getByRole("option", { name: /Prueba UX · 1 nivel/ }).click();
    await page.getByRole("button", { name: "Editar configuración" }).click();
    await page.locator('#flow-destination-fixture-1-level-1').fill("otro@fixture.demo.local");
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("No se pudieron guardar los cambios. Revisá el formulario e intentá nuevamente.")).toBeVisible();
    await expect(page.locator('#flow-destination-fixture-1-level-1')).toHaveValue("otro@fixture.demo.local");
    await expect(page.getByRole("button", { name: "Cancelar" })).toBeVisible();
  });
});

test.describe("Flow Configuración — responsive y consola", () => {
  for (const [name, width, height] of [["390", 390, 844], ["768", 768, 1024], ["1024", 1024, 768], ["1280", 1280, 900]] as const) {
    test(`view y edit sin overflow en ${name}px`, async ({ page }) => {
      const errors: string[] = [];
      trackErrors(page, errors);
      await page.setViewportSize({ width, height });
      await openConfiguration(page);
      await expectNoHorizontalOverflow(page);
      await page.getByRole("button", { name: "Editar configuración" }).click();
      await expect(page.locator('[data-flow-config-editor] input')).toHaveCount(4);
      await expectNoHorizontalOverflow(page);
      await page.locator('#flow-destination-alumbrado-level-1').fill("direccion.muy.larga.para.validar.el.layout@alquimiablue.com");
      await page.locator('#flow-destination-alumbrado-level-1').blur();
      await expectNoHorizontalOverflow(page);
      expect(errors).toEqual([]);
    });
  }
});
