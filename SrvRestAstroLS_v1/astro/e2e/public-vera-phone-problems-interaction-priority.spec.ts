import { expect, test } from "@playwright/test";

test.describe("Vera phone problems — interaction priority", () => {
  test.setTimeout(300000);

  const VERA_URL = "/t360";

  // ── Helpers ─────────────────────────────────────────────────────────────

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
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 60000 });
    await page.waitForTimeout(2000);
  }

  async function clickBlockAndWait(page: any) {
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 60000 });
    await page.waitForTimeout(3000);
  }

  async function blockIsActive(page: any, blockType: string): Promise<boolean> {
    return page.getByTestId(`t360-block-${blockType}`).isVisible().catch(() => false);
  }

  async function blockIsAnswered(page: any, blockType: string): Promise<boolean> {
    return page.getByTestId(`t360-block-${blockType}-answered`).isVisible().catch(() => false);
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

  // ═══════════════════════════════════════════════════════════════════════
  // J: Copy correction (fast, independent)
  // ═══════════════════════════════════════════════════════════════════════

  test("J: question copy says 'las consultas' not 'los consultas'", async ({ page }) => {
    const consoleErrors = setupConsoleTracking(page);

    await page.goto(VERA_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();
    await sendInitial(page, "recibimos muchas llamadas de teléfono");
    await sendChat(page, "problemas");

    const scBlock = page.getByTestId("t360-block-single_choice");
    await expect(scBlock).toBeVisible({ timeout: 20000 });

    const scText = await scBlock.innerText();
    expect(scText).toContain("las consultas");
    expect(scText).not.toContain("los consultas");

    assertNoCriticalErrors(consoleErrors);
  });

  // ═══════════════════════════════════════════════════════════════════════
  // A: single_choice click resolves — block transitions to answered
  // ═══════════════════════════════════════════════════════════════════════

  test("A: single_choice click resolves block", async ({ page }) => {
    const consoleErrors = setupConsoleTracking(page);

    await page.goto(VERA_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();
    await sendInitial(page, "recibimos muchas llamadas de teléfono");
    await sendChat(page, "problemas");

    // single_choice should appear
    const scBlock = page.getByTestId("t360-block-single_choice");
    await expect(scBlock).toBeVisible({ timeout: 20000 });
    await expect(scBlock).toContainText("¿Dónde se registran y siguen hoy las consultas?");

    // Option is active
    const option = page.getByTestId("t360-option-spreadsheet");
    await expect(option).toBeVisible();
    await expect(option).toBeEnabled();

    // Click option and submit
    await option.click();
    const submitBtn = page.getByTestId("t360-single-submit");
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    // Wait for response — block should be consumed, chat continues
    await clickBlockAndWait(page);

    // After click, block is answered or chat progressed — no error
    const hasError = await page.getByTestId("public-vera-error").isVisible().catch(() => false);
    expect(hasError).toBe(false);

    // Chat input should be accessible
    await expect(page.getByTestId("public-vera-chat-input")).toBeVisible();

    assertNoCriticalErrors(consoleErrors);
  });

  // ═══════════════════════════════════════════════════════════════════════
  // C: multi_choice click — counter updates, block resolved
  // ═══════════════════════════════════════════════════════════════════════

  test("C: multi_choice click resolves block", async ({ page }) => {
    const consoleErrors = setupConsoleTracking(page);

    await page.goto(VERA_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();
    await sendInitial(page, "recibimos muchas llamadas de teléfono");
    await sendChat(page, "problemas");

    // Answer single_choice to unlock multi_choice
    const scBlock = page.getByTestId("t360-block-single_choice");
    await expect(scBlock).toBeVisible({ timeout: 20000 });
    await page.getByTestId("t360-option-spreadsheet").click();
    await page.getByTestId("t360-single-submit").click();
    await clickBlockAndWait(page);

    // Check if multi_choice appeared
    const mcBlock = page.getByTestId("t360-block-multi_choice");
    if (await mcBlock.isVisible({ timeout: 15000 }).catch(() => false)) {
      // Counter starts at 0/3
      await expect(mcBlock).toContainText("0/3");

      // Select classify
      await page.getByTestId("t360-option-classify").click();
      await page.waitForTimeout(300);
      await expect(mcBlock).toContainText("1/3");

      // Select escalate
      await page.getByTestId("t360-option-escalate").click();
      await page.waitForTimeout(300);
      await expect(mcBlock).toContainText("2/3");

      // Submit
      await page.getByTestId("t360-multi-submit").click();
      await clickBlockAndWait(page);

      // No error
      const hasError = await page.getByTestId("public-vera-error").isVisible().catch(() => false);
      expect(hasError).toBe(false);
    }

    assertNoCriticalErrors(consoleErrors);
  });

  // ═══════════════════════════════════════════════════════════════════════
  // G: no simultaneous actionable blocks at key checkpoints
  // ═══════════════════════════════════════════════════════════════════════

  test("G: no simultaneous actionable blocks", async ({ page }) => {
    const consoleErrors = setupConsoleTracking(page);

    const checkNoConflict = async (): Promise<number> => {
      const actionable = ["single_choice", "multi_choice", "next_step_choice"];
      let count = 0;
      for (const bt of actionable) {
        if (await blockIsActive(page, bt)) count++;
      }
      return count;
    };

    await page.goto(VERA_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();
    await sendInitial(page, "recibimos muchas llamadas de teléfono");
    await sendChat(page, "problemas");

    // After turn 2: single_choice should appear alone
    let conflicts = await checkNoConflict();
    expect(conflicts).toBeLessThanOrEqual(1);

    // Resolve single_choice
    if (await blockIsActive(page, "single_choice")) {
      await page.getByTestId("t360-option-spreadsheet").click();
      await page.getByTestId("t360-single-submit").click();
      await clickBlockAndWait(page);

      conflicts = await checkNoConflict();
      expect(conflicts).toBeLessThanOrEqual(1);
    }

    // 1-2 more interactions
    for (let i = 0; i < 3; i++) {
      if (await blockIsActive(page, "multi_choice")) {
        await page.getByTestId("t360-option-classify").click();
        await page.waitForTimeout(300);
        await page.getByTestId("t360-option-escalate").click();
        await page.waitForTimeout(300);
        await page.getByTestId("t360-multi-submit").click();
        await clickBlockAndWait(page);
      } else if (await blockIsActive(page, "next_step_choice")) {
        const contBtn = page.getByTestId("t360-action-continue-context");
        if (await contBtn.isVisible().catch(() => false)) {
          await contBtn.click();
          await clickBlockAndWait(page);
        }
      } else {
        const inputOk = await page.getByTestId("public-vera-chat-input").isEnabled().catch(() => false);
        if (!inputOk) break;
        await sendChat(page, "contame más");
      }

      conflicts = await checkNoConflict();
      expect(conflicts).toBeLessThanOrEqual(1);

      if (await page.getByTestId("diagnosis-result").isVisible().catch(() => false)) break;
    }

    assertNoCriticalErrors(consoleErrors);
  });

  // ═══════════════════════════════════════════════════════════════════════
  // H: Planilla / Excel appears once as a system entry in diagnosis
  // ═══════════════════════════════════════════════════════════════════════

  test("H: Planilla / Excel appears once as system entry", async ({ page }) => {
    const consoleErrors = setupConsoleTracking(page);

    await page.goto(VERA_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();
    await sendInitial(page, "recibimos muchas llamadas de teléfono");
    await sendChat(page, "problemas");

    // Answer single_choice with Planilla / Excel
    await expect(page.getByTestId("t360-block-single_choice")).toBeVisible({ timeout: 20000 });
    await page.getByTestId("t360-option-spreadsheet").click();
    await page.getByTestId("t360-single-submit").click();
    await clickBlockAndWait(page);

    // Continue and request diagnosis
    for (const msg of ["recibimos consultas todo el día", "somos tres personas en el equipo"]) {
      await sendChat(page, msg);
    }

    await sendChat(page, "ver diagnostico");
    await page.waitForTimeout(5000);

    // Check diagnosis-result for dedup
    const diagResult = page.getByTestId("diagnosis-result");
    if (await diagResult.isVisible().catch(() => false)) {
      const diagText = await diagResult.innerText().catch(() => "");

      // In the systems list section: no duplicate entries
      // Check bullet-pointed system entries don't have both "Planilla" and "Planilla / Excel"
      const bulletEntries = diagText.match(/(?:^|\n)\s*[-•*]\s+[^\n]+/gm) || [];
      const planillaEntries = bulletEntries.filter(e => /Planilla/i.test(e));
      const planillaExcelEntries = planillaEntries.filter(e => /Planilla \/ Excel/i.test(e));
      const standalonePlanillaEntries = planillaEntries.filter(e => !/Planilla \/ Excel/i.test(e));

      // If systems list has Planilla entries, they should all be "Planilla / Excel"
      if (planillaEntries.length > 0) {
        expect(standalonePlanillaEntries.length).toBe(0);
      }

      // Planilla / Excel should appear as one entry, not multiple
      // (some variation in formatting is OK, but the label shouldn't be duplicated)
      expect(planillaExcelEntries.length).toBeLessThanOrEqual(1);
    }

    assertNoCriticalErrors(consoleErrors);
  });
});
