// Saves the review screenshots: node screenshots.js [outDir]
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("@playwright/test");
const { reportUrl } = require("./support");

async function shoot(browser, out, name, report, scheme, width, motion) {
  const context = await browser.newContext({
    colorScheme: scheme,
    reducedMotion: motion ? "no-preference" : "reduce",
    viewport: { width, height: width <= 480 ? 844 : 900 },
  });
  const page = await context.newPage();
  await page.goto(reportUrl(report));
  await page.waitForSelector("html:not(.booting)", { state: "attached" });
  await page.waitForTimeout(900);
  const tag = name + "-" + scheme + "-" + width;
  await page.screenshot({ path: path.join(out, tag + "-top.png") });
  if (!motion) {
    await page.screenshot({ path: path.join(out, tag + ".png"), fullPage: true });
  }
  const files = [];
  if (motion && width === 1440) {
    const total = await page.evaluate(() => document.documentElement.scrollHeight);
    for (const fraction of [0, 0.25, 0.5, 0.75, 1]) {
      await page.evaluate((y) => window.scrollTo(0, y), Math.round((total - 900) * fraction));
      await page.waitForTimeout(1200);
      const file = path.join(out, "scroll-" + scheme + "-" + Math.round(fraction * 100) + ".png");
      await page.screenshot({ path: file });
      files.push(file);
    }
  }
  await context.close();
  return files;
}

async function filmstrip(browser, out, scheme, files) {
  const html = path.join(os.tmpdir(), "nhb-filmstrip-" + scheme + ".html");
  fs.writeFileSync(html, "<body style='margin:0;display:flex;gap:12px;background:#888;padding:12px'>" +
    files.map((file) => "<img style='width:640px;height:auto;display:block' src='" + pathToFileURL(file).href + "'>").join("") + "</body>");
  const context = await browser.newContext({ viewport: { width: 3380, height: 420 } });
  const page = await context.newPage();
  await page.goto(pathToFileURL(html).href);
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(out, "filmstrip-" + scheme + "-1440.png"), clip: { x: 0, y: 0, width: 3380, height: 380 } });
  await context.close();
}

require("./global-setup")().then(async () => {
  const out = path.resolve(process.argv[2] || path.join(__dirname, "..", "..", "docs", "usability", "screens"));
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const scheme of ["light", "dark"]) {
    for (const width of [1440, 1050, 768, 375]) {
      await shoot(browser, out, "report", "fx07", scheme, width, false);
    }
    const files = await shoot(browser, out, "report-motion", "fx07", scheme, 1440, true);
    await filmstrip(browser, out, scheme, files);
    await shoot(browser, out, "empty", "fx01", scheme, 1440, false);
    await shoot(browser, out, "hostile", "fx14", scheme, 1050, false);
    for (const width of [1440, 375]) {
      const context = await browser.newContext({ colorScheme: scheme, reducedMotion: "reduce", viewport: { width, height: 900 } });
      const page = await context.newPage();
      await page.goto(reportUrl("fx07"));
      await page.waitForSelector("html:not(.booting)", { state: "attached" });
      await page.waitForTimeout(500);
      await page.locator("#completeness").screenshot({ path: path.join(out, "completeness-" + scheme + "-" + width + ".png") });
      await page.locator(".timeline").screenshot({ path: path.join(out, "timeline-" + scheme + "-" + width + ".png") });
      await context.close();
    }
  }
  await browser.close();
});
