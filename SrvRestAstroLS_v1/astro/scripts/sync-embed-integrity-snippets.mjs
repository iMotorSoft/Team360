import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ASTRO_DIR = path.resolve(SCRIPT_DIR, "..");
const MANIFEST_PATH = path.join(
  ASTRO_DIR,
  "public/embed/team360-diagnosticador.manifest.json",
);
const FIXTURE_PATH = path.join(
  ASTRO_DIR,
  "e2e/fixtures/cross-origin-host/t360-cross-origin-integrity-loader.html",
);

const LOADER_SNIPPET_BLOCK = {
  start: "<!-- team360-sync: loader-integrity-snippet:start -->",
  end: "<!-- team360-sync: loader-integrity-snippet:end -->",
};

const LOADER_RUNTIME_BLOCK = {
  start: "<!-- team360-sync: loader-integrity-runtime:start -->",
  end: "<!-- team360-sync: loader-integrity-runtime:end -->",
};

function getRequiredString(value, fieldName) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Embed manifest is missing required field: ${fieldName}`);
  }
  return value.trim();
}

function replaceIntegrityInsideBlock(sourceText, block, nextIntegrity) {
  const blockStart = sourceText.indexOf(block.start);
  const blockEnd = sourceText.indexOf(block.end);

  if (blockStart === -1 || blockEnd === -1 || blockEnd <= blockStart) {
    throw new Error(
      `Sync marker not found for block ${block.start} -> ${block.end}.`,
    );
  }

  const contentStart = blockStart + block.start.length;
  const content = sourceText.slice(contentStart, blockEnd);

  if (!content.includes('data-team360-integrity-source="manifest.loaderIntegrity"')) {
    throw new Error(
      `Block ${block.start} does not declare data-team360-integrity-source="manifest.loaderIntegrity".`,
    );
  }

  const matches = [...content.matchAll(/integrity="([^"]+)"/g)];
  if (matches.length !== 1) {
    throw new Error(
      `Block ${block.start} must contain exactly one integrity attribute; found ${matches.length}.`,
    );
  }

  const currentIntegrity = matches[0][1];
  const nextContent = content.replace(
    /integrity="([^"]+)"/,
    `integrity="${nextIntegrity}"`,
  );

  return {
    changed: currentIntegrity !== nextIntegrity,
    currentIntegrity,
    nextSource: `${sourceText.slice(0, contentStart)}${nextContent}${sourceText.slice(blockEnd)}`,
  };
}

async function main() {
  const manifest = JSON.parse(await readFile(MANIFEST_PATH, "utf-8"));
  const loaderIntegrity = getRequiredString(
    manifest.loaderIntegrity,
    "loaderIntegrity",
  );
  getRequiredString(manifest.entryIntegrity, "entryIntegrity");

  const fixtureSource = await readFile(FIXTURE_PATH, "utf-8");

  let nextSource = fixtureSource;
  const snippetUpdate = replaceIntegrityInsideBlock(
    nextSource,
    LOADER_SNIPPET_BLOCK,
    loaderIntegrity,
  );
  nextSource = snippetUpdate.nextSource;

  const runtimeUpdate = replaceIntegrityInsideBlock(
    nextSource,
    LOADER_RUNTIME_BLOCK,
    loaderIntegrity,
  );
  nextSource = runtimeUpdate.nextSource;

  await writeFile(FIXTURE_PATH, nextSource, "utf-8");

  console.log(`manifest.loaderIntegrity=${loaderIntegrity}`);
  console.log(
    `fixture snippet integrity ${snippetUpdate.changed ? "updated" : "already-synced"}`,
  );
  console.log(
    `fixture runtime integrity ${runtimeUpdate.changed ? "updated" : "already-synced"}`,
  );
  console.log(`synced file=${path.relative(ASTRO_DIR, FIXTURE_PATH)}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
