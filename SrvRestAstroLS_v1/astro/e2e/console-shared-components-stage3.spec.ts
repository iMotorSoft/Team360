import { expect, test } from "@playwright/test";

const CONSOLE_ROOT = "/w/ws-team360-control";

test.describe("Console Etapa 3 - componentes compartidos", () => {
  test("dashboard renderiza cards y estados semanticos sin overflow", async ({ page }) => {
    await page.goto(`${CONSOLE_ROOT}/`);
    await expect(page.getByRole("heading", { name: "Estado general de la red" })).toBeVisible();
    await expect(page.getByText("Organizaciones activas")).toBeVisible();
    await expect(page.getByText("Prioridades visibles")).toBeVisible();
    await expect(page.getByText("Saludable").first()).toBeVisible();

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
  });

  test("reportes conserva tabla desktop, acciones y listado mobile", async ({ page }) => {
    await page.goto(`${CONSOLE_ROOT}/reports`);

    const tableRegion = page.getByRole("region", { name: "Reportes disponibles" });
    await expect(tableRegion).toBeVisible();
    await tableRegion.focus();
    await expect(tableRegion).toBeFocused();
    await expect(tableRegion.getByRole("columnheader", { name: "Reporte" })).toBeVisible();
    await expect(tableRegion.getByRole("button").first()).toBeDisabled();

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(tableRegion).toBeHidden();
    await expect(page.getByRole("heading", { name: "Resumen comercial semanal" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBe(0);
  });

  test("formulario conserva teclado, labels, binding y disabled", async ({ page }) => {
    await page.goto(`${CONSOLE_ROOT}/diagnosis`);
    await page.getByTestId("btn-start-diagnosis").click();

    const question = page.getByTestId("question-card");
    await expect(question).toHaveAttribute("data-step-id", "process_to_automate", { timeout: 30_000 });

    const textarea = page.getByTestId("answer-textarea");
    await expect(textarea).toHaveAttribute("aria-labelledby", "diagnosis-question-label");
    await expect(textarea).toHaveAttribute("aria-describedby", "diagnosis-question-description");
    await expect(page.getByTestId("btn-next")).toBeDisabled();

    await textarea.focus();
    await page.keyboard.type("Calificar consultas comerciales con reglas definidas.");
    await expect(textarea).toHaveValue("Calificar consultas comerciales con reglas definidas.");
    await expect(page.getByTestId("btn-next")).toBeEnabled();
    await expect(page.getByTestId("btn-next")).toHaveAttribute("type", "button");
  });

  test("notificaciones abre y cierra con Escape, click externo y retorno de foco", async ({ page }) => {
    await page.goto(`${CONSOLE_ROOT}/alerts`);
    await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
    const trigger = page.getByRole("button", { name: "Abrir notificaciones" });
    const panel = page.getByRole("region", { name: "Notificaciones" });

    await trigger.click();
    await expect(panel).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");

    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();

    await trigger.click();
    await expect(panel).toBeVisible();
    await page.getByRole("heading", { name: "Alertas", exact: true }).click();
    await expect(panel).toBeHidden();
  });

  test("select nativo conserva ES, EN, HE y RTL", async ({ page }) => {
    await page.goto(`${CONSOLE_ROOT}/`);
    await expect(page.locator('[data-hydrated="true"][dir]')).toBeVisible();
    const locale = page.getByRole("combobox", { name: "Idioma de interfaz" });

    await expect(locale).toHaveValue("es");
    await locale.selectOption("en");
    await expect(page.getByRole("navigation", { name: "Navegación de consola" }).getByRole("link").first()).toHaveText("Home");
    await locale.selectOption("he");
    await expect(page.locator('[data-hydrated="true"][dir]')).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("navigation", { name: "Navegación de consola" }).getByRole("link").first()).toHaveText("ראשי");
  });
});
