import { expect, test } from "@playwright/test";

type LoaderAuthRequest = {
  client_id: string;
  message: string;
  session_id: string;
};

type LoaderAuthResponse = {
  client_id: string;
  timestamp: number;
  signature: string;
} & Record<string, unknown>;

type LoaderTurnRequest = {
  client_id: string;
  message: string;
  session_id: string;
  timestamp: number;
} & Record<string, unknown>;

test.describe("Diagnosticador Loader Demo", () => {
  test.setTimeout(120000);

  const MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";
  const LOADER_URL = "/embed/team360-diagnosticador-loader.js";
  const ASSET_URL = "/embed/team360-diagnosticador.js";
  const LOADER_SESSION_KEY = "team360.embed.loader.demo.session.v1";
  const ASSET_SESSION_KEY = "team360.embed.asset.demo.session.v1";
  const SCRIPT_SESSION_KEY = "team360.embed.script.demo.session.v1";
  const MOUNT_SESSION_KEY = "team360.embed.mount.demo.session.v1";
  const EXTERNAL_SESSION_KEY = "team360.embed.external.demo.session.v1";
  const EMBED_SESSION_KEY = "team360.embed.demo.session.v1";
  const VERA_SESSION_KEY = "team360.vera.session.v1";

  test("carga manifest + loader + asset, registra el global y conserva auth -> turn", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

    let manifestStatus: number | null = null;
    let loaderStatus: number | null = null;
    let assetStatus: number | null = null;
    let authRequestBody: Record<string, unknown> | null = null;
    let authResponseBody: Record<string, unknown> | null = null;
    let turnRequestBody: Record<string, unknown> | null = null;
    let turnRequestHeaders: Record<string, string> | null = null;

    page.on("request", (request) => {
      if (request.method() !== "POST") return;

      if (request.url().includes("/api/diagnosis/embed/auth")) {
        authRequestBody = request.postDataJSON() as Record<string, unknown>;
      }

      if (request.url().includes("/api/diagnosis/turn")) {
        turnRequestBody = request.postDataJSON() as Record<string, unknown>;
        turnRequestHeaders = request.headers();
      }
    });

    page.on("response", async (response) => {
      const url = response.url();
      const method = response.request().method();

      if (url.includes(MANIFEST_URL) && method === "GET") {
        manifestStatus = response.status();
      }

      if (url.includes(LOADER_URL) && method === "GET") {
        loaderStatus = response.status();
      }

      if (url.includes(ASSET_URL) && method === "GET") {
        assetStatus = response.status();
      }

      if (!url.includes("/api/diagnosis/embed/auth") || method !== "POST") return;

      try {
        authResponseBody = (await response.json()) as Record<string, unknown>;
      } catch {
        authResponseBody = null;
      }
    });

    await page.goto("/t360-loader-demo");

    await expect(page.getByTestId("loader-demo")).toBeVisible();
    await expect(page.getByTestId("loader-demo-header")).toContainText(
      "manifest y loader externos minimos",
    );
    await expect(page.getByTestId("loader-demo-target")).toBeVisible();
    await expect(page.getByTestId("loader-demo-manifest-url")).toHaveText(MANIFEST_URL);
    await expect(page.getByTestId("loader-demo-loader-url")).toHaveText(LOADER_URL);
    await expect(page.getByTestId("loader-demo-asset-url")).toHaveText(ASSET_URL);
    await expect(page.getByTestId("loader-demo-preload-global")).toHaveText("absent");
    await expect(page.getByTestId("loader-demo-manifest-version")).toHaveText("0.9.0-experimental");
    await expect(page.getByTestId("loader-demo-loader-version")).toHaveText("experimental-9e");
    await expect(page.getByTestId("loader-demo-asset-version")).toHaveText("experimental-9c");
    await expect(page.getByTestId("loader-demo-status")).toHaveText("mounted");

    await expect.poll(() => manifestStatus).toBe(200);
    await expect.poll(() => loaderStatus).toBe(200);
    await expect.poll(() => assetStatus).toBe(200);

    const globals = await page.evaluate(() => ({
      loaderExists: Boolean(window.Team360DiagnosticadorLoader),
      loaderType: typeof window.Team360DiagnosticadorLoader?.load,
      loaderVersion: window.Team360DiagnosticadorLoader?.version ?? null,
      browserGlobalExists: Boolean(window.Team360Diagnosticador),
      mountType: typeof window.Team360Diagnosticador?.mount,
      assetVersion: window.Team360Diagnosticador?.version ?? null,
    }));
    expect(globals).toEqual({
      loaderExists: true,
      loaderType: "function",
      loaderVersion: "experimental-9e",
      browserGlobalExists: true,
      mountType: "function",
      assetVersion: "experimental-9c",
    });

    const loaderBefore = await page.evaluate((key) => sessionStorage.getItem(key), LOADER_SESSION_KEY);
    const assetBefore = await page.evaluate((key) => sessionStorage.getItem(key), ASSET_SESSION_KEY);
    const scriptBefore = await page.evaluate((key) => sessionStorage.getItem(key), SCRIPT_SESSION_KEY);
    const mountBefore = await page.evaluate((key) => sessionStorage.getItem(key), MOUNT_SESSION_KEY);
    const externalBefore = await page.evaluate((key) => sessionStorage.getItem(key), EXTERNAL_SESSION_KEY);
    const embedBefore = await page.evaluate((key) => sessionStorage.getItem(key), EMBED_SESSION_KEY);
    const veraBefore = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(loaderBefore).toBeNull();
    expect(assetBefore).toBeNull();
    expect(scriptBefore).toBeNull();
    expect(mountBefore).toBeNull();
    expect(externalBefore).toBeNull();
    expect(embedBefore).toBeNull();
    expect(veraBefore).toBeNull();

    await expect(page.getByTestId("embed-demo-wrapper")).toBeVisible();
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();
    await expect(page.getByTestId("public-vera-text")).toBeVisible();

    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas por WhatsApp");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-assistant-message").waitFor({ state: "visible", timeout: 60000 });

    await expect.poll(() => authRequestBody).not.toBeNull();
    await expect.poll(() => authResponseBody).not.toBeNull();
    await expect.poll(() => turnRequestBody).not.toBeNull();
    await expect.poll(() => turnRequestHeaders?.["x-t360-signature"] ?? null).not.toBeNull();

    if (!authRequestBody || !authResponseBody || !turnRequestBody) {
      throw new Error("Loader demo auth or turn request was not captured");
    }

    const authBody = authRequestBody as LoaderAuthRequest;
    const authResponse = authResponseBody as LoaderAuthResponse;
    const turnBody = turnRequestBody as LoaderTurnRequest;

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

    const loaderSession = await page.evaluate((key) => sessionStorage.getItem(key), LOADER_SESSION_KEY);
    const assetAfter = await page.evaluate((key) => sessionStorage.getItem(key), ASSET_SESSION_KEY);
    const scriptAfter = await page.evaluate((key) => sessionStorage.getItem(key), SCRIPT_SESSION_KEY);
    const mountAfter = await page.evaluate((key) => sessionStorage.getItem(key), MOUNT_SESSION_KEY);
    const externalAfter = await page.evaluate((key) => sessionStorage.getItem(key), EXTERNAL_SESSION_KEY);
    const embedAfter = await page.evaluate((key) => sessionStorage.getItem(key), EMBED_SESSION_KEY);
    const veraAfter = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);

    expect(loaderSession).not.toBeNull();
    expect(assetAfter).toBeNull();
    expect(scriptAfter).toBeNull();
    expect(mountAfter).toBeNull();
    expect(externalAfter).toBeNull();
    expect(embedAfter).toBeNull();
    expect(veraAfter).toBeNull();

    const loaderData = JSON.parse(loaderSession!);
    expect(typeof loaderData.session_id).toBe("string");

    await expect(page.getByTestId("public-vera-assistant-message")).toBeVisible();
    await expect(page.getByTestId("loader-demo")).not.toContainText("hmac_secret");

    const criticalErrors = consoleErrors.filter(
      (error) => !error.includes("favicon") && !error.includes("ERR_CONNECTION_REFUSED"),
    );
    expect(criticalErrors).toEqual([]);
  });
});
