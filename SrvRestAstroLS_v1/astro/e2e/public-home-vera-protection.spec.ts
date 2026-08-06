import { expect, test, type Page, type Route } from "@playwright/test";

// TEAM360_PUBLIC_HOME_VERA_PROTECTION_GATE
// Protection spec for the public home (/) and the Vera section (/#vera).
// Mirrors the helpers of public-vera.spec.ts to stay consistent with the
// existing contract coverage.

const HOME_URL = "/";
const VERA_HASH_URL = "/#vera";
const SESSION_KEY = "team360.vera.session.v1";
const DIAGNOSIS_ENDPOINT = "**/api/diagnosis/turn";
const SPANISH_DIALOG = [
  "Quiero responder automáticamente las consultas de venta.",
  "Entran por WhatsApp y Gmail.",
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
    automatable_steps: ["receive inquiries from whatsapp and gmail"],
    human_steps: ["approve exceptions or sensitive actions"],
    risks: ["stale_price_data", "integration_not_confirmed"],
    assumptions: ["spreadsheet data is maintained and accessible"],
    validation_points: ["confirm erp integration method for inventory"],
    next_step: "validate erp and spreadsheet access",
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
  interactionBlock,
}: {
  sessionId: string;
  turnCount: number;
  message: string;
  locale?: "es" | "en" | "he";
  action?: "diagnose" | "reflect_and_ask";
  withDiagnosis?: boolean;
  interactionBlock?: unknown;
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
        status: "success",
        model: "openai_gpt-5.4-nano",
        fallback_used: false,
        fallback_reason: null,
      },
    },
    diagnosis: withDiagnosis ? diagnosis() : null,
    ...(interactionBlock !== undefined ? { interaction_block: interactionBlock } : {}),
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

async function collectConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text().slice(0, 200));
  });
  page.on("pageerror", (error) => errors.push(`PAGEERROR: ${error.message.slice(0, 200)}`));
  return errors;
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

test.describe("TEAM360_PUBLIC_HOME_VERA_PROTECTION — home pública", () => {
  test("carga la home, navega a /#vera, conserva hash y sobrevive reload (desktop)", async ({ page }) => {
    const errors = await collectConsoleErrors(page);

    // 1. Abrir la home.
    await page.goto(HOME_URL);
    await expect(page).toHaveTitle(/Team360/);
    await expect(page.locator("main#contenido")).toBeVisible();
    await expect(page.locator("#solucion")).toBeVisible();
    // Hero CTA apunta a Vera.
    await expect(page.getByRole("link", { name: "Empezar diagnóstico" })).toHaveAttribute("href", "#vera");

    // 2. Navegar directo a /#vera.
    await page.goto(VERA_HASH_URL);
    await expect(page).toHaveURL(/\/#vera$/);
    await expect(page.locator("#vera")).toBeVisible();

    // 3. La sección Vera no queda oculta detrás del header sticky.
    const header = page.locator("header.sticky");
    const section = page.locator("#vera");
    await section.scrollIntoViewIfNeeded();
    await expect(section).toBeInViewport();
    const headerBox = await header.boundingBox();
    const sectionBox = await section.boundingBox();
    expect(headerBox).not.toBeNull();
    expect(sectionBox).not.toBeNull();
    // El tope de la sección debe quedar debajo del header (scroll-mt-24).
    expect(sectionBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height - 4);

    // 4. Reload conserva el hash y la sección.
    await page.reload();
    await expect(page).toHaveURL(/\/#vera$/);
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    // 5. Sin errores de consola nuevos.
    expect(errors).toEqual([]);
  });

  test("interacción mock: responde, action block no duplica mensaje y nueva conversación resetea", async ({ page }) => {
    const errors = await collectConsoleErrors(page);
    await routeDiagnosis(page, async (route, _body, count) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_home_gate_1",
          turnCount: count,
          message: count === 1 ? "Ya tengo una orientación inicial. Elegí cómo querés seguir." : "Con esto ya puedo darte una orientación inicial.",
          action: count === 1 ? "reflect_and_ask" : "diagnose",
          withDiagnosis: count > 1,
          interactionBlock: count === 1
            ? {
                type: "next_step_choice",
                title: "Próximo paso",
                description: "Podés seguir conversando o ver una orientación preliminar.",
                actions: [
                  { id: "show-current-diagnosis", label: "Ver diagnóstico", style: "primary", intent: "show_current_diagnosis" },
                  { id: "continue-context", label: "Seguir conversando", style: "secondary", intent: "continue_conversation" },
                ],
              }
            : undefined,
        })),
      });
    });

    await page.goto(VERA_HASH_URL);
    await page.evaluate((key) => sessionStorage.removeItem(key), SESSION_KEY);
    await page.reload();
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    // Conversación mock.
    await sendTurn(page, SPANISH_DIALOG[0]);
    await expect(page.getByTestId("public-vera-interaction-block")).toHaveAttribute("data-valid", "true");
    const userBubblesBefore = await page.getByTestId("public-vera-user-message").count();

    // Acción del block: no duplica la bubble de usuario (appendUserMessage=false).
    await page.getByTestId("t360-action-show-current-diagnosis").click();
    await expect(page.getByTestId("diagnosis-result")).toBeVisible();
    const userBubblesAfter = await page.getByTestId("public-vera-user-message").count();
    expect(userBubblesAfter).toBe(userBubblesBefore);

    // Nueva conversación resetea al formulario inicial.
    await page.getByTestId("public-vera-new-conversation").click();
    await expect(page.getByTestId("public-vera-text")).toBeVisible();
    await expect(page.getByTestId("diagnosis-result")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("mobile 390px: home y /#vera sin overflow ni contenido cortado", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const errors = await collectConsoleErrors(page);

    await page.goto(VERA_HASH_URL);
    await expect(page.locator("#vera")).toBeVisible();
    await expect(page.getByTestId("public-vera-entry")).toBeInViewport();

    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      return doc.scrollWidth - doc.clientWidth;
    });
    expect(overflow, `mobile horizontal overflow ${overflow}px`).toBeLessThanOrEqual(0);
    expect(errors).toEqual([]);

    // Header mobile sigue visible y la sección Vera posiciona bajo el header.
    const header = page.locator("header.sticky");
    await expect(header).toBeVisible();
    const headerBox = await header.boundingBox();
    const sectionBox = await page.locator("#vera").boundingBox();
    expect(headerBox).not.toBeNull();
    expect(sectionBox).not.toBeNull();
    expect(sectionBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height - 4);
  });

  test("diagnóstico hebreo conserva lang=he y dir=rtl en la home", async ({ page }) => {
    await routeDiagnosis(page, async (route, body, count) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(response({
          sessionId: "conv_home_gate_he",
          turnCount: count,
          locale: "he",
          message: "אפשר לתת הכוונה ראשונית.",
          action: "diagnose",
          withDiagnosis: true,
        })),
      });
    });

    await page.goto(VERA_HASH_URL);
    await page.evaluate((key) => sessionStorage.removeItem(key), SESSION_KEY);
    await page.reload();
    await sendTurn(page, "אנחנו רוצים להפוך פניות מכירה לאוטומטיות. תן לי הכוונה ראשונית.");

    const heDiagnosis = page.getByTestId("diagnosis-result");
    await expect(heDiagnosis).toBeVisible();
    await expect(heDiagnosis).toHaveAttribute("lang", "he");
    await expect(heDiagnosis).toHaveAttribute("dir", "rtl");
    await expect(heDiagnosis).toContainText("ההכוונה הראשונית שלך");
  });

  for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1280, height: 800 }]) {
    test(`matriz ${viewport.width}px: / y /#vera sin overflow ni errores de consola`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const errors = await collectConsoleErrors(page);

      for (const url of [HOME_URL, VERA_HASH_URL]) {
        const resp = await page.goto(url);
        if (resp) {
          expect(resp.status(), `${url} HTTP ${resp.status()}`).toBeLessThan(400);
        }
        await page.waitForLoadState("networkidle").catch(() => {});
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `${url}@${viewport.width} overflow ${overflow}px`).toBeLessThanOrEqual(0);
        await expect(page.locator("#vera")).toBeVisible();
      }

      // En /#vera el hash y la sección sobreviven reload en cada resolución.
      await page.goto(VERA_HASH_URL);
      await expect(page).toHaveURL(/#vera$/);
      await page.reload();
      await expect(page).toHaveURL(/#vera$/);
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();
      expect(errors).toEqual([]);
    });
  }
});
