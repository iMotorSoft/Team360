import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

const ENTRY_URL = "/embed/team360-diagnosticador.js";
const MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";
const LOADER_URL = "/embed/team360-diagnosticador-loader.js";
const LOCAL_IMPORT_PATTERN = /(?:\bfrom\s*|\bimport\s*\(?\s*)["']([^"']+)["']/g;
const LOCAL_ORIGIN_PATTERN = /^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?$/;

const MIME_BY_EXTENSION = {
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function digestBytes(bytes) {
  const digest = createHash("sha256").update(bytes).digest();
  return {
    hex: digest.toString("hex"),
    integrity: `sha256-${digest.toString("base64")}`,
  };
}

function readRequired(filePath, hint) {
  try {
    return readFileSync(filePath);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`[embed-dev] ${hint}: ${detail}`);
  }
}

function resolveDistPath(astroDir, publicPath) {
  const distDir = path.join(astroDir, "dist");
  const filePath = path.resolve(distDir, `.${publicPath}`);
  const relativePath = path.relative(distDir, filePath);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    throw new Error(`[embed-dev] Refusing path outside dist: ${publicPath}`);
  }
  return filePath;
}

function collectEntryGraph(astroDir) {
  const assets = new Map();
  const pending = [ENTRY_URL];

  while (pending.length > 0) {
    const publicPath = pending.pop();
    if (!publicPath || assets.has(publicPath)) continue;

    const filePath = resolveDistPath(astroDir, publicPath);
    const bytes = readRequired(
      filePath,
      `required build asset is missing (${publicPath}); run \`pnpm build\``,
    );
    assets.set(publicPath, bytes);

    if (path.extname(filePath) !== ".js") continue;
    const source = bytes.toString("utf-8");
    for (const match of source.matchAll(LOCAL_IMPORT_PATTERN)) {
      const specifier = match[1];
      if (!specifier.startsWith(".") && !specifier.startsWith("/")) continue;
      const dependencyUrl = new URL(specifier, `http://embed.local${publicPath}`).pathname;
      if (!dependencyUrl.startsWith("/_astro/")) {
        throw new Error(`[embed-dev] Unexpected local import outside /_astro: ${dependencyUrl}`);
      }
      pending.push(dependencyUrl);
    }
  }

  return assets;
}

function writeResponse(request, response, publicPath, bytes) {
  const contentType = MIME_BY_EXTENSION[path.extname(publicPath)] ?? "application/octet-stream";
  response.statusCode = 200;
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Length", String(bytes.byteLength));
  response.setHeader("Content-Type", contentType);
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("X-Team360-Embed-Dev-Asset", "1");
  const origin = request.headers.origin;
  if (typeof origin === "string" && LOCAL_ORIGIN_PATTERN.test(origin)) {
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Vary", "Origin");
  }
  response.end(request.method === "HEAD" ? undefined : bytes);
}

export function team360EmbedDevAssets({ astroDir }) {
  const publicManifestPath = path.join(
    astroDir,
    "public/embed/team360-diagnosticador.manifest.json",
  );
  const publicLoaderPath = path.join(
    astroDir,
    "public/embed/team360-diagnosticador-loader.js",
  );
  const distLoaderPath = path.join(
    astroDir,
    "dist/embed/team360-diagnosticador-loader.js",
  );

  const publicManifestBytes = readRequired(publicManifestPath, "public manifest is missing");
  const publicLoaderBytes = readRequired(publicLoaderPath, "public loader is missing");
  const distLoaderBytes = readRequired(distLoaderPath, "dist loader is missing; run `pnpm build`");
  if (!publicLoaderBytes.equals(distLoaderBytes)) {
    throw new Error("[embed-dev] public and dist loaders differ; rebuild before starting DEV");
  }

  const productManifest = JSON.parse(publicManifestBytes.toString("utf-8"));
  const loaderDigest = digestBytes(publicLoaderBytes);
  if (
    productManifest.loader !== LOADER_URL ||
    productManifest.loaderSha256 !== loaderDigest.hex ||
    productManifest.loaderIntegrity !== loaderDigest.integrity
  ) {
    throw new Error("[embed-dev] product loader metadata does not match the protected loader");
  }
  if (productManifest.entry !== ENTRY_URL || productManifest.asset !== ENTRY_URL) {
    throw new Error("[embed-dev] product manifest uses an unexpected entry URL");
  }

  const assets = collectEntryGraph(astroDir);
  const entryDigest = digestBytes(assets.get(ENTRY_URL));
  const devManifestBytes = Buffer.from(
    `${JSON.stringify({
      ...productManifest,
      entrySha256: entryDigest.hex,
      entryIntegrity: entryDigest.integrity,
    }, null, 2)}\n`,
  );

  return {
    name: "team360-embed-dev-assets",
    apply: "serve",
    configureServer(server) {
      server.config.logger.info(
        `[embed-dev] serving ${assets.size} allowlisted build asset(s); entrySha256=${entryDigest.hex}`,
      );

      server.middlewares.use((request, response, next) => {
        if (request.method !== "GET" && request.method !== "HEAD") {
          next();
          return;
        }

        const pathname = new URL(request.url ?? "/", "http://embed.local").pathname;
        if (pathname === MANIFEST_URL) {
          writeResponse(request, response, pathname, devManifestBytes);
          return;
        }

        const assetBytes = assets.get(pathname);
        if (!assetBytes) {
          next();
          return;
        }
        writeResponse(request, response, pathname, assetBytes);
      });
    },
  };
}
