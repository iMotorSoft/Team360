# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: srv05-safe-runtime.spec.ts >> Srv05 opt-in safe runtime >> home: real API, HMAC where applicable, response and second turn
- Location: e2e/srv05-safe-runtime.spec.ts:9:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Perfecto: hoy recibís ~20 consultas de ventas por Gmail por día, mirás stock en el ERP y precios en un Excel, y como el proceso siempre requiere aprobación humana, el objetivo es que el sistema te ayude a **ordenar/armar la respuesta y derivar para que una persona apruebe** (en vez de hacerlo manual).\n\nPara avanzar: **cuando llega cada consulta, qué hace la persona antes de aprobar—solo confirma stock/precio, o también arma la cotización/propuesta y define el siguiente paso (turno/venta) ?**', { exact: true })
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByText('Perfecto: hoy recibís ~20 consultas de ventas por Gmail por día, mirás stock en el ERP y precios en un Excel, y como el proceso siempre requiere aprobación humana, el objetivo es que el sistema te ayude a **ordenar/armar la respuesta y derivar para que una persona apruebe** (en vez de hacerlo manual).\n\nPara avanzar: **cuando llega cada consulta, qué hace la persona antes de aprobar—solo confirma stock/precio, o también arma la cotización/propuesta y define el siguiente paso (turno/venta) ?**', { exact: true })

```

```yaml
- link "Saltar al contenido":
  - /url: "#contenido"
- banner:
  - link "Team360, inicio":
    - /url: /
    - text: Team360
  - navigation "Navegación principal":
    - link "Qué hacemos":
      - /url: "#solucion"
    - link "Casos de uso":
      - /url: "#casos"
    - link "Nuestro método":
      - /url: "#metodo"
    - link "Partners":
      - /url: "#partners"
  - link "Acceso clientes":
    - /url: https://console.team360.live/login
  - link "Ver diagnóstico inicial":
    - /url: "#vera"
- main:
  - paragraph: Diagnóstico Team360
  - heading "Automatizamos tareas y procesos que hoy tu equipo resuelve a mano." [level=1]
  - paragraph: Consultas, seguimiento, reportes e integraciones organizados con inteligencia artificial y control humano.
  - paragraph: Team360 analiza cómo trabaja tu equipo, detecta qué partes conviene automatizar y conecta canales, sistemas y datos en una operación más clara.
  - paragraph: Para equipos comerciales, administrativos y operativos. No necesitás saber de automatización ni tener definido un proyecto técnico.
  - link "Empezar diagnóstico":
    - /url: "#vera"
  - link "Ver soluciones":
    - /url: "#solucion"
  - paragraph: Vista previa
  - heading "Ejemplo de orientación inicial" [level=2]
  - text: Orientación
  - paragraph: Vera organiza
  - paragraph: Este ejemplo muestra cómo Vera puede organizar la factibilidad, los puntos a validar y los próximos pasos de tu caso.
  - text: Caso de ejemplo
  - textbox "Caso de ejemplo": "Ej: recibimos muchos WhatsApp, nadie sabe quién respondió y después tengo que armar reportes manualmente."
  - link "Probar diagnóstico en vivo":
    - /url: "#vera"
  - paragraph: Usá la sección de Vera para escribir tu caso y recibir una orientación conectada.
  - paragraph: "El diagnóstico inicial debe devolver:"
  - paragraph: Tipo
  - paragraph: Qué se puede automatizar
  - paragraph: Necesita
  - paragraph: Canales, datos o integración
  - paragraph: Síntesis
  - paragraph: Qué conviene hacer ahora
  - paragraph: Este es un ejemplo de orientación inicial. No ejecuta acciones, no crea leads, no confirma por WhatsApp y no deriva datos sin autorización.
  - paragraph: Antes / Después
  - heading "Del desorden operativo a un plan que se puede ejecutar." [level=2]
  - paragraph: Antes
  - list:
    - listitem: Mensajes repartidos entre canales.
    - listitem: Reportes armados a mano y tarde.
    - listitem: Decisiones sin datos claros.
    - listitem: IA usada como herramienta suelta.
  - paragraph: Después
  - list:
    - listitem: Canales ordenados por intención y prioridad.
    - listitem: Tasks medibles dentro de un flujo claro.
    - listitem: Integraciones pensadas según necesidad real.
    - listitem: Diagnóstico primero, automatización después.
  - paragraph: Soluciones principales
  - heading "No vendemos piezas técnicas. Resolvemos dolores comerciales claros." [level=2]
  - paragraph: Team360 detecta qué parte de la operación necesita comunicación, contenido, datos, ventas, conocimiento o validación de backoffice, y arma una solución con el alcance correcto.
  - article:
    - paragraph: Atención y continuidad
    - heading "Communication & Follow-up" [level=3]
    - paragraph: WhatsApp, Telegram, email, calendario, respuestas asistidas y seguimiento para que ninguna consulta quede perdida.
    - text: WhatsApp In Email Reader Follow-up Reminder Response Draft
  - article:
    - paragraph: Contenido que aprende
    - heading "Social Content" [level=3]
    - paragraph: Reels, publicaciones, copies, reglas de marca y métricas para transformar ideas en piezas listas para revisar.
    - text: Reel Brief Post Copy Brand QA Meta Metrics
  - article:
    - paragraph: Ventas con visibilidad
    - heading "Sales KPI" [level=3]
    - paragraph: Leads, campañas, datos comerciales disponibles, seguimiento y reportes para entender qué pasa antes de perder oportunidades.
    - text: CRM Signals Lead Summary Ads KPI Sales Report
  - article:
    - paragraph: Conocimiento usable
    - heading "Knowledge Operations" [level=3]
    - paragraph: Carga, curación y validación de información empresarial para que los asistentes respondan mejor y con límites claros.
    - text: Load Knowledge Validate FAQ Detect Gaps Answer Test
  - article:
    - paragraph: Control operativo
    - heading "Backoffice Validation" [level=3]
    - paragraph: Archivos, documentos, conciliaciones, validación y revisión asistida para tareas administrativas repetitivas.
    - text: File Intake Parse Document Match Records Control Report
  - paragraph: Tasks simples
  - heading "Cada mejora empieza por una acción concreta." [level=2]
  - paragraph: Una Task no es una promesa abstracta. Es una pieza puntual que puede entrar en un Pack o en un Flow.
  - article:
    - heading "Leer un email" [level=3]
    - paragraph: Detecta intención, adjuntos y próximos pasos.
  - article:
    - heading "Recibir WhatsApp" [level=3]
    - paragraph: Ordena la consulta y conserva contexto.
  - article:
    - heading "Consultar una base" [level=3]
    - paragraph: Busca datos disponibles cuando existe integración y permiso.
  - article:
    - heading "Preparar respuesta" [level=3]
    - paragraph: Redacta una salida revisable por el equipo.
  - article:
    - heading "Generar reporte" [level=3]
    - paragraph: Convierte movimientos y métricas en resumen claro.
  - article:
    - heading "Validar archivos" [level=3]
    - paragraph: Cruza documentos y señala diferencias.
  - paragraph: Lógica Team360
  - heading "Diagnosticar primero. Configurar después. Automatizar con criterio." [level=2]
  - paragraph: El diagnóstico no obliga al cliente a entrar en un catálogo cerrado. Primero entiende la operación; después traduce esa necesidad en Packs, Tasks, Flows e Integraciones posibles.
  - article:
    - text: "1"
    - heading "T360 Pack" [level=3]
    - paragraph: "Una solución configurable para una necesidad concreta: atención al cliente, administración, ventas o contenido."
  - article:
    - text: "2"
    - heading "T360 Task" [level=3]
    - paragraph: "Una acción puntual: registrar una consulta, enviar una respuesta, clasificar un pedido, actualizar un estado o generar un reporte."
  - article:
    - text: "3"
    - heading "T360 Pack Flow" [level=3]
    - paragraph: Una secuencia ordenada de Tasks que convierte un proceso en un flujo operativo claro, paso a paso.
  - article:
    - text: "4"
    - heading "T360 Pack Integrate" [level=3]
    - paragraph: Conexión con herramientas, sistemas o canales existentes, según permisos y factibilidad técnica.
  - paragraph: Prueba de método
  - heading "Cómo se ve un diagnóstico útil." [level=2]
  - paragraph: En vez de decir "sí, se puede", Team360 separa factibilidad, prioridad, riesgo y próximo paso.
  - link "Ver diagnóstico inicial":
    - /url: "#vera"
  - article:
    - heading "1. Entender" [level=3]
    - paragraph: Qué canal entra, quién responde, qué datos faltan y cuánto volumen existe.
  - article:
    - heading "2. Clasificar" [level=3]
    - paragraph: Disponible hoy, configurable, requiere desarrollo o no conviene vender todavía.
  - article:
    - heading "3. Diseñar" [level=3]
    - paragraph: Qué Pack, Tasks, Flow o Integración forman una primera solución razonable.
  - article:
    - heading "4. Medir" [level=3]
    - paragraph: "Qué resultado tiene que verse: menos demora, menos errores, más seguimiento o mejor reporte."
  - paragraph: Vera es la asistente de diagnóstico de Team360. Te ayuda a identificar qué se puede automatizar y por dónde conviene empezar.
  - paragraph: Diagnóstico abierto
  - heading "Hablá con Vera" [level=2]
  - paragraph: Contanos qué proceso querés mejorar o automatizar.
  - paragraph: No necesitás completar un formulario. Escribí en tus palabras qué querés mejorar.
  - button "Recibo leads por WhatsApp y no sé quién los sigue."
  - button "Quiero medir campañas de Facebook contra ventas."
  - button "Tengo reportes en Excel que armamos manualmente."
  - paragraph: Vera
  - paragraph: Diagnóstico abierto
  - button "Nueva conversación"
  - text: "Sonda sintética: recibo 20 consultas de ventas por Gmail al día, stock en ERP y precios en Excel; siempre requiere aprobación humana."
  - paragraph:
    - text: "Perfecto: hoy recibís ~20 consultas de ventas por Gmail por día, mirás stock en el ERP y precios en un Excel, y como el proceso siempre requiere aprobación humana, el objetivo es que el sistema te ayude a"
    - strong: ordenar/armar la respuesta y derivar para que una persona apruebe
    - text: (en vez de hacerlo manual).
  - paragraph:
    - text: "Para avanzar:"
    - strong: cuando llega cada consulta, qué hace la persona antes de aprobar—solo confirma stock/precio, o también arma la cotización/propuesta y define el siguiente paso (turno/venta) ?
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
  - link "Solicitar revisión por correo":
    - /url: mailto:contacto@team360.live?subject=Solicitar%20revisi%C3%B3n%20con%20Vera&body=Conversaci%C3%B3n%20con%20Vera%3A%0A%0AUsuario%3A%20Sonda%20sint%C3%A9tica%3A%20recibo%2020%20consultas%20de%20ventas%20por%20Gmail%20al%20d%C3%ADa%2C%20stock%20en%20ERP%20y%20precios%20en%20Excel%3B%20siempre%20requiere%20aprobaci%C3%B3n%20humana.%0AVera%3A%20Perfecto%3A%20hoy%20recib%C3%ADs%20~20%20consultas%20de%20ventas%20por%20Gmail%20por%20d%C3%ADa%2C%20mir%C3%A1s%20stock%20en%20el%20ERP%20y%20precios%20en%20un%20Excel%2C%20y%20como%20el%20proceso%20siempre%20requiere%20aprobaci%C3%B3n%20humana%2C%20el%20objetivo%20es%20que%20el%20sistema%20te%20ayude%20a%20**ordenar%2Farmar%20la%20respuesta%20y%20derivar%20para%20que%20una%20persona%20apruebe**%20(en%20vez%20de%20hacerlo%20manual).%0A%0APara%20avanzar%3A%20**cuando%20llega%20cada%20consulta%2C%20qu%C3%A9%20hace%20la%20persona%20antes%20de%20aprobar%E2%80%94solo%20confirma%20stock%2Fprecio%2C%20o%20tambi%C3%A9n%20arma%20la%20cotizaci%C3%B3n%2Fpropuesta%20y%20define%20el%20siguiente%20paso%20(turno%2Fventa)%20%3F**%0A%0AGracias.
  - paragraph: Equipos y partners
  - heading "Una misma lógica para ventas, operación, administración y contenido." [level=2]
  - article:
    - heading "Equipo interno" [level=3]
    - paragraph: Ordenar tareas repetitivas sin cambiar toda la operación.
  - article:
    - heading "Área comercial" [level=3]
    - paragraph: Medir seguimiento, leads y campañas con mejor contexto.
  - article:
    - heading "Partner operativo" [level=3]
    - paragraph: Diagnosticar clientes y armar soluciones por alcance.
  - paragraph: Preguntas frecuentes
  - heading "Objeciones normales antes de automatizar." [level=2]
  - group: ¿Necesito saber de tecnología? +
  - group: ¿Esto reemplaza a mi equipo? +
  - group: ¿Tengo que cambiar mis sistemas? +
  - group: ¿Todo queda automatizado desde el día uno? +
  - paragraph: Siguiente paso
  - heading "Contanos qué operación querés ordenar y te devolvemos un primer mapa de solución." [level=2]
  - paragraph: El diagnóstico puede orientar aunque todavía no exista el Pack o la Task exacta. Si requiere integración o desarrollo, debe decirlo sin ejecutarlo desde esta Home.
  - link "Ver diagnóstico inicial":
    - /url: "#vera"
  - link "Volver al diagnóstico inicial":
    - /url: "#vera"
  - paragraph: La toma de datos se agrega solo con autorización explícita y después de entregar una síntesis valiosa.
- contentinfo:
  - link "Team360, inicio":
    - /url: /
    - text: Team360 OPERACIONES INTELIGENTES
  - paragraph: Automatización con IA aplicada a procesos reales de negocio, con implementación gradual, seguimiento y resultados medibles.
  - paragraph: Explorar
  - list:
    - listitem:
      - link "Qué hacemos":
        - /url: "#solucion"
    - listitem:
      - link "Casos de uso":
        - /url: "#casos"
    - listitem:
      - link "Nuestro método":
        - /url: "#metodo"
    - listitem:
      - link "Partners":
        - /url: "#partners"
  - paragraph: Contacto
  - list:
    - listitem:
      - link "contacto@team360.live":
        - /url: mailto:contacto@team360.live
    - listitem:
      - link "Acceso clientes":
        - /url: https://console.team360.live/login
    - listitem:
      - link "Solicitar diagnóstico":
        - /url: "#vera"
  - paragraph: © 2026 Team360. Operaciones inteligentes para empresas.
  - paragraph: Privacidad y términos disponibles próximamente.
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