import { createReadStream, statSync } from "node:fs"
import { createServer, request as proxyRequest } from "node:http"
import { extname, join, normalize } from "node:path"
import process from "node:process"
import { fileURLToPath, URL } from "node:url"

const defaultRoot = fileURLToPath(new URL("../dist/", import.meta.url))
const defaultProxyTarget = new URL(process.env.VITE_NORA_PROXY_TARGET || "http://api:8000")
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

export const securityHeaders = Object.freeze({
  "content-security-policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
  "referrer-policy": "no-referrer",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
})

function responseHeaders(upstreamHeaders = {}, { proxied = false } = {}) {
  const headers = { ...upstreamHeaders }
  delete headers["strict-transport-security"]
  if (proxied) headers["x-nora-web-proxy"] = "true"
  return { ...headers, ...securityHeaders }
}

function proxy(request, response, proxyTarget) {
  const incoming = new URL(request.url, "http://localhost")
  const target = new URL(proxyTarget)
  target.pathname = incoming.pathname.replace(/^\/api/, "") || "/"
  target.search = incoming.search
  const upstream = proxyRequest(
    target,
    { method: request.method, headers: { ...request.headers, host: proxyTarget.host } },
    (upstreamResponse) => {
      response.writeHead(
        upstreamResponse.statusCode || 502,
        responseHeaders(upstreamResponse.headers, { proxied: true }),
      )
      upstreamResponse.pipe(response)
    },
  )
  upstream.on("error", () => {
    response.writeHead(502, responseHeaders(
      { "content-type": "text/plain; charset=utf-8" },
      { proxied: true },
    ))
    response.end("Bad Gateway")
  })
  request.pipe(upstream)
}

function staticFile(request, response, root) {
  const pathname = new URL(request.url, "http://localhost").pathname
  let relative
  try {
    relative = normalize(decodeURIComponent(pathname)).replace(/^[/\\]+/, "")
  } catch {
    response.writeHead(400, securityHeaders)
    response.end()
    return
  }
  let file = join(root, relative)
  if (!file.startsWith(root)) {
    response.writeHead(400, securityHeaders)
    response.end()
    return
  }
  try {
    if (statSync(file).isDirectory()) file = join(file, "index.html")
    if (!statSync(file).isFile()) throw new Error("not a file")
  } catch {
    file = join(root, "index.html")
  }
  response.writeHead(200, responseHeaders({
    "cache-control": extname(file) === ".html" ? "no-cache" : "public, max-age=31536000, immutable",
    "content-type": contentTypes[extname(file)] || "application/octet-stream",
  }))
  if (request.method === "HEAD") response.end()
  else createReadStream(file).pipe(response)
}

export function createRuntimeServer({ root = defaultRoot, proxyTarget = defaultProxyTarget } = {}) {
  const normalizedRoot = root.endsWith("/") ? root : `${root}/`
  const normalizedTarget = proxyTarget instanceof URL ? proxyTarget : new URL(proxyTarget)
  return createServer((request, response) => {
    if (request.url === "/api" || request.url.startsWith("/api/")) {
      proxy(request, response, normalizedTarget)
    } else {
      staticFile(request, response, normalizedRoot)
    }
  })
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  createRuntimeServer().listen(port, "0.0.0.0")
}
