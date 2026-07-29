import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST_DIR = path.resolve(__dirname, "dist");
const PORT = 3050;
const HOST = "127.0.0.1";
const API_TARGET = "http://127.0.0.1:7050";

const MIME_TYPES = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function getMimeType(ext) {
  return MIME_TYPES[ext] || "application/octet-stream";
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);
  const pathname = url.pathname;

  // Proxy /api requests to backend
  if (pathname.startsWith("/api")) {
    const proxyReq = http.request(
      `${API_TARGET}${pathname}${url.search}`,
      {
        method: req.method,
        headers: { ...req.headers, host: new URL(API_TARGET).host },
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
      },
    );
    req.pipe(proxyReq);
    proxyReq.on("error", () => {
      res.writeHead(502);
      res.end("Bad Gateway");
    });
    return;
  }

  // Serve static files from dist/
  let filePath = path.join(DIST_DIR, pathname === "/" ? "index.html" : pathname);

  // Try the exact path
  if (fs.existsSync(filePath)) {
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      // Directory → serve index.html
      filePath = path.join(filePath, "index.html");
      if (!fs.existsSync(filePath)) {
        res.writeHead(404);
        res.end("Not Found");
        return;
      }
    }
  } else {
    // Path doesn't exist — try with .html or index.html in subdir
    if (!path.extname(filePath)) {
      const htmlPath = filePath + ".html";
      if (fs.existsSync(htmlPath)) {
        filePath = htmlPath;
      } else {
        // Try index.html in directory
        const indexHtmlPath = path.join(filePath, "index.html");
        if (fs.existsSync(indexHtmlPath)) {
          filePath = indexHtmlPath;
        } else {
          res.writeHead(404);
          res.end("Not Found");
          return;
        }
      }
    } else {
      res.writeHead(404);
      res.end("Not Found");
      return;
    }
  }

  const ext = path.extname(filePath).toLowerCase();
  const mimeType = getMimeType(ext);

  // Handle SRI: Serve with CORS headers for embed assets
  let corsHeader = "";
  if (pathname.startsWith("/embed/")) {
    corsHeader = "Access-Control-Allow-Origin";
  }

  const stream = fs.createReadStream(filePath);
  stream.on("open", () => {
    res.writeHead(200, {
      "Content-Type": mimeType,
      ...(corsHeader ? { [corsHeader]: "*" } : {}),
    });
    stream.pipe(res);
  });
  stream.on("error", () => {
    res.writeHead(404);
    res.end("Not Found");
  });
});

server.listen(PORT, HOST, () => {
  console.log(`[serve-dist] Serving ${DIST_DIR} at http://${HOST}:${PORT}`);
  console.log(`[serve-dist] Proxy /api → ${API_TARGET}`);
});
