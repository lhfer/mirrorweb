import { defineConfig } from "playwright/test";

export default defineConfig({
  testDir: "tests",
  timeout: 120000,
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://127.0.0.1:5280",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    channel: "chrome",
    launchOptions: {
      args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
    },
  },
});
