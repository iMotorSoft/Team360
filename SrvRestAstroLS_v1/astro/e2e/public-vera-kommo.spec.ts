import { expect, test } from "@playwright/test";

test.describe("Public Vera — Kommo appointment flow", () => {
  test("completes full kommo appointment diagnosis", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    // Navigate to /t360
    await page.goto("/t360");
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    // Send initial message
    await page.getByTestId("public-vera-text").fill(
      "Necesito responder los WhatsApp que llegan a Kommo para pedir turnos."
    );
    await page.getByTestId("public-vera-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 10000 });

    async function send(msg: string) {
      await page.getByTestId("public-vera-chat-input").fill(msg);
      await page.getByTestId("public-vera-chat-submit").click();
      await page.waitForTimeout(3000);
    }

    // Send conversation turns
    await send("Pedir turno.");
    await send("Lo cargo manual.");
    await send("Número de cliente, celular, fecha y horario.");
    await send("Tipo de servicio.");
    await send("Lo confirmo a mano por WhatsApp.");
    await send("Aproximadamente 100 por día.");
    await send("La disponibilidad la consulto en Kommo.");

    // Request diagnosis
    await send("Dame el diagnóstico.");
    await page.waitForTimeout(4000);

    // Validate final state
    const bodyText = await page.locator("body").innerText();
    const lower = bodyText.toLowerCase();

    expect(lower).toContain("whatsapp");
    expect(lower).toContain("kommo");
    expect(lower).toContain("turno");
    expect(lower).toContain("tipo de servicio");
    expect(lower).toContain("diagnóstico");

    // No critical console errors (ignore transient net::ERR failures)
    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes("ERR_CONNECTION_REFUSED") && !e.includes("Failed to load resource")
    );
    expect(criticalErrors).toEqual([]);
  });
});
