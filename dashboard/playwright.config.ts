import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  timeout: 30000,
  use: {
    baseURL: process.env.DASHBOARD_BASE_URL || "http://127.0.0.1:5173",
    headless: true,
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    },
    viewport: { width: 1440, height: 1000 },
  },
  reporter: "list",
});
