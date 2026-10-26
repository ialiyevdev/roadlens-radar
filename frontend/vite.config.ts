import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  base: mode === "showcase" ? "./" : "/",
  build: { outDir: mode === "showcase" ? "dist-showcase" : "dist" },
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    strictPort: true,
    fs: {
      allow: [".", "../examples/traffic", "../docs/benchmarks"],
    },
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  preview: { host: "127.0.0.1", strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    restoreMocks: true,
    maxWorkers: 2,
  },
}));
