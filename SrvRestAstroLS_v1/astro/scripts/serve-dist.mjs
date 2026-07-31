import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname, resolve } from "node:path";

const DIST_DIR = resolve(import.meta.dirname, "../dist");
const PORT = parseInt(process.env.PORT || "3050", 10);
const API_TARGET = process.env.API_TARGET || "http://127.0.0.1:7050";

const MIME = {
  ".html": "text/html;charset=utf-8",
  ".js": "application/javascript;charset=utf-8",
  ".mjs": "application/javascript;charset=utf-8",
  ".css": "text/css;charset=utf-8",
  ".json": "application/json;charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".map": "application/json",
};

function proxyRequest(req, res) {
  const url = new URL(req.url, API_TARGET);
  const options = {
    hostname: url.hostname,
    port: url.port,
    path: url.pathname + url.search,
    method: req.method,
    headers: { ...req.headers },
  };

  const proxyReq = httpRequest(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on("error", (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { "Content-Type": "text/plain" });
      res.end("Bad Gateway");
    }
  });

  if (req.method !== "GET" && req.method !== "HEAD") {
    req.pipe(proxyReq);
  } else {
    proxyReq.end();
  }
}

function serveFile(res, filePath) {
  const ext = extname(filePath);
  const mime = MIME[ext] || "application/octet-stream";
  try {
    const content = readFileSync(filePath);
    res.writeHead(200, { "Content-Type": mime, "Cache-Control": "no-cache" });
    res.end(content);
  } catch (err) {
    res.writeHead(500);
    res.end("Internal Server Error");
  }
}

createServer((req, res) => {
  try {
    if (req.url.startsWith("/api")) {
      proxyRequest(req, res);
      return;
    }

    // Normalize path
    let url = req.url.split("?")[0].split("#")[0];
    if (url === "/") url = "/index.html";

    const forbidden = url.includes("..");
    if (forbidden) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    let filePath = join(DIST_DIR, url);

    // Check if path exists as a directory -> serve index.html
    if (existsSync(filePath) && statSync(filePath).isDirectory()) {
      filePath = join(filePath, "index.html");
    }

    if (!existsSync(filePath)) {
      res.writeHead(404);
      res.end("Not Found");
      return;
    }

    serveFile(res, filePath);
  } catch (err) {
    // Fallback: try index.html
    try {
      const fallback = join(DIST_DIR, req.url.split("?")[0], "index.html");
      if (existsSync(fallback)) {
        serveFile(res, fallback);
        return;
      }
    } catch (_) {}
    res.writeHead(500);
    res.end("Internal Server Error");
  }
}).listen(PORT, () => {
  console.log(`Static server on http://127.0.0.1:${PORT}`);
  console.log(`Serving ${DIST_DIR}`);
  console.log(`Proxying /api -> ${API_TARGET}`);
});
