const { test, expect } = require("@playwright/test");

test("the home and search flow fit a mobile viewport", async ({ browser }) => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Veja o que mudou/ })).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Pesquisar legislação" });
  await search.fill("LGDP");
  await expect(page.getByRole("link", { name: /Lei Geral de Proteção de Dados Pessoais/ }).first()).toBeVisible();
  await page.goto("/lei/13709-2018/artigo/7");
  await expect(page.getByRole("heading", { name: "Art. 7º" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.close();
});

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

test("the history flow opens an official before-and-after diff", async ({ page, request }) => {
  await page.goto("/lei/11340-2006/historico");
  const prepare = page.getByRole("button", { name: /Buscar histórico oficial|Tentar atualizar o histórico/ });
  const queuedResponse = page.waitForResponse(response =>
    response.url().endsWith("/api/laws/11340-2006/history/prepare") && response.request().method() === "POST"
  );
  await expect(prepare).toBeVisible();
  await prepare.click();
  const queued = await queuedResponse;
  expect(queued.status()).toBe(202);
  const historyJob = await queued.json();
  await expect.poll(async () => {
    const response = await request.get(`/api/jobs/${historyJob.id}`);
    const job = await response.json();
    return job.status;
  }, { timeout: 60_000 }).toBe("succeeded");
  await expect.poll(async () => {
    const response = await request.get("/api/laws/11340-2006");
    const detail = await response.json();
    return Boolean(detail.version);
  }, { timeout: 60_000 }).toBe(true);
  await page.reload();

  const event = page.getByRole("link", { name: /Ver antes e depois/ }).first();
  await expect(event).toBeVisible({ timeout: 45_000 });
  await event.click();

  await expect(page.getByRole("heading", { name: /Acrescentou o § 4º/ })).toBeVisible();
  await expect(page.getByText("Antes", { exact: true })).toBeVisible();
  await expect(page.getByText("Depois", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Lei nº 14\.550\/2023/ })).toHaveAttribute("href", /L14550\.htm/);
});

test("a cold law shows preparation progress and becomes readable on demand", async ({ page }) => {
  await page.goto("/lei/12527-2011");
  await expect(page.getByRole("heading", { name: "Lei de Acesso à Informação" })).toBeVisible();
  await expect(page.getByText("Estamos preparando esta norma")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Art. 1º" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("link", { name: /Fonte oficial/ })).toHaveAttribute("href", /l12527\.htm/);
});

test("article-only search labels its multiple exact matches as ambiguity", async ({ page, request }) => {
  for (const slug of ["5172-1966", "10406-2002"]) {
    const queued = await request.post(`/api/laws/${slug}/hydrate`);
    expect(queued.status()).toBe(202);
    await expect.poll(async () => {
      const response = await request.get(`/api/laws/${slug}`);
      const body = await response.json();
      return { status: body.law.materialization_status, hasVersion: Boolean(body.version) };
    }, { timeout: 60_000 }).toEqual({ status: "partial", hasVersion: true });
  }

  await page.goto("/buscar?q=art%20121");
  await expect(page.getByText(/Art\. 121 aparece em \d+ normas/)).toBeVisible();
  await expect(page.getByText(/sugestão aproximada/)).toHaveCount(0);
});
