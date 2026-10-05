const { test, expect } = require("@playwright/test");

test("real evidence demo: home to amendment, before/after, official source and device blame", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Entenda como uma lei/ })).toBeVisible();
  await page.getByRole("link", { name: /Veja por que este artigo mudou/ }).click();
  await expect(page).toHaveURL(/\/diff\/3b1c3ba3-dc6e-4481-9aa0-3e197f2f8c10/);
  await expect(page.getByText("Antes", { exact: true })).toBeVisible();
  await expect(page.getByText("Depois", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Fonte oficial da norma modificadora/ })).toHaveAttribute("href", /L14550\.htm/);
  await page.getByRole("link", { name: /Ver evidências deste dispositivo/ }).click();
  await expect(page).toHaveURL(/\/lei\/11340-2006\/blame\?node=/);
  await expect(page.getByText(/O ato abaixo tem comparação de texto registrada/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Ver antes e depois/ })).toBeVisible();
});

test("LGDP typo search and mobile home stay usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/stats", async route => {
    const response = await route.fetch();
    const stats = await response.json();
    await route.fulfill({ response, json: {
      ...stats,
      indexed_laws: 1_356_548,
      materialized_laws: 26_228,
      enumerated_sources: 383,
      documented_changes: 537,
    }});
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Entenda como uma lei/ })).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Pesquisar legislação" });
  await search.fill("LGDP");
  await expect(page.getByRole("link", { name: /Lei Geral de Proteção de Dados Pessoais/ }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
