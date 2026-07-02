import { expect, test, type Page, type Route } from "@playwright/test";

const LAB_URL = "/t360-diagnosticador-lab";
const T360_URL = "/t360";
const DIAGNOSIS_ENDPOINT = "**/diagnosis/turn";
const LAB_SESSION_KEY = "team360.diagnosticador.lab.session.v1";
const VERA_SESSION_KEY = "team360.vera.session.v1";

function mockTurnResponse({
  sessionId,
  turnCount,
  message,
}: {
  sessionId: string;
  turnCount: number;
  message: string;
}) {
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

async function routeDiagnosis(page: Page, handler: (route: Route, body: Record<string, unknown>, count: number) => Promise<void> | void) {
  let count = 0;
  await page.route(DIAGNOSIS_ENDPOINT, async (route) => {
    count += 1;
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await handler(route, body, count);
  });
}

test.describe("Diagnosticador Embed Lab", () => {
  test.setTimeout(120000);

  test("carga, monta Core, usa key aislada y no colisiona con Vera", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await routeDiagnosis(page, async (route, _body, count) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(mockTurnResponse({
          sessionId: "vera_tab_session",
          turnCount: count,
          message: "Gracias, sigo reuniendo contexto.",
        })),
      });
    });

    await page.goto(T360_URL);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    await page.getByTestId("public-vera-text").fill("recibimos muchas llamadas de teléfono");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 15000 });

    await expect
      .poll(() => page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY))
      .not.toBeNull();
    const veraKey = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    const veraData = JSON.parse(veraKey!);
    expect(typeof veraData.session_id).toBe("string");

    const labPage = await page.context().newPage();
    const labErrors: string[] = [];
    labPage.on("console", (msg) => { if (msg.type() === "error") labErrors.push(msg.text()); });
    labPage.on("pageerror", (err) => labErrors.push(err.message));

    let labRequestUrl: string | null = null;
    let labRequestBody: string | null = null;
    await routeDiagnosis(labPage, async (route, body, count) => {
      labRequestUrl = route.request().url();
      labRequestBody = JSON.stringify(body);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(mockTurnResponse({
          sessionId: "lab_tab_session",
          turnCount: count,
          message: "Perfecto, sigo el diagnóstico desde el lab.",
        })),
      });
    });

    await labPage.goto(LAB_URL);
    await expect(labPage.getByTestId("diagnosticador-core")).toBeVisible();

    const labKeyBefore = await labPage.evaluate((key) => sessionStorage.getItem(key), LAB_SESSION_KEY);
    expect(labKeyBefore).toBeNull();

    await expect(labPage.getByTestId("public-vera-text")).toBeVisible();
    await labPage.getByTestId("public-vera-text").fill("problemas con el seguimiento de leads");
    await labPage.getByTestId("public-vera-submit").click();
    await labPage.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 15000 });

    await expect
      .poll(() => labPage.evaluate((key) => sessionStorage.getItem(key), LAB_SESSION_KEY))
      .not.toBeNull();
    const labKeyAfter = await labPage.evaluate((key) => sessionStorage.getItem(key), LAB_SESSION_KEY);
    const labData = JSON.parse(labKeyAfter!);
    expect(typeof labData.session_id).toBe("string");

    expect(labRequestUrl).not.toBeNull();
    expect(labRequestUrl!).toMatch(/\/api\/diagnosis\/turn$/);
    expect(labRequestBody).not.toBeNull();
    const labBody = JSON.parse(labRequestBody!);
    expect(labBody).toMatchObject({
      assistant_instance_code: "team360_sales_diagnosis",
      package_code: "pkg_sales_diagnosis",
      knowledge_scope_code: "ks_team360_sales_diagnosis",
    });

    const veraNotInLab = await labPage.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(veraNotInLab).toBeNull();

    await labPage.close();

    const veraStill = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(veraStill).not.toBeNull();
    const veraStillData = JSON.parse(veraStill!);
    expect(veraStillData.session_id).toBe(veraData.session_id);

    expect(consoleErrors.filter(
      (e) =>
        !e.includes("favicon") &&
        !e.includes("ERR_CONNECTION_REFUSED") &&
        !e.includes("404 (Not Found)")
    )).toEqual([]);
    expect(labErrors.filter(
      (e) =>
        !e.includes("favicon") &&
        !e.includes("ERR_CONNECTION_REFUSED") &&
        !e.includes("404 (Not Found)")
    )).toEqual([]);
  });
});
