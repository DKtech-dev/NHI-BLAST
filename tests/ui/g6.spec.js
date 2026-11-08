const fs = require("node:fs");
const { test, expect } = require("@playwright/test");
const { open, theme, watch } = require("./support");

const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const WIDTHS = [320, 375, 390, 768, 1050, 1440];
const island = (page) => page.evaluate(() => JSON.parse(document.getElementById("report-data").textContent));

function expectClean(seen) {
  expect(seen.errors, "uncaught page errors").toEqual([]);
  expect(seen.consoleErrors, "console errors").toEqual([]);
}

async function scrollThrough(page) {
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < height; y += 600) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(60);
  }
  await page.locator("#tagline").scrollIntoViewIfNeeded();
  await page.waitForTimeout(1400);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
}

async function installFrameControl(page) {
  await page.addInitScript(() => {
    const request = window.requestAnimationFrame.bind(window);
    const pending = new Set();
    window.requestAnimationFrame = (callback) => {
      let id;
      id = request((time) => { pending.delete(id); callback(time); });
      pending.add(id);
      return id;
    };
    window.pauseDecorativeFrames = () => {
      for (const id of pending) window.cancelAnimationFrame(id);
      pending.clear();
      window.requestAnimationFrame = () => 0;
    };
  });
}

test.describe("layout never overflows horizontally", () => {
  for (const scheme of ["light", "dark"]) {
    for (const width of WIDTHS) {
      test(scheme + " theme at " + width + " px", async ({ browser }) => {
        const context = await browser.newContext({ colorScheme: scheme, viewport: { width, height: 844 } });
        const page = await context.newPage();
        const seen = watch(page);
        for (const name of ["fx07", "fx01"]) {
          await open(page, name);
          const sizes = await page.evaluate(() => ({
            sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
          }));
          expect(sizes.sw, name + " scrollWidth").toBeLessThanOrEqual(sizes.cw);
        }
        expectClean(seen);
        await context.close();
      });
    }
  }
});

test("the primary action is in the first screen at 390 px", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await open(page, "fx07");
  const cta = page.locator(".hero-actions .button.primary");
  await expect(cta).toHaveText("Review rotation order");
  const box = await cta.boundingBox();
  expect(box.y + box.height).toBeLessThanOrEqual(844);
  await context.close();
});

test.describe("section nav", () => {
  for (const width of [1440, 1280, 1050, 900, 761]) {
    test("never clips at " + width + " px", async ({ browser }) => {
      const context = await browser.newContext({ viewport: { width, height: 800 } });
      const page = await context.newPage();
      await open(page, "fx07");
      const result = await page.evaluate(() => {
        const pill = document.querySelector(".toc").getBoundingClientRect();
        const track = document.querySelector(".toc-track");
        const links = [...track.querySelectorAll("a:not([hidden])")];
        track.scrollLeft = track.scrollWidth;
        const last = links[links.length - 1].getBoundingClientRect();
        const trackRect = track.getBoundingClientRect();
        return {
          pillLeft: pill.left, pillRight: pill.right, vw: window.innerWidth,
          lastReachable: last.right <= trackRect.right + 1,
          scrollable: track.scrollWidth > track.clientWidth + 2,
          fadeSet: getComputedStyle(track).getPropertyValue("--fade-l").trim(),
        };
      });
      expect(result.pillLeft).toBeGreaterThanOrEqual(0);
      expect(result.pillRight).toBeLessThanOrEqual(result.vw);
      expect(result.lastReachable).toBe(true);
      if (width >= 1280) { expect(result.scrollable).toBe(false); }
      await context.close();
    });
  }

  test("on a phone the menu opens a full height panel, traps focus and closes with Escape", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "fx07");
    const toggle = page.locator("#nav-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator(".toc a").first()).toBeHidden();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = await page.locator("#nav-panel").boundingBox();
    expect(panel.height).toBeGreaterThanOrEqual(844 - 1);
    await expect(page.locator(".toc a").first()).toBeVisible();
    for (let step = 0; step < 20; step += 1) { await page.keyboard.press("Tab"); }
    const inside = await page.evaluate(() => {
      const active = document.activeElement;
      return active === document.getElementById("nav-toggle") || Boolean(active.closest("#nav-panel"));
    });
    expect(inside).toBe(true);
    await page.keyboard.press("Escape");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toBeFocused();
    await toggle.click();
    await page.locator('.toc a[href="#graph"]').click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#nav-current")).toHaveText(/Graph|Survival|Rotation|Findings/);
    expectClean(seen);
    await context.close();
  });
});

test.describe("survival timeline", () => {
  test("mirrors the partition in the report data", async ({ page }) => {
    await open(page, "fx07");
    const data = await island(page);
    const partition = data.scenarios[0].partition;
    const rows = page.locator(".timeline .tl-row");
    const cap = (n) => Math.min(n, 8);
    await expect(rows).toHaveCount(cap(partition.R.length) + cap(partition.E.length) + cap(partition.Z.length));
    await expect(page.locator(".timeline .tl-bar-e")).toHaveCount(cap(partition.E.length));
    await expect(page.locator(".timeline .tl-bar-z")).toHaveCount(cap(partition.Z.length));
    await expect(page.locator(".timeline .tl-mark")).toHaveCount(cap(partition.R.length));
    const seconds = partition.E[0].ttl_seconds;
    const label = seconds % 3600 === 0 ? (seconds / 3600) + " h" : seconds % 60 === 0 ? (seconds / 60) + " min" : seconds + " s";
    await expect(page.locator(".timeline .tl-ttl").first()).toHaveText("up to " + label);
    await expect(page.locator(".timeline .tl-axis")).toContainText("Revoked now");
    await expect(page.locator(".timeline .tl-axis")).toContainText("Job ends");
    await expect(page.locator(".timeline .tl-axis")).toContainText(label);
    await expect(page.locator(".timeline .tl-axis")).toContainText("After revocation");
    for (const row of await rows.all()) {
      expect(await row.getAttribute("aria-label")).not.toBe("");
      expect(await row.getAttribute("tabindex")).toBe("0");
    }
    // The real table stays as the accessible equivalent.
    await expect(page.locator("#survival table").first()).toBeAttached();
  });

  test("a focused row shows its detail line", async ({ page }) => {
    await open(page, "fx07");
    const row = page.locator(".timeline .tl-row").nth(3);
    await row.focus();
    await expect(page.locator(".timeline .tl-detail")).toContainText("Expires on its own, up to");
  });
});

test.describe("effects layer contract", () => {
  test("at most three halftone hosts, masked so the title side stays quiet", async ({ page }) => {
    await open(page, "fx07");
    const hosts = await page.locator("[data-fx-halftone]").count();
    expect(hosts).toBe(3);
    const mask = await page.locator(".hero-field").evaluate((el) => {
      const style = getComputedStyle(el);
      return { mask: style.maskImage || style.webkitMaskImage, opacity: style.opacity };
    });
    expect(mask.mask).toMatch(/transparent|rgba\(0, 0, 0, 0\)/);
    expect(Number(mask.opacity)).toBeGreaterThan(0);
    expect(Number(mask.opacity)).toBeLessThanOrEqual(0.2);
  });

  test("the journey and the progress bar follow the scroll position", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference", viewport: { width: 1440, height: 900 } });
    try {
      const page = await context.newPage();
      await open(page, "fx07");
      const read = () => page.evaluate(() => {
        const bar = document.querySelector(".fx-progress");
        return Number(bar ? getComputedStyle(bar).getPropertyValue("--fx-progress") || bar.style.getPropertyValue("--fx-progress") : -1);
      });
      const top = await read();
      // CSS smooth scrolling need not have started at the sample time; set actual positions.
      await page.evaluate(() => window.scrollTo({ top: (document.documentElement.scrollHeight - innerHeight) / 2, behavior: "instant" }));
      await page.waitForTimeout(300);
      const half = await read();
      const halfPosition = await page.evaluate(() => scrollY / (document.documentElement.scrollHeight - innerHeight));
      await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
      await page.waitForTimeout(300);
      const bottom = await read();
      expect(top).toBeGreaterThanOrEqual(0);
      expect(top).toBeLessThan(0.05);
      expect(halfPosition).toBeCloseTo(0.5, 2);
      expect(half).toBeGreaterThan(top);
      expect(half).toBeCloseTo(0.5, 2);
      expect(bottom).toBeGreaterThan(half);
      expect(bottom).toBeCloseTo(1, 2);
      await expect(page.locator("svg[data-fx-journey] path").first()).toBeAttached();
    } finally {
      await context.close();
    }
  });

  test("count ups finish on the exact figures", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference", viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await open(page, "fx07");
    const data = await island(page);
    const partition = data.scenarios[0].partition;
    await page.locator("#summary-grid").scrollIntoViewIfNeeded();
    await page.waitForTimeout(1800);
    const values = await page.locator("#summary-grid .stat-value").allTextContents();
    expect(values.slice(0, 3)).toEqual([String(partition.Z.length), String(partition.R.length), String(partition.E.length)]);
    expect(values[3]).toBe(String(data.findings.length));
    await context.close();
  });

  test("the tagline words are real text and all lit when motion is off", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await open(page, "fx07");
    const text = await page.locator("#tagline-text").innerText();
    expect(text).toContain("Know what survives revocation.");
    expect(text).toContain("Rotate in the order that keeps the next secret safe.");
    const opacities = await page.locator("#tagline-text .tl-w").evaluateAll((all) => all.map((w) => getComputedStyle(w).opacity));
    expect(new Set(opacities)).toEqual(new Set(["1"]));
    await context.close();
  });
});

test.describe("motion switch", () => {
  test("defaults from reduced motion, toggles, and persists", async ({ browser }) => {
    const reduced = await browser.newContext({ reducedMotion: "reduce" });
    const page = await reduced.newPage();
    await open(page, "fx07");
    const sw = page.getByRole("switch", { name: /Motion/ });
    await expect(sw).toHaveAttribute("aria-checked", "false");
    await expect(sw).toContainText("Off");
    await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
    await sw.click();
    await expect(sw).toHaveAttribute("aria-checked", "true");
    await expect(sw).toContainText("On");
    await expect(page.locator("html")).toHaveAttribute("data-motion", "on");
    await page.reload();
    await page.waitForSelector("html:not(.booting)", { state: "attached" });
    await expect(page.getByRole("switch", { name: /Motion/ })).toHaveAttribute("aria-checked", "true");
    await reduced.close();
    const free = await browser.newContext({ reducedMotion: "no-preference" });
    const second = await free.newPage();
    await open(second, "fx07");
    await expect(second.getByRole("switch", { name: /Motion/ })).toHaveAttribute("aria-checked", "true");
    await second.getByRole("switch", { name: /Motion/ }).press("Space");
    await expect(second.getByRole("switch", { name: /Motion/ })).toHaveAttribute("aria-checked", "false");
    await free.close();
  });

  test("works with storage blocked and leaves no console error", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference" });
    await context.addInitScript(() => {
      Object.defineProperty(window, "sessionStorage", {
        configurable: true,
        get() { throw new DOMException("The operation is insecure.", "SecurityError"); },
      });
    });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "fx07");
    const sw = page.getByRole("switch", { name: /Motion/ });
    await sw.click();
    await expect(sw).toHaveAttribute("aria-checked", "false");
    await sw.click();
    await expect(sw).toHaveAttribute("aria-checked", "true");
    await expect(page.locator("h1")).toBeVisible();
    expectClean(seen);
    await context.close();
  });

  test("with motion off a pressed button does not move", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await open(page, "fx07");
    const button = page.locator(".hero-actions .button.primary");
    await button.hover();
    await page.mouse.down();
    const transform = await button.evaluate((el) => getComputedStyle(el).transform);
    await page.mouse.up();
    expect(["none", "matrix(1, 0, 0, 1, 0, 0)"]).toContain(transform);
    await context.close();
  });
});

test("every control in the first stops shows a focus ring", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await open(page, "fx07");
  for (let step = 0; step < 22; step += 1) {
    await page.keyboard.press("Tab");
    const ring = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) { return null; }
      const style = getComputedStyle(el);
      return { tag: el.tagName, style: style.outlineStyle, width: parseFloat(style.outlineWidth), shadow: style.boxShadow };
    });
    if (ring) { expect(ring.style !== "none" && ring.width > 0, JSON.stringify(ring)).toBe(true); }
  }
  await context.close();
});

test.describe("essential report data under delayed decorative frames", () => {
  test("metrics remain exact when decorative frames are suspended", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference", viewport: { width: 1440, height: 900 } });
    try {
      const page = await context.newPage();
      await installFrameControl(page);
      await open(page, "fx07");
      const data = await island(page);
      const partition = data.scenarios[0].partition;
      await page.evaluate(() => {
        window.pauseDecorativeFrames();
        const summary = document.getElementById("summary-grid");
        window.scrollTo({ top: summary.getBoundingClientRect().top + scrollY, behavior: "instant" });
      });
      await page.waitForTimeout(300);
      const values = await page.locator("#summary-grid .stat-value").allTextContents();
      expect(values).toEqual([String(partition.Z.length), String(partition.R.length), String(partition.E.length), String(data.findings.length), String(data.findings.filter((finding) => finding.severity === "CRITICAL").length)]);
    } finally {
      await context.close();
    }
  });

  test("scroll progress remains exact when decorative frames are suspended", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference", viewport: { width: 1440, height: 900 } });
    try {
      const page = await context.newPage();
      await installFrameControl(page);
      await open(page, "fx07");
      const progress = () => page.locator(".fx-progress").evaluate((bar) => Number(getComputedStyle(bar).getPropertyValue("--fx-progress")));
      await page.evaluate(() => {
        window.pauseDecorativeFrames();
        window.scrollTo({ top: (document.documentElement.scrollHeight - innerHeight) / 2, behavior: "instant" });
      });
      await page.waitForTimeout(300);
      expect(await page.evaluate(() => scrollY / (document.documentElement.scrollHeight - innerHeight))).toBeCloseTo(0.5, 2);
      expect(await progress()).toBeCloseTo(0.5, 2);
      await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
      await page.waitForTimeout(300);
      expect(await progress()).toBeCloseTo(1, 2);
    } finally {
      await context.close();
    }
  });
});

test.describe("completeness status readability", () => {
  for (const motion of ["off", "on"]) {
    test("status badges stay fully readable with motion " + motion, async ({ browser }) => {
      const context = await browser.newContext({
        colorScheme: "light", reducedMotion: motion === "on" ? "no-preference" : "reduce",
        viewport: { width: 1440, height: 900 },
      });
      try {
        const page = await context.newPage();
        await open(page, "fx07");
        await expect(page.locator("html")).toHaveAttribute("data-motion", motion);
        const badges = await page.locator(".cmp-counts .cmp-status, .class-list > li, .notes-list li, .evidence-guide, .guide-card, .stat, .outcome").evaluateAll((nodes) => nodes.map((badge) => {
          let opacity = 1;
          for (let element = badge; element; element = element.parentElement) {
            opacity *= Number(getComputedStyle(element).opacity);
          }
          return { label: badge.textContent, opacity };
        }));
        expect(badges.length).toBeGreaterThan(0);
        for (const badge of badges) {
          expect(badge.opacity, JSON.stringify(badge)).toBeCloseTo(1, 4);
        }
      } finally {
        await context.close();
      }
    });
  }
});

test.describe("axe-core: the whole page has no automated violations", () => {
  for (const scheme of ["light", "dark"]) {
    for (const motion of ["off", "on"]) {
      test(scheme + " theme, motion " + motion, async ({ browser }) => {
        const context = await browser.newContext({
          colorScheme: scheme, reducedMotion: motion === "on" ? "no-preference" : "reduce", bypassCSP: true,
          viewport: { width: 1440, height: 900 },
        });
        const page = await context.newPage();
        await open(page, "fx07");
        if (motion === "on") { await scrollThrough(page); }
        await page.evaluate(AXE);
        const violations = await page.evaluate(async () => {
          const result = await window.axe.run(document, {
            runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
          });
          return result.violations.map((v) => ({
            id: v.id, help: v.help,
            nodes: v.nodes.slice(0, 5).map((n) => n.target.join(" ") + " :: " + (n.failureSummary || "").replace(/\s+/g, " ").slice(0, 220)),
          }));
        });
        expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
        await context.close();
      });
    }
  }
});
