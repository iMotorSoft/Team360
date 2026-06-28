import { expect, test } from "@playwright/test";

test.describe("Diagnosticador Embed Lab", () => {
  test.setTimeout(120000);

  const LAB_SESSION_KEY = "team360.diagnosticador.lab.session.v1";
  const VERA_SESSION_KEY = "team360.vera.session.v1";

  test("carga, monta Core, usa key aislada y no colisiona con Vera", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    // 1. Crear sesión Vera primero
    await page.goto("/t360");
    await expect(page.getByTestId("public-vera-entry")).toBeVisible();

    await page.getByTestId("public-vera-text").fill("recibimos muchas llamadas de teléfono");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-assistant-message").waitFor({ state: "visible", timeout: 60000 });

    // Vera key debe tener session_id
    const veraKey = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(veraKey).not.toBeNull();
    const veraData = JSON.parse(veraKey!);
    expect(typeof veraData.session_id).toBe("string");

    // 2. Abrir lab en pestaña nueva (sessionStorage aislada por tab)
    const labPage = await page.context().newPage();
    const labErrors: string[] = [];
    labPage.on("console", (msg) => { if (msg.type() === "error") labErrors.push(msg.text()); });
    labPage.on("pageerror", (err) => labErrors.push(err.message));

    // Interceptar request del lab para verificar apiBaseUrl y contexto
    let labRequestUrl: string | null = null;
    let labRequestBody: string | null = null;
    labPage.route("**/diagnosis/turn", (route) => {
      labRequestUrl = route.request().url();
      labRequestBody = route.request().postData();
      route.continue();
    });

    await labPage.goto("/t360-diagnosticador-lab");
    await expect(labPage.getByTestId("diagnosticador-core")).toBeVisible();

    // 3. Lab key no existe aún (no se ha enviado mensaje)
    const labKeyBefore = await labPage.evaluate((key) => sessionStorage.getItem(key), LAB_SESSION_KEY);
    expect(labKeyBefore).toBeNull();

    // 4. Lab envía mensaje y recibe respuesta real
    await expect(labPage.getByTestId("public-vera-text")).toBeVisible();
    await labPage.getByTestId("public-vera-text").fill("problemas con el seguimiento de leads");
    await labPage.getByTestId("public-vera-submit").click();
    await labPage.getByTestId("public-vera-assistant-message").waitFor({ state: "visible", timeout: 60000 });

    // Después del mensaje, lab key debe tener session_id
    const labKeyAfter = await labPage.evaluate((key) => sessionStorage.getItem(key), LAB_SESSION_KEY);
    expect(labKeyAfter).not.toBeNull();
    const labData = JSON.parse(labKeyAfter!);
    expect(typeof labData.session_id).toBe("string");

    // 5. El request del lab usó API_BASE_URL explícito y contexto pasado
    expect(labRequestUrl).not.toBeNull();
    expect(labRequestUrl!).toContain("http://localhost:7050/api/diagnosis/turn");
    expect(labRequestBody).not.toBeNull();
    const labBody = JSON.parse(labRequestBody!);
    expect(labBody).toMatchObject({
      assistant_instance_code: "team360_sales_diagnosis",
      package_code: "pkg_sales_diagnosis",
      knowledge_scope_code: "ks_team360_sales_diagnosis",
    });

    // 6. La key de Vera NO está en sessionStorage del lab (tab aislada)
    const veraNotInLab = await labPage.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(veraNotInLab).toBeNull();

    labPage.close();

    // 7. Vera en su tab original mantiene su sesión intacta
    const veraStill = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(veraStill).not.toBeNull();
    const veraStillData = JSON.parse(veraStill!);
    expect(veraStillData.session_id).toBe(veraData.session_id);

    expect(consoleErrors.filter(
      (e) => !e.includes("favicon") && !e.includes("ERR_CONNECTION_REFUSED")
    )).toEqual([]);
    expect(labErrors.filter(
      (e) => !e.includes("favicon") && !e.includes("ERR_CONNECTION_REFUSED")
    )).toEqual([]);
  });
});
