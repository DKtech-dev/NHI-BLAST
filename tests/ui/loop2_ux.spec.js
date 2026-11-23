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
let diffHtml;
let whatifHtml;

test.beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "nhb-loop2-ui-"));
  const fx07Out = path.join(tmpDir, "fx07");
  const fx14Out = path.join(tmpDir, "fx14");
  const diffOut = path.join(tmpDir, "diff");
  const whatifOut = path.join(tmpDir, "whatif");

  const runPy = (args) =>
    execFileSync(PYTHON, ["-m", "nhi_blast", ...args], {
      cwd: REPO_ROOT,
      stdio: "pipe",
    });

  runPy([
    "scan",
    "tests/fixtures/fx07-incident",
    "--repo-slug",
    "acme/shop",
    "--simulate-compromise",
    "action:tj-actions/changed-files@v45",
    "--format",
    "json",
    "--format",
    "html",
    "--out",
    fx07Out,
  ]);
  runPy([
    "scan",
    "tests/fixtures/fx14-hostile",
    "--repo-slug",
    "acme/shop",
    "--format",
    "json",
    "--format",
    "html",
    "--out",
    fx14Out,
  ]);
  try {
    runPy([
      "diff",
      path.join(fx07Out, "report.json"),
      path.join(fx14Out, "report.json"),
      "--format",
      "html",
      "--out",
      diffOut,
    ]);
  } catch (err) {
    if (!fs.existsSync(path.join(diffOut, "diff.html"))) throw err;
  }
  runPy([
    "whatif",
    path.join(fx07Out, "report.json"),
    "--auto-plan",
    "--format",
    "html",
    "--out",
    whatifOut,
  ]);

  reportHtml = "file://" + path.join(fx07Out, "report.html");
  diffHtml = "file://" + path.join(diffOut, "diff.html");
  whatifHtml = "file://" + path.join(whatifOut, "whatif.html");
});

test.afterAll(() => {
  if (tmpDir && fs.existsSync(tmpDir)) {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

async function runAxe(browser, url) {
  const ctx = await browser.newContext({
    bypassCSP: true,
    colorScheme: "light",
    reducedMotion: "reduce",
  });
  try {
    const p = await ctx.newPage();
    await p.goto(url);
    await p.waitForLoadState("load");
    if (await p.locator("html.booting").count()) {
      await p.waitForSelector("html:not(.booting)", { state: "attached" });
    }
    await p.addScriptTag({ content: AXE });
    const result = await p.evaluate(() =>
      window.axe.run(document, {
        resultTypes: ["violations"],
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"],
        },
      })
    );
    return result.violations.map(
      (v) => v.id + " (" + v.impact + "): " + v.nodes.map((n) => n.target.join(" ")).join(", ")
    );
  } finally {
    await ctx.close();
  }
}

test("Hallmark Light Theme default (#fcfcfd) and zero axe-core violations across report, diff, and whatif", async ({
  browser,
}) => {
  for (const [name, url] of [
    ["report.html", reportHtml],
    ["diff.html", diffHtml],
    ["whatif.html", whatifHtml],
  ]) {
    const ctx = await browser.newContext({ colorScheme: "light", offline: true });
    const page = await ctx.newPage();
    const requests = [];
    const errors = [];
    page.on("request", (req) => requests.push(req.url()));
    page.on("pageerror", (err) => errors.push(String(err)));

    await page.goto(url);
    if (name === "report.html") {
      await page.waitForSelector("html:not(.booting)", { state: "attached" });
    }
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(bg, name + " light theme canvas").toBe("rgb(252, 252, 253)");
    expect(await page.locator("html").getAttribute("data-theme")).toBe("light");

    const external = requests.filter((u) => !/^(file|data|blob|about):/.test(u));
    expect(external, name + " external network requests").toEqual([]);
    expect(errors, name + " runtime errors").toEqual([]);
    await ctx.close();

    expect(await runAxe(browser, url), name + " axe violations").toEqual([]);
  }
});

test("live findings search, severity pills, live counter, reset, and / + Escape shortcuts work", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(reportHtml);
  await page.waitForSelector("html:not(.booting)", { state: "attached" });

  const search = page.locator("#findings-search");
  const counter = page.locator("#findings-count");
  const cards = page.locator("#findings-content .finding");

  const totalCount = await cards.count();
  expect(totalCount).toBeGreaterThan(0);
  await expect(counter).toContainText(`Showing ${totalCount} of ${totalCount} finding`);

  // Press '/' outside an input to focus search
  await page.locator("h1").click();
  await page.keyboard.press("/");
  await expect(search).toBeFocused();

  // Typing '/' while inside search should insert '/' into the input rather than re-triggering
  await search.fill("oidc");
  const oidcCount = await cards.count();
  expect(oidcCount).toBeGreaterThan(0);
  expect(oidcCount).toBeLessThanOrEqual(totalCount);
  await expect(counter).toContainText(`Showing ${oidcCount} of ${totalCount} finding`);

  // Pressing Escape while focused in search clears the query
  await page.keyboard.press("Escape");
  await expect(search).toHaveValue("");
  await expect(cards).toHaveCount(totalCount);

  // Severity filter pills
  const criticalPill = page.locator('#finding-severity-pills button[data-severity="CRITICAL"]');
  const highPill = page.locator('#finding-severity-pills button[data-severity="HIGH"]');
  const allPill = page.locator('#finding-severity-pills button[data-severity=""]');

  await highPill.click();
  await expect(highPill).toHaveAttribute("aria-pressed", "true");
  const highCount = await cards.count();
  await expect(counter).toContainText(`Showing ${highCount} of ${totalCount} finding`);

  await criticalPill.click();
  await expect(criticalPill).toHaveAttribute("aria-pressed", "true");
  const critCount = await cards.count();
  await expect(counter).toContainText(`Showing ${critCount} of ${totalCount} finding`);

  // Reset restores all findings and 'All' pill
  await page.locator("#finding-clear").click();
  await expect(allPill).toHaveAttribute("aria-pressed", "true");
  await expect(cards).toHaveCount(totalCount);
  await expect(counter).toContainText(`Showing ${totalCount} of ${totalCount} finding`);

  expect(errors).toEqual([]);
});

test("one-click copy on finding cards and AWSRevokeOlderSessions JSON shows accessible toast", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(reportHtml);
  await page.waitForSelector("html:not(.booting)", { state: "attached" });

  const copyIdBtn = page.locator("#findings-content .finding .finding-copy-btn").first();
  await expect(copyIdBtn).toBeVisible();
  await copyIdBtn.click();

  const toast = page.locator("#nhb-toast");
  await expect(toast).toHaveAttribute("aria-live", "polite");
  await expect(toast).toHaveClass(/is-visible/);
  await expect(toast).toContainText(/copied to clipboard|Unable to copy/i);

  // Verify whatif.html AWSRevokeOlderSessions snippet + Copy JSON button
  await page.goto(whatifHtml);
  const copyJsonBtn = page.locator("button[data-copy-target^='revoke-policy-']").first();
  await expect(copyJsonBtn).toBeVisible();
  await expect(page.locator("#revoke-policy-0")).toContainText("AWSRevokeOlderSessions");
  await copyJsonBtn.click();

  const wfToast = page.locator("#nhb-toast");
  await expect(wfToast).toHaveAttribute("aria-live", "polite");
  await expect(wfToast).toHaveClass(/is-visible/);

  expect(errors).toEqual([]);
});

test("interactive graph Zoom In, Zoom Out, and Reset buttons update SVG transform safely", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(reportHtml);
  await page.waitForSelector("html:not(.booting)", { state: "attached" });

  const zoomIn = page.locator("#graph-zoom-in");
  const zoomOut = page.locator("#graph-zoom-out");
  const resetBtn = page.locator("#graph-fit");
  const level = page.locator("#graph-zoom-level");
  const viewport = page.locator("#graph-svg .graph-viewport");

  await expect(zoomIn).toBeVisible();
  await expect(zoomOut).toBeVisible();
  await expect(resetBtn).toBeVisible();

  const parsePercent = async () => parseInt((await level.textContent()).replace(/\D/g, ""), 10);
  const initialPct = await parsePercent();

  await zoomIn.click();
  const zoomedInPct = await parsePercent();
  expect(zoomedInPct).toBeGreaterThan(initialPct);
  const zoomedInTransform = await viewport.evaluate((el) => el.style.transform);
  expect(zoomedInTransform).toMatch(/scale\(/);

  await zoomOut.click();
  await zoomOut.click();
  const zoomedOutPct = await parsePercent();
  expect(zoomedOutPct).toBeLessThan(zoomedInPct);

  await resetBtn.click();
  const resetPct = await parsePercent();
  expect(resetPct).toBeGreaterThan(0);

  expect(errors).toEqual([]);
});

test("zero forbidden DOM/eval sinks in src/nhi_blast/report/", async () => {
  const reportDir = path.join(REPO_ROOT, "src", "nhi_blast", "report");
  const forbidden = /\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval)\b|new\s+Function\b/;
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "assets" || entry.name === "__pycache__") continue;
        walk(full);
      } else if (/\.(js|html|py)$/.test(entry.name)) {
        const text = fs.readFileSync(full, "utf8");
        expect(forbidden.test(text), "Forbidden sink in " + full).toBe(false);
      }
    }
  };
  walk(reportDir);
});
