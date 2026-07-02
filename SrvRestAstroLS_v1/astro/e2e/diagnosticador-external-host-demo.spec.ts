import { expect, test } from "@playwright/test";

type ExternalHostAuthRequest = {
  client_id: string;
  message: string;
  session_id: string;
};

type ExternalHostAuthResponse = {
  client_id: string;
  timestamp: number;
  signature: string;
} & Record<string, unknown>;

type ExternalHostTurnRequest = {
  client_id: string;
  message: string;
  session_id: string;
  timestamp: number;
} & Record<string, unknown>;

test.describe("Diagnosticador External Host Demo", () => {
  test.setTimeout(120000);

  const EXTERNAL_SESSION_KEY = "team360.embed.external.demo.session.v1";
  const EMBED_SESSION_KEY = "team360.embed.demo.session.v1";
  const VERA_SESSION_KEY = "team360.vera.session.v1";

  test("monta el embed desde un host externo controlado y conserva el contrato auth -> turn", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));

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
      if (!response.url().includes("/api/diagnosis/embed/auth")) return;
      if (response.request().method() !== "POST") return;
      try {
        authResponseBody = (await response.json()) as Record<string, unknown>;
      } catch {
        authResponseBody = null;
      }
    });

    await page.goto("/t360-external-host-demo");

    await expect(page.getByTestId("external-host-demo")).toBeVisible();
    await expect(page.getByTestId("external-host-header")).toContainText("External Host Demo");
    await expect(page.getByTestId("external-host-embed-slot")).toBeVisible();
    await expect(page.getByTestId("embed-demo-wrapper")).toBeVisible();
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();
    await expect(page.getByTestId("public-vera-text")).toBeVisible();

    const veraBefore = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    const embedBefore = await page.evaluate((key) => sessionStorage.getItem(key), EMBED_SESSION_KEY);
    const externalBefore = await page.evaluate((key) => sessionStorage.getItem(key), EXTERNAL_SESSION_KEY);
    expect(veraBefore).toBeNull();
    expect(embedBefore).toBeNull();
    expect(externalBefore).toBeNull();

    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas por WhatsApp");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-assistant-message").waitFor({ state: "visible", timeout: 60000 });

    await expect.poll(() => authRequestBody).not.toBeNull();
    await expect.poll(() => authResponseBody).not.toBeNull();
    await expect.poll(() => turnRequestBody).not.toBeNull();
    await expect.poll(() => turnRequestHeaders?.["x-t360-signature"] ?? null).not.toBeNull();

    if (!authRequestBody || !authResponseBody || !turnRequestBody) {
      throw new Error("External host auth or turn request was not captured");
    }

    const authBody = authRequestBody as ExternalHostAuthRequest;
    const authResponse = authResponseBody as ExternalHostAuthResponse;
    const turnBody = turnRequestBody as ExternalHostTurnRequest;

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
    ]) {
      expect(authResponse).not.toHaveProperty(forbiddenField);
      expect(turnBody).not.toHaveProperty(forbiddenField);
    }

    const externalSession = await page.evaluate((key) => sessionStorage.getItem(key), EXTERNAL_SESSION_KEY);
    const embedSession = await page.evaluate((key) => sessionStorage.getItem(key), EMBED_SESSION_KEY);
    const veraAfter = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);

    expect(externalSession).not.toBeNull();
    expect(embedSession).toBeNull();
    expect(veraAfter).toBeNull();

    const externalData = JSON.parse(externalSession!);
    expect(typeof externalData.session_id).toBe("string");

    await expect(page.getByTestId("public-vera-assistant-message")).toBeVisible();
    expect(page.url()).toContain("/t360-external-host-demo");

    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes("favicon") && !e.includes("ERR_CONNECTION_REFUSED"),
    );
    expect(criticalErrors).toEqual([]);
  });
});
