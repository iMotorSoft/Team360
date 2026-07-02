import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ASTRO_DIR = path.resolve(SCRIPT_DIR, "..");
const PUBLIC_MANIFEST_PATH = path.join(
  ASTRO_DIR,
  "public/embed/team360-diagnosticador.manifest.json",
);
const PUBLIC_LOADER_PATH = path.join(
  ASTRO_DIR,
  "public/embed/team360-diagnosticador-loader.js",
);
const DIST_MANIFEST_PATH = path.join(
  ASTRO_DIR,
  "dist/embed/team360-diagnosticador.manifest.json",
);
const DIST_LOADER_PATH = path.join(
  ASTRO_DIR,
  "dist/embed/team360-diagnosticador-loader.js",
);
const DIST_ENTRY_PATH = path.join(
  ASTRO_DIR,
  "dist/embed/team360-diagnosticador.js",
);

const ORDERED_KEYS = [
  "name",
  "version",
  "channel",
  "asset",
  "entry",
  "entrySha256",
  "entryIntegrity",
  "loader",
  "loaderSha256",
  "loaderIntegrity",
  "format",
  "global",
  "api",
  "requires",
];

function digestBytes(buffer) {
  const digest = createHash("sha256").update(buffer).digest();
  return {
    hex: digest.toString("hex"),
    integrity: `sha256-${digest.toString("base64")}`,
  };
}

function orderManifest(manifest) {
  const ordered = {};

  for (const key of ORDERED_KEYS) {
    if (key in manifest) {
      ordered[key] = manifest[key];
    }
  }

  for (const [key, value] of Object.entries(manifest)) {
    if (!(key in ordered)) {
      ordered[key] = value;
    }
  }

  return ordered;
}

async function readRequiredFile(filePath, missingMessage) {
  try {
    return await readFile(filePath);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
      throw new Error(missingMessage);
    }
    throw error;
  }
}

async function main() {
  const [publicManifestRaw, publicLoaderRaw, distLoaderRaw, distEntryRaw] = await Promise.all([
    readRequiredFile(
      PUBLIC_MANIFEST_PATH,
      "Embed manifest source not found in public/embed.",
    ),
    readRequiredFile(
      PUBLIC_LOADER_PATH,
      "Embed loader source not found in public/embed.",
    ),
    readRequiredFile(
      DIST_LOADER_PATH,
      "Embed dist loader not found. Run `corepack pnpm build` first.",
    ),
    readRequiredFile(
      DIST_ENTRY_PATH,
      "Embed dist entry not found. Run `corepack pnpm build` first.",
    ),
  ]);

  if (!publicLoaderRaw.equals(distLoaderRaw)) {
    throw new Error(
      "Embed loader source and dist loader differ. Rebuild before updating integrity.",
    );
  }

  const manifest = JSON.parse(publicManifestRaw.toString("utf-8"));
  const entryDigest = digestBytes(distEntryRaw);
  const loaderDigest = digestBytes(publicLoaderRaw);

  const nextManifest = orderManifest({
    ...manifest,
    entrySha256: entryDigest.hex,
    entryIntegrity: entryDigest.integrity,
    loaderSha256: loaderDigest.hex,
    loaderIntegrity: loaderDigest.integrity,
  });

  const formattedManifest = `${JSON.stringify(nextManifest, null, 2)}\n`;

  await Promise.all([
    writeFile(PUBLIC_MANIFEST_PATH, formattedManifest, "utf-8"),
    writeFile(DIST_MANIFEST_PATH, formattedManifest, "utf-8"),
  ]);

  console.log(`entrySha256=${entryDigest.hex}`);
  console.log(`entryIntegrity=${entryDigest.integrity}`);
  console.log(`loaderSha256=${loaderDigest.hex}`);
  console.log(`loaderIntegrity=${loaderDigest.integrity}`);
}

main().catch((error) => {
  console.error(
    error instanceof Error ? error.message : String(error),
  );
  process.exitCode = 1;
});
