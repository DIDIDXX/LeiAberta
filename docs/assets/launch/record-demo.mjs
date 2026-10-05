import { chromium } from "@playwright/test";
import { copyFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const base = (process.env.LEIABERTA_BASE_URL || "https://web-production-12e95.up.railway.app").replace(/\/$/, "");
const output = new URL(".", import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });

async function capture(path, name, viewport = { width: 1440, height: 1000 }, fullPage = true) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`${base}${path}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: new URL(name, output).pathname, fullPage, timeout: 90000 });
  await context.close();
}

await capture("/", "01-home.png");
await capture("/buscar?q=LGDP", "02-search-typo.png");
await capture("/lei/10406-2002/artigo/389", "03-law-reader.png");
await capture("/lei/10406-2002/blame?node=art%3A389", "04-why-this-text.png");
await capture("/diff/be3a1531-edaa-5a78-94ca-70c6544e3853", "05-diff.png");
await capture("/lei/10406-2002/blame", "06-blame.png");
await capture("/cobertura", "07-coverage.png");
// The production source registry has hundreds of entries; a viewport capture
// keeps this asset representative without producing a multi-megabyte page image.
await capture("/fontes", "08-sources.png", { width: 1440, height: 1000 }, false);
await capture("/diff/be3a1531-edaa-5a78-94ca-70c6544e3853", "09-mobile.png", { width: 390, height: 844 });
await copyFile(new URL("../../../static/og-image.png", import.meta.url), new URL("og-image.png", output));

const videoTemp = await mkdtemp(join(tmpdir(), "leiaberta-demo-"));
const videoContext = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: videoTemp, size: { width: 1440, height: 900 } },
});
const demo = await videoContext.newPage();
await demo.goto(`${base}/`, { waitUntil: "networkidle", timeout: 60000 });
await demo.waitForTimeout(3500);
await demo.getByRole("link", { name: /Veja o antes e depois de um artigo/ }).click();
await demo.waitForTimeout(4500);
await demo.getByRole("link", { name: /Ver evidências deste dispositivo/ }).click();
await demo.waitForTimeout(4500);
await demo.goto(`${base}/diff/be3a1531-edaa-5a78-94ca-70c6544e3853`, { waitUntil: "networkidle" });
await demo.waitForTimeout(3500);
await videoContext.close();
await demo.video().saveAs(new URL("demo.webm", output).pathname);
await rm(videoTemp, { recursive: true, force: true });

await browser.close();
