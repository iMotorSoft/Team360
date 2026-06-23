import { expect, test } from "@playwright/test";

type TestCase = {
  name: string;
  messages: string[];
  checks: Record<string, string | ((s: string) => boolean)>;
  skip?: boolean;
};

const CASES: TestCase[] = [
  {
    name: "A: ideal base flow (Kommo turnos)",
    messages: [
      "Necesito responder los WhatsApp que llegan a Kommo.",
      "Pedir turnos.", "Lo cargamos manualmente.",
      "Número de cliente, celular, fecha, horario y tipo de servicio.",
      "Son unos 100 pedidos por día.",
      "La disponibilidad la vemos en Kommo.",
      "Confirmamos a mano por WhatsApp.",
      "Dame el diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", turno: "turno", tipo: "tipo de servicio", diagnosis: "diagnóstico" },
  },
  {
    name: "B: short answers (one-word)",
    messages: [
      "Quiero automatizar turnos por WhatsApp.", "Kommo", "Manual", "Tipo de servicio", "100", "Dame diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", diagnosis: "diagnóstico" },
  },
  {
    name: "C: out of order info (Salesforce)",
    messages: [
      "Tenemos unos 100 pedidos diarios y confirmamos por WhatsApp, pero los turnos los cargamos manualmente en Salesforce.",
      "Son turnos de servicio técnico.", "Dame un diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", salesforce: "salesforce", diagnosis: "diagnóstico" },
  },
  {
    name: "D: explicit correction",
    messages: [
      "Necesito gestionar turnos por WhatsApp en Kommo.",
      "No necesitamos sucursal.",
      "No, me equivoqué: también necesitamos sucursal.",
      "Dame el diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", diagnosis: "diagnóstico" },
  },
  {
    name: "E: impatient user",
    messages: [
      "Quiero saber si esto se puede automatizar.",
      "Los turnos llegan por WhatsApp y los cargamos en Kommo.",
      "Dame una conclusión ahora.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", diagnosis: (s) => s.includes("diagnóstico") || s.includes("diagnostico") },
  },
  {
    name: "F: detailed user (long paragraph)",
    messages: [
      "Gestionamos turnos técnicos. Los clientes piden turno por WhatsApp, los cargamos en Kommo. Necesitamos: nombre, teléfono, fecha, horario y tipo de servicio. Vemos disponibilidad en Kommo, confirmamos manual por WhatsApp. Son unos 80-100 por día. El turno queda como cargado en Kommo y después actualizamos a confirmado o cancelado.",
      "Dame el diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", diagnosis: "diagnóstico" },
  },
  {
    name: "H: refusal to answer",
    messages: [
      "Necesito gestionar los turnos que llegan por WhatsApp.", "Lo cargamos en Kommo.", "Prefiero no dar ese dato.", "Dame un diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", diagnosis: "diagnóstico" },
  },
  {
    name: "J: unknown system (Atlas)",
    messages: [
      "Los turnos se cargan en un sistema propio llamado Atlas.", "Llegan por WhatsApp.", "Son unos 50 por día.",
    ],
    checks: { atlas: "atlas", whatsapp: "whatsapp" },
  },
  {
    name: "K: multiple systems (Salesforce + Google Calendar)",
    messages: [
      "El pedido entra por WhatsApp, lo registramos en Salesforce y el calendario está en Google Calendar.",
      "Pedimos tipo de servicio y horario.", "Dame diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", salesforce: "salesforce", diagnosis: "diagnóstico" },
  },
  {
    name: "L: partially automated",
    messages: [
      "WhatsApp responde automáticamente, pero una persona revisa la disponibilidad y carga el turno en Kommo.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo" },
  },
  {
    name: "M: contradiction (availability source)",
    messages: [
      "Gestionamos turnos que llegan por WhatsApp y los cargamos en Kommo.",
      "La disponibilidad la da Kommo.",
      "En realidad la miramos en una planilla.",
      "Dame el diagnóstico.",
    ],
    checks: { whatsapp: "whatsapp", kommo: "kommo", diagnosis: "diagnóstico" },
  },
  {
    name: "S: English",
    messages: [
      "I receive appointment requests through WhatsApp and record them in Salesforce.",
      "We need name, phone, date and time.", "Give me a diagnosis.",
    ],
    checks: { whatsapp: "whatsapp", salesforce: "salesforce", diagnosis: (s) => s.includes("diagnosis") || s.includes("assessment") },
  },
];

async function sendTurn(page: any, msg: string, isFirst: boolean) {
  if (isFirst) {
    await page.getByTestId("public-vera-text").fill(msg);
    await page.getByTestId("public-vera-submit").click();
  } else {
    await page.getByTestId("public-vera-chat-input").waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
    await page.getByTestId("public-vera-chat-input").fill(msg);
    await page.getByTestId("public-vera-chat-submit").click();
  }
  await page.waitForTimeout(3000);
}

test.describe("Public Vera — adversarial conversational coverage", () => {
  for (const tc of CASES) {
    test(tc.name, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });
      page.on("pageerror", (error) => consoleErrors.push(error.message));

      await page.goto("/t360");
      await expect(page.getByTestId("public-vera-entry")).toBeVisible();

      for (let i = 0; i < tc.messages.length; i++) {
        await sendTurn(page, tc.messages[i], i === 0);
      }
      await page.waitForTimeout(2000);

      const bodyText = await page.locator("body").innerText();
      const lower = bodyText.toLowerCase();

      for (const [key, check] of Object.entries(tc.checks)) {
        if (typeof check === "string") {
          expect(lower, `${key} should be present`).toContain(check);
        } else {
          expect(check(lower), `${key} should pass custom check`).toBe(true);
        }
      }

      const criticalErrors = consoleErrors.filter(
        (e) => !e.includes("ERR_CONNECTION_REFUSED") && !e.includes("favicon")
      );
      expect(criticalErrors).toEqual([]);
    });
  }
});
