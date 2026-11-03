# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: srv05-safe-runtime.spec.ts >> Srv05 opt-in safe runtime >> mamamia: real API, HMAC where applicable, response and second turn
- Location: e2e/srv05-safe-runtime.spec.ts:9:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Perfecto: hoy llegan ~20 consultas de ventas por **Gmail**, miran **stock en el ERP** y **precios en un Excel**, y como hay que validar, **siempre termina en aprobación humana** (derivar a una persona).\n\nPara armar el diagnóstico del flujo, necesito entender esto: **cuando llega una consulta, qué hace la persona primero y dónde registra el caso (CRM, planilla, correo reenviado, etc.) antes de pedir/confirmar stock y precio?**', { exact: true })
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByText('Perfecto: hoy llegan ~20 consultas de ventas por **Gmail**, miran **stock en el ERP** y **precios en un Excel**, y como hay que validar, **siempre termina en aprobación humana** (derivar a una persona).\n\nPara armar el diagnóstico del flujo, necesito entender esto: **cuando llega una consulta, qué hace la persona primero y dónde registra el caso (CRM, planilla, correo reenviado, etc.) antes de pedir/confirmar stock y precio?**', { exact: true })

```

```yaml
- banner:
  - heading "Mamamia360 · Diagnosticador Vera" [level=1]
  - paragraph: Demo del componente embebible — diagnóstico de factibilidad
- main:
  - text: Diagnóstico de factibilidad
  - paragraph: Vera
  - paragraph: Diagnóstico abierto
  - button "Nueva conversación"
  - text: "Sonda sintética: recibo 20 consultas de ventas por Gmail al día, stock en ERP y precios en Excel; siempre requiere aprobación humana."
  - paragraph:
    - text: "Perfecto: hoy llegan ~20 consultas de ventas por"
    - strong: Gmail
    - text: ", miran"
    - strong: stock en el ERP
    - text: "y"
    - strong: precios en un Excel
    - text: ", y como hay que validar,"
    - strong: siempre termina en aprobación humana
    - text: (derivar a una persona).
  - paragraph:
    - text: "Para armar el diagnóstico del flujo, necesito entender esto:"
    - strong: cuando llega una consulta, qué hace la persona primero y dónde registra el caso (CRM, planilla, correo reenviado, etc.) antes de pedir/confirmar stock y precio?
  - heading "Qué falta para afinar el diagnóstico" [level=2]
  - paragraph: Ya hay una orientación inicial. Estos datos ayudarían a hacerla más precisa.
  - article:
    - heading "Canal principal" [level=3]
    - text: Confirmado Diagnóstico preliminar
  - article:
    - heading "Sistema de gestión actual" [level=3]
    - text: Confirmado Diagnóstico completo
  - article:
    - heading "Proceso actual descripto" [level=3]
    - text: Confirmado Diagnóstico preliminar
  - article:
    - heading "Qué acciones necesitan aprobación humana" [level=3]
    - text: Confirmado Implementación
  - article:
    - heading "Volumen aproximado de consultas" [level=3]
    - text: Faltante Diagnóstico completo
  - button "Completar datos"
  - button "Ver diagnóstico actual"
  - textbox "Escribí tu mensaje..."
  - button "Enviar" [disabled]
  - text: Powered by
  - strong: Team360
- contentinfo: Team360 · Diagnosticador embebible para distribuidores
```

# Test source

```ts
  1  | import { randomUUID } from "node:crypto";
  2  | import { expect, test } from "@playwright/test";
  3  | 
  4  | // Run only with backend-dev.sh TEAM360_DEV_PROFILE=srv05-e2e and astro-dev.sh.
  5  | // Supply fresh scoped IDs, never mock responses or reuse production sessions.
  6  | test.describe("Srv05 opt-in safe runtime", () => {
  7  |   test.skip(process.env.TEAM360_SRV05_SAFE_E2E !== "1", "Requires test-only guarded listener");
  8  |   for (const surface of ["home", "mamamia"] as const) {
  9  |     test(`${surface}: real API, HMAC where applicable, response and second turn`, async ({ page }) => {
  10 |       test.setTimeout(120_000);
  11 |       const session = "full_gate_" + randomUUID().replaceAll("-", "");
  12 |       const errors: string[] = [];
  13 |       const serverErrors: string[] = [];
  14 |       const counts: number[] = [];
  15 |       let authCount = 0;
  16 |       let turnCount = 0;
  17 |       page.on("pageerror", error => errors.push(error.message));
  18 |       page.on("console", msg => { if (msg.type() === "error") errors.push(msg.text()); });
  19 |       page.on("response", response => { if (response.status() >= 500) serverErrors.push(response.url()); });
  20 |       await page.route("**/api/diagnosis/{turn,embed/auth}", async route => {
  21 |         const request = route.request();
  22 |         if (request.method() !== "POST") return route.continue();
  23 |         const body = request.postDataJSON();
  24 |         body.session_id = session;
  25 |         if (request.url().endsWith("/turn")) turnCount++;
  26 |         else authCount++;
  27 |         await route.continue({ postData: JSON.stringify(body) });
  28 |       });
  29 |       await page.goto(surface === "home" ? "/t360" : "/embed-demo/mamamia360.html");
  30 |       await expect(page.getByTestId("public-vera-text")).toBeVisible({ timeout: 20_000 });
  31 |       const first = page.waitForResponse(r => r.url().endsWith("/api/diagnosis/turn") && r.request().method() === "POST");
  32 |       await page.getByTestId("public-vera-text").fill("Sonda sintética: recibo 20 consultas de ventas por Gmail al día, stock en ERP y precios en Excel; siempre requiere aprobación humana.");
  33 |       await page.getByTestId("public-vera-submit").click();
  34 |       const firstResponse = await first;
  35 |       expect(firstResponse.status()).toBe(201);
  36 |       const firstBody = await firstResponse.json();
  37 |       expect(firstBody.session_id).toBe(session);
  38 |       expect(firstBody.response_text.length).toBeGreaterThan(0);
  39 |       expect(firstBody.turn_decision.generation.fallback_used).toBe(false);
  40 |       counts.push(firstBody.turn_count);
  41 |       await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 60_000 });
> 42 |       await expect(page.getByText(firstBody.response_text, { exact: true })).toBeVisible();
     |                                                                              ^ Error: expect(locator).toBeVisible() failed
  43 |       const second = page.waitForResponse(r => r.url().endsWith("/api/diagnosis/turn") && r.request().method() === "POST");
  44 |       await page.getByTestId("public-vera-chat-input").fill("Necesito una orientación inicial, sin ejecutar ninguna acción externa.");
  45 |       await page.getByTestId("public-vera-chat-submit").click();
  46 |       const secondResponse = await second;
  47 |       expect(secondResponse.status()).toBe(201);
  48 |       const secondBody = await secondResponse.json();
  49 |       expect(secondBody.session_id).toBe(session);
  50 |       expect(secondBody.turn_count).toBe(firstBody.turn_count + 1);
  51 |       expect(secondBody.turn_decision.generation.fallback_used).toBe(false);
  52 |       counts.push(secondBody.turn_count);
  53 |       await expect(page.getByTestId("public-vera-chat-input")).toBeEnabled({ timeout: 60_000 });
  54 |       expect(turnCount).toBe(2);
  55 |       if (surface === "mamamia") expect(authCount).toBe(2);
  56 |       expect(errors).toEqual([]);
  57 |       expect(serverErrors).toEqual([]);
  58 |       await test.info().attach("safe-runtime", { body: JSON.stringify({ surface, session, counts, turnCount, authCount, errors, serverErrors }), contentType: "application/json" });
  59 |     });
  60 |   }
  61 | });
  62 | 
```