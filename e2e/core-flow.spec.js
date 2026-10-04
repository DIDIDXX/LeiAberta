const { test, expect } = require("@playwright/test");

test("LGDP resolves to LGPD, shows article 7 and links the official source", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Veja o que mudou/ })).toBeVisible();

  const search = page.getByRole("searchbox", { name: "Pesquisar legislação" });
  await search.fill("LGDP");
  const result = page.getByRole("link", { name: /Lei Geral de Proteção de Dados Pessoais/ }).first();
  await expect(result).toBeVisible();
  await result.click();
  await expect(page).toHaveURL(/\/lei\/13709-2018/);

  await page.goto("/lei/13709-2018/artigo/7");
  await expect(page.getByRole("heading", { name: "Art. 7º" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Fonte oficial/ })).toHaveAttribute("href", /planalto\.gov\.br/);
});

test("the history flow opens an official before-and-after diff", async ({ page }) => {
  await page.goto("/lei/11340-2006/historico");
  const event = page.getByRole("link", { name: /Ver antes e depois/ }).first();
  await expect(event).toBeVisible({ timeout: 45_000 });
  await event.click();

  await expect(page.getByRole("heading", { name: /Acrescentou o § 4º/ })).toBeVisible();
  await expect(page.getByText("Antes", { exact: true })).toBeVisible();
  await expect(page.getByText("Depois", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Lei nº 14\.550\/2023/ })).toHaveAttribute("href", /L14550\.htm/);
});
