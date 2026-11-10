// node --test backend/modules/telchi/test_dev_proxy.mjs (from SrvRestAstroLS_v1)
// Real Vite proxy with a synthetic upstream. Not an enterprise/Luna E2E.
import assert from 'node:assert/strict';
import { createServer as httpServer } from 'node:http';
import { createRequire } from 'node:module';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { mkdtemp, rm, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const astroRoot = fileURLToPath(new URL('../../../astro/', import.meta.url));
const require = createRequire(await realpath(new URL('../../../astro/node_modules/astro/package.json', import.meta.url)));
const { createServer } = await import(require.resolve('vite'));

test('DEV proxy preserves HTTP, incremental SSE, disconnect and reconnect', { timeout: 20000 }, async () => {
  const cacheDir = await mkdtemp(join(tmpdir(), 'telchi-proxy-'));
  let released;
  let disconnected;
  const disconnectedPromise = new Promise(resolve => { disconnected = resolve; });
  const upstream = httpServer((req, res) => {
    assert.equal(req.headers.authorization, 'Bearer fixture-only');
    if (req.url.endsWith('/session')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end('{"fixture":true}');
    } else {
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store' });
      res.write('event: accepted\ndata: {}\n\n');
      released = () => res.end('event: result\ndata: {"fixture":true}\n\n');
      res.on('close', disconnected);
    }
  });
  let vite;
  try {
    upstream.listen(0, '127.0.0.1');
    await once(upstream, 'listening');
    process.env.TEAM360_TELCHIAI_PORT = String(upstream.address().port);
    const { default: config } = await import('../../../astro/astro.config.dev.mjs');
    assert.equal(config.vite.server.proxy['/api'], 'http://127.0.0.1:7050');
    vite = await createServer({ configFile: false, root: astroRoot, cacheDir,
      optimizeDeps: { noDiscovery: true, entries: [] },
      server: { host: '127.0.0.1', port: 0, proxy: config.vite.server.proxy },
      logLevel: 'error' });
    await vite.listen();
    const url = `http://127.0.0.1:${vite.httpServer.address().port}`;
    const headers = { Authorization: 'Bearer fixture-only' };
    for (const path of ['/api/telchiai/session', '/api/telchi/luna/session']) {
      assert.deepEqual(await (await fetch(url + path, { headers })).json(), { fixture: true });
    }
    const controller = new AbortController();
    const response = await fetch(url + '/api/telchiai/ask', {
      method: 'POST', headers, signal: controller.signal });
    const reader = response.body.getReader();
    const first = new TextDecoder().decode((await reader.read()).value);
    assert.match(first, /event: accepted/);
    assert.doesNotMatch(first, /event: result/); // Upstream result is still withheld.
    controller.abort();
    await Promise.race([disconnectedPromise, new Promise((_, reject) =>
      setTimeout(() => reject(new Error('upstream not disconnected')), 3000).unref())]);
    const retry = await fetch(url + '/api/telchiai/ask', { method: 'POST', headers });
    released();
    assert.match(await retry.text(), /event: result/);
  } finally {
    await vite?.close();
    upstream.closeAllConnections();
    await new Promise(resolve => upstream.close(resolve));
    await rm(cacheDir, { recursive: true, force: true });
  }
});
