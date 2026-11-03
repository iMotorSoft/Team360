import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

// Run only with backend-dev.sh TEAM360_DEV_PROFILE=srv05-e2e and astro-dev.sh.
// Supply fresh scoped IDs, never mock responses or reuse production sessions.
test.describe("Srv05 opt-in safe runtime", () => {
  test.skip(process.env.TEAM360_SRV05_SAFE_E2E !== "1", "Requires test-only guarded listener");
  for (const surface of ["home", "mamamia"] as const) {
    test(`${surface}: real API, HMAC where applicable, response and second turn`, async ({ page }) => {
      test.setTimeout(120_000);
      const session = "full_gate_" + randomUUID().replaceAll("-", "");
      const errors: string[] = [];
      const serverErrors: string[] = [];
      const counts: number[] = [];
      let authCount = 0;
      let turnCount = 0;
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", msg => { if (msg.type() === "error") errors.push(msg.text()); });
      page.on("response", response => { if (response.status() >= 500) serverErrors.push(response.url()); });
      await page.route("**/api/diagnosis/{turn,embed/auth}", async route => {
        const request = route.request();
        if (request.method() !== "POST") return route.continue();
        const body = request.postDataJSON();
        body.session_id = session;
        if (request.url().endsWith("/turn")) turnCount++;
        else authCount++;
        await route.continue({ postData: JSON.stringify(body) });
      });
      await page.goto(surface === "home" ? "/t360" : "/embed-demo/mamamia360.html");
      await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 20_000 });
      const first = page.waitForResponse(r => r.url().endsWith("/api/diagnosis/turn") && r.request().method() === "POST");
      await page.getByTestId("public-vera-text").fill("Sonda sintética: recibo 20 consultas de ventas por Gmail al día, stock en ERP y precios en Excel; siempre requiere aprobación humana.");
      await page.getByTestId("public-vera-submit").click();
      const firstResponse = await first;
      expect(firstResponse.status()).toBe(201);
      const firstBody = await firstResponse.json();
      expect(firstBody.session_id).toBe(session);
      expect(firstBody.response_text.length).toBeGreaterThan(0);
      expect(firstBody.turn_decision.generation.fallback_used).toBe(false);
      counts.push(firstBody.turn_count);
      await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 60_000 });
      const rendered = firstBody.response_text.replace(/[*_`]/g, "").replace(/\s+/g, " ").trim();
      await expect(page.getByTestId("public-vera-assistant-message").last()).toContainText(rendered);
      const second = page.waitForResponse(r => r.url().endsWith("/api/diagnosis/turn") && r.request().method() === "POST");
      await page.getByTestId("public-vera-chat-input").fill("Necesito una orientación inicial, sin ejecutar ninguna acción externa.");
      await page.getByTestId("public-vera-chat-submit").click();
      const secondResponse = await second;
      expect(secondResponse.status()).toBe(201);
      const secondBody = await secondResponse.json();
      expect(secondBody.session_id).toBe(session);
      expect(secondBody.turn_count).toBe(firstBody.turn_count + 1);
      expect(secondBody.turn_decision.generation.fallback_used).toBe(false);
      counts.push(secondBody.turn_count);
      await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 60_000 });
      await expect(page.getByTestId("public-vera-assistant-message")).toHaveCount(2);
      expect(turnCount).toBe(2);
      if (surface === "mamamia") expect(authCount).toBe(2);
      expect(errors).toEqual([]);
      expect(serverErrors).toEqual([]);
      await test.info().attach("safe-runtime", { body: JSON.stringify({ surface, session, counts, turnCount, authCount, errors, serverErrors }), contentType: "application/json" });
    });
  }
});
