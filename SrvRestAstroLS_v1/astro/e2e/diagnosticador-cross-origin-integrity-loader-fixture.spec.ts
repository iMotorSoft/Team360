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

type EmbedManifest = {
  entryIntegrity: string;
  loaderIntegrity: string;
  loader: string;
  entry: string;
};

type ServerHandle = {
  close: () => Promise<void>;
};

const FIXTURE_SESSION_KEY = "team360.embed.cross_origin.integrity.fixture.session.v1";
const VERA_SESSION_KEY = "team360.vera.session.v1";
const ALLOWED_ORIGIN = "http://127.0.0.1:3060";
const LOADER_URL = "http://127.0.0.1:3050/embed/team360-diagnosticador-loader.js";
const ASSET_PATHNAME = "/embed/team360-diagnosticador.js";
const GOOD_FIXTURE_PATH = "/t360-cross-origin-integrity-loader.html";
const BAD_LOADER_FIXTURE_PATH = "/t360-cross-origin-integrity-loader-invalid.html";
const BAD_LOADER_INTEGRITY = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
const SPEC_DIRNAME = path.dirname(fileURLToPath(import.meta.url));
const SNIPPET_SYNC_BLOCK = {
  start: "<!-- team360-sync: loader-integrity-snippet:start -->",
  end: "<!-- team360-sync: loader-integrity-snippet:end -->",
};
const RUNTIME_SYNC_BLOCK = {
  start: "<!-- team360-sync: loader-integrity-runtime:start -->",
  end: "<!-- team360-sync: loader-integrity-runtime:end -->",
};

function hasForbiddenText(text: string) {
  return [
    "hmac_secret",
    "organization_code",
    "workspace_code",
    "package_code",
    "knowledge_scope_code",
    "allowed_origins",
    "assistant_instance_code",
    "service_code",
    "template_code",
  ].some((term) => text.includes(term));
}

function extractSyncBlock(source: string, block: { start: string; end: string }) {
  const blockStart = source.indexOf(block.start);
  const blockEnd = source.indexOf(block.end);
  expect(blockStart).toBeGreaterThanOrEqual(0);
  expect(blockEnd).toBeGreaterThan(blockStart);
  return source.slice(blockStart + block.start.length, blockEnd);
}

function readIntegrityFromBlock(source: string, block: { start: string; end: string }) {
  const content = extractSyncBlock(source, block);
  expect(content).toContain('data-team360-integrity-source="manifest.loaderIntegrity"');
  const match = content.match(/integrity="([^"]+)"/);
  expect(match?.[1]).toBeTruthy();
  return match![1];
}

async function readFixtureTemplate() {
  const fixturePath = path.resolve(
    SPEC_DIRNAME,
    "fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html",
  );
  return readFile(fixturePath, "utf-8");
}

async function readManifestFile() {
  const manifestPath = path.resolve(
    SPEC_DIRNAME,
    "../public/embed/team360-diagnosticador.manifest.json",
  );
  return JSON.parse(await readFile(manifestPath, "utf-8")) as EmbedManifest;
}

async function startFixtureServer(port: number): Promise<ServerHandle> {
  const template = await readFixtureTemplate();
  const manifest = await readManifestFile();
  const snippetIntegrity = readIntegrityFromBlock(template, SNIPPET_SYNC_BLOCK);
  const runtimeIntegrity = readIntegrityFromBlock(template, RUNTIME_SYNC_BLOCK);

  expect(template).not.toContain("__TEAM360_LOADER_INTEGRITY__");
  expect(snippetIntegrity).toBe(manifest.loaderIntegrity);
  expect(runtimeIntegrity).toBe(manifest.loaderIntegrity);

  const server = http.createServer((req, res) => {
    if (!req.url) {
      res.writeHead(400, { "content-type": "text/plain; charset=utf-8" });
      res.end("Missing URL");
      return;
    }

    const pathname = new URL(req.url, `http://127.0.0.1:${port}`).pathname;
    if (pathname !== GOOD_FIXTURE_PATH && pathname !== BAD_LOADER_FIXTURE_PATH) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    const loaderIntegrity =
      pathname === BAD_LOADER_FIXTURE_PATH ? BAD_LOADER_INTEGRITY : manifest.loaderIntegrity;
    const html =
      pathname === BAD_LOADER_FIXTURE_PATH
        ? template.replaceAll(manifest.loaderIntegrity, loaderIntegrity)
        : template;

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

test.describe("Diagnosticador Cross-Origin Integrity Loader Fixture", () => {
  test.setTimeout(120000);

  let server: ServerHandle | undefined;

  test.beforeAll(async () => {
    server = await startFixtureServer(3060);
  });

  test.afterAll(async () => {
    if (server) {
      await server.close();
    }
  });

  test("mantiene el fixture 9H sincronizado con manifest.loaderIntegrity", async ({
    request,
  }) => {
    const manifestResponse = await request.get("/embed/team360-diagnosticador.manifest.json");
    expect(manifestResponse.status()).toBe(200);
    const manifest = (await manifestResponse.json()) as EmbedManifest;
    const fixtureHtml = await readFixtureTemplate();

    expect(readIntegrityFromBlock(fixtureHtml, SNIPPET_SYNC_BLOCK)).toBe(
      manifest.loaderIntegrity,
    );
    expect(readIntegrityFromBlock(fixtureHtml, RUNTIME_SYNC_BLOCK)).toBe(
      manifest.loaderIntegrity,
    );
    expect(fixtureHtml).not.toContain("__TEAM360_LOADER_INTEGRITY__");
  });

  test("carga host externo con loaderIntegrity + verifyEntryIntegrity y conserva auth -> turn", async ({
    page,
    request,
  }) => {
    const consoleErrors: string[] = [];
    const authRequests: Array<{ headers: Record<string, string>; body: Record<string, unknown> }> = [];
    const authResponses: AuthResponse[] = [];
    const turnRequests: Array<{ headers: Record<string, string>; body: Record<string, unknown> }> = [];
    const manifest = (await request.get("/embed/team360-diagnosticador.manifest.json")).json() as Promise<EmbedManifest>;

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("request", async (playwrightRequest) => {
      if (playwrightRequest.method() !== "POST") return;
      const headers = await playwrightRequest.allHeaders();
      if (playwrightRequest.url().includes("/api/diagnosis/embed/auth")) {
        authRequests.push({
          headers,
          body: playwrightRequest.postDataJSON() as Record<string, unknown>,
        });
      }
      if (playwrightRequest.url().includes("/api/diagnosis/turn")) {
        turnRequests.push({
          headers,
          body: playwrightRequest.postDataJSON() as Record<string, unknown>,
        });
      }
    });
    page.on("response", async (response) => {
      if (!response.url().includes("/api/diagnosis/embed/auth")) return;
      if (response.request().method() !== "POST") return;
      authResponses.push((await response.json()) as AuthResponse);
    });

    await page.goto(`${ALLOWED_ORIGIN}${GOOD_FIXTURE_PATH}`);

    const manifestJson = await manifest;

    await expect(page.getByTestId("cross-origin-integrity-loader-fixture")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Team360 cross-origin integrity loader fixture" }),
    ).toBeVisible();
    await expect(page.getByTestId("fixture-host-origin")).toHaveText(ALLOWED_ORIGIN);
    await expect(page.getByTestId("fixture-status")).toHaveText("mounted");
    await expect(page.getByTestId("fixture-verify-entry-integrity")).toHaveText("enabled");
    await expect(page.getByTestId("fixture-loader-integrity")).toHaveText(manifestJson.loaderIntegrity);
    await expect(page.getByTestId("fixture-loader-version")).toHaveText("experimental-9e");
    await expect(page.getByTestId("fixture-global-version")).toHaveText("experimental-9c");

    const browserState = await page.evaluate((loaderUrl) => {
      const fixtureWindow = window as Window & {
        __team360CrossOriginIntegrityFixture?: { getState?: () => unknown };
      };
      const loaderScript = Array.from(document.querySelectorAll("script")).find(
        (script) => (script as HTMLScriptElement).src === loaderUrl,
      ) as HTMLScriptElement | undefined;
      const entryScript = document.querySelector(
        'script[data-team360-diagnosticador-entry="true"]',
      ) as HTMLScriptElement | null;

      return {
        fixtureState: fixtureWindow.__team360CrossOriginIntegrityFixture?.getState?.() ?? null,
        hasLoader: typeof window.Team360DiagnosticadorLoader?.load === "function",
        hasGlobal: typeof window.Team360Diagnosticador?.mount === "function",
        loaderScript: loaderScript
          ? {
              integrity: loaderScript.getAttribute("integrity"),
              crossOriginAttr: loaderScript.getAttribute("crossorigin"),
              crossOriginProp: loaderScript.crossOrigin,
            }
          : null,
        entryScript: entryScript
          ? {
              pathname: new URL(entryScript.src).pathname,
              integrity: entryScript.getAttribute("integrity"),
              crossOriginAttr: entryScript.getAttribute("crossorigin"),
              crossOriginProp: entryScript.crossOrigin,
            }
          : null,
      };
    }, LOADER_URL);

    expect(browserState.fixtureState).toMatchObject({
      status: "mounted",
      lastAction: "mount",
      verifyEntryIntegrity: true,
      mounted: true,
      hasLoader: true,
      hasGlobal: true,
    });
    expect(browserState.hasLoader).toBe(true);
    expect(browserState.hasGlobal).toBe(true);
    expect(browserState.loaderScript).toEqual({
      integrity: manifestJson.loaderIntegrity,
      crossOriginAttr: "anonymous",
      crossOriginProp: "anonymous",
    });
    expect(browserState.entryScript).toEqual({
      pathname: ASSET_PATHNAME,
      integrity: manifestJson.entryIntegrity,
      crossOriginAttr: "anonymous",
      crossOriginProp: "anonymous",
    });

    const fixtureBefore = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraBefore = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(fixtureBefore).toBeNull();
    expect(veraBefore).toBeNull();

    await expect(page.getByTestId("vera-embed-wrapper")).toBeVisible();
    await expect(page.getByTestId("diagnosticador-core")).toBeVisible();

    await page.getByTestId("public-vera-text").fill("Quiero automatizar consultas por WhatsApp");
    await page.getByTestId("public-vera-submit").click();
    await page.getByTestId("public-vera-assistant-message").last().waitFor({
      state: "visible",
      timeout: 60000,
    });

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

    const assistantText = await page.getByTestId("public-vera-assistant-message").last().innerText();
    expect(assistantText.trim().length).toBeGreaterThan(0);

    const fixtureSession = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraAfter = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(fixtureSession).not.toBeNull();
    expect(veraAfter).toBeNull();

    const pageText = await page.locator("body").innerText();
    expect(pageText).toContain("Team360 cross-origin integrity loader fixture");
    expect(hasForbiddenText(pageText)).toBe(false);

    const criticalErrors = consoleErrors.filter(
      (error) => !error.includes("favicon") && !hasForbiddenText(error),
    );
    expect(criticalErrors).toEqual([]);
  });

  test("bloquea el loader cuando loaderIntegrity no coincide y no llega a auth -> turn", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    let authCalls = 0;
    let turnCalls = 0;

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("request", (playwrightRequest) => {
      if (playwrightRequest.method() !== "POST") return;
      if (playwrightRequest.url().includes("/api/diagnosis/embed/auth")) authCalls += 1;
      if (playwrightRequest.url().includes("/api/diagnosis/turn")) turnCalls += 1;
    });

    await page.goto(`${ALLOWED_ORIGIN}${BAD_LOADER_FIXTURE_PATH}`);

    await expect(page.getByTestId("cross-origin-integrity-loader-fixture")).toBeVisible();
    await expect(page.getByTestId("fixture-host-origin")).toHaveText(ALLOWED_ORIGIN);
    await expect(page.getByTestId("fixture-status")).toHaveText("loader-missing");
    await expect(page.getByTestId("fixture-error")).toContainText("loader script is unavailable");

    const browserState = await page.evaluate((loaderUrl) => {
      const fixtureWindow = window as Window & {
        __team360CrossOriginIntegrityFixture?: { getState?: () => unknown };
      };
      const loaderScript = Array.from(document.querySelectorAll("script")).find(
        (script) => (script as HTMLScriptElement).src === loaderUrl,
      ) as HTMLScriptElement | undefined;
      return {
        fixtureState: fixtureWindow.__team360CrossOriginIntegrityFixture?.getState?.() ?? null,
        hasLoader: typeof window.Team360DiagnosticadorLoader?.load === "function",
        hasGlobal: Boolean(window.Team360Diagnosticador?.mount),
        loaderScript: loaderScript
          ? {
              integrity: loaderScript.getAttribute("integrity"),
              crossOriginAttr: loaderScript.getAttribute("crossorigin"),
              crossOriginProp: loaderScript.crossOrigin,
            }
          : null,
        datasetError: document.body.dataset.team360IntegrityError || "",
      };
    }, LOADER_URL);

    expect(browserState.fixtureState).toMatchObject({
      status: "loader-missing",
      lastAction: "load-error",
      mounted: false,
      verifyEntryIntegrity: true,
      hasLoader: false,
      hasGlobal: false,
    });
    expect(browserState.hasLoader).toBe(false);
    expect(browserState.hasGlobal).toBe(false);
    expect(browserState.loaderScript).toEqual({
      integrity: BAD_LOADER_INTEGRITY,
      crossOriginAttr: "anonymous",
      crossOriginProp: "anonymous",
    });
    expect(browserState.datasetError).toContain("loader script is unavailable");

    expect(authCalls).toBe(0);
    expect(turnCalls).toBe(0);

    const fixtureSession = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraSession = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(fixtureSession).toBeNull();
    expect(veraSession).toBeNull();

    const pageText = await page.locator("body").innerText();
    expect(hasForbiddenText(pageText)).toBe(false);
    expect(consoleErrors.every((error) => !hasForbiddenText(error))).toBe(true);
  });

  test("rechaza verifyEntryIntegrity cuando el manifest entrega entryIntegrity invalido", async ({
    page,
    request,
  }) => {
    const consoleErrors: string[] = [];
    let authCalls = 0;
    let turnCalls = 0;
    const manifest = (await request.get("/embed/team360-diagnosticador.manifest.json")).json() as Promise<EmbedManifest>;

    await page.route("**/embed/team360-diagnosticador.manifest.json", async (route) => {
      const manifestJson = await manifest;
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify({
          ...manifestJson,
          entryIntegrity: "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        }),
      });
    });

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.on("request", (playwrightRequest) => {
      if (playwrightRequest.method() !== "POST") return;
      if (playwrightRequest.url().includes("/api/diagnosis/embed/auth")) authCalls += 1;
      if (playwrightRequest.url().includes("/api/diagnosis/turn")) turnCalls += 1;
    });

    await page.goto(`${ALLOWED_ORIGIN}${GOOD_FIXTURE_PATH}`);

    await expect(page.getByTestId("cross-origin-integrity-loader-fixture")).toBeVisible();
    await expect(page.getByTestId("fixture-status")).toHaveText("error");
    await expect(page.getByTestId("fixture-error")).toContainText("failed integrity verification");
    await expect(page.getByTestId("diagnosticador-core")).toHaveCount(0);

    const browserState = await page.evaluate((loaderUrl) => {
      const fixtureWindow = window as Window & {
        __team360CrossOriginIntegrityFixture?: { getState?: () => unknown };
      };
      const loaderScript = Array.from(document.querySelectorAll("script")).find(
        (script) => (script as HTMLScriptElement).src === loaderUrl,
      ) as HTMLScriptElement | undefined;
      return {
        fixtureState: fixtureWindow.__team360CrossOriginIntegrityFixture?.getState?.() ?? null,
        hasLoader: typeof window.Team360DiagnosticadorLoader?.load === "function",
        hasGlobal: Boolean(window.Team360Diagnosticador?.mount),
        entryScripts: document.querySelectorAll('script[data-team360-diagnosticador-entry="true"]').length,
        datasetError: document.body.dataset.team360IntegrityError || "",
        loaderScript: loaderScript
          ? {
              crossOriginAttr: loaderScript.getAttribute("crossorigin"),
              crossOriginProp: loaderScript.crossOrigin,
            }
          : null,
      };
    }, LOADER_URL);

    expect(browserState.fixtureState).toMatchObject({
      status: "error",
      lastAction: "load-error",
      mounted: false,
      verifyEntryIntegrity: true,
      hasLoader: true,
      hasGlobal: false,
    });
    expect(browserState.hasLoader).toBe(true);
    expect(browserState.hasGlobal).toBe(false);
    expect(browserState.entryScripts).toBe(0);
    expect(browserState.datasetError).toContain("failed integrity verification");
    expect(browserState.loaderScript).toEqual({
      crossOriginAttr: "anonymous",
      crossOriginProp: "anonymous",
    });

    expect(authCalls).toBe(0);
    expect(turnCalls).toBe(0);

    const fixtureSession = await page.evaluate((key) => sessionStorage.getItem(key), FIXTURE_SESSION_KEY);
    const veraSession = await page.evaluate((key) => sessionStorage.getItem(key), VERA_SESSION_KEY);
    expect(fixtureSession).toBeNull();
    expect(veraSession).toBeNull();

    const pageText = await page.locator("body").innerText();
    expect(hasForbiddenText(pageText)).toBe(false);

    const filteredErrors = consoleErrors.filter((error) => !hasForbiddenText(error));
    expect(filteredErrors.join("\n")).not.toContain("hmac_secret");
  });
});
