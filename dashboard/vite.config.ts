import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom" },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("node_modules/recharts") ||
            id.includes("node_modules/d3-")
          )
            return "charts";
          if (
            id.includes("node_modules/react") ||
            id.includes("node_modules/@tanstack")
          )
            return "framework";
        },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
