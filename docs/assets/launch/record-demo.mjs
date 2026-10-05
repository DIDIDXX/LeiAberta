import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const base = (process.env.LEIABERTA_BASE_URL || "https://web-production-12e95.up.railway.app").replace(/\/$/, "");
const output = new URL(".", import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });

async function capture(path, name, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`${base}${path}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: new URL(name, output).pathname, fullPage: true });
  await context.close();
}

await capture("/", "01-home.png");
await capture("/buscar?q=LGDP", "02-search-typo.png");
await capture("/lei/11340-2006/artigo/19", "03-law-reader.png");
await capture("/lei/11340-2006/blame?node=art%3A19.par%3A4", "04-why-this-text.png");
await capture("/diff/3b1c3ba3-dc6e-4481-9aa0-3e197f2f8c10", "05-diff.png");
await capture("/lei/11340-2006/blame", "06-blame.png");
await capture("/cobertura", "07-coverage.png");
await capture("/fontes", "08-sources.png");
await capture("/diff/3b1c3ba3-dc6e-4481-9aa0-3e197f2f8c10", "09-mobile.png", { width: 390, height: 844 });
await capture("/static/og-image.svg", "og-image.png", { width: 1200, height: 630 });
await capture("/static/og-image.svg", "../../../static/og-image.png", { width: 1200, height: 630 });

const videoContext = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: output.pathname, size: { width: 1440, height: 900 } },
});
const demo = await videoContext.newPage();
await demo.goto(`${base}/`, { waitUntil: "networkidle", timeout: 60000 });
await demo.waitForTimeout(3500);
await demo.getByRole("link", { name: /Veja por que este artigo mudou/ }).click();
await demo.waitForTimeout(4500);
await demo.getByRole("link", { name: /Ver evidências deste dispositivo/ }).click();
await demo.waitForTimeout(4500);
await demo.goto(`${base}/diff/3b1c3ba3-dc6e-4481-9aa0-3e197f2f8c10`, { waitUntil: "networkidle" });
await demo.waitForTimeout(3500);
await videoContext.close();
await demo.video().saveAs(new URL("demo.webm", output).pathname);

await browser.close();
