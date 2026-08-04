import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const ASTRO_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";
const LOADER_URL = "/embed/team360-diagnosticador-loader.js";
const ENTRY_URL = "/embed/team360-diagnosticador.js";

function digestBytes(bytes: Buffer) {
  const digest = createHash("sha256").update(bytes).digest();
  return {
    hex: digest.toString("hex"),
    integrity: `sha256-${digest.toString("base64")}`,
  };
}

test("runtime DEV sirve el entry construido y conserva intacto el contrato productivo", async ({
  request,
}) => {
  const [manifestResponse, loaderResponse, entryResponse, productManifestRaw] = await Promise.all([
    request.get(MANIFEST_URL),
    request.get(LOADER_URL),
    request.get(ENTRY_URL),
    readFile(path.join(ASTRO_DIR, "public/embed/team360-diagnosticador.manifest.json"), "utf-8"),
  ]);

  expect(manifestResponse.status()).toBe(200);
  expect(loaderResponse.status()).toBe(200);
  expect(entryResponse.status()).toBe(200);
  expect(entryResponse.url()).toBe(`http://127.0.0.1:3050${ENTRY_URL}`);
  expect(entryResponse.headers()["content-type"]).toContain("application/javascript");
  expect(entryResponse.headers()["x-team360-embed-dev-asset"]).toBe("1");

  const entryBytes = Buffer.from(await entryResponse.body());
  const entrySource = entryBytes.toString("utf-8");
  expect(entryBytes.byteLength).toBeGreaterThan(0);
  expect(entrySource).toContain("Team360Diagnosticador");
  expect(entrySource.trimStart().startsWith("<!doctype html")).toBe(false);

  const runtimeManifest = await manifestResponse.json();
  const productManifest = JSON.parse(productManifestRaw);
  const entryDigest = digestBytes(entryBytes);
  expect(runtimeManifest).toEqual({
    ...productManifest,
    entrySha256: entryDigest.hex,
    entryIntegrity: entryDigest.integrity,
  });

  const firstImport = entrySource.match(/from["']([^"']+)["']/)?.[1];
  expect(firstImport).toBeTruthy();
  const dependencyUrl = new URL(firstImport!, `http://127.0.0.1:3050${ENTRY_URL}`);
  const dependencyResponse = await request.get(dependencyUrl.toString());
  expect(dependencyResponse.status()).toBe(200);
  expect(dependencyResponse.headers()["content-type"]).toContain("application/javascript");
  expect(dependencyResponse.headers()["x-team360-embed-dev-asset"]).toBe("1");

  const localOriginResponse = await request.get(ENTRY_URL, {
    headers: { Origin: "http://127.0.0.1:3060" },
  });
  expect(localOriginResponse.headers()["access-control-allow-origin"]).toBe(
    "http://127.0.0.1:3060",
  );
  expect(localOriginResponse.headers()["vary"]).toContain("Origin");

  const externalOriginResponse = await request.get(ENTRY_URL, {
    headers: { Origin: "https://untrusted.example" },
  });
  expect(externalOriginResponse.headers()["access-control-allow-origin"]).toBeUndefined();
});
