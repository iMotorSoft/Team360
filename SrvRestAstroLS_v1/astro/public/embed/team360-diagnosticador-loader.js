// @ts-nocheck

(function registerTeam360DiagnosticadorLoader(globalObject) {
  const VERSION = "experimental-9e";
  const DEFAULT_ASSET_URL = "/embed/team360-diagnosticador.js";
  const DEFAULT_MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";

  if (globalObject.Team360DiagnosticadorLoader) {
    return;
  }

  let pendingLoad = null;

  async function resolveAssetUrl(options) {
    const assetUrl = typeof options?.assetUrl === "string" ? options.assetUrl.trim() : "";
    if (assetUrl) {
      return assetUrl;
    }

    const manifestUrl =
      typeof options?.manifestUrl === "string" && options.manifestUrl.trim()
        ? options.manifestUrl.trim()
        : DEFAULT_MANIFEST_URL;

    const response = await fetch(manifestUrl, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(
        "Team360DiagnosticadorLoader: manifest request failed with status " +
          response.status +
          ".",
      );
    }

    const manifest = await response.json();
    if (!manifest || typeof manifest.asset !== "string" || !manifest.asset.trim()) {
      throw new Error("Team360DiagnosticadorLoader: manifest asset is missing.");
    }

    return manifest.asset.trim();
  }

  async function load(options) {
    if (globalObject.Team360Diagnosticador?.mount) {
      return globalObject.Team360Diagnosticador;
    }

    if (pendingLoad) {
      return pendingLoad;
    }

    pendingLoad = (async () => {
      const assetUrl = (await resolveAssetUrl(options)) || DEFAULT_ASSET_URL;
      await import(assetUrl);

      if (!globalObject.Team360Diagnosticador?.mount) {
        throw new Error("Team360DiagnosticadorLoader: asset loaded without mount API.");
      }

      return globalObject.Team360Diagnosticador;
    })();

    try {
      return await pendingLoad;
    } finally {
      pendingLoad = null;
    }
  }

  globalObject.Team360DiagnosticadorLoader = Object.freeze({
    version: VERSION,
    load,
    defaults: Object.freeze({
      assetUrl: DEFAULT_ASSET_URL,
      manifestUrl: DEFAULT_MANIFEST_URL,
    }),
  });
})(window);
