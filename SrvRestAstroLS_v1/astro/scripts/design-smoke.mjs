import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const baseUrl = process.env.TEAM360_DEMO_URL ?? "http://127.0.0.1:4321";
const chromiumBin = process.env.CHROMIUM_BIN ?? "/snap/bin/chromium";
const screenshotDir = path.resolve(process.cwd(), "../docs/design-review/screenshots");
const profileDir = await mkdtemp(path.join(os.tmpdir(), "team360-design-smoke-"));
const chromiumLog = [];

const routes = {
  home: "/",
  login: "/login",
  selectWorkspace: "/select-workspace",
  ownerDashboard: "/w/ws-team360-control",
  ownerServices: "/w/ws-team360-control/services",
  ownerReports: "/w/ws-team360-control/reports",
  ownerAlerts: "/w/ws-team360-control/alerts",
  ownerTasks: "/w/ws-team360-control/tasks",
  ownerWorkers: "/w/ws-team360-control/workers",
  ownerRuns: "/w/ws-team360-control/runs",
  partnerDashboard: "/w/ws-mama-mia-israel?profile=partner_admin",
  clientDashboard: "/w/ws-netzaj-marketplace?profile=client_admin",
  clientServices: "/w/ws-netzaj-marketplace/services?profile=client_admin",
  clientDetail: "/w/ws-netzaj-marketplace/services/svc-netzaj-questions?profile=client_admin",
  clientReports: "/w/ws-netzaj-marketplace/reports?profile=client_admin",
  clientAlerts: "/w/ws-netzaj-marketplace/alerts?profile=client_admin",
  clientWorkers: "/w/ws-netzaj-marketplace/workers?profile=client_admin",
  clientRuns: "/w/ws-netzaj-marketplace/runs?profile=client_admin",
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Request failed: ${response.status} ${url}`);
  return response.json();
}

async function waitFor(check, message, timeout = 8_000) {
  const startedAt = Date.now();
  let lastError;

  while (Date.now() - startedAt < timeout) {
    try {
      if (await check()) return;
    } catch (error) {
      lastError = error;
    }
    await delay(100);
  }

  throw new Error(`${message}${lastError ? `: ${lastError.message}` : ""}`);
}

function createCdpClient(webSocketUrl) {
  const socket = new WebSocket(webSocketUrl);
  const pending = new Map();
  const listeners = new Map();
  let sequence = 0;

  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(data);

    if (message.id) {
      const request = pending.get(message.id);
      if (!request) return;
      pending.delete(message.id);
      if (message.error) request.reject(new Error(message.error.message));
      else request.resolve(message.result);
      return;
    }

    for (const listener of listeners.get(message.method) ?? []) {
      listener(message.params);
    }
  });

  return {
    async ready() {
      if (socket.readyState === WebSocket.OPEN) return;
      await new Promise((resolve, reject) => {
        socket.addEventListener("open", resolve, { once: true });
        socket.addEventListener("error", reject, { once: true });
      });
    },
    send(method, params = {}) {
      const id = ++sequence;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    },
    waitEvent(method, timeout = 5_000) {
      return new Promise((resolve, reject) => {
        const callbacks = listeners.get(method) ?? [];
        const onEvent = (params) => {
          clearTimeout(timer);
          listeners.set(method, callbacks.filter((callback) => callback !== onEvent));
          resolve(params);
        };
        const timer = setTimeout(() => {
          listeners.set(method, callbacks.filter((callback) => callback !== onEvent));
          reject(new Error(`Timed out waiting for ${method}`));
        }, timeout);

        callbacks.push(onEvent);
        listeners.set(method, callbacks);
      });
    },
    close() {
      socket.close();
    },
  };
}

const debugPort = await getFreePort();
const chromium = spawn(
  chromiumBin,
  [
    "--headless=new",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-sandbox",
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${profileDir}`,
    "about:blank",
  ],
  { stdio: ["ignore", "ignore", "pipe"] },
);

chromium.stderr.on("data", (chunk) => {
  chromiumLog.push(chunk.toString());
  if (chromiumLog.length > 20) chromiumLog.shift();
});

let cdp;

try {
  await mkdir(screenshotDir, { recursive: true });

  await waitFor(async () => {
    const response = await fetch(`${baseUrl}/`);
    return response.ok;
  }, `Demo is not available at ${baseUrl}`);

  await waitFor(async () => {
    const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
    return response.ok;
  }, "Chromium CDP endpoint did not start");

  const target = await fetchJson(`http://127.0.0.1:${debugPort}/json/new?about:blank`, { method: "PUT" });
  cdp = createCdpClient(target.webSocketDebuggerUrl);
  await cdp.ready();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");

  async function evaluate(expression) {
    const response = await cdp.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });

    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.text);
    }

    return response.result.value;
  }

  async function setViewport(width, height) {
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: width < 768,
    });
  }

  async function navigate(route, expectedText) {
    const loaded = cdp.waitEvent("Page.loadEventFired").catch(() => undefined);
    await cdp.send("Page.navigate", { url: `${baseUrl}${route}` });
    await loaded;
    await waitFor(
      async () =>
        evaluate(`document.readyState === "complete" && document.body.innerText.includes(${JSON.stringify(expectedText)})`),
      `Expected text was not rendered at ${route}: ${expectedText}`,
    );
    await delay(180);
  }

  async function screenshot(filename, { fullPage = true } = {}) {
    await waitFor(
      () => evaluate(`document.documentElement.clientWidth > 0 && document.body.scrollWidth > 0`),
      `Screenshot viewport is not ready for ${filename}`,
    );
    const { data } = await cdp.send("Page.captureScreenshot", {
      captureBeyondViewport: fullPage,
      format: "png",
      fromSurface: true,
    });
    await writeFile(path.join(screenshotDir, filename), Buffer.from(data, "base64"));
  }

  async function assertNoHorizontalOverflow(route, expectedText) {
    await navigate(route, expectedText);
    const metrics = await evaluate(`({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      offenders: Array.from(document.querySelectorAll("body *"))
        .map((element) => {
          const rect = element.getBoundingClientRect();
          return {
            element: element.tagName.toLowerCase(),
            className: typeof element.className === "string" ? element.className.slice(0, 120) : "",
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            width: Math.round(rect.width)
          };
        })
        .filter(({ left, right }) => left < -1 || right > document.documentElement.clientWidth + 1)
        .slice(0, 8)
    })`);
    assert(
      metrics.scrollWidth <= metrics.clientWidth + 1 && metrics.bodyScrollWidth <= metrics.clientWidth + 1,
      `Horizontal overflow at ${route}: ${JSON.stringify(metrics)}`,
    );
  }

  async function assertChangeWorkspaceAccess(route, expectedText, expectedProfile = null) {
    await navigate(route, expectedText);
    const link = await evaluate(`(() => {
      const element = document.querySelector('[data-design-action="change-workspace"]');
      if (!element) return null;
      const url = new URL(element.href);
      const rect = element.getBoundingClientRect();
      return {
        text: element.textContent.trim(),
        pathname: url.pathname,
        profile: url.searchParams.get("profile"),
        visible: rect.width > 0 && rect.height > 0
      };
    })()`);

    assert(link, `Missing Cambiar workspace link at ${route}`);
    assert(link.text === "Cambiar workspace", `Unexpected workspace switch label at ${route}: ${link.text}`);
    assert(link.pathname === "/select-workspace", `Unexpected workspace switch destination at ${route}: ${link.pathname}`);
    assert(link.profile === expectedProfile, `Unexpected workspace switch profile at ${route}: ${link.profile}`);
    assert(link.visible, `Cambiar workspace link is not visible at ${route}`);

    await evaluate(`document.querySelector('[data-design-action="change-workspace"]').click()`);
    await waitFor(() => evaluate(`location.pathname === "/select-workspace"`), `Workspace switch link did not navigate from ${route}`);
    assert(
      (await evaluate(`new URLSearchParams(location.search).get("profile")`)) === expectedProfile,
      `Workspace switch navigation lost profile from ${route}`,
    );
  }

  for (const route of [
    routes.home,
    routes.login,
    routes.selectWorkspace,
    routes.ownerDashboard,
    routes.ownerServices,
    routes.ownerReports,
    routes.ownerAlerts,
    routes.ownerTasks,
    routes.ownerWorkers,
    routes.ownerRuns,
    routes.partnerDashboard,
    routes.clientDashboard,
    routes.clientDetail,
  ]) {
    const response = await fetch(`${baseUrl}${route}`);
    assert(response.ok, `Route returned ${response.status}: ${route}`);
  }

  await setViewport(1440, 900);
  await navigate(routes.home, "Automatización con IA");
  assert(await evaluate(`Boolean(document.querySelector('a[href="/login"]'))`), "Home is missing a local console CTA");
  await screenshot("desktop-home.png");
  await evaluate(`document.querySelector('a[href="/login"]').click()`);
  await waitFor(() => evaluate(`location.pathname === "/login"`), "Home CTA did not navigate to /login");
  await screenshot("desktop-login.png");

  await navigate(routes.selectWorkspace, "Elegí una experiencia operativa");
  await screenshot("desktop-select-workspace.png");
  await assertChangeWorkspaceAccess(routes.ownerDashboard, "Team360 Admin");
  await assertChangeWorkspaceAccess(routes.ownerServices, "Servicios");
  await assertChangeWorkspaceAccess(routes.clientDetail, "Gestión de preguntas de marketplace", "client_admin");
  await assertChangeWorkspaceAccess(routes.partnerDashboard, "Admin Distribuidor", "partner_admin");
  await navigate(routes.ownerDashboard, "Team360 Admin");
  await screenshot("desktop-change-workspace-link.png");
  await screenshot("desktop-console-dashboard-team360.png");
  await navigate(routes.clientServices, "Servicios contratados");
  await screenshot("desktop-services.png");
  await navigate(routes.clientDetail, "Gestión de preguntas de marketplace");
  await screenshot("desktop-service-detail.png");
  await evaluate(
    `Array.from(document.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent.trim() === "Resultados").click()`,
  );
  await waitFor(() => evaluate(`location.search.includes("tab=results")`), "Service detail tabs did not update");
  assert(
    await evaluate(`document.querySelector('[role="tab"][aria-selected="true"]').textContent.trim() === "Resultados"`),
    "Results tab was not activated",
  );
  await navigate(routes.clientReports, "Reportes");
  await screenshot("desktop-reports.png");
  await navigate(routes.clientAlerts, "Alertas");
  await screenshot("desktop-alerts.png");
  await navigate(routes.clientDashboard, "Admin Cliente");
  await screenshot("desktop-client-dashboard.png");

  assert(
    await evaluate(`!Array.from(document.querySelectorAll('nav a')).some((link) => /\\/(workers|runs)(\\?|$)/.test(link.href))`),
    "Client navigation exposes workers or runs",
  );
  await navigate(routes.clientWorkers, "Esta vista técnica no está incluida");
  await navigate(routes.clientRuns, "Esta vista técnica no está incluida");

  for (const [width, height] of [
    [1440, 900],
    [1280, 800],
    [768, 1024],
    [390, 844],
    [430, 932],
  ]) {
    await setViewport(width, height);
    for (const [route, expectedText] of [
      [routes.home, "Automatización con IA"],
      [routes.login, "Acceso de diseño"],
      [routes.ownerDashboard, "Team360 Admin"],
      [routes.clientServices, "Servicios contratados"],
      [routes.clientDetail, "Gestión de preguntas"],
      [routes.clientReports, "Reportes"],
      [routes.clientAlerts, "Alertas"],
    ]) {
      await assertNoHorizontalOverflow(route, expectedText);
    }
  }

  await setViewport(390, 844);
  await navigate(routes.home, "Automatización con IA");
  assert(await evaluate(`Boolean(document.querySelector('a[href="/login"]'))`), "Mobile home is missing the console CTA");
  await screenshot("mobile-home.png");
  await navigate(routes.login, "Acceso de diseño");
  await screenshot("mobile-login.png");
  await navigate(routes.clientDashboard, "Admin Cliente");
  await screenshot("mobile-console-dashboard.png");
  await evaluate(`document.querySelector('button[aria-label="Abrir navegación"]').click()`);
  await waitFor(
    () => evaluate(`Boolean(document.querySelector('button.fixed[aria-label="Cerrar navegación"]'))`),
    "Mobile drawer did not open",
  );
  await waitFor(
    () =>
      evaluate(
        `Math.abs(document.querySelector('aside[aria-label="Navegación contextual"]').getBoundingClientRect().left) <= 1`,
      ),
    "Mobile drawer did not become visible",
  );
  assert(
    await evaluate(
      `document.querySelector('[data-design-action="change-workspace"]').textContent.trim() === "Cambiar workspace"`,
    ),
    "Mobile drawer is missing Cambiar workspace",
  );
  await screenshot("mobile-change-workspace-link.png", { fullPage: false });
  await screenshot("mobile-drawer.png", { fullPage: false });
  await evaluate(
    `document.querySelector('aside[aria-label="Navegación contextual"] button[aria-label="Cerrar navegación"]').click()`,
  );
  await waitFor(
    () =>
      evaluate(
        `!document.querySelector('button.fixed[aria-label="Cerrar navegación"]') &&
          document.querySelector('aside[aria-label="Navegación contextual"]').getBoundingClientRect().right <= 1`,
      ),
    "Mobile drawer did not close",
  );
  await navigate(routes.clientServices, "Servicios contratados");
  await screenshot("mobile-services.png");
  await navigate(routes.clientDetail, "Gestión de preguntas");
  await screenshot("mobile-service-detail.png");
  await evaluate(`document.querySelector('button[aria-label="Abrir navegación"]').click()`);
  await waitFor(
    () =>
      evaluate(
        `Math.abs(document.querySelector('aside[aria-label="Navegación contextual"]').getBoundingClientRect().left) <= 1`,
      ),
    "Mobile detail drawer did not become visible",
  );
  await evaluate(`document.querySelector('[data-design-action="change-workspace"]').click()`);
  await waitFor(
    () => evaluate(`location.pathname === "/select-workspace" && location.search.includes("profile=client_admin")`),
    "Mobile detail workspace switch did not navigate to the selector",
  );
  await navigate(routes.clientAlerts, "Alertas");
  await screenshot("mobile-alerts.png");

  console.log("Design smoke passed.");
  console.log(`Validated ${Object.keys(routes).length} named routes and 5 responsive viewports.`);
  console.log(`Screenshots written to ${screenshotDir}`);
} catch (error) {
  console.error(error.stack ?? error.message);
  if (chromiumLog.length) console.error(chromiumLog.join(""));
  process.exitCode = 1;
} finally {
  cdp?.close();
  chromium.kill("SIGTERM");
  await rm(profileDir, { recursive: true, force: true });
}
