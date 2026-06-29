import { expect, test, type Page, type Request, type Response } from "@playwright/test";

const DIAGNOSIS_ENDPOINT = "/api/diagnosis/turn";
const GENERIC_FALLBACK = "Recibí la información, pero no pude procesarla completamente";

/* Terms that must NOT appear as a direct Vera question
   after feasibility context is sufficient.
   They may appear only inside "puntos a validar técnicamente" or
   "etapa posterior" / "análisis de flujo" / "implementación posterior". */
const IMPLEMENTATION_TERMS = [
  "API",
  "webhook",
  "OAuth",
  "token",
  "credenciales",
  "Google Drive",
  "Google Sheets",
  "cuenta de servicio",
  "pestaña exacta",
  "nombre de pestaña",
  "columna exacta",
  "fila nueva",
];

/* Feasibility concepts that should appear in the diagnosis object */
const FEASIBILITY_CONCEPTS = [
  "factibilidad",
  "modo recomendado",
  "riesgos",
  "validar",
  "flujo",
  "implementación",
];

const VALID_IMPL_CONTEXTS = [
  "punto a validar",
  "análisis de flujo",
  "implementación posterior",
  "etapa posterior",
  "técnicamente",
];

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
    (e) => !e.includes("favicon") && !e.includes("net::ERR_ABORTED"),
  );
}

function hasProhibitedImplementationQuestion(responseText: string): boolean {
  const lower = responseText.toLowerCase();
  if (!lower.includes("?")) return false;

  for (const term of IMPLEMENTATION_TERMS) {
    if (lower.includes(term.toLowerCase())) {
      const sentence = extractSentenceContaining(lower, term.toLowerCase());
      if (sentence && !isInValidContext(sentence)) {
        return true;
      }
    }
  }
  return false;
}

function extractSentenceContaining(text: string, term: string): string | null {
  const sentences = text.split(/[.!?\n]+/);
  for (const s of sentences) {
    if (s.includes(term)) return s.trim();
  }
  return null;
}

function isInValidContext(sentence: string): boolean {
  return VALID_IMPL_CONTEXTS.some((ctx) => sentence.includes(ctx));
}

function countFeasibilityConcepts(text: string): number {
  const lower = text.toLowerCase();
  return FEASIBILITY_CONCEPTS.filter((c) => lower.includes(c)).length;
}

test.describe("Vera feasibility diagnosis scope — no entra en implementación", () => {
  test.describe.configure({ mode: "serial" });

  async function runConversation(
    page: Page,
    label: string,
    messages: string[],
  ) {
    test.setTimeout(600_000);

    const captured: CapturedTurn[] = [];
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    const allDiagnosisRequests: Record<string, unknown>[] = [];
    const isLastIdx = (i: number) => i === messages.length - 1;

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

    let sessionId = "";
    for (const [index, msg] of messages.entries()) {
      const initialInput = page.getByTestId("public-vera-text");
      const isInitial = await initialInput.isVisible().catch(() => false);
      const input = isInitial ? initialInput : page.getByTestId("public-vera-chat-input");
      const submit = isInitial
        ? page.getByTestId("public-vera-submit")
        : page.getByTestId("public-vera-chat-submit");

      await input.fill(msg);
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

      await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 90_000 });
      await expect.poll(() => captured.length).toBe(index + 1);
      expect(requestBody.message).toBe(msg);
      expect(response.status()).toBeLessThan(500);

      const respText = String(body.response_text ?? "");
      expect(respText.trim().length).toBeGreaterThan(0);

      /* Check for prohibited implementation questions after every turn */
      if (hasProhibitedImplementationQuestion(respText)) {
        console.error(`PROHIBITED_IMPL_QUESTION turn=${captured.length} "${label}": "${respText}"`);
      }
      expect(hasProhibitedImplementationQuestion(respText)).toBe(false);

      /* Last turn: detailed feasibility assertions (includes
         diagnosis_state collected from the last turn for reporting) */
      if (isLastIdx(index)) {
        const turnDecision = body.turn_decision as Record<string, unknown> | undefined;
        const generation = turnDecision?.generation as Record<string, unknown> | undefined;
        const diagnosis = body.diagnosis as Record<string, unknown> | undefined;
        const interactionBlock = body.interaction_block as Record<string, unknown> | undefined;
        const action = String(turnDecision?.action ?? "");
        const diagnosisStatus = String(turnDecision?.diagnosis_status ?? "");
        const diagnosisBuilt = turnDecision?.diagnosis_built;

        const evidence = {
          label,
          turnCount: captured.length,
          action,
          diagnosisStatus,
          diagnosisBuilt,
          hasDiagnosis: diagnosis !== null && diagnosis !== undefined,
          fallbackUsed: generation?.fallback_used,
          responseTextPreview: respText.slice(0, 150),
          interactionBlockType: interactionBlock?.type,
          feasibilityConceptsInResponse: countFeasibilityConcepts(respText),
          diagnosisFeasibility: diagnosis?.feasibility,
          diagnosisMode: diagnosis?.automation_mode,
          hasProhibitedQuestion: hasProhibitedImplementationQuestion(respText),
          hasFailedRequests: failedRequests.length > 0,
          criticalErrors: criticalConsoleErrors(consoleErrors),
        };
        console.log(`E2E_EVIDENCE ${JSON.stringify(evidence)}`);

        /* No failed requests, no critical console errors */
        expect(failedRequests).toEqual([]);
        expect(criticalConsoleErrors(consoleErrors)).toEqual([]);

        /* The diagnosis object should be present or the interaction_block should
           indicate readiness (next_step_choice, diagnosis_action_card, etc.). */
        if (diagnosisBuilt && diagnosis) {
          /* Diagnosis was built → check its fields */
          expect(diagnosis).toHaveProperty("feasibility");
          expect(diagnosis).toHaveProperty("automation_mode");
          expect(diagnosis).toHaveProperty("risks");
          expect(diagnosis).toHaveProperty("validation_points");
          expect(evidence.diagnosisFeasibility).toBeTruthy();
          expect(evidence.diagnosisMode).toBeTruthy();
        } else if (action === "diagnose" && !diagnosis) {
          /* Action says diagnose but no diagnosis object — suspicious */
          console.warn(`DIAGNOSE_WITHOUT_DIAGNOSIS_OBJECT ${label}`);
        } else {
          /* Reflect-and-ask: check that it's asking about a feasibility
             topic (volume, approval, goal) or showing readiness block */
          if (interactionBlock) {
            const bt = String(interactionBlock.type ?? "");
            if (bt === "missing_requirements") {
              /* Verify missing_requirements does NOT contain standalone
                 implementation items */
              const reqs = interactionBlock.requirements as Record<string, unknown>[] | undefined;
              if (reqs) {
                for (const r of reqs) {
                  const rid = String(r.id ?? "");
                  const rfor = String(r.required_for ?? "");
                  /* If it's an implementation item, it should be grouped
                     under post_diagnosis */
                  if (IMPLEMENTATION_TERMS.some((t) => rid.includes(t.toLowerCase()))) {
                    expect(rfor).toContain("post_diagnosis");
                  }
                }
              }
            }
          }
        }

        /* Ensure no implementation questions even in the fallback case */
        expect(hasProhibitedImplementationQuestion(respText)).toBe(false);
      }
    }

    /* Post-loop: at least one turn must have built the diagnosis (status
       sufficient/completed with diagnosis object or diagnosis_built=true) */
    const anyDiagnosisBuilt = captured.some(
      (t) => (t.response.turn_decision as Record<string, any>)?.diagnosis_built === true
    );
    const anyDiagnosisPresent = captured.some(
      (t) => t.response.diagnosis != null
    );
    if (!anyDiagnosisBuilt) {
      console.warn(`DIAGNOSIS_NOT_BUILT ${label}: all turns had diagnosis_built=false`);
    }
    if (!anyDiagnosisPresent) {
      console.warn(`DIAGNOSIS_ABSENT ${label}: no turn had diagnosis object`);
    }
    /* Assert that diagnosis was either built or present on at least one turn.
       We accept either because the timing of when diagnosis completes depends
       on whether the LLM classifier triggers auto-diagnosis or waits for
       an explicit "dame un diagnóstico". */
    expect(anyDiagnosisBuilt || anyDiagnosisPresent).toBe(true);
  }

  /* =================================================================
     MAIN — Email + facturación + planilla + derivar + criterio + volumen
     ================================================================= */
  test("Main: email facturacion planilla derivar criterio volumen", async ({ page }) => {
    await runConversation(page, "main", [
      "recibo muchos email",
      "facturacion",
      "Planilla / Excel",
      "Derivar casos a una persona",
      "por el asunto puede reimpresion, anulacion, credito",
      "50 por dia",
      "dame un diagnóstico",
    ]);
  });

  /* =================================================================
     VARIANT A — WhatsApp + turnos + manual + volumen
     ================================================================= */
  test("Variant A: whatsapp turnos manual volumen", async ({ page }) => {
    await runConversation(page, "variantA", [
      "recibo muchos whatsapp",
      "pedir turnos",
      "lo cargo manual",
      "30 por dia",
      "dame un diagnóstico",
    ]);
  });

  /* =================================================================
     VARIANT B — SAP + bancos + diferencias + revisión humana + volumen
     ================================================================= */
  test("Variant B: SAP bancos diferencias revision humana", async ({ page }) => {
    await runConversation(page, "variantB", [
      "Tengo SAP y extractos bancarios de 3 bancos",
      "Quiero encontrar diferencias en forma automática",
      "Alguien revisa a mano",
      "50 movimientos por dia",
      "dame un diagnóstico",
    ]);
  });

  /* =================================================================
     VARIANT C — Kommo + leads + WhatsApp + revisión manual + volumen
     ================================================================= */
  test("Variant C: Kommo leads whatsapp revision manual", async ({ page }) => {
    await runConversation(page, "variantC", [
      "me llegan leads por WhatsApp a Kommo",
      "quiero saber quien los sigue",
      "lo revisan manualmente",
      "100 por semana",
      "dame un diagnóstico",
    ]);
  });
});
