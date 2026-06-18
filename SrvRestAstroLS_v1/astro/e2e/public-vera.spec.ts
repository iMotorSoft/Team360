import { expect, test, type Page, type Route } from "@playwright/test";

const T360_URL = "/t360";
const SESSION_KEY = "team360.vera.session.v1";
const DIAGNOSIS_ENDPOINT = "**/api/diagnosis/turn";

const SPANISH_DIALOG = [
  "Quiero responder automáticamente las consultas de venta.",
  "Entran por WhatsApp y Gmail.",
  "Son unas 80 por día.",
  "El stock está en el ERP y los precios en una planilla.",
  "Las respuestas comunes pueden salir solas, pero los descuentos especiales requieren aprobación de un gerente.",
  "Con esto dame una orientación inicial.",
];

function diagnosis(overrides = {}) {
  return {
    version: "v1",
    feasibility: "high",
    automation_mode: "human_in_the_loop",
    confidence: "high",
    summary: null,
    channels: ["whatsapp", "gmail"],
    systems: ["erp", "spreadsheet"],
    entities: ["inventory", "prices", "discounts", "sales_inquiries"],
    entity_sources: { inventory: "erp", prices: "spreadsheet" },
    human_approval: "conditional",
    automatable_steps: [
      "receive inquiries from whatsapp and gmail",
      "retrieve inventory from erp",
      "retrieve prices from spreadsheet",
      "generate standard replies",
    ],
    human_steps: ["approve exceptions or sensitive actions"],
    risks: ["stale_price_data", "integration_not_confirmed"],
    assumptions: ["spreadsheet data is maintained and accessible"],
    validation_points: [
      "confirm erp integration method for inventory",
      "confirm spreadsheet integration method for prices",
      "confirm spreadsheet update responsibility",
      "define approval rules for exceptions",
    ],
    next_step: "validate erp and spreadsheet access, then design the whatsapp and gmail response flow with approval rules",
    availability: "requires_validation",
    ...overrides,
  };
}

function response({
  sessionId,
  turnCount,
  message,
  locale = "es",
  action = "reflect_and_ask",
  withDiagnosis = false,
  fallback = false,
}: {
  sessionId: string;
  turnCount: number;
  message: string;
  locale?: "es" | "en" | "he";
  action?: "diagnose" | "reflect_and_ask";
  withDiagnosis?: boolean;
  fallback?: boolean;
}) {
  return {
    session_id: sessionId,
    response_text: message,
    turn_count: turnCount,
    is_new: turnCount === 1,
    language: {
      initial_language: locale,
      current_language: locale,
      preferred_response_language: locale,
      response_language: locale,
      language_confidence: 1,
      language_source: "test",
      explicit_language_preference: false,
    },
    turn_decision: {
      action,
      diagnosis_built: withDiagnosis,
      diagnosis_status: withDiagnosis ? "completed" : "gathering",
      generation: {
        status: fallback ? "fallback" : "success",
        model: "openai_gpt-5-nano",
        fallback_used: fallback,
        fallback_reason: fallback ? "transient_error" : null,
      },
    },
    diagnosis: withDiagnosis ? diagnosis() : null,
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

async function openClean(page: Page) {
  await page.goto(T360_URL);
  await page.evaluate((key) => sessionStorage.removeItem(key), SESSION_KEY);
  await page.reload();
  await expect(page.getByTestId("public-vera-entry")).toBeVisible();
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

test.describe("Team360 pública - Vera estructurada", () => {
  test("renderiza diagnóstico completo, localizado y sin códigos internos", async ({ page }) => {
    const requests: Record<string, unknown>[] = [];
    await routeDiagnosis(page, async (route, body, count) => {
      requests.push(body);
      const finalTurn = count === SPANISH_DIALOG.length;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_e2e_es",
          turnCount: count,
          message: finalTurn ? "Con esto ya puedo darte una orientación inicial." : "Gracias, sigo reuniendo contexto.",
          action: finalTurn ? "diagnose" : "reflect_and_ask",
          withDiagnosis: finalTurn,
        })),
      });
    });

    await openClean(page);
    for (const turn of SPANISH_DIALOG) {
      await sendTurn(page, turn);
    }

    const result = page.getByTestId("diagnosis-result");
    await expect(result).toBeVisible();
    await expect(result).toContainText("Tu orientación inicial");
    await expect(result).toContainText("Factibilidad inicial");
    await expect(result).toContainText("Con aprobación humana");
    await expect(result).toContainText("Requiere validación técnica");
    await expect(result.getByText("WhatsApp", { exact: true })).toBeVisible();
    await expect(result.getByText("Gmail", { exact: true })).toBeVisible();
    await expect(result.getByText("Stock", { exact: true })).toBeVisible();
    expect(await result.getByText("ERP", { exact: true }).count()).toBeGreaterThan(0);
    await expect(result.getByText("Precios", { exact: true })).toBeVisible();
    expect(await result.getByText("Planilla", { exact: true }).count()).toBeGreaterThan(0);
    await expect(result).toContainText("aprobar excepciones o acciones sensibles");
    await expect(result).toContainText("Los datos pueden estar desactualizados");
    await expect(result).toContainText("confirmar método de integración de ERP para Stock");
    await expect(result).toContainText("validar acceso a ERP y Planilla");

    const diagnosisText = await result.innerText();
    expect(diagnosisText).not.toMatch(/stale_price_data|security_control_required|closed_software_dependency|receive inquiries|retrieve inventory/);
    expect(requests).toHaveLength(SPANISH_DIALOG.length);
    expect(new Set(requests.slice(1).map((body) => body.session_id))).toEqual(new Set(["conv_e2e_es"]));
  });

  test("no renderiza DiagnosisResult para una consulta puntual reflect_and_ask", async ({ page }) => {
    await routeDiagnosis(page, async (route, body, count) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_e2e_reflect",
          turnCount: count,
          message: body.message === "¿Se puede conectar Gmail?"
            ? "Sí, Gmail puede evaluarse como canal, pero necesito entender el flujo antes de diagnosticar."
            : "Contame un poco más del proceso.",
        })),
      });
    });

    await openClean(page);
    await sendTurn(page, "Queremos automatizar consultas de clientes.");
    await sendTurn(page, "¿Se puede conectar Gmail?");

    await expect(page.getByText("Sí, Gmail puede evaluarse")).toBeVisible();
    await expect(page.getByTestId("diagnosis-result")).toHaveCount(0);
    await expect(page.getByText("Turno 2")).toBeVisible();
  });

  test("muestra fallback localizado sin ocultar el diagnóstico", async ({ page }) => {
    await routeDiagnosis(page, async (route, _body, count) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_e2e_fallback",
          turnCount: count,
          message: "Recibí la información, pero no pude procesarla completamente en este momento.",
          action: "diagnose",
          withDiagnosis: true,
          fallback: true,
        })),
      });
    });

    await openClean(page);
    await sendTurn(page, "Con esto dame una orientación inicial.");

    await expect(page.getByTestId("diagnosis-result")).toBeVisible();
    await expect(page.getByText("Nota: la respuesta automática no pudo generarse")).toBeVisible();
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled();
  });

  test("HTTP 503 muestra error localizado y permite reintentar", async ({ page }) => {
    await routeDiagnosis(page, async (route, _body, count) => {
      if (count === 1) {
        await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "unavailable" }) });
        return;
      }
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_e2e_retry",
          turnCount: 1,
          message: "Ahora sí puedo continuar.",
        })),
      });
    });

    await openClean(page);
    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas.");
    await page.getByTestId("public-vera-submit").click();
    await expect(page.getByTestId("public-vera-error")).toContainText("Vera no está disponible");
    await expect(page.getByTestId("public-vera-user-message")).toContainText("Quiero automatizar consultas.");
    await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled();

    await page.getByTestId("public-vera-chat-input").fill("Reintento con el mismo contexto.");
    await page.getByTestId("public-vera-chat-submit").click();
    await expect(page.getByText("Ahora sí puedo continuar.")).toBeVisible();
  });

  test("localiza inglés y hebreo, con RTL local en el diagnóstico hebreo", async ({ page }) => {
    await routeDiagnosis(page, async (route, body, count) => {
      const message = String(body.message ?? "");
      const locale = /[\u0590-\u05ff]/.test(message) ? "he" : "en";
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: `conv_e2e_${locale}`,
          turnCount: count,
          locale,
          message: locale === "he" ? "אפשר לתת הכוונה ראשונית." : "I can provide an initial assessment.",
          action: "diagnose",
          withDiagnosis: true,
        })),
      });
    });

    await openClean(page);
    await sendTurn(page, "We want to automate sales inquiries. Give me an initial assessment.");
    let result = page.getByTestId("diagnosis-result");
    await expect(result).toContainText("Your initial assessment");
    await expect(result).toContainText("Initial feasibility");
    await expect(result.getByText("Inventory", { exact: true })).toBeVisible();
    await expect(result).not.toContainText("Factibilidad");

    await page.getByTestId("public-vera-new-conversation").click();
    await sendTurn(page, "אנחנו רוצים להפוך פניות מכירה לאוטומטיות. תן לי הכוונה ראשונית.");
    const heDiagnosis = page.getByTestId("diagnosis-result");
    await expect(heDiagnosis).toBeVisible();
    await expect(heDiagnosis).toHaveAttribute("lang", "he");
    await expect(heDiagnosis).toHaveAttribute("dir", "rtl");
    await expect(heDiagnosis).toContainText("ההכוונה הראשונית שלך");
    await expect(heDiagnosis.getByText("וואטסאפ", { exact: true })).toBeVisible();
    await expect(heDiagnosis.getByText("ג'ימייל", { exact: true })).toBeVisible();
  });

  test("mobile mantiene diagnóstico dentro del ancho visible", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await routeDiagnosis(page, async (route, _body, count) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_e2e_mobile",
          turnCount: count,
          message: "אפשר לתת הכוונה ראשונית.",
          locale: "he",
          action: "diagnose",
          withDiagnosis: true,
        })),
      });
    });

    await openClean(page);
    await sendTurn(page, "אנחנו רוצים להפוך פניות מכירה לאוטומטיות. תן לי הכוונה ראשונית.");
    await expect(page.getByTestId("diagnosis-result")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.getByTestId("public-vera-chat-input")).toBeVisible();
    await expect(page.getByTestId("public-vera-chat-submit")).toBeVisible();
  });
});

test("smoke real /t360 contra backend vivo", async ({ page }) => {
  test.skip(process.env.T360_REAL_E2E !== "1", "Set T360_REAL_E2E=1 con frontend 3050 y backend 7050 activos.");

  await openClean(page);
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/diagnosis/turn")) {
      requests.push(request.url());
    }
  });

  for (const turn of SPANISH_DIALOG) {
    await sendTurn(page, turn);
  }

  const result = page.getByTestId("diagnosis-result");
  await expect(result).toBeVisible({ timeout: 30_000 });
  await expect(result).toContainText("Tu orientación inicial");
  await expect(result.getByText("WhatsApp", { exact: true })).toBeVisible();
  await expect(result.getByText("Gmail", { exact: true })).toBeVisible();
  expect(requests).toHaveLength(SPANISH_DIALOG.length);
});
