import { expect, test, type Page, type Route } from "@playwright/test";

const T360_URL = "/t360";
const SESSION_KEY = "team360.vera.session.v1";
const DIAGNOSIS_ENDPOINT = "**/api/diagnosis/turn";

type DiagnosisRequestBody = Record<string, unknown>;

function response(sessionId: string, turnCount: number, message: string) {
  return {
    session_id: sessionId,
    response_text: message,
    turn_count: turnCount,
    is_new: turnCount === 1,
    language: {
      initial_language: "es",
      current_language: "es",
      preferred_response_language: "es",
      response_language: "es",
      language_confidence: 1,
      language_source: "test",
      explicit_language_preference: false,
    },
    turn_decision: {
      action: "reflect_and_ask",
      diagnosis_built: false,
      diagnosis_status: "gathering",
      generation: {
        status: "success",
        model: "openai_gpt-5-nano",
        fallback_used: false,
        fallback_reason: null,
      },
    },
    diagnosis: null,
  };
}

async function routeDiagnosis(
  page: Page,
  handler: (route: Route, body: DiagnosisRequestBody, count: number) => Promise<void> | void,
) {
  let count = 0;
  await page.route(DIAGNOSIS_ENDPOINT, async (route) => {
    count += 1;
    const body = route.request().postDataJSON() as DiagnosisRequestBody;
    await handler(route, body, count);
  });
}

async function openClean(page: Page) {
  await page.goto(T360_URL);
  await page.evaluate((key) => sessionStorage.removeItem(key), SESSION_KEY);
  await page.reload();
  await expect(page.getByTestId("public-vera-entry")).toBeVisible();
  await expect(page.getByTestId("public-vera-text")).toBeVisible();
}

async function sendTurn(page: Page, text: string) {
  const initialInput = page.getByTestId("public-vera-text");
  if (await initialInput.isVisible().catch(() => false)) {
    await initialInput.fill(text);
    await expect(page.getByTestId("public-vera-submit")).toBeEnabled();
    await page.getByTestId("public-vera-submit").click();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled();
    return;
  }

  await page.getByTestId("public-vera-chat-input").fill(text);
  await expect(page.getByTestId("public-vera-chat-submit")).toBeEnabled();
  await page.getByTestId("public-vera-chat-submit").click();
  await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled();
}

test.describe("Public Vera — New conversation reset", () => {
  test("clears conversation state and isolates new session", async ({ page }) => {
    const consoleErrors: string[] = [];
    const requests: DiagnosisRequestBody[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    await routeDiagnosis(page, async (route, body, count) => {
      requests.push(body);

      if (count === 1) {
        expect(body.session_id ?? null).toBeNull();
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(response("conv_vera_reset_a", 1, "Entiendo. Veo WhatsApp y Kommo en tu operación.")),
        });
        return;
      }

      if (count === 2) {
        expect(body.session_id).toBe("conv_vera_reset_a");
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(response("conv_vera_reset_a", 2, "También registré turnos y pedidos como parte del flujo.")),
        });
        return;
      }

      expect(count).toBe(3);
      expect(body.session_id ?? null).toBeNull();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response("conv_vera_reset_b", 1, "Ahora veo consultas de soporte por email.")),
      });
    });

    await openClean(page);

    // === CONVERSATION A: Kommo ===
    await sendTurn(page, "Necesito responder los WhatsApp que llegan a Kommo.");
    await sendTurn(page, "Quiero automatizar pedidos de turnos.");

    const entryA = await page.getByTestId("public-vera-entry").innerText();
    expect(entryA.toLowerCase()).toContain("whatsapp");
    expect(entryA.toLowerCase()).toContain("kommo");

    // === CLICK NUEVA CONVERSACIÓN ===
    await page.getByTestId("public-vera-new-conversation").click();

    // Verify initial state restored
    await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 15000 });
    const inputValue = await page.getByTestId("public-vera-text").inputValue();
    expect(inputValue).toBe("");

    const entryAfterReset = await page.getByTestId("public-vera-entry").innerText();
    const lowerReset = entryAfterReset.toLowerCase();
    expect(lowerReset).not.toContain("kommo");
    expect(lowerReset).not.toContain("turnos");

    // === CONVERSATION B: Email (completely different topic) ===
    await sendTurn(page, "Recibo consultas de soporte por email.");

    const entryB = await page.getByTestId("public-vera-entry").innerText();
    const lowerB = entryB.toLowerCase();
    expect(lowerB).not.toContain("kommo");
    expect(lowerB).not.toContain("turnos");
    expect(lowerB).toContain("email");
    expect(requests).toHaveLength(3);
    expect(requests[2]?.session_id ?? null).toBeNull();

    const criticalErrors = consoleErrors.filter(
      (e) =>
        !e.includes("ERR_CONNECTION_REFUSED") &&
        !e.includes("favicon") &&
        !e.includes("404 (Not Found)")
    );
    expect(criticalErrors).toEqual([]);
  });
});
