import { test, expect } from "@playwright/test";

const DIAGNOSIS_URL = "/w/ws-team360-control/diagnosis";

const ANSWERS: Array<{ id: string; type: "text" | "options"; value: string | string[] }> = [
  { id: "process_to_automate", type: "text", value: "Calificar leads desde el sitio web." },
  { id: "business_pain", type: "text", value: "Las consultas llegan sin diagnostico previo." },
  { id: "systems_involved", type: "options", value: ["email", "whatsapp"] },
  { id: "frequency_volume", type: "options", value: ["daily", "medium_volume"] },
  { id: "rules_clarity", type: "options", value: ["clear"] },
  { id: "human_dependency", type: "options", value: ["medium"] },
  { id: "access_security", type: "options", value: ["role_permissions"] },
  { id: "data_sensitivity", type: "options", value: ["personal_data"] },
  { id: "expected_result", type: "text", value: "Lead calificado y siguiente paso sugerido." },
  { id: "economic_impact", type: "options", value: ["high"] },
];

const VALID_CLASSIFICATIONS = [
  "standard_package",
  "operational_automation",
  "consulting_required",
  "not_recommended",
];

const UI_READY_TIMEOUT_MS = 30_000;
const REAL_RUNTIME_TIMEOUT_MS = 120_000;

test.describe("Diagnosis E2E - flujo completo", () => {
  test("usuario completa diagnostico y ve resultado", async ({ page }) => {
    test.setTimeout(180_000);

    await page.goto(DIAGNOSIS_URL);

    await expect(page.getByRole("heading", { name: "Diagnosticador" })).toBeVisible();
    const diagnosisRoot = page.getByTestId("diagnosis-root");
    await expect(diagnosisRoot).toBeVisible();
    await expect(diagnosisRoot).toHaveAttribute("data-hydrated", "true");
    await expect(page.getByTestId("diagnosis-welcome")).toBeVisible();

    await page.getByTestId("btn-start-diagnosis").click();

    const questionCard = page.getByTestId("question-card");
    await expect(questionCard).toBeVisible({ timeout: UI_READY_TIMEOUT_MS });
    await expect(questionCard).toHaveAttribute("data-step-id", ANSWERS[0].id);

    for (let i = 0; i < ANSWERS.length; i++) {
      const answer = ANSWERS[i];
      const nextAnswer = ANSWERS[i + 1];

      await expect(questionCard).toHaveAttribute("data-step-id", answer.id);

      if (answer.type === "text") {
        await page.getByTestId("answer-textarea").fill(answer.value as string);
      } else {
        for (const option of answer.value as string[]) {
          await page.getByTestId(`option-${option}`).click();
        }
      }

      const nextButton = page.getByTestId("btn-next");
      await expect(nextButton).toBeEnabled();
      await nextButton.click();

      if (nextAnswer) {
        await expect(questionCard).toHaveAttribute("data-step-id", nextAnswer.id, { timeout: UI_READY_TIMEOUT_MS });
      }
    }

    await expect(page.getByTestId("diagnosis-result")).toBeVisible({ timeout: REAL_RUNTIME_TIMEOUT_MS });

    const classification = page.getByTestId("result-classification");
    await expect(classification).toBeVisible();
    await expect(classification).toContainText(new RegExp(`^(${VALID_CLASSIFICATIONS.join("|")})$`));

    const scoreText = await page.getByTestId("result-score").textContent();
    const score = parseInt(scoreText?.trim() || "0", 10);
    expect(score).toBeGreaterThanOrEqual(0);

    await expect(page.getByTestId("result-mode")).not.toBeEmpty();
    await expect(page.getByTestId("result-package")).not.toBeEmpty();
    await expect(page.getByTestId("result-next-step")).not.toBeEmpty();
    await expect(page.getByTestId("btn-new-diagnosis")).toBeVisible();
  });

  test("muestra error cuando backend no esta disponible", async ({ page }) => {
    // NOTA: Esta prueba requiere backend apagado.
    // Ejecutar manualmente con:
    //   # Terminal 1: frontend solo
    //   cd astro && corepack pnpm dev
    //   # Terminal 2: playwright
    //   cd astro && PLAYWRIGHT_SKIP_BACKEND=1 corepack pnpm test:e2e
    test.skip(true, "Requiere backend apagado manualmente");

    await page.goto(DIAGNOSIS_URL);
    await expect(page.getByTestId("diagnosis-welcome")).toBeVisible();
    await page.getByTestId("btn-start-diagnosis").click();
    await expect(page.getByTestId("diagnosis-error")).toBeVisible({ timeout: 15_000 });
  });
});
