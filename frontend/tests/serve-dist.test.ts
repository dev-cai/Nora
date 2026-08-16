// @vitest-environment node

import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises"
import { createServer, type Server } from "node:http"
import { tmpdir } from "node:os"
import { join } from "node:path"

import { afterEach, describe, expect, test } from "vitest"

import { createRuntimeServer, securityHeaders } from "../scripts/serve-dist.mjs"

const servers: Server[] = []
const roots: string[] = []

async function listen(server: Server): Promise<string> {
  servers.push(server)
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve))
  const address = server.address()
  if (address === null || typeof address === "string") throw new Error("server did not bind")
  return `http://127.0.0.1:${address.port}`
}

async function distRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "nora-web-runtime-"))
  roots.push(root)
  await mkdir(join(root, "assets"))
  await writeFile(join(root, "index.html"), "<!doctype html><title>Nora</title>")
  await writeFile(join(root, "assets", "app.js"), "console.log('nora')")
  return root
}

afterEach(async () => {
  await Promise.all(servers.splice(0).map((server) => new Promise<void>((resolve) => server.close(() => resolve()))))
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

describe("production Web runtime", () => {
  test("serves static files and SPA fallback with application security headers", async () => {
    const root = await distRoot()
    const origin = await listen(createRuntimeServer({ root, proxyTarget: "http://127.0.0.1:1" }))

    const html = await fetch(`${origin}/missing/route`)
    expect(html.status).toBe(200)
    expect(html.headers.get("content-type")).toBe("text/html; charset=utf-8")
    expect(html.headers.get("cache-control")).toBe("no-cache")
    for (const [name, value] of Object.entries(securityHeaders)) {
      expect(html.headers.get(name)).toBe(value)
    }
    expect(html.headers.get("strict-transport-security")).toBeNull()

    const asset = await fetch(`${origin}/assets/app.js`, { method: "HEAD" })
    expect(asset.status).toBe(200)
    expect(asset.headers.get("cache-control")).toBe("public, max-age=31536000, immutable")
    expect(await asset.text()).toBe("")
  })

  test("proxies API paths, preserves business headers and forwards normalized proxy identity", async () => {
    const upstream = createServer((request, response) => {
      expect(request.url).toBe("/auth/login?attempt=1")
      expect(request.headers["x-forwarded-for"]).toBe("198.51.100.10")
      expect(request.headers["x-forwarded-proto"]).toBe("https")
      const body = JSON.stringify({ status: "upstream" })
      response.writeHead(401, {
        "Content-Length": Buffer.byteLength(body),
        "Content-Type": "application/json",
        "Retry-After": "30",
        "Strict-Transport-Security": "max-age=1",
        "WWW-Authenticate": "Bearer",
      })
      response.end(body)
    })
    const upstreamOrigin = await listen(upstream)
    const root = await distRoot()
    const origin = await listen(createRuntimeServer({ root, proxyTarget: upstreamOrigin }))

    const response = await fetch(`${origin}/api/auth/login?attempt=1`, {
      headers: {
        "X-Forwarded-For": "198.51.100.10",
        "X-Forwarded-Proto": "https",
      },
    })

    expect(response.status).toBe(401)
    expect(response.headers.get("content-type")).toBe("application/json")
    expect(response.headers.get("content-length")).toBe("21")
    expect(response.headers.get("retry-after")).toBe("30")
    expect(response.headers.get("www-authenticate")).toBe("Bearer")
    expect(response.headers.get("x-nora-web-proxy")).toBe("true")
    expect(response.headers.get("strict-transport-security")).toBeNull()
    for (const [name, value] of Object.entries(securityHeaders)) {
      expect(response.headers.get(name)).toBe(value)
    }
  })
})
