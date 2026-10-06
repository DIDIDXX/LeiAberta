const { test, expect } = require("@playwright/test");

test.beforeEach(async ({ page }) => {
  // Keep the browser run hermetic: only the local fixture server is reachable.
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
    return route.abort();
  });
});

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

test("LGDP typo search, keyboard navigation, and mobile home stay usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Entenda como uma lei/ })).toBeVisible();

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Pular para o conteúdo" });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);

  const search = page.getByRole("searchbox", { name: "Pesquisar legislação" });
  await search.fill("LGDP");
  const result = page.getByRole("listbox").getByRole("link", { name: /Lei Geral de Proteção de Dados Pessoais/ }).first();
  await expect(result).toBeVisible();
  await search.press("ArrowDown");
  await expect(result).toHaveAttribute("aria-selected", "true");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/lei\/13709-2018/);
  await expect(page.getByRole("heading", { name: /Lei Geral de Proteção de Dados Pessoais/ })).toBeVisible();
  await expect(page.locator(".law-progress")).toContainText("Estamos preparando esta norma");
  await expect(page.getByRole("link", { name: /Fonte oficial/ }).first()).toHaveAttribute("href", /planalto\.gov\.br/);

  for (const width of [390, 430, 768, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Entenda como uma lei/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      `home should not overflow horizontally at ${width}px`).toBeTruthy();
  }
});

test("federal article, history, recorded before/after, official source and provenance", async ({ page }) => {
  await page.goto("/lei/10406-2002/artigo/389");
  await expect(page.getByRole("heading", { name: "Art. 389º" })).toBeVisible();
  await expect(page.getByText(/juros, atualização monetária e honorários de advogado/)).toBeVisible();
  const officialLawSource = page.getByRole("link", { name: /Fonte oficial/ }).first();
  await expect(officialLawSource).toHaveAttribute("href", /planalto\.gov\.br/);

  await page.locator("#article-389").getByRole("link", { name: /Por que este artigo está assim/ }).click();
  await expect(page).toHaveURL(/\/lei\/10406-2002\/blame\?node=art%3A389/);
  await expect(page.getByRole("heading", { name: "Quem responde pelo texto?" })).toBeVisible();
  await expect(page.getByText(/O ato abaixo tem comparação de texto registrada/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Ver antes e depois/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Abrir norma modificadora oficial/ })).toHaveAttribute("href", /normas\.leg\.br/);

  await page.goto("/lei/10406-2002/historico");
  await expect(page.getByRole("status")).toContainText(/referência\(s\) oficial\(is\)|alterações ligadas/i);
  await expect(page.getByRole("heading", { name: "Alteração: Art. 389º" })).toBeVisible();
  await page.getByRole("link", { name: /Ver antes e depois/ }).click();
  await expect(page).toHaveURL(/\/diff\/be3a1531-edaa-5a78-94ca-70c6544e3853/);
  await expect(page.getByText("Antes", { exact: true })).toBeVisible();
  await expect(page.getByText("Depois", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Versão da comparação no Normas\.leg\.br/ })).toHaveAttribute("href", /normas\.leg\.br/);
});

test("route and viewport smoke matrix: 9 routes across 390, 430, 768 and 1440 px", async ({ page }) => {
  test.setTimeout(120_000);
  const routes = [
    ["/", /Entenda como uma lei/],
    ["/buscar?q=LGDP", /Encontre uma norma/],
    ["/lei/10406-2002", /Código Civil/],
    ["/lei/10406-2002/artigo/389", /Art\. 389º/],
    ["/lei/10406-2002/historico", /Alteração: Art\. 389º/],
    ["/lei/10406-2002/blame?node=art%3A389", /Quem responde pelo texto/],
    ["/diff/be3a1531-edaa-5a78-94ca-70c6544e3853", /Alteração: Art\. 389º/],
    ["/fontes", /Fontes oficiais, estado por estado/],
    ["/cobertura", /Cobertura que mostra as lacunas/],
  ];
  const widths = [390, 430, 768, 1440];
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));

  for (const [path, heading] of routes) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(path);
      await expect(page.locator("main#main").getByRole("heading", { name: heading }).first(), `${path} at ${width}px`).toBeVisible();
      if (path === "/fontes") {
        await expect(page.getByText("Ainda não há registries de fontes carregados neste ambiente.")).toBeVisible();
      }
      if (path === "/cobertura") {
        await expect(page.getByText("registros catalogados", { exact: true })).toBeVisible();
        await expect(page.getByRole("heading", { name: "Federal", exact: true })).toBeVisible();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
        `${path} should not overflow horizontally at ${width}px`).toBeTruthy();
    }
  }
  expect(pageErrors).toEqual([]);
});
