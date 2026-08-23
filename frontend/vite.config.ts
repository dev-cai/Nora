import { fileURLToPath, URL } from "node:url"

import vue from "@vitejs/plugin-vue"
import { defineConfig, loadEnv } from "vite"

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
    },
  }
})
