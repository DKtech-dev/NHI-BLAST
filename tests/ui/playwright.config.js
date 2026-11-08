// Dev-time browser tests for the generated report. The report itself makes no network requests.
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: ".",
  testMatch: "*.spec.js",
  globalSetup: require.resolve("./global-setup.js"),
  timeout: 45000,
  fullyParallel: true,
  // Software WebGL and full-page accessibility scans share GPU/CPU resources.
  // Keep every case and timeout, but serialize by default; CLI --workers can override.
  workers: 1,
  reporter: [["list"]],
  outputDir: "test-results",
  use: { viewport: { width: 1280, height: 900 }, trace: "off" },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
