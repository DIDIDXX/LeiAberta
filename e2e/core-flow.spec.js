const { test, expect } = require("@playwright/test");

test("real existing article: home to before/after comparison and device evidence", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Entenda como uma lei/ })).toBeVisible();
  await page.getByRole("link", { name: /Veja o antes e depois de um artigo/ }).click();
  await expect(page).toHaveURL(/\/diff\/be3a1531-edaa-5a78-94ca-70c6544e3853/);
  await expect(page.getByRole("link", { name: "Código Civil" })).toBeVisible();
  await expect(page.getByText("Data registrada: 28 de jun. de 2024")).toBeVisible();
  await expect(page.getByText("Comparação registrada", { exact: true })).toBeVisible();
  await expect(page.getByText("Antes", { exact: true })).toBeVisible();
  await expect(page.getByText("Depois", { exact: true })).toBeVisible();
  await expect(page.getByText(/segundo índices oficiais regularmente estabelecidos/)).toBeVisible();
  await expect(page.getByText(/juros, atualização monetária e honorários de advogado/)).toBeVisible();
  await expect(page.getByText(/valor jurídico não oficial/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Versão da comparação no Normas.leg.br/ })).toHaveAttribute("href", /normas\.leg\.br/);
  await page.getByRole("link", { name: /Ver evidências deste dispositivo/ }).click();
  await expect(page).toHaveURL(/\/lei\/10406-2002\/blame\?node=/);
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
  const result = page.getByRole("listbox").getByRole("link", { name: /Lei Geral de Proteção de Dados Pessoais/ }).first();
  await expect(result).toBeVisible();
  await search.press("ArrowDown");
  await expect(result).toHaveAttribute("aria-selected", "true");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/lei\/13709-2018/);

  for (const width of [390, 430, 768, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Entenda como uma lei/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      `home should not overflow horizontally at ${width}px`).toBeTruthy();
  }
});
