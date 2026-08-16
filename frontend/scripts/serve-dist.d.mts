import type { Server } from "node:http"

export const securityHeaders: Readonly<Record<string, string>>

export function createRuntimeServer(options?: {
  root?: string
  proxyTarget?: string | URL
}): Server
