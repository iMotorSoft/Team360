import { expect, test } from "@playwright/test";

const DIAGNOSIS_ENDPOINT = "/api/diagnosis/turn";
const EMBED_AUTH_ENDPOINT = "/api/diagnosis/embed/auth";

function criticalConsoleErrors(errors: string[]): string[] {
  return errors.filter(
    (e) => !e.includes("favicon") && !e.includes("net::ERR_ABORTED") && !e.includes("ERR_CONNECTION_REFUSED"),
  );
}

test.describe("Mamamia360 embed — Vera diagnosticador embebible", () => {
  test.describe.configure({ mode: "serial" });

  const MAMAMIA_CLIENT_ID = "mamamia360";
  const EMBED_SESSION_KEY_PREFIX = "team360.vera.embed.";

  test("loader and component mount successfully", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    // Track all requests to verify cross-origin asset resolution
    const embeddedScripts: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("team360-diagnosticador") && req.resourceType() === "script") {
        embeddedScripts.push(req.url());
      }
    });

    // Track status and decoded size of the secondary loader and entry bundle
    const embeddedResponses = new Map<
      string,
      { status: number | null; bodyBytes: number }
    >();
    page.on("response", async (res) => {
      if (
        res.url().includes("team360-diagnosticador-loader.js") ||
        res.url().includes("team360-diagnosticador.js")
      ) {
        let bodyBytes = 0;
        try {
          bodyBytes = (await res.body()).length;
        } catch {
          bodyBytes = -1;
        }
        embeddedResponses.set(res.url(), { status: res.status(), bodyBytes });
      }
    });

    await page.goto("/embed-demo/mamamia360.html");
    await expect(page.getByTestId("mamamia360-embed-target")).toBeVisible();

    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible({ timeout: 15000 });

    // Anti-debug: no technical strings in the visible UI
    const pageText = await page.locator("body").innerText();
    const forbidden = [
      "svc_sales_diagnosis",
      "assistant_instance_code",
      "package_code",
      "knowledge_scope_code",
      "Turno",
      "sessionId",
    ];
    for (const term of forbidden) {
      expect(pageText, `forbidden text "${term}" found in embed UI`).not.toContain(term);
    }

    // Verify commercial-grade wrapper header and footer
    await expect(page.locator(".vera-embed-badge")).toBeVisible();
    await expect(page.locator(".vera-embed-footer")).toBeVisible();

    // Verify commercial-grade UI elements — button is present and visible
    // (disabled until text is entered is expected behavior)
    await expect(page.getByTestId("public-vera-submit")).toBeVisible();
    const textarea = page.getByTestId("public-vera-text");
    await expect(textarea).toBeVisible();
    // textarea should have non-zero dimensions (usable, not collapsed)
    const textareaBox = await textarea.boundingBox();
    expect(textareaBox).not.toBeNull();
    expect(textareaBox!.width).toBeGreaterThan(100);
    expect(textareaBox!.height).toBeGreaterThan(50);

    const criticalErrors = criticalConsoleErrors(consoleErrors);
    expect(criticalErrors).toEqual([]);
    expect(consoleErrors.some((e) => e.includes("[VeraLoader] Failed to load"))).toBe(false);

    // Secondary loader must load with a real body (guards against 0-byte
    // responses like the one observed in production after the WP Rocket purge).
    const loaderResponses = Array.from(embeddedResponses.entries()).filter(([url]) =>
      url.includes("team360-diagnosticador-loader.js"),
    );
    expect(loaderResponses.length, "secondary loader response captured").toBeGreaterThan(0);
    for (const [, info] of loaderResponses) {
      expect(info.status, "secondary loader HTTP status").toBe(200);
      expect(info.bodyBytes, "secondary loader body size").toBeGreaterThan(0);
    }

    // Entry bundle must appear in Network and load with a real body.
    const entryResponses = Array.from(embeddedResponses.entries()).filter(([url]) =>
      url.includes("team360-diagnosticador.js"),
    );
    expect(entryResponses.length, "entry bundle requested in Network").toBeGreaterThan(0);
    for (const [, info] of entryResponses) {
      expect(info.status, "entry bundle HTTP status").toBe(200);
      expect(info.bodyBytes, "entry bundle body size").toBeGreaterThan(0);
    }

    // Cross-origin safety: the loader must NOT request assets relative to
    // the host domain. Every embedded script should be loaded from an
    // absolute URL (not a root-relative path like "/embed/...").
    const hostRelative = embeddedScripts.filter((url) => url.startsWith("/"));
    expect(hostRelative, "no host-relative embedded script requests").toEqual([]);
    expect(embeddedScripts.length, "at least one embedded script loaded").toBeGreaterThan(0);
    // No request must ever target the client site's own /embed/ directory.
    const hostEmbedRequests = embeddedScripts.filter((url) =>
      url.includes("mamamia360.com/embed/"),
    );
    expect(hostEmbedRequests, "no requests to mamamia360.com/embed/").toEqual([]);
  });

  test("conversation flow: feasibility diagnosis works", async ({ page }) => {
    test.setTimeout(300_000);

    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    let authRequestCaptured = false;
    let turnRequestCaptured = false;

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    page.on("request", (request) => {
      if (request.method() !== "POST") return;
      if (request.url().includes(EMBED_AUTH_ENDPOINT)) {
        authRequestCaptured = true;
        const body = request.postDataJSON() as Record<string, unknown>;
        expect(body.client_id).toBe(MAMAMIA_CLIENT_ID);
        expect(body).not.toHaveProperty("package_code");
        expect(body).not.toHaveProperty("knowledge_scope_code");
        expect(body).not.toHaveProperty("assistant_instance_code");
        expect(body).not.toHaveProperty("organization_code");
        expect(body).not.toHaveProperty("workspace_code");
      }
      if (request.url().includes(DIAGNOSIS_ENDPOINT)) {
        turnRequestCaptured = true;
        const body = request.postDataJSON() as Record<string, unknown>;
        expect(body.client_id).toBe(MAMAMIA_CLIENT_ID);
        expect(body).not.toHaveProperty("package_code");
        expect(body).not.toHaveProperty("knowledge_scope_code");
      }
    });

    page.on("requestfailed", (request) => {
      if (request.method() === "POST" && request.url().includes(DIAGNOSIS_ENDPOINT)) {
        failedRequests.push(`${request.url()} ${request.failure()?.errorText ?? "unknown"}`);
      }
    });

    await page.goto("/embed-demo/mamamia360.html");
    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 15000 });

    await page.getByTestId("public-vera-text").fill("recibo muchos email");
    await page.getByTestId("public-vera-submit").click();

    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });
    await expect.poll(() => authRequestCaptured).toBe(true);
    await expect.poll(() => turnRequestCaptured).toBe(true);

    await page.getByTestId("public-vera-chat-input").fill("facturacion");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    await page.getByTestId("public-vera-chat-input").fill("Planilla / Excel");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    await page.getByTestId("public-vera-chat-input").fill("Derivar casos a una persona");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    await page.getByTestId("public-vera-chat-input").fill("por el asunto puede reimpresion, anulacion, credito");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    await page.getByTestId("public-vera-chat-input").fill("50 por dia");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    await page.getByTestId("public-vera-chat-input").fill("dame un diagnóstico");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    const criticalErrors = criticalConsoleErrors(consoleErrors);
    expect(criticalErrors).toEqual([]);
    expect(failedRequests).toEqual([]);

    const embedSessionKey = EMBED_SESSION_KEY_PREFIX + MAMAMIA_CLIENT_ID + ".session.v1";
    const sessionData = await page.evaluate((key) => sessionStorage.getItem(key), embedSessionKey);
    expect(sessionData).not.toBeNull();
  });

  test("no implementation questions in feasibility diagnosis", async ({ page }) => {
    test.setTimeout(300_000);

    const IMPLEMENTATION_TERMS = [
      "API", "webhook", "OAuth", "token", "credenciales",
      "Google Drive", "Google Sheets", "cuenta de servicio",
      "columna exacta", "fila nueva",
    ];

    const VALID_CONTEXTS = [
      "punto a validar", "análisis de flujo", "implementación posterior",
      "etapa posterior", "técnicamente",
    ];

    function hasProhibitedQuestion(text: string): boolean {
      const lower = text.toLowerCase();
      if (!lower.includes("?")) return false;
      for (const term of IMPLEMENTATION_TERMS) {
        if (lower.includes(term.toLowerCase())) {
          const sentences = lower.split(/[.!?\n]+/);
          for (const s of sentences) {
            if (s.includes(term.toLowerCase())) {
              const inValidContext = VALID_CONTEXTS.some((ctx) => s.includes(ctx));
              if (!inValidContext) return true;
            }
          }
        }
      }
      return false;
    }

    const responseTexts: string[] = [];

    page.on("response", async (response) => {
      if (response.url().includes(DIAGNOSIS_ENDPOINT) && response.status() < 500) {
        try {
          const body = (await response.json()) as Record<string, unknown>;
          const text = String(body.response_text ?? "");
          if (text.trim()) responseTexts.push(text);
        } catch {}
      }
    });

    await page.goto("/embed-demo/mamamia360.html");
    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 15000 });

    const messages = [
      "recibo muchos email",
      "facturacion",
      "Planilla / Excel",
      "Derivar casos a una persona",
      "por el asunto puede reimpresion, anulacion, credito",
      "50 por dia",
      "dame un diagnóstico",
    ];

    for (const msg of messages) {
      const isInitial = await page.getByTestId("public-vera-text").isVisible().catch(() => false);
      const input = isInitial
        ? page.getByTestId("public-vera-text")
        : page.getByTestId("public-vera-chat-input");
      const submit = isInitial
        ? page.getByTestId("public-vera-submit")
        : page.getByTestId("public-vera-chat-submit");

      await input.fill(msg);
      await expect(submit).toBeEnabled();
      const turnResponse = page.waitForResponse(
        (response) =>
          response.url().includes(DIAGNOSIS_ENDPOINT) &&
          response.request().method() === "POST",
        { timeout: 90_000 },
      );
      await submit.click();
      const response = await turnResponse;
      expect(response.status(), "diagnosis turn HTTP status").toBeLessThan(500);
      await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });
      await expect(page.getByTestId("public-vera-chat-submit")).toHaveText("Enviar", {
        timeout: 90_000,
      });
    }

    for (const text of responseTexts) {
      if (hasProhibitedQuestion(text)) {
        console.error(`PROHIBITED_QUESTION in response: "${text.slice(0, 200)}"`);
      }
      expect(hasProhibitedQuestion(text)).toBe(false);
    }
  });

  test("interactive blocks appear in the conversation", async ({ page }) => {
    test.setTimeout(180_000);

    await page.goto("/embed-demo/mamamia360.html");
    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 15000 });

    await page.getByTestId("public-vera-text").fill("recibo muchos email de facturacion, 50 por dia");
    await page.getByTestId("public-vera-submit").click();

    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    const hasInteractionBlock = await page.getByTestId("t360-interaction-block").isVisible().catch(() => false);
    if (hasInteractionBlock) {
      await expect(page.getByTestId("t360-interaction-block")).toBeVisible();
    }
  });

  test("single-choice options are visible, selectable, and advance the conversation", async ({ page }) => {
    test.setTimeout(240_000);

    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    const hostEmbedRequests: string[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("request", (request) => {
      if (request.url().includes("mamamia360.com/embed/")) {
        hostEmbedRequests.push(request.url());
      }
    });
    page.on("requestfailed", (request) => {
      if (request.url().includes("team360.live")) {
        failedRequests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? "unknown"}`);
      }
    });

    await page.goto("/embed-demo/mamamia360.html");
    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible({ timeout: 15_000 });

    const sendTextTurn = async (message: string, initial = false) => {
      const input = page.getByTestId(initial ? "public-vera-text" : "public-vera-chat-input");
      const submit = page.getByTestId(initial ? "public-vera-submit" : "public-vera-chat-submit");
      await input.fill(message);
      await expect(submit).toBeEnabled();
      const turnResponse = page.waitForResponse(
        (response) => response.url().includes(DIAGNOSIS_ENDPOINT)
          && response.request().method() === "POST",
        { timeout: 90_000 },
      );
      await submit.click();
      expect((await turnResponse).status()).toBeLessThan(500);
      await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });
    };

    await sendTextTurn("Vendo tortas", true);
    await sendTextTurn("Por whatsapp");

    const question = "¿Dónde se registran y siguen hoy las consultas?";
    const block = page.getByTestId("t360-block-single_choice").filter({ hasText: question }).last();
    await expect(block).toBeVisible({ timeout: 90_000 });

    const option = block.getByText("Solo en WhatsApp Business", { exact: true });
    const optionCard = option.locator("xpath=ancestor::label");
    const continueButton = block.getByTestId("t360-single-submit");

    await expect(optionCard).toBeVisible();
    await expect(continueButton).toBeVisible();
    await expect(continueButton).toBeDisabled();

    const optionBox = await optionCard.boundingBox();
    expect(optionBox).not.toBeNull();
    expect(optionBox!.width).toBeGreaterThan(250);
    expect(optionBox!.height).toBeGreaterThan(32);
    expect(await optionCard.evaluate((element) => getComputedStyle(element).display)).not.toBe("inline");

    await optionCard.click();
    await expect(optionCard.locator("input")).toBeChecked();
    await expect(continueButton).toBeEnabled();
    await expect(optionCard).toHaveCSS("border-color", "rgb(22, 139, 136)");
    await expect(optionCard).toHaveCSS("background-color", "rgb(230, 245, 243)");

    const previousAssistantMessages = await page.getByTestId("public-vera-assistant-message").count();
    const interactionResponse = page.waitForResponse(
      (response) => response.url().includes(DIAGNOSIS_ENDPOINT)
        && response.request().method() === "POST",
      { timeout: 90_000 },
    );
    await continueButton.click();
    expect((await interactionResponse).status()).toBeLessThan(500);
    await expect(page.getByTestId("public-vera-assistant-message")).toHaveCount(
      previousAssistantMessages + 1,
      { timeout: 90_000 },
    );
    await expect(page.getByTestId("public-vera-error")).toHaveCount(0);

    const visibleText = await page.locator("body").innerText();
    for (const forbidden of ["Turno", "svc_sales_diagnosis", "sessionId"]) {
      expect(visibleText).not.toContain(forbidden);
    }
    expect(hostEmbedRequests).toEqual([]);
    expect(failedRequests).toEqual([]);
    expect(criticalConsoleErrors(consoleErrors)).toEqual([]);
  });

  test("embed auth does not leak sensitive data", async ({ page }) => {
    const capturedBodies: Record<string, unknown>[] = [];

    page.on("response", async (response) => {
      if (response.url().includes(EMBED_AUTH_ENDPOINT) && response.status() === 200) {
        try {
          capturedBodies.push((await response.json()) as Record<string, unknown>);
        } catch {}
      }
    });

    await page.goto("/embed-demo/mamamia360.html");
    await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 15000 });

    await page.getByTestId("public-vera-text").fill("recibo muchos email");
    await page.getByTestId("public-vera-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });

    await expect.poll(() => capturedBodies.length).toBeGreaterThanOrEqual(1);

    for (const body of capturedBodies) {
      expect(body).toHaveProperty("client_id", MAMAMIA_CLIENT_ID);
      expect(body).toHaveProperty("timestamp");
      expect(body).toHaveProperty("signature");
      expect(String(body.signature)).toMatch(/^sha256=[0-9a-f]{64}$/);

      for (const forbidden of [
        "hmac_secret", "allowed_origins", "package_code",
        "knowledge_scope_code", "assistant_instance_code",
        "organization_code", "workspace_code",
      ]) {
        expect(body).not.toHaveProperty(forbidden);
      }
    }
  });
});
