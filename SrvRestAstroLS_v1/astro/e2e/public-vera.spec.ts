import { expect, test } from "@playwright/test";

const HOME_URL = "/";
const TEST_TEXT = "Recibo leads por WhatsApp y no sé quién los sigue después del primer mensaje.";

test.describe("Home pública - Vera", () => {
  test("permite iniciar con texto libre y recibe respuesta preliminar", async ({ page }) => {
    await page.goto(HOME_URL);

    const entry = page.getByTestId("public-vera-entry");
    await entry.scrollIntoViewIfNeeded();
    await expect(page.getByRole("heading", { name: "Hablá con Vera" })).toBeVisible();

    await page.getByTestId("public-vera-text").fill(TEST_TEXT);
    await page.getByTestId("public-vera-submit").click();

    await expect(page.getByTestId("public-vera-response")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("public-vera-response")).toContainText("Lo tomo como punto de partida");
    await expect(page.getByTestId("public-vera-text")).toHaveValue(TEST_TEXT);
  });

  test("mantiene el texto y muestra fallback si backend no responde", async ({ page }) => {
    await page.route("**/api/automation-diagnosis/**", (route) => route.abort());
    await page.goto(HOME_URL);

    const entry = page.getByTestId("public-vera-entry");
    await entry.scrollIntoViewIfNeeded();

    await page.getByTestId("public-vera-text").fill(TEST_TEXT);
    await page.getByTestId("public-vera-submit").click();

    await expect(page.getByTestId("public-vera-error")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("public-vera-error")).toContainText("No pudimos iniciar el diagnóstico automático ahora");
    await expect(page.getByTestId("public-vera-text")).toHaveValue(TEST_TEXT);
    await expect(page.getByTestId("public-vera-mailto")).toHaveAttribute("href", /mailto:contacto@team360\.live/);
  });
});
