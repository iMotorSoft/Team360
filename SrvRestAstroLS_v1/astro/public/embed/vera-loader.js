(function (globalObject) {
  var SCRIPT_ATTR_CLIENT_ID = "data-client-id";
  var SCRIPT_ATTR_LOCALE = "data-locale";
  var SCRIPT_ATTR_TARGET = "data-target";
  var SCRIPT_ATTR_ASSISTANT_NAME = "data-assistant-name";
  var SCRIPT_ATTR_COMPACT = "data-compact";
  var SCRIPT_ATTR_INITIAL_MESSAGE = "data-initial-message";
  var API_BASE_PATH = "/api";

  var LOADER_URL = "/embed/team360-diagnosticador-loader.js";
  var MANIFEST_URL = "/embed/team360-diagnosticador.manifest.json";

  if (globalObject.__team360VeraLoader) {
    return;
  }

  var loaderScript = globalObject.document?.currentScript;

  function getAttr(name) {
    if (!loaderScript) return null;
    return loaderScript.getAttribute(name) || null;
  }

  function resolveDefaultBaseUrl() {
    if (typeof globalObject.location?.origin === "string") {
      return globalObject.location.origin;
    }
    return "http://localhost:3050";
  }

  function resolveApiBaseUrl() {
    var scriptSrc = loaderScript?.src || "";
    var origin = globalObject.location?.origin || "http://localhost:3050";

    try {
      var url = new URL(scriptSrc);
      origin = url.origin;
    } catch (_) {}

    return origin + API_BASE_PATH;
  }

  function getTargetElement() {
    var targetAttr = getAttr(SCRIPT_ATTR_TARGET) || "#team360-vera";
    var selector = targetAttr.trim();
    if (!selector) return null;
    try {
      return globalObject.document.querySelector(selector);
    } catch (_) {
      return null;
    }
  }

  function validateTarget(target) {
    if (!target) {
      console.error("[VeraLoader] Target element not found. Check data-target attribute.");
      return false;
    }
    if (!(target instanceof HTMLElement)) {
      console.error("[VeraLoader] Target is not an HTMLElement.");
      return false;
    }
    return true;
  }

  function loadMainLoader() {
    return new Promise(function (resolve, reject) {
      if (globalObject.Team360DiagnosticadorLoader) {
        resolve(globalObject.Team360DiagnosticadorLoader);
        return;
      }

      var script = globalObject.document.createElement("script");
      script.type = "module";
      script.async = true;
      script.src = LOADER_URL;

      script.addEventListener("load", function () {
        if (globalObject.Team360DiagnosticadorLoader) {
          resolve(globalObject.Team360DiagnosticadorLoader);
        } else {
          reject(new Error("[VeraLoader] Loader loaded but Team360DiagnosticadorLoader not found."));
        }
      }, { once: true });

      script.addEventListener("error", function () {
        reject(new Error("[VeraLoader] Failed to load " + LOADER_URL));
      }, { once: true });

      (globalObject.document.head || globalObject.document.body).appendChild(script);
    });
  }

  function init() {
    var clientId = getAttr(SCRIPT_ATTR_CLIENT_ID);
    if (!clientId) {
      console.error("[VeraLoader] data-client-id is required.");
      return;
    }

    var target = getTargetElement();
    if (!validateTarget(target)) return;

    var apiBaseUrl = resolveApiBaseUrl();
    var locale = getAttr(SCRIPT_ATTR_LOCALE) || "es";
    var assistantName = getAttr(SCRIPT_ATTR_ASSISTANT_NAME) || "Vera";
    var compact = getAttr(SCRIPT_ATTR_COMPACT) === "true";
    var initialMessage = getAttr(SCRIPT_ATTR_INITIAL_MESSAGE) || "";

    var sessionKey = "team360.vera.embed." + clientId + ".session.v1";

    loadMainLoader().then(function () {
      return globalObject.Team360DiagnosticadorLoader.load({
        manifestUrl: MANIFEST_URL,
      });
    }).then(function () {
      if (!globalObject.Team360Diagnosticador?.mount) {
        throw new Error("[VeraLoader] Team360Diagnosticador mount API not available.");
      }

      var handle = globalObject.Team360Diagnosticador.mount(target, {
        clientId: clientId,
        apiBaseUrl: apiBaseUrl,
        assistantName: assistantName,
        compact: compact,
        initialMessage: initialMessage,
        sessionStorageKey: sessionKey,
        locale: locale,
      });

      return handle;
    }).catch(function (err) {
      console.error("[VeraLoader]", err.message || String(err));
      target.textContent = "[Vera no disponible en este momento]";
    });
  }

  if (globalObject.document?.readyState === "loading") {
    globalObject.document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  globalObject.__team360VeraLoader = true;
})(window);
