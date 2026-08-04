import { expect, test } from "@playwright/test";
import http from "node:http";
import path from "node:path";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

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

const FIXTURE_SESSION_KEY = "team360.embed.cross_origin.fixture.session.v1";
const VERA_SESSION_KEY = "team360.vera.session.v1";
const ALLOWED_ORIGIN = "http://127.0.0.1:3060";
const DENIED_ORIGIN = "http://127.0.0.1:3061";
const SPEC_DIRNAME = path.dirname(fileURLToPath(import.meta.url));

type ServerHandle = {
  close: () => Promise<void>;
};

async function startFixtureServer(port: number): Promise<ServerHandle> {
  const fixturePath = path.resolve(SPEC_DIRNAME, "fixtures/cross-origin-host/t360-cross-origin-loader.html");
  const html = await readFile(fixturePath, "utf-8");

  const server = http.createServer((req, res) => {
    if (!req.url) {
      res.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
      res.end("Missing URL");
      return;
    }

    const pathname = new URL(req.url, `http://127.0.0.1:${port}`).pathname;
    if (pathname !== "/t360-cross-origin-loader.html") {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    res.writeHead(200, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    });
    res.end(html);
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => resolve());
  });

  return {
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close((error) => {
          if (error) {
            reject(error);
            return;
          }
          resolve();
        });
      }),
  };
}

test.describe("Diagnosticador Cross-Origin Loader Fixture", () => {
  test.setTimeout(120000);

  let allowedServer: ServerHandle | undefined;
  let deniedServer: ServerHandle | undefined;

  test.beforeAll(async () => {
    allowedServer = await startFixtureServer(3060);
    deniedServer = await startFixtureServer(3061);
  });

  test.afterAll(async () => {
    if (deniedServer) {
      await deniedServer.close();
    }
    if (allowedServer) {
      await allowedServer.close();
    }
  });

  test("permite host cross-origin controlado y conserva auth -> turn con Origin real", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const authRequests: Array<{
      headers: Record<string, string>;
      body: Record<string, unknown>;
    }> = [];
    const authResponses: AuthResponse[] = [];
    const turnRequests: Array<{
      headers: Record<string, string>;
      body: Record<string, unknown>;
    }> = [];

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("request", async (request) => {
      if (request.method() !== "POST") return;
      const headers = await request.allHeaders();
      if (request.url().includes("/api/diagnosis/embed/auth")) {
        authRequests.push({
          headers,
          body: request.postDataJSON() as Record<string, unknown>,
        });
      }
      if (request.url().includes("/api/diagnosis/turn")) {
        turnRequests.push({
          headers,
          body: request.postDataJSON() as Record<string, unknown>,
        });
      }
    });
    page.on("response", async (response) => {
      if (!response.url().includes("/api/diagnosis/embed/auth")) return;
      if (response.request().method() !== "POST") return;
      authResponses.push((await response.json()) as AuthResponse);
    });

    await page.goto(`${ALLOWED_ORIGIN}/t360-cross-origin-loader.html`);

    await expect(page.getByTestId("cross-origin-loader-fixture")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Team360 cross-origin loader fixture" })).toBeVisible();
    await expect(page.getByTestId("fixture-host-origin")).toHaveText(ALLOWED_ORIGIN);
    await expect(page.getByTestId("fixture-status")).toHaveText("mounted");
    await expect(page.getByTestId("fixture-loader-version")).toHaveText("experimental-9e");
    await expect(page.getByTestId("fixture-global-version")).toHaveText("experimental-9c");
    await expect(page.getByTestId("fixture-destroy-support")).toHaveText("function");

    const browserApi = await page.evaluate(() => ({
      loaderType: typeof window.Team360DiagnosticadorLoader?.load,
      browserGlobalExists: Boolean(window.Team360Diagnosticador),
      mountType: typeof window.Team360Diagnosticador?.mount,
      assetVersion: window.Team360Diagnosticador?.version ?? null,
      locationOrigin: window.location.origin,
    }));
    expect(browserApi).toEqual({
      loaderType: "function",
      browserGlobalExists: true,
      mountType: "function",
      assetVersion: "experimental-9c",
      locationOrigin: ALLOWED_ORIGIN,
    });

    const fixtureBefore = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraBefore = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(fixtureBefore).toBeNull();
    expect(veraBefore).toBeNull();

    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible();
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();
    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas por WhatsApp");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-assistant-message").waitFor({ state: "visible", timeout: 60000 });

    await expect.poll(() => authRequests.length).toBe(1);
    await expect.poll(() => authResponses.length).toBe(1);
    await expect.poll(() => turnRequests.length).toBe(1);

    const authRequest = authRequests[0];
    const authResponse = authResponses[0];
    const turnRequest = turnRequests[0];
    const authBody = authRequest.body as AuthRequest;
    const turnBody = turnRequest.body as TurnRequest;

    expect(authRequest.headers.origin).toBe(ALLOWED_ORIGIN);
    expect(authBody).toMatchObject({
      client_id: "local_embed_demo",
      message: "Quiero automatizar consultas por WhatsApp",
    });
    expect(typeof authBody.session_id).toBe("string");

    expect(authResponse).toHaveProperty("client_id", "local_embed_demo");
    expect(typeof authResponse.timestamp).toBe("number");
    expect(String(authResponse.signature)).toMatch(/^sha256=[0-9a-f]{64}$/);

    expect(turnRequest.headers.origin).toBe(ALLOWED_ORIGIN);
    expect(turnRequest.headers["x-t360-signature"]).toMatch(/^sha256=[0-9a-f]{64}$/);
    expect(turnBody).toMatchObject({
      client_id: "local_embed_demo",
      message: "Quiero automatizar consultas por WhatsApp",
      session_id: authBody.session_id,
    });
    expect(typeof turnBody.timestamp).toBe("number");

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
    expect(fixtureSession).not.toBeNull();
    expect(veraAfter).toBeNull();

    const pageText = await page.locator("body").innerText();
    expect(pageText).toContain("Team360 cross-origin loader fixture");
    expect(pageText).not.toContain("hmac_secret");
    expect(pageText).not.toContain("organization_code");
    expect(pageText).not.toContain("workspace_code");
    expect(pageText).not.toContain("package_code");
    expect(pageText).not.toContain("knowledge_scope_code");
    expect(pageText).not.toContain("allowed_origins");

    await page.getByTestId("fixture-destroy").click();
    await expect(page.getByTestId("fixture-status")).toHaveText("destroyed");
    await expect(page.getByTestId("diagnosticador-core")).toHaveCount(0);

    await page.getByTestId("fixture-remount").click();
    await expect(page.getByTestId("fixture-status")).toHaveText("mounted");
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();

    const criticalErrors = consoleErrors.filter(
      (error) =>
        !error.includes("favicon") &&
        !error.includes("ERR_CONNECTION_REFUSED") &&
        !error.includes("Failed to load resource: the server responded with a status of 403"),
    );
    expect(criticalErrors).toEqual([]);
  });

  test("rechaza origin cross-origin no permitido sin emitir turn exitoso", async ({ page }) => {
    const consoleErrors: string[] = [];
    let authResponseStatus: number | null = null;
    let authRequestOrigin: string | null = null;
    let turnCalls = 0;

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("request", async (request) => {
      if (request.method() !== "POST") return;
      if (request.url().includes("/api/diagnosis/embed/auth")) {
        authRequestOrigin = (await request.allHeaders()).origin ?? null;
      }
      if (request.url().includes("/api/diagnosis/turn")) {
        turnCalls += 1;
      }
    });
    page.on("response", async (response) => {
      if (!response.url().includes("/api/diagnosis/embed/auth")) return;
      if (response.request().method() !== "POST") return;
      authResponseStatus = response.status();
      await response.body().catch(() => null);
    });

    await page.goto(`${DENIED_ORIGIN}/t360-cross-origin-loader.html`);

    await expect(page.getByTestId("cross-origin-loader-fixture")).toBeVisible();
    await expect(page.getByTestId("fixture-host-origin")).toHaveText(DENIED_ORIGIN);
    await expect(page.getByTestId("fixture-status")).toHaveText("mounted");
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();

    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas por WhatsApp");
    await page.getByTestId("public-vera-submit").click();

    await expect.poll(() => authResponseStatus).toBe(403);
    expect(authRequestOrigin).toBe(DENIED_ORIGIN);
    expect(turnCalls).toBe(0);

    await expect(page.getByTestId("public-vera-error")).toContainText("Vera no está disponible");

    const pageText = await page.locator("body").innerText();
    expect(pageText).not.toContain("hmac_secret");
    expect(pageText).not.toContain("organization_code");
    expect(pageText).not.toContain("workspace_code");
    expect(pageText).not.toContain("package_code");
    expect(pageText).not.toContain("knowledge_scope_code");
    expect(pageText).not.toContain("allowed_origins");

    const criticalErrors = consoleErrors.filter(
      (error) =>
        !error.includes("favicon") &&
        !error.includes("ERR_CONNECTION_REFUSED") &&
        !error.includes("Failed to load resource: the server responded with a status of 403"),
    );
    expect(criticalErrors).toEqual([]);
  });
});
