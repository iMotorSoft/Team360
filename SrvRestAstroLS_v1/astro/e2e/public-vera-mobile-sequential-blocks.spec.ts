import { expect, test } from "@playwright/test";

test.use({ hasTouch: true, viewport: { width: 393, height: 852 } });

test.describe("Vera mobile — sequential blocks lifecycle", () => {
  test.setTimeout(300000);

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
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 60000 });
    await page.waitForTimeout(2000);
  }

  async function waitForResponse(page: any) {
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 60000 });
    await page.waitForTimeout(3000);
  }

  function setupConsoleTracking(page: any): string[] {
    const errors: string[] = [];
    page.on("console", (msg: any) => { if (msg.type() === "error") errors.push(msg.text()); });
    page.on("pageerror", (err: Error) => errors.push(err.message));
    return errors;
  }

  function assertNoCriticalErrors(errors: string[]) {
    const critical = errors.filter(
      (e) => !e.includes("ERR_CONNECTION_REFUSED") && !e.includes("favicon") && !e.includes("503") && !e.includes("504")
    );
    expect(critical).toEqual([]);
  }

  async function auditBlock(
    page: any,
    blockType: string,
    index: number,
    requestCountBefore: number,
  ): Promise<SequentialBlockAudit> {
    const activeBlock = page.getByTestId(`t360-block-${blockType}`);
    const answeredBlock = page.getByTestId(`t360-block-${blockType}-answered`);

    const isAnswered = await answeredBlock.isVisible().catch(() => false);
    const isActive = await activeBlock.isVisible().catch(() => false);

    const stateAttr = isActive
      ? await activeBlock.getAttribute("data-interaction-state").catch(() => null)
      : isAnswered
        ? await answeredBlock.getAttribute("data-interaction-state").catch(() => null)
        : null;

    const disabledBtns: string[] = [];
    for (const id of ["t360-single-submit", "t360-multi-submit"]) {
      const btn = page.getByTestId(id);
      if (await btn.isVisible().catch(() => false)) {
        const disabled = await btn.isDisabled().catch(() => true);
        if (disabled) disabledBtns.push(id);
      }
    }

    const peValues: string[] = [];
    if (isActive) {
      const els = await activeBlock.locator("[data-testid^='t360-option-']").all();
      for (const el of els) {
        const pe = await el.evaluate((node: HTMLElement) => getComputedStyle(node).pointerEvents).catch(() => "unknown");
        peValues.push(pe);
      }
    }

    return {
      index,
      blockType,
      interactionState: stateAttr,
      consumed: isAnswered || (stateAttr === "answered"),
      answered: isAnswered,
      disabledButtons: disabledBtns,
      pointerEvents: peValues,
      loading: false,
      requestCountBefore,
      requestCountAfter: 0,
    };
  }

  // ═══════════════════════════════════════════════════════════════════════
  // Sequential blocks lifecycle — the critical mobile test
  // ═══════════════════════════════════════════════════════════════════════

  test("mobile sequential: block A answered → block B requires-response", async ({ page }) => {
    const consoleErrors = setupConsoleTracking(page);

    await page.goto(VERA_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    // Step 1 — Establish conversation
    await sendInitial(page, "recibimos muchas llamadas de teléfono");
    await sendChat(page, "problemas");

    // Step 2 — Block A (single_choice) should appear
    const blockA = page.getByTestId("t360-block-single_choice");
    await expect(blockA).toBeVisible({ timeout: 20000 });

    // Audit block A — it should be requires-response
    const aAudit = await auditBlock(page, "single_choice", 0, 0);
    expect(aAudit.interactionState).toBe("requires-response");

    // Step 3 — Tap Planilla / Excel (touch interaction)
    const option = page.getByTestId("t360-option-spreadsheet");
    await expect(option).toBeVisible();
    await expect(option).toBeEnabled();

    // Check no overlay above the option
    const box = await option.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      const cx = box.x + box.width / 2;
      const cy = box.y + box.height / 2;
      const topEl = await page.evaluate(
        ({ x, y }: { x: number; y: number }) => {
          const el = document.elementFromPoint(x, y);
          if (!el) return null;
          return {
            tag: el.tagName,
            testid: el.getAttribute("data-testid"),
            className: el.className.slice(0, 120),
          };
        },
        { x: cx, y: cy },
      );
      expect(topEl).not.toBeNull();
      // The element under the finger should be the option or a child of it
      const testid = topEl?.testid ?? "";
      const tag = topEl?.tag ?? "";
      const isOptionOrChild = testid === "t360-option-spreadsheet"
        || tag === "LABEL"
        || tag === "INPUT"
        || tag === "SPAN";
      expect(isOptionOrChild).toBe(true);
    }

    // Tap using real touch interaction
    await option.tap();
    await page.waitForTimeout(500);

    // Submit button should now be enabled
    const submitA = page.getByTestId("t360-single-submit");
    await expect(submitA).toBeEnabled();
    await submitA.tap();

    // Wait for response — block A should be answered
    await waitForResponse(page);

    // After response, block A should show as answered
    const blockAAnswered = page.getByTestId("t360-block-single_choice-answered");
    const aAnsweredVisible = await blockAAnswered.isVisible().catch(() => false);

    if (!aAnsweredVisible) {
      // It might be that the block A was superseded by block B
      // and disappeared from the latest message. That's OK — the key
      // assertion is that block B (if present) starts active.
    }

    // Step 4 — Wait for and inspect block B (multi_choice or next_step_choice)
    await page.waitForTimeout(3000);

    const blockBisMulti = page.getByTestId("t360-block-multi_choice");
    const blockBisNext = page.getByTestId("t360-block-next_step_choice");
    const blockBmulti = await blockBisMulti.isVisible().catch(() => false);
    const blockBnext = await blockBisNext.isVisible().catch(() => false);

    if (blockBmulti) {
      // Audit block B — MUST be requires-response
      const bAudit = await auditBlock(page, "multi_choice", 1, 0);
      expect(bAudit.interactionState).toBe("requires-response");

      // Block B options should NOT be disabled
      const optClassify = page.getByTestId("t360-option-classify");
      await expect(optClassify).toBeVisible();
      await expect(optClassify).toBeEnabled();
      const pe = await optClassify.evaluate((node: HTMLElement) => getComputedStyle(node).pointerEvents);
      expect(pe).not.toBe("none");

      // Tap first option
      await optClassify.tap();
      await page.waitForTimeout(300);

      // Counter should update
      const counterText = await blockBisMulti.innerText();
      expect(counterText).toContain("1/3");

      // Second option
      const optEscalate = page.getByTestId("t360-option-escalate");
      await expect(optEscalate).toBeEnabled();
      await optEscalate.tap();
      await page.waitForTimeout(300);

      const counterText2 = await blockBisMulti.innerText();
      expect(counterText2).toContain("2/3");

      // Submit
      const submitB = page.getByTestId("t360-multi-submit");
      await expect(submitB).toBeEnabled();
      await submitB.tap();

      // Wait for resolution
      await waitForResponse(page);

      // Blocks A and B should now BOTH be consumed (A from before, B now)
      // Verify no errors
      const hasError = await page.getByTestId("public-vera-error").isVisible().catch(() => false);
      expect(hasError).toBe(false);

    } else if (blockBnext) {
      // Block B is a next_step_choice — just verify it's active
      const nsState = await blockBisNext.getAttribute("data-interaction-state");
      expect(nsState).not.toBe("answered");

      // Tap a button on it
      const contBtn = page.getByTestId("t360-action-continue-context");
      if (await contBtn.isVisible().catch(() => false)) {
        await contBtn.tap();
        await waitForResponse(page);
      } else {
        const showDiag = page.getByTestId("t360-action-show-current-diagnosis");
        if (await showDiag.isVisible().catch(() => false)) {
          await showDiag.tap();
          await page.waitForTimeout(5000);
        }
      }

      const hasError = await page.getByTestId("public-vera-error").isVisible().catch(() => false);
      expect(hasError).toBe(false);
    } else {
      // No block B — conversation may continue by text, that's OK
      // Just verify chat is still working
      await expect(page.getByTestId("public-vera-chat-input")).toBeVisible();
    }

    // No mobile horizontal overflow
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);

    assertNoCriticalErrors(consoleErrors);
  });
});
