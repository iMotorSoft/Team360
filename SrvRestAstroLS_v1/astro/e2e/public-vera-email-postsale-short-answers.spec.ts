import { expect, test, type Page, type Request, type Response } from "@playwright/test";

const DIAGNOSIS_ENDPOINT = "/api/diagnosis/turn";
const GENERIC_FALLBACK = "Recibí la información, pero no pude procesarla completamente";

type CapturedTurn = {
  request: Record<string, unknown>;
  status: number;
  response: Record<string, unknown>;
};

function isDiagnosisRequest(request: Request): boolean {
  return request.method() === "POST" && request.url().endsWith(DIAGNOSIS_ENDPOINT);
}

function criticalConsoleErrors(errors: string[]): string[] {
  return errors.filter(
    (error) =>
      !error.includes("favicon") &&
      !error.includes("net::ERR_ABORTED"),
  );
}

async function submitTurn(page: Page, text: string, captured: CapturedTurn[]): Promise<CapturedTurn> {
  const initialInput = page.getByTestId("public-vera-text");
  const isInitial = await initialInput.isVisible().catch(() => false);
  const input = isInitial ? initialInput : page.getByTestId("public-vera-chat-input");
  const submit = isInitial
    ? page.getByTestId("public-vera-submit")
    : page.getByTestId("public-vera-chat-submit");

  const requestCountBefore = captured.length;
  await input.fill(text);
  await expect(submit).toBeEnabled();

  const responsePromise = page.waitForResponse(
    (response: Response) => isDiagnosisRequest(response.request()),
    { timeout: 90_000 },
  );
  await submit.click();
  const response = await responsePromise;
  const body = (await response.json()) as Record<string, unknown>;
  const requestBody = response.request().postDataJSON() as Record<string, unknown>;
  const turn = { request: requestBody, status: response.status(), response: body };
  captured.push(turn);
  console.log(`TURN_EVIDENCE ${JSON.stringify(turn)}`);

  await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });
  await expect.poll(() => captured.length).toBe(requestCountBefore + 1);
  expect(requestBody.message).toBe(text);
  expect(response.status()).toBeLessThan(500);
  expect(body.response_text).not.toContain(GENERIC_FALLBACK);
  expect((body.turn_decision as Record<string, any> | undefined)?.generation?.fallback_used).toBe(false);
  expect(String(body.response_text ?? "").trim().length).toBeGreaterThan(0);

  return turn;
}

test.describe("Vera email postventa — respuestas breves con contexto activo", () => {
  test("flujo exacto mantiene estado, no duplica requests y no usa fallback", async ({ page }) => {
    test.setTimeout(300_000);

    const captured: CapturedTurn[] = [];
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    const allDiagnosisRequests: Record<string, unknown>[] = [];

    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("requestfailed", (request) => {
      if (isDiagnosisRequest(request)) {
        failedRequests.push(`${request.url()} ${request.failure()?.errorText ?? "unknown"}`);
      }
    });
    page.on("request", (request) => {
      if (isDiagnosisRequest(request)) {
        allDiagnosisRequests.push(request.postDataJSON() as Record<string, unknown>);
      }
    });

    await page.goto("/t360");
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    const turns = [
      "Recibo muchos emails",
      "Postventa",
      "Solo en la bandeja de email",
      "En la bandeja de email",
      "Sistema propio",
    ];

    let sessionId = "";
    for (const [index, text] of turns.entries()) {
      const turn = await submitTurn(page, text, captured);
      const responseSessionId = String(turn.response.session_id ?? "");
      expect(responseSessionId).not.toBe("");
      if (index === 0) sessionId = responseSessionId;
      expect(responseSessionId).toBe(sessionId);
      expect(turn.response.turn_count).toBe(index + 1);
      expect(allDiagnosisRequests).toHaveLength(index + 1);
      await expect(page.getByTestId("public-vera-entry")).not.toContainText(GENERIC_FALLBACK);
      await expect.poll(async () => {
        const userMessages = await page.getByTestId("public-vera-user-message").allTextContents();
        return userMessages.filter((message) => message.trim() === text).length;
      }).toBe(1);
    }

    expect(captured).toHaveLength(turns.length);
    expect(allDiagnosisRequests).toHaveLength(turns.length);
    expect(failedRequests).toEqual([]);
    expect(criticalConsoleErrors(consoleErrors)).toEqual([]);
  });

  for (const variant of [
    { message: "Bandeja de email", canonical: "Solo en la bandeja de email" },
    { message: "Sistema interno", canonical: "Sistema propio" },
    { message: "Planilla / Excel", canonical: "Planilla / Excel" },
    { message: "No usamos sistema", canonical: "No hay un seguimiento definido" },
    { message: "Alguien revisa a mano", canonical: "No hay un seguimiento definido" },
  ]) {
    test(`variante textual activa: ${variant.message}`, async ({ page }) => {
      test.setTimeout(240_000);
      const captured: CapturedTurn[] = [];
      const consoleErrors: string[] = [];
      const failedRequests: string[] = [];

      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      page.on("pageerror", (error) => consoleErrors.push(error.message));
      page.on("requestfailed", (request) => {
        if (isDiagnosisRequest(request)) {
          failedRequests.push(`${request.url()} ${request.failure()?.errorText ?? "unknown"}`);
        }
      });

      await page.goto("/t360");
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();
      await submitTurn(page, "Recibo muchos emails", captured);
      await submitTurn(page, "Postventa", captured);
      await expect(page.getByTestId("t360-block-single_choice")).toBeVisible();

      const resolved = await submitTurn(page, variant.message, captured);
      const generation = (resolved.response.turn_decision as Record<string, any>).generation;
      expect(generation.response_source).toBe("deterministic_active_context");
      expect(generation.provider_called).toBe(false);
      expect(String(resolved.response.response_text)).toContain(variant.canonical);
      expect(resolved.request.interaction_response).toBeUndefined();
      expect((resolved.response.interaction_block as Record<string, unknown> | null)?.type).not.toBe("single_choice");
      expect(captured).toHaveLength(3);
      expect(failedRequests).toEqual([]);
      expect(criticalConsoleErrors(consoleErrors)).toEqual([]);
    });
  }

  test("click de opción hace un request y no duplica visualmente el label", async ({ page }) => {
    test.setTimeout(240_000);
    const captured: CapturedTurn[] = [];
    const diagnosisRequests: Request[] = [];

    page.on("request", (request) => {
      if (isDiagnosisRequest(request)) diagnosisRequests.push(request);
    });

    await page.goto("/t360");
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();
    await submitTurn(page, "Recibo muchos emails", captured);
    await submitTurn(page, "Postventa", captured);
    await expect(page.getByTestId("t360-block-single_choice")).toBeVisible();

    const requestCountBefore = diagnosisRequests.length;
    const responsePromise = page.waitForResponse(
      (response) => isDiagnosisRequest(response.request()),
      { timeout: 90_000 },
    );
    await page.getByTestId("t360-option-custom_system").click();
    await page.getByTestId("t360-single-submit").click();
    const response = await responsePromise;
    const responseBody = (await response.json()) as Record<string, any>;
    const requestBody = response.request().postDataJSON() as Record<string, any>;

    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });
    expect(diagnosisRequests).toHaveLength(requestCountBefore + 1);
    expect(requestBody.interaction_response).toMatchObject({
      block_type: "single_choice",
      option_id: "custom_system",
      value: "custom_system",
      label: "Sistema propio",
    });
    expect(response.status()).toBeLessThan(500);
    expect(responseBody.turn_decision.generation.fallback_used).toBe(false);
    await expect(page.getByTestId("t360-block-single_choice-answered")).toContainText("Sistema propio");
    await expect.poll(async () => {
      const userMessages = await page.getByTestId("public-vera-user-message").allTextContents();
      return userMessages.filter((message) => message.trim() === "Sistema propio").length;
    }).toBe(0);
  });
});
