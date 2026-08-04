import { fileURLToPath, URL } from "node:url"

import vue from "@vitejs/plugin-vue"
import { defineConfig, loadEnv } from "vite"
import { configDefaults } from "vitest/config"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const apiProxy = {
    "/api": {
      target: env.VITE_NORA_PROXY_TARGET || "http://localhost:8000",
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ""),
    },
  }
  return {
    plugins: [vue()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: apiProxy,
    },
    preview: { port: 5173, strictPort: true, proxy: apiProxy },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./tests/setup.ts"],
      // e2e/ 由 Playwright 负责，vitest 不收集其中的 *.spec.ts
      exclude: [...configDefaults.exclude, "e2e/**"],
    },
  }
})
