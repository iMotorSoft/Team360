import { test, expect, devices, type Page } from "@playwright/test";

function observeRuntime(page: Page) {
  const criticalErrors: string[] = [];
  const serverErrors: string[] = [];
  const requests = new Map<string, number>();

  page.on("console", (message) => {
    if (message.type() === "error") criticalErrors.push(message.text());
  });
  page.on("pageerror", (error) => criticalErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
  });
  page.on("request", (request) => {
    if (request.method() !== "GET") {
      const key = `${request.method()} ${request.url()}`;
      requests.set(key, (requests.get(key) ?? 0) + 1);
    }
  });

  return { criticalErrors, serverErrors, requests };
}

async function expectNoHorizontalOverflow(page: Page) {
  const sizes = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(sizes.documentWidth).toBeLessThanOrEqual(sizes.viewportWidth);
}

test.describe("TelchiAI - primera experiencia", () => {
  test("prioriza la consulta, completa sugerencias y evoluciona sin navegar", async ({ page }) => {
    const runtime = observeRuntime(page);
    await page.goto("/telchiai");

    await expect(page).toHaveTitle("TelchiAI | Team360");
    await expect(page.getByRole("heading", { name: "¿Qué querés saber de Telchi?" })).toBeVisible();

    const input = page.getByRole("textbox", { name: "Escribí una consulta sobre Telchi" });
    const send = page.getByRole("button", { name: "Enviar consulta" });
    await expect(input).toBeVisible();
    await expect(send).toBeDisabled();

    await page.getByRole("button", { name: "Dame las ventas de septiembre" }).click();
    await expect(input).toHaveValue("Dame las ventas de septiembre");
    await expect(input).toBeFocused();
    await expect(send).toBeEnabled();

    const initialUrl = page.url();
    await send.click();
    await expect(page.locator('[data-testid="telchiai-shell"]')).toHaveAttribute("data-state", "processing");
    await expect(page.getByText("Entendiendo tu consulta…")).toBeVisible();
    await expect(page.locator('[data-testid="telchiai-shell"]')).toHaveAttribute("data-state", "ready", { timeout: 5_000 });
    await expect(page.getByRole("heading", { name: "La transición hacia el análisis está lista." })).toBeVisible();
    expect(page.url()).toBe(initialUrl);

    expect(runtime.serverErrors).toEqual([]);
    expect(runtime.criticalErrors).toEqual([]);
    expect([...runtime.requests.entries()].filter(([, count]) => count > 1)).toEqual([]);
  });

  test("mantiene el histórico subordinado en un drawer accesible", async ({ page }) => {
    await page.goto("/telchiai");

    const history = page.getByRole("button", { name: "Análisis anteriores" });
    await history.click();

    const drawer = page.getByRole("dialog", { name: "Análisis anteriores" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("Acá vas a encontrar tus análisis")).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Cerrar" })).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
    await expect(history).toBeFocused();
  });

  test("no tiene overflow horizontal en desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/telchiai");
    await expectNoHorizontalOverflow(page);
  });
});

test.describe("TelchiAI - móvil táctil", () => {
  test.use({
    viewport: devices["Pixel 5"].viewport,
    userAgent: devices["Pixel 5"].userAgent,
    deviceScaleFactor: devices["Pixel 5"].deviceScaleFactor,
    hasTouch: true,
    isMobile: true,
  });

  test("conserva áreas táctiles, input visible y layout sin overflow", async ({ page }) => {
    const runtime = observeRuntime(page);
    await page.goto("/telchiai");

    const suggestion = page.getByRole("button", { name: "¿Qué clientes tienen deuda vencida?" });
    const history = page.getByRole("button", { name: "Análisis anteriores" });
    const send = page.getByRole("button", { name: "Enviar consulta" });

    for (const control of [suggestion, history, send]) {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }

    await suggestion.tap();
    await expect(page.getByRole("textbox", { name: "Escribí una consulta sobre Telchi" })).toHaveValue(
      "¿Qué clientes tienen deuda vencida?",
    );
    await expectNoHorizontalOverflow(page);

    await history.tap();
    await expect(page.getByRole("dialog", { name: "Análisis anteriores" })).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Cerrar" }).tap();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    expect(runtime.serverErrors).toEqual([]);
    expect(runtime.criticalErrors).toEqual([]);
  });
});
