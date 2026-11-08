const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const { test, expect } = require("@playwright/test");
const { open, watch } = require("./support");

const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const island = (page) => page.evaluate(() => JSON.parse(document.getElementById("report-data").textContent));
const motionSwitch = (page) => page.getByRole("switch", { name: /^Motion/ });

function expectClean(seen) {
  expect(seen.errors, "uncaught page errors").toEqual([]);
  expect(seen.consoleErrors, "console errors").toEqual([]);
  expect(seen.dialogs, "hostile dialogs").toEqual([]);
  expect(seen.requests.filter((url) => !/^(file|data|blob|about):/.test(url)), "network requests").toEqual([]);
}

async function ready(page, name = "fx07") {
  await open(page, name);
  await expect(page.locator("html")).not.toHaveClass(/booting|boot-failed/);
  await expect(page.locator("#hero-diagram svg")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

async function setMotion(page, on) {
  if (await motionSwitch(page).getAttribute("aria-checked") !== String(on)) await motionSwitch(page).click();
  await expect(page.locator("html")).toHaveAttribute("data-motion", on ? "on" : "off");
}

async function revealReport(page) {
  await page.evaluate(async () => {
    for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight / 2) {
      scrollTo({ top: y, behavior: "instant" });
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }
    scrollTo({ top: 0, behavior: "instant" });
  });
  await expect.poll(() => page.locator("[data-fx-reveal]").evaluateAll((all) =>
    all.filter((el) => getComputedStyle(el).opacity !== "1").length)).toBe(0);
}

test("the actual offline artifact stays within budget and hashes every executable script", async ({ page }) => {
  const seen = watch(page);
  await ready(page);
  const file = fs.readFileSync(path.join(process.env.NHB_UI_REPORT_DIR, "fx07", "report.html"));
  expect(file.length).toBeLessThan(650 * 1024);
  const scripts = await page.locator("script:not([type='application/json'])").allTextContents();
  const csp = await page.locator("meta[http-equiv='Content-Security-Policy']").getAttribute("content");
  expect(csp).toContain("default-src 'none'");
  expect(csp).not.toContain("'unsafe-eval'");
  for (const script of scripts) expect(csp).toContain("'sha256-" + crypto.createHash("sha256").update(script).digest("base64") + "'");
  expectClean(seen);
});

test("integrated halftone hosts render a shader when available and honest fallback otherwise", async ({ page }, info) => {
  const seen = watch(page);
  await ready(page);
  const hosts = page.locator("[data-fx-halftone]");
  await expect(hosts).toHaveCount(3);
  const canGL = await page.evaluate(() => !!document.createElement("canvas").getContext("webgl"));
  for (const host of await hosts.all()) {
    await expect(host).toHaveAttribute("aria-hidden", "true");
    await expect(host).toHaveAttribute("data-fx-state", canGL ? "gl" : "fallback");
    const state = await host.getAttribute("data-fx-state");
    info.annotations.push({ type: "integrated-halftone", description: state });
    const canvas = host.locator("canvas");
    await expect(canvas).toHaveAttribute("aria-hidden", "true");
    if (state === "gl") {
      const pixels = await canvas.evaluate((c) => {
        const copy = document.createElement("canvas");
        copy.width = c.width; copy.height = c.height;
        const ctx = copy.getContext("2d"); ctx.drawImage(c, 0, 0);
        const data = ctx.getImageData(0, 0, copy.width, copy.height).data;
        const levels = new Set();
        for (let i = 0; i < data.length; i += 64) levels.add(data[i]);
        return { width: c.width, height: c.height, levels: levels.size };
      });
      expect(pixels.width).toBeGreaterThan(1);
      expect(pixels.height).toBeGreaterThan(1);
      expect(pixels.levels).toBeGreaterThan(2);
    } else await expect(host.locator(".fx-halftone__fallback")).toBeVisible();
  }
  expectClean(seen);
});

test("forced no-WebGL keeps fallback decoration and the report tables readable", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (kind, ...args) {
      return /webgl/.test(kind) ? null : original.call(this, kind, ...args);
    };
  });
  const seen = watch(page);
  await ready(page);
  await setMotion(page, false);
  for (const host of await page.locator("[data-fx-halftone]").all()) {
    await expect(host).toHaveAttribute("data-fx-state", "fallback");
    await expect(host.locator(".fx-halftone__fallback")).toBeVisible();
  }
  await expect(page.locator("#summary-grid")).toBeVisible();
  await page.locator("#survival").scrollIntoViewIfNeeded();
  await expect(page.locator("#survival table").first()).toBeVisible();
  await page.locator("#rotation").scrollIntoViewIfNeeded();
  await expect(page.locator("#rotation")).toContainText("Rotation plan");
  expectClean(seen);
});

test("without the effects API the report still reads and responds", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, "NHBEffects", { configurable: true, get: () => undefined, set: () => {} }));
  const seen = watch(page);
  await ready(page);
  await setMotion(page, false);
  await expect(page.locator("#summary-grid")).toBeVisible();
  await page.locator("#survival").scrollIntoViewIfNeeded();
  await expect(page.locator("#survival table").first()).toBeVisible();
  await page.locator(".timeline .tl-row").first().focus();
  await expect(page.locator(".timeline .tl-detail")).toContainText("Ends with the entrypoint");
  expectClean(seen);
});

test("hero output counts and timeline rows preserve the real scenario data", async ({ page }) => {
  const root = path.resolve(__dirname, "..", "..");
  const out = fs.mkdtempSync(path.join(process.env.NHB_UI_REPORT_DIR, "fx07-rotating-"));
  const scan = spawnSync(process.env.NHB_PYTHON || path.join(root, ".venv", "Scripts", "python.exe"), [
    "-c", "from nhi_blast.cli.app import app; app()",
    "scan", path.join(root, "tests", "fixtures", "fx07-incident"),
    "--format", "html", "--out", out, "--repo-slug", "acme/shop",
    "--simulate-compromise", "action:tj-actions/changed-files@v45",
  ], { cwd: root, encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" } });
  expect(scan.status, scan.stdout + scan.stderr).toBe(0);
  await ready(page, path.basename(out));
  await setMotion(page, false);
  const data = await island(page);
  let rotatingSeen = false;
    for (const [scenarioIndex, scenario] of data.scenarios.entries()) {
    await page.locator("#scenario-picker").selectOption({ index: scenarioIndex });
    const partition = scenario.partition;
    for (const code of ["R", "E", "Z"]) {
      await expect(page.locator(".hd-value-" + code)).toHaveText(String(partition[code].length));
      await expect(page.locator("#hero-diagram-text")).toContainText(String(partition[code].length));
    }
    await expect(page.locator(".timeline .tl-row")).toHaveCount(["R", "E", "Z"].reduce((n, code) => n + Math.min(partition[code].length, 8), 0));
    const zRows = page.locator(".timeline .tl-row").filter({ has: page.locator(".tl-bar-z") });
    for (const [index, entry] of partition.Z.slice(0, 8).entries()) {
      const row = zRows.nth(index);
      expect(await row.getAttribute("aria-label")).toContain(entry.survival_window);
      await expect(row).toContainText(entry.survival_window);
      expect(await row.getAttribute("aria-label")).not.toMatch(/with no recorded expiry/);
      await row.focus();
      await expect(page.locator(".timeline .tl-detail")).toContainText(entry.survival_window);
    }
    rotatingSeen ||= partition.Z.some((entry) => entry.lifetime === "persistent_rotating");
    }
    expect(rotatingSeen, "fixture exercises bounded rotating Z").toBe(true);
  await expect(page.locator(".tl-axis")).not.toContainText("No expiry");
  await expect(page.locator(".tl-caption")).toContainText("not to scale");
});

test("Motion Off prevents new inspection animations, not merely CSS transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.addInitScript(() => {
    window.__inspectionAnimations = [];
    const original = Element.prototype.animate;
    Element.prototype.animate = function (...args) {
      if (this.id === "entity-details") window.__inspectionAnimations.push(document.documentElement.getAttribute("data-motion"));
      return original.apply(this, args);
    };
  });
  await ready(page);
  await setMotion(page, false);
  await page.locator(".gnode").first().focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#entity-details h3")).toBeVisible();
  expect(await page.evaluate(() => window.__inspectionAnimations)).toEqual([]);
  expect(await page.locator("#entity-details").evaluate((el) => el.style.opacity)).toBe("");
});

test("Motion Off and reduced-motion expose every content reveal immediately", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await ready(page);
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "false");
  const hidden = () => page.locator("[data-fx-reveal]").evaluateAll((all) => all.filter((el) => getComputedStyle(el).opacity !== "1").length);
  expect(await hidden()).toBe(0);
  await motionSwitch(page).focus();
  await page.keyboard.press("Space");
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Enter");
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "false");
  expect(await hidden()).toBe(0);
  await expect.poll(() => page.locator(".fx-journey__ink").getAttribute("stroke-dashoffset")).toBe("0.00");
});

test("scroll drawing advances the integrated SVG path and Motion Off finishes it", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await ready(page);
  await setMotion(page, true);
  const ink = page.locator("svg[data-fx-journey] .fx-journey__ink");
  await expect(ink).toHaveAttribute("d", /^M/);
  const offset = () => ink.evaluate((el) => Number(el.getAttribute("stroke-dashoffset")));
  const initial = await offset();
  expect(initial).toBeGreaterThan(0);
  await page.evaluate(() => scrollTo({ top: document.documentElement.scrollHeight / 2, behavior: "instant" }));
  await expect.poll(offset).toBeLessThan(initial);
  const midway = await offset();
  expect(midway).toBeGreaterThan(0);
  await page.evaluate(() => scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
  await expect.poll(offset).toBe(0);
  await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
  await expect.poll(offset).toBeGreaterThan(0);
  await setMotion(page, false);
  await expect.poll(offset).toBe(0);
});

test("live OS motion changes follow the system only until an explicit user choice", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await ready(page);
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "true");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "false");
  expect(await page.evaluate(() => localStorage.getItem("nhb-motion"))).toBeNull();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "true");
  await setMotion(page, false);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(motionSwitch(page)).toHaveAttribute("aria-checked", "false");
});

test("switching Motion Off finishes an in-progress inspection without hiding data", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.addInitScript(() => {
    const original = Element.prototype.animate;
    window.__presence = null;
    Element.prototype.animate = function (...args) {
      const animation = original.apply(this, args);
      if (this.id === "entity-details") { animation.pause(); window.__presence = animation; }
      return animation;
    };
  });
  await ready(page);
  await setMotion(page, true);
  const started = await page.evaluate(() => {
    const node = document.querySelector(".gnode");
    node.focus();
    node.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    const started = Boolean(window.__presence);
    window.NHBTheme.setMotion(false);
    return { started, opacity: document.getElementById("entity-details").style.opacity };
  });
  expect(started.started, "inspection animation was in progress at disable").toBe(true);
  expect(started.opacity, "disable restores content synchronously").toBe("");
  await expect.poll(() => page.locator("#entity-details").evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  await expect(page.locator("#entity-details h3")).toBeVisible();
  expect(await page.evaluate(() => window.__presence.playState)).not.toBe("paused");
});

test("R prose describes job end or token expiry rather than immediate revocation", async ({ page }) => {
  await ready(page);
  await setMotion(page, false);
  await expect(page.locator("#summary-grid")).not.toContainText("end when it is revoked");
  await expect(page.locator("#summary-grid")).toContainText("job end or token expiry");
  await expect(page.locator("#read-guide")).not.toContainText("ending when that entrypoint is revoked");
});

for (const scheme of ["light", "dark"]) {
  for (const width of [320, 375, 768, 1050, 1440]) {
    test(scheme + " report has no page overflow at " + width + " px", async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      const seen = watch(page);
      for (const name of ["fx07", "fx01", "fx14"]) {
        await ready(page, name);
        const sizes = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
        expect(sizes.scroll, name + " page scrollWidth").toBeLessThanOrEqual(sizes.client);
        await expect(motionSwitch(page)).toBeVisible();
      }
      expectClean(seen);
    });
  }
  for (const on of [true, false]) {
    test(scheme + " full-page axe with Motion " + (on ? "On" : "Off"), async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: scheme, reducedMotion: "no-preference", bypassCSP: true });
      const page = await context.newPage();
      await ready(page);
      await setMotion(page, on);
      if (on) await revealReport(page);
      await page.evaluate(AXE);
      const violations = await page.evaluate(async () => (await axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
      })).violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })) })));
      expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
      await context.close();
    });
  }
  test(scheme + " phone menu supports keyboard entry, a focus cycle and Escape", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 844 });
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
    await ready(page);
    const toggle = page.locator("#nav-toggle");
    const links = page.locator("#nav-panel a:not([hidden])");
    await expect(links.first()).toBeHidden();
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(links.first()).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(toggle).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(links.last()).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(toggle).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toBeFocused();
    await expect(links.first()).toBeHidden();
    await page.keyboard.press("Space");
    await links.filter({ hasText: /^Graph$/ }).click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#graph")).toBeInViewport();
  });
  test(scheme + " hostile fixture stays text even after effects and inspection", async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const seen = watch(page);
    await ready(page, "fx14");
    await setMotion(page, false);
    await page.locator("details").evaluateAll((all) => all.forEach((el) => { el.open = true; }));
    const data = await island(page);
    const hostile = data.graph.nodes.filter((node) => /<|onerror|script/i.test(node.label));
    expect(hostile.length).toBeGreaterThan(0);
    for (const node of hostile) expect(await page.locator("body").textContent()).toContain(node.label);
    expect(await page.locator("img, iframe, object, embed, script[src]").count()).toBe(0);
    expect(await page.evaluate(() => [...document.querySelectorAll("*")].filter((el) => [...el.attributes].some((a) => /^on/i.test(a.name))).length)).toBe(0);
    expectClean(seen);
  });
}
