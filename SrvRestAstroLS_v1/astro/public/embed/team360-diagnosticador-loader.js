// @ts-nocheck

(function registerTeam360DiagnosticadorLoader(globalObject) {
  const VERSION = "experimental-9e";
  const DEFAULT_ASSET_URL = "/embed/team360-diagnosticador.js";
  const DEFAULT_MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";
  const ENTRY_SCRIPT_ATTRIBUTE = "data-team360-diagnosticador-entry";
  const LOADER_FILE_NAME = "team360-diagnosticador-loader.js";

  if (globalObject.Team360DiagnosticadorLoader) {
    return;
  }

  let pendingLoad = null;

  function resolveUrl(url, baseUrl) {
    return new URL(url, baseUrl).toString();
  }

  function resolveDocumentBaseUrl() {
    return globalObject.document?.baseURI || globalObject.location?.href || "http://localhost/";
  }

  function resolveLoaderBaseUrl() {
    const documentRef = globalObject.document;
    const currentScriptSrc =
      typeof documentRef?.currentScript?.src === "string" ? documentRef.currentScript.src.trim() : "";
    if (currentScriptSrc) {
      return currentScriptSrc;
    }

    const scripts = Array.from(documentRef?.querySelectorAll?.("script[src]") || []);
    for (let index = scripts.length - 1; index >= 0; index -= 1) {
      const scriptSrc = typeof scripts[index]?.src === "string" ? scripts[index].src.trim() : "";
      if (scriptSrc && scriptSrc.includes(LOADER_FILE_NAME)) {
        return scriptSrc;
      }
    }

    return resolveDocumentBaseUrl();
  }

  function resolveManifestUrl(options) {
    const manifestUrl =
      typeof options?.manifestUrl === "string" && options.manifestUrl.trim()
        ? options.manifestUrl.trim()
        : DEFAULT_MANIFEST_URL;
    return resolveUrl(manifestUrl, resolveLoaderBaseUrl());
  }

  function resolveExplicitAssetUrl(options) {
    const assetUrl = typeof options?.assetUrl === "string" ? options.assetUrl.trim() : "";
    if (!assetUrl) {
      return "";
    }
    return resolveUrl(assetUrl, resolveDocumentBaseUrl());
  }

  async function fetchManifest(options) {
    const manifestUrl = resolveManifestUrl(options);

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

    return {
      manifestUrl,
      manifest: await response.json(),
    };
  }

  async function resolveEntryConfig(options) {
    const verifyEntryIntegrity = options?.verifyEntryIntegrity === true;
    const explicitAssetUrl = resolveExplicitAssetUrl(options);

    if (!explicitAssetUrl || verifyEntryIntegrity) {
      const { manifestUrl, manifest } = await fetchManifest(options);
      const manifestAsset =
        typeof manifest?.asset === "string" && manifest.asset.trim()
          ? manifest.asset.trim()
          : typeof manifest?.entry === "string" && manifest.entry.trim()
            ? manifest.entry.trim()
            : "";
      const resolvedManifestAssetUrl = manifestAsset
        ? resolveUrl(manifestAsset, manifestUrl)
        : "";
      const entryIntegrity =
        typeof manifest?.entryIntegrity === "string" && manifest.entryIntegrity.trim()
          ? manifest.entryIntegrity.trim()
          : "";

      if (!resolvedManifestAssetUrl) {
        throw new Error("Team360DiagnosticadorLoader: manifest asset is missing.");
      }

      if (explicitAssetUrl && explicitAssetUrl !== resolvedManifestAssetUrl) {
        throw new Error(
          "Team360DiagnosticadorLoader: assetUrl must match manifest entry when verifyEntryIntegrity is enabled.",
        );
      }

      if (verifyEntryIntegrity && !entryIntegrity) {
        throw new Error(
          "Team360DiagnosticadorLoader: entry integrity is required when verifyEntryIntegrity=true.",
        );
      }

      return {
        assetUrl: explicitAssetUrl || resolvedManifestAssetUrl,
        entryIntegrity: verifyEntryIntegrity ? entryIntegrity : "",
      };
    }

    return {
      assetUrl: explicitAssetUrl,
      entryIntegrity: "",
    };
  }

  function removeDynamicEntryScripts() {
    const scripts = globalObject.document?.querySelectorAll(`script[${ENTRY_SCRIPT_ATTRIBUTE}="true"]`);
    if (!scripts?.length) {
      return;
    }
    scripts.forEach((script) => script.remove());
  }

  function loadEntryScript(assetUrl, entryIntegrity) {
    return new Promise((resolve, reject) => {
      const documentRef = globalObject.document;
      if (!documentRef?.createElement || !documentRef.head || !documentRef.body) {
        reject(new Error("Team360DiagnosticadorLoader: document is not available."));
        return;
      }

      removeDynamicEntryScripts();

      const script = documentRef.createElement("script");
      script.type = "module";
      script.async = true;
      script.src = assetUrl;
      script.setAttribute(ENTRY_SCRIPT_ATTRIBUTE, "true");

      if (entryIntegrity) {
        script.integrity = entryIntegrity;
        script.crossOrigin = "anonymous";
      }

      script.addEventListener(
        "load",
        () => {
          resolve();
        },
        { once: true },
      );
      script.addEventListener(
        "error",
        () => {
          script.remove();
          reject(
            new Error(
              entryIntegrity
                ? "Team360DiagnosticadorLoader: entry script failed to load or failed integrity verification."
                : "Team360DiagnosticadorLoader: entry script failed to load.",
            ),
          );
        },
        { once: true },
      );

      (documentRef.head || documentRef.body).appendChild(script);
    });
  }

  async function load(options) {
    if (globalObject.Team360Diagnosticador?.mount) {
      return globalObject.Team360Diagnosticador;
    }

    if (pendingLoad) {
      return pendingLoad;
    }

    pendingLoad = (async () => {
      const { assetUrl, entryIntegrity } =
        (await resolveEntryConfig(options)) || { assetUrl: DEFAULT_ASSET_URL, entryIntegrity: "" };
      await loadEntryScript(assetUrl || DEFAULT_ASSET_URL, entryIntegrity);

      if (!globalObject.Team360Diagnosticador?.mount) {
        removeDynamicEntryScripts();
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
