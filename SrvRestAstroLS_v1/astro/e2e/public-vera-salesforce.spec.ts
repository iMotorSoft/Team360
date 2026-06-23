import { expect, test } from "@playwright/test";

test.describe("Public Vera — Salesforce CRM flow", () => {
  test("completes salesforce appointment diagnosis", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await page.goto("/t360");
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    await page.getByTestId("public-vera-text").fill(
      "Necesito responder los WhatsApp que llegan a Salesforce."
    );
    await page.getByTestId("public-vera-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 10000 });

    async function send(msg: string) {
      await page.getByTestId("public-vera-chat-input").fill(msg);
      await page.getByTestId("public-vera-chat-submit").click();
      await page.waitForTimeout(3000);
    }

    await send("Pedir turnos.");
    await send("Lo cargamos manualmente.");
    await send("Dame un diagnóstico inicial.");
    await page.waitForTimeout(4000);

    const bodyText = await page.locator("body").innerText();
    const lower = bodyText.toLowerCase();

    expect(lower).toContain("whatsapp");
    expect(lower).toContain("salesforce");
    expect(lower).toContain("turno");
    expect(lower).not.toContain("kommo");
    expect(lower).toContain("diagnóstico");

    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes("ERR_CONNECTION_REFUSED")
    );
    expect(criticalErrors).toEqual([]);
  });
});
