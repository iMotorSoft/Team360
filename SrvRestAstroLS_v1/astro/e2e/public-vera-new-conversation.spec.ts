import { expect, test } from "@playwright/test";

test.describe("Public Vera — New conversation reset", () => {
  test("clears conversation state and isolates new session", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await page.goto("/t360");
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    async function sendInitial(msg: string) {
      await page.getByTestId("public-vera-text").fill(msg);
      await page.getByTestId("public-vera-submit").click();
      await page.waitForTimeout(3000);
    }

    async function sendChat(msg: string) {
      await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 15000 });
      await page.getByTestId("public-vera-chat-input").fill(msg);
      await page.getByTestId("public-vera-chat-submit").click();
      await page.waitForTimeout(3000);
    }

    // === CONVERSATION A: Kommo ===
    await sendInitial("Necesito responder los WhatsApp que llegan a Kommo.");
    await sendChat("Quiero automatizar pedidos de turnos.");

    const entryA = await page.getByTestId("public-vera-entry").innerText();
    expect(entryA.toLowerCase()).toContain("whatsapp");
    expect(entryA.toLowerCase()).toContain("kommo");

    // === CLICK NUEVA CONVERSACIÓN ===
    await page.getByTestId("public-vera-new-conversation").click();
    await page.waitForTimeout(2000);

    // Verify initial state restored
    await expect(page.getByTestId("public-vera-text")).toBeVisible();
    const inputValue = await page.getByTestId("public-vera-text").inputValue();
    expect(inputValue).toBe("");

    const entryAfterReset = await page.getByTestId("public-vera-entry").innerText();
    const lowerReset = entryAfterReset.toLowerCase();
    expect(lowerReset).not.toContain("kommo");
    expect(lowerReset).not.toContain("turnos");

    // === CONVERSATION B: Email (completely different topic) ===
    await sendInitial("Recibo consultas de soporte por email.");

    const entryB = await page.getByTestId("public-vera-entry").innerText();
    const lowerB = entryB.toLowerCase();
    expect(lowerB).not.toContain("kommo");
    expect(lowerB).not.toContain("turnos");

    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes("ERR_CONNECTION_REFUSED") && !e.includes("favicon")
    );
    expect(criticalErrors).toEqual([]);
  });
});
