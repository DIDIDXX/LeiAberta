const { test, expect } = require("@playwright/test");

test.beforeEach(async ({ page }) => {
  // Keep the browser run hermetic: only the local fixture server is reachable.
  await page.route("**/*", route => {
    const url = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(url.hostname)) return route.continue();
    return route.abort();
  });
});

test("the provenance link names the provision and the destination", async ({ page }) => {
  await page.goto("/lei/10406-2002/artigo/389");
  await expect(page.getByRole("heading", { name: "Art. 389º" })).toBeVisible();

  // The visible words stay at the start of the accessible name, so the link
  // is still addressable by what a sighted user reads out loud.
  const link = page.locator("#article-389").getByRole("link", { name: /^Por que este artigo está assim\?/ });
  await expect(link).toHaveAccessibleName("Por que este artigo está assim? — Art. 389º, abrir evidências no Blame");
  // The decorative arrow is not part of what gets announced.
  await expect(link).not.toHaveAccessibleName(/→/);
});

test("the provenance link is reachable by keyboard with a visible focus ring", async ({ page }) => {
  await page.goto("/lei/10406-2002/artigo/389");
  await expect(page.getByRole("heading", { name: "Art. 389º" })).toBeVisible();

  const link = page.locator("#article-389").getByRole("link", { name: /^Por que este artigo está assim\?/ });
  let reached = false;
  const order = [];
  for (let step = 0; step < 30 && !reached; step += 1) {
    await page.keyboard.press("Tab");
    order.push(await page.evaluate(() => document.activeElement?.textContent?.trim().slice(0, 40) || ""));
    reached = await link.evaluate(node => node === document.activeElement);
  }
  expect(reached, `provenance link should be reachable by Tab; order was ${JSON.stringify(order)}`).toBeTruthy();

  // Focus arrived from the keyboard, so the focus ring must be drawn.
  const outline = await link.evaluate(node => getComputedStyle(node).outlineWidth);
  expect(Number.parseFloat(outline)).toBeGreaterThan(0);
});

test("following the provenance link puts focus on the evidence panel", async ({ page }) => {
  await page.goto("/lei/10406-2002/artigo/389");
  const link = page.locator("#article-389").getByRole("link", { name: /^Por que este artigo está assim\?/ });
  await link.focus();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/lei\/10406-2002\/blame\?node=art%3A389/);
  const panel = page.locator(".why-panel");
  await expect(panel).toBeVisible();
  // Without this the user would land at the top of the document and have to
  // hunt for the evidence the navigation was about.
  await expect(panel).toBeFocused();
  // The panel is exposed as a named region rather than an anonymous block.
  await expect(page.getByRole("region", { name: "Art. 389º" })).toBeVisible();
});

test("the active section is announced, not only coloured", async ({ page }) => {
  await page.goto("/lei/10406-2002/blame?node=art%3A389");
  await expect(page.getByRole("link", { name: "Blame" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("link", { name: "Texto" })).not.toHaveAttribute("aria-current", "page");
});

test("the before and after panes are named regions", async ({ page }) => {
  await page.goto("/diff/be3a1531-edaa-5a78-94ca-70c6544e3853");
  await expect(page.getByRole("heading", { name: "Alteração: Art. 389º" })).toBeVisible();

  // Pink and green headers are the only visual difference between the two
  // panes, so each side carries its own accessible name.
  const before = page.getByRole("region", { name: "Antes Texto anterior" });
  const after = page.getByRole("region", { name: /^Depois/ });
  await expect(before).toBeVisible();
  await expect(after).toBeVisible();
  await expect(before).toContainText("segundo índices oficiais regularmente estabelecidos");
  await expect(after).toContainText("juros, atualização monetária e honorários de advogado");
  await expect(page.getByRole("heading", { name: "Antes", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Depois", exact: true })).toBeVisible();
});

test("pagination links state the range they lead to", async ({ page }) => {
  // The seeded database holds a single provision, so the real response is
  // patched to report a catalog larger than one page. Only the counters are
  // changed; the payload shape stays the server's own.
  await page.route("**/api/laws/10406-2002/blame?*", async route => {
    const response = await route.fetch();
    const payload = await response.json();
    await route.fulfill({ response, json: { ...payload, count: 600, offset: 250, has_more: true } });
  });

  await page.goto("/lei/10406-2002/blame?offset=250");
  const pagination = page.getByRole("navigation", { name: "Páginas de dispositivos" });
  await expect(pagination).toBeVisible();
  await expect(pagination).toContainText("de 600");
  await expect(pagination.getByRole("link", { name: /^Anterior/ }))
    .toHaveAccessibleName("Anterior — dispositivos a partir do 1º");
  await expect(pagination.getByRole("link", { name: /^Próximos dispositivos/ }))
    .toHaveAccessibleName("Próximos dispositivos — a partir do 501º");
});

test("the main region reports when it has finished filling", async ({ page }) => {
  // The shell ships a loading row and fetches the view, so aria-busy must be
  // cleared once the content is in place.
  await page.goto("/lei/10406-2002/blame?node=art%3A389");
  await expect(page.getByRole("heading", { name: "Quem responde pelo texto?" })).toBeVisible();
  await expect(page.locator("main#main")).not.toHaveAttribute("aria-busy", "true");
});
