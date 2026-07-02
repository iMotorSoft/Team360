import { expect, test } from "@playwright/test";

const MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";
const LOADER_URL = "/embed/team360-diagnosticador-loader.js";
const ASSET_URL = "/embed/team360-diagnosticador.js";

test.describe("Diagnosticador Loader Manifest", () => {
  test("publica manifest + loader + asset con contrato minimo e idempotencia", async ({
    page,
    request,
  }) => {
    const manifestResponse = await request.get(MANIFEST_URL);
    expect(manifestResponse.status()).toBe(200);

    const manifestText = await manifestResponse.text();
    const manifest = JSON.parse(manifestText) as Record<string, unknown>;

    expect(manifest).toMatchObject({
      name: "team360-diagnosticador",
      version: "0.9.0-experimental",
      entry: ASSET_URL,
      loader: LOADER_URL,
      format: "browser-global",
      global: "Team360Diagnosticador",
    });

    for (const forbiddenText of [
      "hmac_secret",
      "organization_code",
      "workspace_code",
      "assistant_instance_code",
      "package_code",
      "knowledge_scope_code",
      "allowed_origins",
      "service_code",
      "template_code",
    ]) {
      expect(manifestText).not.toContain(forbiddenText);
    }

    const loaderResponse = await request.get(LOADER_URL);
    expect(loaderResponse.status()).toBe(200);
    const loaderText = await loaderResponse.text();
    expect(loaderText).toContain("Team360DiagnosticadorLoader");
    expect(loaderText).not.toContain("hmac_secret");

    const assetResponse = await request.get(ASSET_URL);
    expect(assetResponse.status()).toBe(200);
    const assetText = await assetResponse.text();
    expect(assetText).toContain("Team360Diagnosticador");
    expect(assetText).not.toContain("hmac_secret");

    await page.goto("/");
    await page.setContent(
      `<!doctype html>
      <html lang="es">
        <body>
          <div id="loader-manifest-root"></div>
          <script type="module" src="${LOADER_URL}"></script>
        </body>
      </html>`,
    );

    await expect
      .poll(() =>
        page.evaluate(() => ({
          hasLoader: Boolean(window.Team360DiagnosticadorLoader),
          loaderType: typeof window.Team360DiagnosticadorLoader?.load,
        })),
      )
      .toEqual({
        hasLoader: true,
        loaderType: "function",
      });

    const runtime = await page.evaluate(async ({ manifestUrl, loaderUrl }) => {
      const beforeScriptCount = document.querySelectorAll(`script[src="${loaderUrl}"]`).length;
      const first = await window.Team360DiagnosticadorLoader!.load({ manifestUrl });
      const middleScriptCount = document.querySelectorAll(`script[src="${loaderUrl}"]`).length;
      const second = await window.Team360DiagnosticadorLoader!.load({ manifestUrl });
      const afterScriptCount = document.querySelectorAll(`script[src="${loaderUrl}"]`).length;

      return {
        loaderVersion: window.Team360DiagnosticadorLoader?.version ?? null,
        defaults: window.Team360DiagnosticadorLoader?.defaults ?? null,
        browserGlobalExists: Boolean(window.Team360Diagnosticador),
        mountType: typeof window.Team360Diagnosticador?.mount,
        assetVersion: window.Team360Diagnosticador?.version ?? null,
        sameGlobalReference: first === second && first === window.Team360Diagnosticador,
        beforeScriptCount,
        middleScriptCount,
        afterScriptCount,
      };
    }, { manifestUrl: MANIFEST_URL, loaderUrl: LOADER_URL });

    expect(runtime).toEqual({
      loaderVersion: "experimental-9e",
      defaults: {
        assetUrl: ASSET_URL,
        manifestUrl: MANIFEST_URL,
      },
      browserGlobalExists: true,
      mountType: "function",
      assetVersion: "experimental-9c",
      sameGlobalReference: true,
      beforeScriptCount: 1,
      middleScriptCount: 1,
      afterScriptCount: 1,
    });
  });

  test("rechaza load() con manifest ausente sin montar el asset", async ({ page }) => {
    await page.route("**/embed/team360-diagnosticador.manifest.json", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json; charset=utf-8",
        body: JSON.stringify({ detail: "missing" }),
      });
    });

    await page.goto("/");
    await page.setContent(
      `<!doctype html>
      <html lang="es">
        <body>
          <div id="loader-manifest-root"></div>
          <script type="module" src="${LOADER_URL}"></script>
        </body>
      </html>`,
    );

    await expect
      .poll(() =>
        page.evaluate(() => ({
          hasLoader: Boolean(window.Team360DiagnosticadorLoader),
          hasGlobal: Boolean(window.Team360Diagnosticador),
        })),
      )
      .toEqual({
        hasLoader: true,
        hasGlobal: false,
      });

    const result = await page.evaluate(async ({ manifestUrl }) => {
      try {
        await window.Team360DiagnosticadorLoader!.load({ manifestUrl });
        return { ok: true, message: "", hasGlobal: Boolean(window.Team360Diagnosticador) };
      } catch (error) {
        return {
          ok: false,
          message: error instanceof Error ? error.message : String(error),
          hasGlobal: Boolean(window.Team360Diagnosticador),
        };
      }
    }, { manifestUrl: MANIFEST_URL });

    expect(result.ok).toBe(false);
    expect(result.message).toContain("manifest request failed with status 404");
    expect(result.hasGlobal).toBe(false);
  });
});
