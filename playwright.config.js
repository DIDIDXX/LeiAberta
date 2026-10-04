const { defineConfig } = require("@playwright/test");

const dbUrl = "sqlite:///./.e2e.db";

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
    command: `rm -f .e2e.db && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} .venv/bin/alembic upgrade head && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} .venv/bin/python -m app.seed && APP_ENV=test LOCAL_INLINE_JOBS=1 DATABASE_URL=${dbUrl} .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8012`,
    url: "http://127.0.0.1:8012/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
