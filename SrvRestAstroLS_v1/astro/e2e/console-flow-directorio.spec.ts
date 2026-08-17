import { test, expect, type Page } from "@playwright/test";

// Team360 Flow — Directorio Premium V1
// E2E sobre el runtime estático (mock/design mode). Cubre: navegación Flow,
// KPIs, lista, filtros, búsqueda, detalle por estado (LIVE escalado N1→N2→N3,
// pending approval, rejected, AUDIT_SNAPSHOT resuelto), evidencia, timeline,
// configuración futura, responsive y consola limpia.

const DIRECTORIO_URL = "/w/ws-team360-control/flow";
const CONFIG_URL = "/w/ws-team360-control/flow/configuracion";

// El grupo Administración también tiene un link "Configuración" (settings);
// el del grupo Flow se distingue por href.
const flowConfigLink = (page: Page) => page.locator('nav a[href*="/flow/configuracion"]');

async function openFlow(page: Page, url = DIRECTORIO_URL) {
  await page.goto(url);
  await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
}

function trackErrors(page: Page, errors: string[]) {
  page.on("console", (msg) => {
    if (msg.type() === "error" && !msg.text().includes("favicon")) errors.push(`console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("requestfailed", (req) => errors.push(`requestfailed: ${req.url()}`));
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflow, `overflow horizontal esperado <= 1, fue ${overflow}`).toBeLessThanOrEqual(1);
}

async function selectCaseByText(page: Page, text: string) {
  await page.locator("ul li button", { hasText: text }).click();
}

function detailSection(page: Page) {
  return page.locator('[data-selected="yes"]');
}

test.describe("Flow Directorio — navegación", () => {
  test("sidebar muestra el grupo Flow con Directorio y Configuración", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const nav = page.getByRole("navigation", { name: "Navegación de consola" });
    await expect(nav.getByText("Flow", { exact: true })).toBeVisible();
    const directorio = nav.getByRole("link", { name: "Directorio" });
    const configuracion = flowConfigLink(page);
    await expect(directorio).toBeVisible();
    await expect(configuracion).toBeVisible();
    await expect(directorio).toHaveAttribute("href", /\/flow$/);
    await expect(configuracion).toHaveAttribute("href", /\/flow\/configuracion$/);
    expect(errors).toEqual([]);
  });

  test("navega a Configuración → Sectores y niveles sin flujo de escritura", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await flowConfigLink(page).click();
    await expect(page).toHaveURL(/\/flow\/configuracion\/?$/);

    await expect(page.getByRole("heading", { name: "Sectores y niveles" })).toBeVisible();
    await expect(page.getByText("Configuración preparada", { exact: true })).toBeVisible();
    await expect(page.getByText("Modo demo · solo lectura", { exact: true })).toBeVisible();
    await expect(page.getByText(/La persistencia real se habilitará cuando exista el backend mutativo/)).toBeVisible();
    await expect(page.getByText("Alumbrado Público", { exact: true }).first()).toBeVisible();

    for (const email of ["alumbrado.n1@alquimiablue.com", "alumbrado.n2@alquimiablue.com", "alumbrado.n3@alquimiablue.com"]) {
      await expect(page.getByText(email, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText("Supervisor de cierre", { exact: true })).toBeVisible();
    await expect(page.getByText("alumbrado.n2@alquimiablue.com", { exact: true }).last()).toBeVisible();

    const editable = await page.locator("main input, main textarea, main select").count();
    expect(editable, "Configuración no debe tener controles editables sin backend mutativo").toBe(0);
    expect(errors).toEqual([]);
  });

  test("refresh directo de Directorio conserva la ruta y el shell", async ({ page }) => {
    await openFlow(page);
    await expect(page.getByRole("heading", { name: "Vista Ejecutiva" })).toBeVisible();
    await page.reload();
    await expect(page.locator('[data-hydrated="true"]')).toBeVisible();
    await expect(page.getByRole("heading", { name: "Vista Ejecutiva" })).toBeVisible();
  });
});

test.describe("Flow Directorio — KPIs y lista", () => {
  test("los KPIs reflejan los casos demo", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const articles = page.locator("main article");
    await expect(articles).toHaveCount(5);

    async function kpiValue(label: string) {
      return page.locator("article", { hasText: label }).getByText(/^\d+$/, { exact: false }).first().textContent();
    }

    expect(await kpiValue("Casos activos")).toBe("3");
    expect(await kpiValue("SLA comprometidos")).toBe("3");
    // 3 casos escalaron: N1→N2 (activo), N1→N2 (resuelto), N1→N2→N3 (activo).
    expect(await kpiValue("Escalados")).toBe("3");
    expect(await kpiValue("Pendientes de aprobación")).toBe("1");
    expect(await kpiValue("Resueltos")).toBe("1");
    expect(errors).toEqual([]);
  });

  test("la lista muestra los 5 casos con identificador corto, sector y estado", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const rows = page.locator("ul li button");
    await expect(rows).toHaveCount(5);

    await expect(rows.first()).toContainText("#333a15d0");
    await expect(rows.first()).toContainText("Alumbrado Público");
    await expect(rows.first()).toContainText("Activo");

    await expect(rows.nth(1)).toContainText("#814f38ce");
    await expect(rows.nth(1)).toContainText("Resuelto");

    await expect(rows.nth(2)).toContainText("Pendiente de aprobación");

    await expect(rows.nth(4)).toContainText("Subestación de la plaza sin suministro");
    expect(errors).toEqual([]);
  });

  test("los filtros por estado muestran los conteos correctos", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const tabs = page.getByRole("tablist", { name: "Filtrar casos" });
    const rows = page.locator("ul li button");

    async function filter(label: string) {
      await tabs.getByRole("tab", { name: label }).click();
    }

    await filter("Activos");
    await expect(rows).toHaveCount(3);
    await filter("SLA vencidos");
    await expect(rows).toHaveCount(3);
    await filter("Escalados");
    await expect(rows).toHaveCount(3);
    await filter("Pendientes");
    await expect(rows).toHaveCount(1);
    await filter("Resueltos");
    await expect(rows).toHaveCount(1);
    await filter("Todos");
    await expect(rows).toHaveCount(5);
    expect(errors).toEqual([]);
  });

  test("la búsqueda filtra y el estado vacío no rompe", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    const search = page.getByRole("searchbox", { name: "Buscar caso" });
    await search.fill("Lavalle");
    await expect(page.locator("ul li button")).toHaveCount(1);
    await expect(page.locator("ul li button").first()).toContainText("#814f38ce");

    await search.fill("zzzz-inexistente");
    await expect(page.getByText("No hay casos que coincidan")).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio — detalle", () => {
  test("caso LIVE escalado N1→N2→N3 sin resumen LLM", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Subestación de la plaza sin suministro");
    const detail = detailSection(page);

    await expect(detail.getByRole("heading", { name: "Subestación de la plaza sin suministro" })).toBeVisible();
    await expect(detail.getByText("Alumbrado Público · Plaza San Martín · Nivel 3")).toBeVisible();
    await expect(detail.getByText("Estado actual en vivo")).toBeVisible();
    await expect(detail.getByText("Resumen ejecutivo no disponible")).toBeVisible();
    await expect(detail.getByText("La evidencia estructurada continúa disponible.")).toBeVisible();

    await expect(detail.getByText("Nivel 1 · Vencido", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 2 · Vencido", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 3 · Dentro de SLA", { exact: true })).toBeVisible();

    await expect(detail.getByText("Nivel 1 → Nivel 2", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 2 → Nivel 3", { exact: true })).toBeVisible();
    await expect(detail.getByText("SLA de primera respuesta vencido", { exact: false }).first()).toBeVisible();

    const timeline = detail.locator("ol li");
    await expect(timeline).toHaveCount(14);
    await expect(detail.getByText("Asignado a Nivel 1", { exact: true })).toBeVisible();
    await expect(detail.getByText("Asignado a Nivel 2", { exact: true })).toBeVisible();
    await expect(detail.getByText("Asignado a Nivel 3", { exact: true })).toBeVisible();
    await expect(detail.getByText("Escalamiento de nivel", { exact: true })).toHaveCount(2);
    expect(errors).toEqual([]);
  });

  test("caso LIVE pendiente de aprobación no comunica resuelto", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Poste de luz dañado por temporal");
    const detail = detailSection(page);

    await expect(detail.locator('[aria-label*="Pendiente de aprobación"]')).toBeVisible();
    await expect(detail.getByText("Estado actual en vivo")).toBeVisible();
    await expect(detail.getByText("Propuesta del técnico", { exact: true })).toBeVisible();
    await expect(detail.getByText("Poste reemplazado y cableado asegurado.", { exact: true })).toBeVisible();
    await expect(detail.getByText("Pendiente de decisión", { exact: true })).toBeVisible();

    await expect(detail.getByText("Registro final auditado", { exact: false })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("caso LIVE con cierre rechazado muestra motivo y estado activo", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Cuadra a oscuras por varias luminarias apagadas");
    const detail = detailSection(page);

    await expect(detail.locator('[aria-label*="Activo"]')).toBeVisible();
    await expect(detail.getByText("Rechazado", { exact: true })).toBeVisible();
    await expect(detail.getByText("Falta verificar el sector norte de la cuadra.", { exact: true })).toBeVisible();
    await expect(detail.getByText("Registro final auditado", { exact: false })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("caso AUDIT_SNAPSHOT resuelto transmite cierre e integridad", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Lavalle");
    const detail = detailSection(page);

    await expect(detail.locator('[aria-label*="Resuelto"]')).toBeVisible();
    await expect(detail.getByText("Registro final auditado", { exact: false }).first()).toBeVisible();
    await expect(detail.getByText("Propuesta del técnico", { exact: true })).toBeVisible();
    await expect(detail.getByText("La luminaria quedó reparada y verificada en cuadrilla.", { exact: true })).toBeVisible();
    await expect(detail.getByText("Decisión del supervisor", { exact: true })).toBeVisible();
    await expect(detail.getByText("Aprobado", { exact: true })).toBeVisible();

    const timeline = detail.locator("ol li");
    await expect(timeline).toHaveCount(9);
    await expect(detail.getByText("Cierre autorizado por supervisor", { exact: true })).toBeVisible();
    await expect(detail.getByText("Caso resuelto", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("caso LIVE escalado N1→N2 con SLA mixto y resumen disponible", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Olleros");
    const detail = detailSection(page);

    await expect(detail.getByText("Resumen ejecutivo", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 1 · Vencido", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 2 · Dentro de SLA", { exact: true })).toBeVisible();
    await expect(detail.getByText("Nivel 1 → Nivel 2", { exact: true })).toBeVisible();
    await expect(detail.locator("ol li")).toHaveCount(7);
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio — evidencia", () => {
  test("las referencias técnicas quedan plegadas y disponibles", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Lavalle");
    const detail = detailSection(page);

    const evidence = detail.getByText("Evidencia y trazabilidad", { exact: true });
    await expect(evidence).toBeVisible();
    await expect(detail.getByText("Request ID", { exact: true })).toBeHidden();

    await evidence.click();
    await expect(detail.getByText("Request ID", { exact: true })).toBeVisible();
    await expect(detail.getByText("814f38ce-9509-4cd6-a355-fa176e63edb2", { exact: true })).toBeVisible();
    await expect(detail.getByText("Audit record", { exact: true })).toBeVisible();
    await expect(detail.getByText("a23aa1ec", { exact: true })).toBeVisible();
    await expect(detail.getByText("Hash de auditoría", { exact: true })).toBeVisible();
    await expect(detail.getByText("Routing N1", { exact: true })).toBeVisible();
    await expect(detail.getByText("r-n1-814f", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe("Flow Directorio — responsive", () => {
  for (const [vp, width, height] of [["mobile", 390, 844], ["tablet", 768, 1024], ["desktop", 1280, 900]] as const) {
    test(`sin overflow horizontal en ${vp} (Directorio)`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const errors: string[] = [];
      trackErrors(page, errors);
      await openFlow(page);
      await expectNoHorizontalOverflow(page);
      await expect(page.getByRole("heading", { name: "Vista Ejecutiva" })).toBeVisible();
      expect(errors).toEqual([]);
    });

    test(`sin overflow horizontal en ${vp} (Configuración)`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      const errors: string[] = [];
      trackErrors(page, errors);
      await openFlow(page, CONFIG_URL);
      await expectNoHorizontalOverflow(page);
      await expect(page.getByRole("heading", { name: "Sectores y niveles" })).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test("mobile: seleccionar un caso muestra el detalle con volver", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Lavalle");

    const back = page.getByRole("button", { name: /Volver al listado/ });
    await expect(back).toBeVisible();
    await expect(page.locator("ol li").first()).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await back.click();
    await expect(page.locator("ul li button")).toHaveCount(5);
  });

  test("desktop: listado y detalle conviven tras seleccionar", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openFlow(page);

    await selectCaseByText(page, "Luminaria apagada en la calle Lavalle");

    await expect(page.locator("ul li button").first()).toBeVisible();
    await expect(page.getByText("Registro final auditado", { exact: false }).first()).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
});

test.describe("Flow Directorio — accesibilidad básica", () => {
  test("filtros, búsqueda y badges usan semántica y no dependen solo del color", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFlow(page);

    const search = page.getByRole("searchbox", { name: "Buscar caso" });
    await expect(search).toBeVisible();
    await search.focus();
    await expect(search).toBeFocused();

    const tabs = page.getByRole("tablist", { name: "Filtrar casos" });
    await expect(tabs.getByRole("tab", { name: "Todos" })).toHaveAttribute("aria-selected", "true");
    await tabs.getByRole("tab", { name: "Resueltos" }).focus();
    await expect(tabs.getByRole("tab", { name: "Resueltos" })).toBeFocused();

    const badge = page.locator("ul li button").first().locator('[aria-label*="Estado actual"]').first();
    await expect(badge).toBeAttached();

    await selectCaseByText(page, "Luminaria apagada en la calle Lavalle");
    const back = page.getByRole("button", { name: /Volver al listado/ });
    await back.focus();
    await expect(back).toBeFocused();
  });
});

test.describe("Flow Directorio — consola limpia", () => {
  test("navegación completa sin errores de consola ni promesas rechazadas", async ({ page }) => {
    const errors: string[] = [];
    trackErrors(page, errors);
    await openFlow(page);

    await selectCaseByText(page, "Subestación de la plaza sin suministro");
    await expect(page.getByText("Resumen ejecutivo no disponible")).toBeVisible();
    await selectCaseByText(page, "Luminaria apagada en la calle Lavalle");
    await expect(page.getByText("Registro final auditado", { exact: false }).first()).toBeVisible();
    await page.getByText("Evidencia y trazabilidad", { exact: true }).click();
    await flowConfigLink(page).click();
    await expect(page.getByRole("heading", { name: "Sectores y niveles" })).toBeVisible();

    expect(errors).toEqual([]);
  });
});
