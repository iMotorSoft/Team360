import { expect, test } from "@playwright/test";

test.describe("Team360 interaction blocks lab", () => {
  test("renderiza fixtures y emite eventos frontend", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await page.goto("/t360-interaction-lab");

    await expect(page.getByTestId("t360-interaction-lab")).toBeVisible();
    await expect(page.getByTestId("t360-block-next_step_choice")).toContainText("Próximo paso recomendado");
    await expect(page.getByTestId("t360-block-single_choice")).toContainText("¿Cuál canal concentra hoy la mayor parte de las consultas?");
    await expect(page.getByTestId("t360-block-multi_choice")).toContainText("¿Qué sistemas deberían consultarse para responder bien?");
    await expect(page.getByTestId("t360-block-missing_requirements").first()).toContainText("Datos que faltan para cerrar el alcance");
    await expect(page.getByTestId("t360-block-product_fit_card")).toContainText("Diagnóstico de automatización comercial");
    await expect(page.getByTestId("t360-block-diagnosis_action_card")).toContainText("Orientación lista para revisar");
    await expect(page.getByTestId("t360-diagnosis-summary")).toContainText("Diagnóstico preliminar de automatización comercial");
    await expect(page.getByTestId("t360-block-invalid")).toContainText("No hay interacción disponible");

    await page.getByTestId("t360-action-show-preliminary").click();
    await expect(page.getByTestId("t360-event-log")).toContainText("t360action");
    await expect(page.getByTestId("t360-event-log")).toContainText("show-preliminary");

    await page.getByTestId("t360-option-whatsapp").click();
    await page.getByTestId("t360-single-submit").click();
    await expect(page.getByTestId("t360-event-log")).toContainText("t360choice");
    await expect(page.getByTestId("t360-event-log")).toContainText("submit-channel");
    await expect(page.getByTestId("t360-event-log")).toContainText("selected_option");

    await page.getByTestId("t360-option-erp").click();
    await page.getByTestId("t360-option-spreadsheet").click();
    await page.getByTestId("t360-option-crm").click();
    await expect(page.getByTestId("t360-option-free-text").locator("input")).toBeDisabled();
    await page.getByTestId("t360-multi-submit").click();
    await expect(page.getByTestId("t360-event-log")).toContainText("t360choices");
    await expect(page.getByTestId("t360-event-log")).toContainText("submit-systems");
    await expect(page.getByTestId("t360-event-log")).toContainText("selected_options");

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("t360-block-single_choice")).toBeVisible();
    await expect(page.getByTestId("t360-single-submit")).toBeEnabled();
    await expect(page.getByTestId("t360-block-invalid")).toBeVisible();

    expect(consoleErrors).toEqual([]);
  });
});
