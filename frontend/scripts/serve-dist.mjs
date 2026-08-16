import { createReadStream, statSync } from "node:fs"
import { createServer, request as proxyRequest } from "node:http"
import { extname, join, normalize } from "node:path"
import process from "node:process"
import { fileURLToPath, URL } from "node:url"

const root = fileURLToPath(new URL("../dist/", import.meta.url))
const proxyTarget = new URL(process.env.VITE_NORA_PROXY_TARGET || "http://api:8000")
const port = Number.parseInt(process.env.PORT || "5173", 10)
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
}

function proxy(request, response) {
  const incoming = new URL(request.url, "http://localhost")
  const target = new URL(proxyTarget)
  target.pathname = incoming.pathname.replace(/^\/api/, "") || "/"
  target.search = incoming.search
  const upstream = proxyRequest(
    target,
    { method: request.method, headers: { ...request.headers, host: proxyTarget.host } },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers)
      upstreamResponse.pipe(response)
    },
  )
  upstream.on("error", () => {
    response.writeHead(502, { "content-type": "text/plain; charset=utf-8" })
    response.end("Bad Gateway")
  })
  request.pipe(upstream)
}

function staticFile(request, response) {
  const pathname = new URL(request.url, "http://localhost").pathname
  let relative
  try {
    relative = normalize(decodeURIComponent(pathname)).replace(/^[/\\]+/, "")
  } catch {
    response.writeHead(400)
    response.end()
    return
  }
  let file = join(root, relative)
  if (!file.startsWith(root)) {
    response.writeHead(400)
    response.end()
    return
  }
  try {
    if (statSync(file).isDirectory()) file = join(file, "index.html")
    if (!statSync(file).isFile()) throw new Error("not a file")
  } catch {
    file = join(root, "index.html")
  }
  response.writeHead(200, {
    "cache-control": extname(file) === ".html" ? "no-cache" : "public, max-age=31536000, immutable",
    "content-type": contentTypes[extname(file)] || "application/octet-stream",
    "x-content-type-options": "nosniff",
  })
  if (request.method === "HEAD") response.end()
  else createReadStream(file).pipe(response)
}

createServer((request, response) => {
  if (request.url === "/api" || request.url.startsWith("/api/")) proxy(request, response)
  else staticFile(request, response)
}).listen(port, "0.0.0.0")
