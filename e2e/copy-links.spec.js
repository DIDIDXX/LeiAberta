const { test, expect } = require("@playwright/test");

test.beforeEach(async ({ page }) => {
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
    return route.abort();
  });
});

test("deep links can be copied from comparison, article, and evidence pages", async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: "http://127.0.0.1:8012" });

  await page.goto("/diff/be3a1531-edaa-5a78-94ca-70c6544e3853");
  await page.getByRole("button", { name: "Copiar link desta alteração" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Link copiado." })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/\/diff\/be3a1531-edaa-5a78-94ca-70c6544e3853/);

  await page.goto("/lei/10406-2002/artigo/389");
  await page.getByRole("button", { name: "Copiar link deste artigo" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Link copiado." })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/\/lei\/10406-2002\/artigo\/389/);

  await page.goto("/lei/10406-2002/blame?node=art%3A389");
  await page.getByRole("button", { name: "Copiar link desta evidência" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Link copiado." })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/\/lei\/10406-2002\/blame\?node=art%3A389/);
});
