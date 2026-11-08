const fs = require("node:fs");
const { test, expect } = require("@playwright/test");
const { open, watch } = require("./support");

const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const ORDER = ["Partially analysed", "Not provided", "Not supported", "Analysed", "Not applicable"];
const KEYS = ["partially_analysed", "not_provided", "not_supported", "analysed", "not_applicable"];

const island = (page) => page.evaluate(() => JSON.parse(document.getElementById("report-data").textContent));
const panel = (page) => page.locator("#completeness");

function expectClean(seen) {
  expect(seen.errors, "uncaught page errors").toEqual([]);
  expect(seen.consoleErrors, "console errors").toEqual([]);
}

test.describe("analysis completeness panel", () => {
  test("is shown after the summary with counts that match the embedded data", async ({ page }) => {
    const seen = watch(page);
    await open(page, "fx07");
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).getByRole("heading", { level: 2, name: "Analysis completeness" })).toBeVisible();
    // G6: sections sit in bands, so read them in document order across the whole main element.
    const order = await page.evaluate(() => [...document.querySelectorAll("main section")].map((s) => s.id));
    expect(order.indexOf("summary")).toBeLessThan(order.indexOf("completeness"));
    expect(order.indexOf("completeness")).toBeLessThan(order.indexOf("survival"));
    await expect(page.locator('.toc a[href="#completeness"]')).toBeVisible();

    const data = await island(page);
    const expected = KEYS.map((key) => data.completeness.items.filter((item) => item.status === key).length);
    const shown = await panel(page).locator(".cmp-counts li").evaluateAll((rows) =>
      rows.map((row) => [row.querySelector(".cmp-status").textContent, Number(row.querySelector(".cmp-count-num").textContent)]));
    expect(shown).toEqual(ORDER.map((label, index) => [label, expected[index]]));

    const headings = await panel(page).locator(".cmp-group > h3").allTextContents();
    const wanted = ORDER.map((label, index) => (expected[index] ? label + " (" + expected[index] + ")" : null)).filter(Boolean);
    expect(headings).toEqual(wanted);
    expectClean(seen);
  });

  test("every item carries a text status badge, the family label and its explanation", async ({ page }) => {
    await open(page, "fx07");
    await page.locator("#completeness details").evaluateAll((all) => all.forEach((d) => { d.open = true; }));
    const data = await island(page);
    const items = panel(page).locator(".cmp-item");
    await expect(items).toHaveCount(data.completeness.items.length);
    const rows = await items.evaluateAll((all) => all.map((row) => ({
      family: row.querySelector(".cmp-family").textContent,
      badge: row.querySelector(".cmp-status").textContent,
      explanation: row.querySelector(".cmp-explanation") ? row.querySelector(".cmp-explanation").textContent : "",
    })));
    for (const row of rows) {
      expect(row.family.trim()).not.toBe("");
      expect(ORDER).toContain(row.badge);
      expect(row.explanation.trim()).not.toBe("");
    }
    const byText = (await panel(page).innerText()).toLowerCase();
    expect(byText).toContain("the report says nothing about that family, not that nothing is there");
  });

  test("no percentage and no completeness claim in the wording", async ({ page }) => {
    await open(page, "fx07");
    await page.locator("#completeness details").evaluateAll((all) => all.forEach((d) => { d.open = true; }));
    const text = await panel(page).innerText();
    expect(text).not.toMatch(/%/);
    expect(text).not.toMatch(/\bcomplete\b/i);
    expect(text).not.toMatch(/fully analysed|fully covered|everything was/i);
  });

  test("analysed and not applicable groups are collapsed and toggle from the keyboard", async ({ page }) => {
    await open(page, "fx07");
    const details = panel(page).locator("details.cmp-group-details, .cmp-group > details");
    await expect(details).toHaveCount(2);
    for (const index of [0, 1]) {
      const one = details.nth(index);
      await expect(one).not.toHaveAttribute("open", /.*/);
      const summary = one.locator("summary");
      await summary.focus();
      await page.keyboard.press("Enter");
      await expect(one).toHaveAttribute("open", "");
      await expect(one.locator(".cmp-item").first()).toBeVisible();
      await page.keyboard.press("Space");
      await expect(one).not.toHaveAttribute("open", /.*/);
    }
  });

  test("assumption and diagnostic references link to the existing sections", async ({ page }) => {
    await open(page, "fx07");
    const link = panel(page).locator('a[href="#assumption-A-NO-SCP"]').first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page.locator("#assumption-A-NO-SCP")).toBeInViewport();
    const hrefs = await panel(page).locator("a").evaluateAll((all) => all.map((a) => a.getAttribute("href")));
    for (const href of hrefs) {
      expect(href).toMatch(/^#(assumption|diagnostic)-[A-Za-z0-9_-]+$/);
      expect(await page.locator(href).count()).toBe(1);
    }
  });

  test("zero findings with gaps shows the scope notice, never a bare empty state", async ({ page }) => {
    const seen = watch(page);
    await open(page, "fx01");
    const data = await island(page);
    expect(data.findings).toEqual([]);
    expect(data.completeness.items.some((item) => ["partially_analysed", "not_provided", "not_supported"].includes(item.status))).toBe(true);
    const target = page.locator("#findings-content");
    await expect(target).toHaveText("No findings in the analysed scope - see Analysis completeness");
    await expect(target.locator("a")).toHaveAttribute("href", "#completeness");
    await expect(target).not.toContainText("No findings were generated");
    await expect(page.locator(".finding")).toHaveCount(0);
    expectClean(seen);
  });

  test("renders when the animation runtime is missing", async ({ browser }) => {
    const context = await browser.newContext();
    await context.addInitScript(() => {
      Object.defineProperty(window, "Motion", { configurable: true, get() { return undefined; }, set() {} });
    });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "fx07");
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).locator(".cmp-item").first()).toBeVisible();
    expectClean(seen);
    await context.close();
  });
});

test.describe("completeness: axe-core no automated violations", () => {
  for (const scheme of ["light", "dark"]) {
    for (const expanded of [false, true]) {
      test(scheme + " theme" + (expanded ? ", groups expanded" : ""), async ({ browser }) => {
        const context = await browser.newContext({ colorScheme: scheme, reducedMotion: "reduce", bypassCSP: true });
        const page = await context.newPage();
        await open(page, "fx07");
        if (expanded) {
          await page.locator("#completeness details").evaluateAll((all) => all.forEach((d) => { d.open = true; }));
        }
        await page.evaluate(AXE);
        const violations = await page.evaluate(async () => {
          const result = await window.axe.run(document.getElementById("completeness"), {
            runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
          });
          return result.violations.map((v) => ({
            id: v.id, help: v.help,
            nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ") + " :: " + (n.failureSummary || "").replace(/\s+/g, " ").slice(0, 200)),
          }));
        });
        expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
        await context.close();
      });
    }
  }
});

test.describe("completeness: hostile fixture renders inert", () => {
  for (const scheme of ["light", "dark"]) {
    test(scheme + " theme", async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: scheme });
      const page = await context.newPage();
      const seen = watch(page);
      await open(page, "fx14");
      await expect(panel(page)).toBeVisible();
      await page.locator("#completeness details").evaluateAll((all) => all.forEach((d) => { d.open = true; }));
      const data = await island(page);
      const paths = data.completeness.items.flatMap((item) => item.sources.map((source) => source.path));
      expect(paths.length).toBeGreaterThan(0);
      const text = await panel(page).innerText();
      for (const path of paths) {
        expect(text.replace(/\s+/g, "")).toContain(path.replace(/\s+/g, ""));
      }
      const inert = await panel(page).evaluate((root) => {
        const allowed = new Set(["H2", "H3", "H4", "P", "UL", "LI", "DIV", "DL", "DT", "DD", "SPAN", "A", "DETAILS", "SUMMARY", "WBR"]);
        const nodes = [...root.querySelectorAll("*")];
        return {
          foreign: nodes.filter((n) => !allowed.has(n.tagName)).map((n) => n.tagName),
          handlers: nodes.filter((n) => [...n.attributes].some((a) => /^on/i.test(a.name))).length,
          badLinks: [...root.querySelectorAll("a")].filter((a) => !/^#[A-Za-z0-9_-]+$/.test(a.getAttribute("href"))).length,
        };
      });
      expect(inert).toEqual({ foreign: [], handlers: 0, badLinks: 0 });
      expect(seen.dialogs).toEqual([]);
      expect(seen.requests.filter((url) => !/^(file|data|blob|about):/.test(url))).toEqual([]);
      expectClean(seen);
      await context.close();
    });
  }
});
