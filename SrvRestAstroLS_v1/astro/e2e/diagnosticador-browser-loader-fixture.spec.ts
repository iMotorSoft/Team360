import { expect, test } from "@playwright/test";

type AuthRequest = {
  client_id: string;
  message: string;
  session_id: string;
};

type AuthResponse = {
  client_id: string;
  timestamp: number;
  signature: string;
} & Record<string, unknown>;

type TurnRequest = {
  client_id: string;
  message: string;
  session_id: string;
  timestamp: number;
} & Record<string, unknown>;

test.describe("Diagnosticador Browser Loader Fixture", () => {
  test.setTimeout(120000);

  const FIXTURE_URL = "/embed-fixtures/t360-external-loader.html";
  const FIXTURE_SESSION_KEY = "team360.embed.loader.fixture.session.v1";
  const VERA_SESSION_KEY = "team360.vera.session.v1";
  const MOUNT_SESSION_KEY = "team360.embed.mount.demo.session.v1";
  const EXTERNAL_SESSION_KEY = "team360.embed.external.demo.session.v1";

  test("carga un host HTML externo estático, monta con loader público y conserva auth -> turn", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    let authRequestBody: Record<string, unknown> | null = null;
    let authResponseBody: Record<string, unknown> | null = null;
    let turnRequestBody: Record<string, unknown> | null = null;
    let turnRequestHeaders: Record<string, string> | null = null;
    let authCalls = 0;
    let turnCalls = 0;

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    page.on("request", (request) => {
      if (request.method() !== "POST") return;

      if (request.url().includes("/api/diagnosis/embed/auth")) {
        authCalls += 1;
        authRequestBody = request.postDataJSON() as Record<string, unknown>;
      }

      if (request.url().includes("/api/diagnosis/turn")) {
        turnCalls += 1;
        turnRequestBody = request.postDataJSON() as Record<string, unknown>;
        turnRequestHeaders = request.headers();
      }
    });

    page.on("response", async (response) => {
      if (!response.url().includes("/api/diagnosis/embed/auth")) return;
      if (response.request().method() !== "POST") return;
      try {
        authResponseBody = (await response.json()) as Record<string, unknown>;
      } catch {
        authResponseBody = null;
      }
    });

    await page.goto(FIXTURE_URL);

    await expect(page.getByTestId("browser-loader-fixture")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Team360 external loader fixture" })).toBeVisible();
    await expect(page.getByTestId("fixture-status")).toHaveText("mounted");
    await expect(page.getByTestId("fixture-loader-version")).toHaveText("experimental-9e");
    await expect(page.getByTestId("fixture-global-version")).toHaveText("experimental-9c");
    await expect(page.getByTestId("fixture-destroy-support")).toHaveText("function");
    await expect(page.getByTestId("fixture-target")).toBeVisible();

    const browserApi = await page.evaluate(() => ({
      loaderType: typeof window.Team360DiagnosticadorLoader?.load,
      browserGlobalExists: Boolean(window.Team360Diagnosticador),
      mountType: typeof window.Team360Diagnosticador?.mount,
      assetVersion: window.Team360Diagnosticador?.version ?? null,
    }));
    expect(browserApi).toEqual({
      loaderType: "function",
      browserGlobalExists: true,
      mountType: "function",
      assetVersion: "experimental-9c",
    });

    const fixtureBefore = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraBefore = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    const mountBefore = await page.evaluate((key) => sessionStorage.getItem(key), MOUNT_SESSION_KEY);
    const externalBefore = await page.evaluate((key) => sessionStorage.getItem(key), EXTERNAL_SESSION_KEY);
    expect(fixtureBefore).toBeNull();
    expect(veraBefore).toBeNull();
    expect(mountBefore).toBeNull();
    expect(externalBefore).toBeNull();

    await expect(page.getByTestId("embed-demo-wrapper")).toBeVisible();
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();
    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas por WhatsApp");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-assistant-message").waitFor({ state: "visible", timeout: 60000 });

    await expect.poll(() => authRequestBody).not.toBeNull();
    await expect.poll(() => authResponseBody).not.toBeNull();
    await expect.poll(() => turnRequestBody).not.toBeNull();
    await expect.poll(() => turnRequestHeaders?.["x-t360-signature"] ?? null).not.toBeNull();

    if (!authRequestBody || !authResponseBody || !turnRequestBody) {
      throw new Error("Fixture auth or turn request was not captured");
    }

    const authBody = authRequestBody as AuthRequest;
    const authResponse = authResponseBody as AuthResponse;
    const turnBody = turnRequestBody as TurnRequest;

    expect(authBody).toMatchObject({
      client_id: "local_embed_demo",
      message: "Quiero automatizar consultas por WhatsApp",
    });
    expect(typeof authBody.session_id).toBe("string");
    expect(authResponse).toHaveProperty("client_id", "local_embed_demo");
    expect(typeof authResponse.timestamp).toBe("number");
    expect(String(authResponse.signature)).toMatch(/^sha256=[0-9a-f]{64}$/);

    expect(turnBody).toMatchObject({
      client_id: "local_embed_demo",
      message: "Quiero automatizar consultas por WhatsApp",
      session_id: authBody.session_id,
    });
    expect(typeof turnBody.timestamp).toBe("number");
    expect(turnRequestHeaders?.["x-t360-signature"]).toMatch(/^sha256=[0-9a-f]{64}$/);

    for (const forbiddenField of [
      "assistant_instance_code",
      "organization_code",
      "workspace_code",
      "package_code",
      "knowledge_scope_code",
      "allowed_origins",
      "hmac_secret",
      "service_code",
      "template_code",
    ]) {
      expect(authResponse).not.toHaveProperty(forbiddenField);
      expect(turnBody).not.toHaveProperty(forbiddenField);
    }

    const fixtureSession = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraAfter = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    const mountAfter = await page.evaluate((key) => sessionStorage.getItem(key), MOUNT_SESSION_KEY);
    const externalAfter = await page.evaluate((key) => sessionStorage.getItem(key), EXTERNAL_SESSION_KEY);
    expect(fixtureSession).not.toBeNull();
    expect(veraAfter).toBeNull();
    expect(mountAfter).toBeNull();
    expect(externalAfter).toBeNull();

    const fixtureData = JSON.parse(fixtureSession!);
    expect(typeof fixtureData.session_id).toBe("string");

    const pageText = await page.locator("body").innerText();
    expect(pageText).toContain("Team360 external loader fixture");
    expect(pageText).not.toContain("hmac_secret");
    expect(pageText).not.toContain("organization_code");
    expect(pageText).not.toContain("workspace_code");
    expect(pageText).not.toContain("package_code");
    expect(pageText).not.toContain("knowledge_scope_code");

    await page.getByTestId("fixture-destroy").click();
    await expect(page.getByTestId("fixture-status")).toHaveText("destroyed");
    await expect(page.getByTestId("fixture-last-action")).toHaveText("destroy");
    await expect(page.getByTestId("diagnosticador-core")).toHaveCount(0);

    await page.getByTestId("fixture-remount").click();
    await expect(page.getByTestId("fixture-status")).toHaveText("mounted");
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();

    const invalidResult = await page.evaluate(() => {
      try {
        if (!window.Team360Diagnosticador) {
          throw new Error("Team360Diagnosticador global is not available.");
        }
        window.Team360Diagnosticador.mount("#team360-diagnosticador-root", {
          apiBaseUrl: "http://127.0.0.1:7050/api",
        } as any);
        return { ok: true, message: "" };
      } catch (error) {
        return {
          ok: false,
          message: error instanceof Error ? error.message : String(error),
        };
      }
    });
    expect(invalidResult.ok).toBe(false);
    expect(invalidResult.message).toContain("clientId is required");
    expect(authCalls).toBe(1);
    expect(turnCalls).toBe(1);

    const criticalErrors = consoleErrors.filter(
      (error) => !error.includes("favicon") && !error.includes("ERR_CONNECTION_REFUSED"),
    );
    expect(criticalErrors).toEqual([]);
  });
});
