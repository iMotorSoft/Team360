import { expect, test } from "@playwright/test";

test.describe("Vera post-diagnosis continuation", () => {
  test.setTimeout(600000);

  const VERA_URL = "/t360";

  async function sendInitial(page: any, msg: string) {
    await page.getByTestId("public-vera-text").fill(msg);
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 30000 });
    await page.waitForTimeout(2000);
  }

  async function sendChat(page: any, msg: string) {
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 20000 });
    await page.getByTestId("public-vera-chat-input").fill(msg);
    await page.getByTestId("public-vera-chat-submit").click();
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 120000 });
    await page.waitForTimeout(2000);
  }

  function setupConsoleTracking(page: any): string[] {
    const errors: string[] = [];
    page.on("console", (msg: any) => { if (msg.type() === "error") errors.push(msg.text()); });
    page.on("pageerror", (err: Error) => errors.push(err.message));
    return errors;
  }

  function assertNoCriticalErrors(consoleErrors: string[]) {
    const critical = consoleErrors.filter(
      (e) => !e.includes("ERR_CONNECTION_REFUSED") && !e.includes("favicon") && !e.includes("503") && !e.includes("504")
    );
    expect(critical).toEqual([]);
  }

  async function getEntryText(page: any): Promise<string> {
    return (await page.getByTestId("public-vera-entry").innerText()) || "";
  }

  test.describe("Real backend (T360_REAL_E2E=1 required)", () => {
    test.skip(process.env.T360_REAL_E2E !== "1",
      "Set T360_REAL_E2E=1 with backend 7050 and astro 3050 active");

    test("A: continuation with number 1 after diagnosis", async ({ page }) => {
      const consoleErrors = setupConsoleTracking(page);
      await page.goto(VERA_URL);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      await sendInitial(page, "Tengo SAP y extractos bancarios de 3 bancos");
      await sendChat(page, "Quiero encontrar diferencias en forma automática");
      await sendChat(page, "Alguien revisa a mano");
      await sendChat(page, "Ver diagnóstico");

      let text = await getEntryText(page);
      expect(text).toContain("SAP");

      await sendChat(page, "Seguir conversando");
      text = await getEntryText(page);
      expect(text).not.toContain("Qué entendí");

      await sendChat(page, "1");
      text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);
      expect(text).not.toContain("Recibí la información");

      assertNoCriticalErrors(consoleErrors);
    });

    test("B: continuation with text 'Tipo de diferencias' after diagnosis", async ({ page }) => {
      const consoleErrors = setupConsoleTracking(page);
      await page.goto(VERA_URL);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      await sendInitial(page, "Tengo SAP y extractos bancarios de 3 bancos");
      await sendChat(page, "Quiero encontrar diferencias en forma automática");
      await sendChat(page, "Alguien revisa a mano");
      await sendChat(page, "Ver diagnóstico");
      await sendChat(page, "Seguir conversando");
      await sendChat(page, "Tipo de diferencias");

      const text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);
      expect(text).not.toContain("Recibí la información");
      expect(text).not.toContain("Qué entendí");
      // Response must reference SAP
      expect(text.toLowerCase()).toContain("sap");

      assertNoCriticalErrors(consoleErrors);
    });

    test("C: 'Tipo de diferencias' response contains specific discrepancy categories", async ({ page }) => {
      const consoleErrors = setupConsoleTracking(page);
      await page.goto(VERA_URL);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      await sendInitial(page, "Tengo SAP y extractos bancarios de 3 bancos");
      await sendChat(page, "Quiero encontrar diferencias en forma automática");
      await sendChat(page, "Alguien revisa a mano");
      await sendChat(page, "Ver diagnóstico");
      await sendChat(page, "Seguir conversando");
      await sendChat(page, "Tipo de diferencias");

      const text = await getEntryText(page);
      expect(text).not.toContain("system");
      expect(text).not.toContain("inquiry");
      // Must reference bank/SAP concepts
      expect(text.toLowerCase()).toContain("sap");
      expect(text.toLowerCase()).toContain("banc");
      // Must mention at least 3 discrepancy types
      const concepts = ["faltante", "distinto", "fecha", "duplicado",
        "comision", "cargo", "moneda", "cotización", "referencia",
        "pendiente", "conciliación", "diferencia"];
      const matched = concepts.filter(c => text.toLowerCase().includes(c));
      expect(matched.length).toBeGreaterThanOrEqual(3);

      assertNoCriticalErrors(consoleErrors);
    });

    test("D: second option 'Flujo operativo' after diagnosis", async ({ page }) => {
      const consoleErrors = setupConsoleTracking(page);
      await page.goto(VERA_URL);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      await sendInitial(page, "Tengo SAP y extractos bancarios de 3 bancos");
      await sendChat(page, "Quiero encontrar diferencias en forma automática");
      await sendChat(page, "Alguien revisa a mano");
      await sendChat(page, "Ver diagnóstico");
      await sendChat(page, "Seguir conversando");
      await sendChat(page, "Flujo operativo");

      const text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);
      expect(text).not.toContain("Recibí la información");

      assertNoCriticalErrors(consoleErrors);
    });

    test("E: continuation in English after diagnosis", async ({ page }) => {
      const consoleErrors = setupConsoleTracking(page);
      await page.goto(VERA_URL);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      await sendInitial(page, "I have SAP and bank statements from 3 banks");
      await sendChat(page, "I want to find discrepancies automatically");
      await sendChat(page, "Someone reviews them manually");
      await sendChat(page, "View diagnosis");

      let text = await getEntryText(page);
      expect(text).toContain("SAP");

      await sendChat(page, "Continue the conversation");
      text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);

      await sendChat(page, "1");
      text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);
      // Response should be in English
      const lower = text.toLowerCase();
      const hasEnglish = lower.includes("difference") || lower.includes("discrepanc") || lower.includes("type");
      expect(hasEnglish).toBeTruthy();

      assertNoCriticalErrors(consoleErrors);
    });

    test("F: continuation in Hebrew after diagnosis", async ({ page }) => {
      const consoleErrors = setupConsoleTracking(page);
      await page.goto(VERA_URL);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      await sendInitial(page, "יש לי SAP ודפי חשבון משלושה בנקים");
      await sendChat(page, "אני רוצה לזהות פערים באופן אוטומטי");
      await sendChat(page, "מישהו בודק אותם ידנית");
      await sendChat(page, "תצוגת אבחון");

      let text = await getEntryText(page);
      expect(text).toContain("SAP");

      await sendChat(page, "המשך שיחה");
      text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);

      await sendChat(page, "1");
      text = await getEntryText(page);
      expect(text.length).toBeGreaterThan(50);
      // Should contain Hebrew Unicode characters
      const hasHebrew = /[\u0590-\u05FF]/.test(text);
      expect(hasHebrew).toBeTruthy();

      assertNoCriticalErrors(consoleErrors);
    });
  });
});
