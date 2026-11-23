const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { execFileSync } = require("node:child_process");

const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const PYTHON = process.env.NHB_PYTHON || "python3";

let tmpDir;
let reportHtml;
let hostileHtml;
let diffHtml;
let whatifHtml;

test.beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nhb-w4-ui-"));
  const fx07Out = path.join(tmpDir, "fx07");
  const fx14Out = path.join(tmpDir, "fx14");
  const diffOut = path.join(tmpDir, "diff");
  const whatifOut = path.join(tmpDir, "whatif");

  const runPy = (args) =>
    execFileSync(PYTHON, ["-m", "nhi_blast", ...args], {
      cwd: REPO_ROOT,
      stdio: "pipe",
    });

  runPy(["scan", "tests/fixtures/fx07-incident", "--repo-slug", "acme/shop", "--simulate-compromise", "repo-write", "--format", "json", "--format", "html", "--out", fx07Out]);
  runPy(["scan", "tests/fixtures/fx14-hostile", "--repo-slug", "acme/shop", "--format", "json", "--format", "html", "--out", fx14Out]);
  try {
    runPy(["diff", path.join(fx07Out, "report.json"), path.join(fx14Out, "report.json"), "--format", "html", "--out", diffOut]);
  } catch (err) {
    if (!fs.existsSync(path.join(diffOut, "diff.html"))) throw err;
  }
  runPy(["whatif", path.join(fx07Out, "report.json"), "--auto-plan", "--format", "html", "--out", whatifOut]);

  reportHtml = "file://" + path.join(fx07Out, "report.html");
  hostileHtml = "file://" + path.join(fx14Out, "report.html");
  diffHtml = "file://" + path.join(diffOut, "diff.html");
  whatifHtml = "file://" + path.join(whatifOut, "whatif.html");
});

test.afterAll(() => {
  if (tmpDir && fs.existsSync(tmpDir)) {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

async function runAxe(browser, url) {
  const ctx = await browser.newContext({ bypassCSP: true });
  try {
    const p = await ctx.newPage();
    await p.goto(url);
    await p.addScriptTag({ content: AXE });
    const result = await p.evaluate(() => window.axe.run(document, { resultTypes: ["violations"] }));
    return result.violations.map((v) => v.id + " (" + v.impact + "): " + v.nodes.map((n) => n.target.join(" ")).join(", "));
  } finally {
    await ctx.close();
  }
}

test("graph table fallback toggles cleanly and containment preview updates badge", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(reportHtml);
  await expect(page.locator("#graph-table-toggle")).toBeVisible();
  await expect(page.locator("#graph-table-panel")).toBeHidden();

  await page.locator("#graph-table-toggle").click();
  await expect(page.locator("#graph-table-panel")).toBeVisible();
  await expect(page.locator("#graph-table-panel table")).toHaveCount(2);

  const badge = page.locator("#containment-preview-badge");
  await expect(badge).toBeVisible();
  const initialText = await badge.textContent();
  const firstCheckbox = page.locator('#containment-sim input[type="checkbox"]').first();
  await firstCheckbox.check();
  const updatedText = await badge.textContent();
  expect(updatedText).not.toEqual(initialText);

  expect(errors).toEqual([]);
});

test("fx14-hostile renders with zero runtime errors", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(hostileHtml);
  await expect(page.locator("h1")).toBeVisible();
  expect(errors).toEqual([]);
});

test("companion diff.html passes zero-error and axe check", async ({ page, browser }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(diffHtml);
  await expect(page.locator("h1")).toContainText("Report comparison");
  expect(await runAxe(browser, diffHtml)).toEqual([]);
  expect(errors).toEqual([]);
});

test("companion whatif.html passes zero-error and axe check", async ({ page, browser }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(whatifHtml);
  await expect(page.locator("h1")).toContainText("Containment simulation report");
  expect(await runAxe(browser, whatifHtml)).toEqual([]);
  expect(errors).toEqual([]);
});
