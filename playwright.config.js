const { defineConfig } = require("@playwright/test");
const fs = require("node:fs");

const dbUrl = "sqlite:///./.e2e.db";
const python = fs.existsSync(".venv/bin/python") ? ".venv/bin/python" : "python";

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
    command: `rm -f .e2e.db && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} ${python} -m alembic upgrade head && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} ${python} -m app.seed && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} ${python} -m scripts.seed_e2e_demo && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} ${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8012`,
    url: "http://127.0.0.1:8012/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
