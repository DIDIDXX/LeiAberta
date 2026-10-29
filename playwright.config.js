const { defineConfig } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const dbUrl = "sqlite:///./.e2e.db";
const venvPython = path.join(".venv", ...(process.platform === "win32" ? ["Scripts", "python.exe"] : ["bin", "python"]));
const python = fs.existsSync(venvPython) ? venvPython : "python";

// "rm -f .e2e.db" is not a command outside a POSIX shell. The removal has to
// stay the first step of the server command: this config is re-evaluated in
// every worker process, and deleting the file while the server holds it open
// fails on Windows. Node is always available, since it runs Playwright.
const removeDb = `node -e "require('node:fs').rmSync('.e2e.db',{force:true})"`;

module.exports = defineConfig({
  testDir: "./e2e",
  timeout: 70_000,
  expect: { timeout: 25_000 },
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8012",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    // The settings are passed through "env" rather than as a "VAR=value
    // command" prefix, which only a POSIX shell understands.
    command: `${removeDb} && "${python}" -m alembic upgrade head && "${python}" -m app.seed && "${python}" -m scripts.seed_e2e_demo && "${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8012`,
    env: {
      SUPPORT_URL: "",
      APP_ENV: "test",
      LOCAL_INLINE_JOBS: "1",
      DATABASE_URL: dbUrl,
    },
    url: "http://127.0.0.1:8012/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
