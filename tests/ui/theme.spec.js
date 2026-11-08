const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");
const { open, theme, watch } = require("./support");

const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const group = (page) => page.getByRole("radiogroup", { name: "Colour theme" });
const radio = (page, name) => group(page).getByRole("radio", { name, exact: true });

function expectClean(seen) {
  expect(seen.errors, "uncaught page errors").toEqual([]);
  expect(seen.consoleErrors, "console errors").toEqual([]);
}

async function expectRendered(page) {
  await expect(page.locator("html")).not.toHaveClass(/booting|boot-failed/);
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.locator("#summary-grid")).toBeVisible();
  await expect(page.locator(".graph-svg")).toHaveCount(1);
}

test.describe("default theme follows the system", () => {
  // Current engines never report "no preference": prefers-color-scheme is light or dark.
  for (const scheme of ["light", "dark"]) {
    test("emulated colorScheme " + scheme, async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: scheme });
      const page = await context.newPage();
      const seen = watch(page);
      await open(page, "fx07");
      await expect.poll(() => theme(page)).toEqual({ theme: scheme === "light" ? "light" : "dark", choice: "system" });
      await expect(radio(page, "System")).toHaveAttribute("aria-checked", "true");
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      // G5 owner design system: --dp-ground is #fcfcfd in the light theme and #0e1116 in the dark one.
      expect(bg).toBe(scheme === "light" ? "rgb(252, 252, 253)" : "rgb(14, 17, 22)");
      expectClean(seen);
      await context.close();
    });
  }

  test("a live system change updates the theme only while the choice is System", async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: "dark" });
    const page = await context.newPage();
    await open(page, "fx07");
    await page.emulateMedia({ colorScheme: "light" });
    await expect.poll(() => theme(page).then((t) => t.theme)).toBe("light");
    await radio(page, "Dark").click();
    await page.emulateMedia({ colorScheme: "dark" });
    await page.emulateMedia({ colorScheme: "light" });
    await expect.poll(async () => (await theme(page)).theme).toBe("dark");
    await context.close();
  });
});

test.describe("switcher", () => {
  test("is a labelled radiogroup with three visible options", async ({ page }) => {
    await open(page, "fx07");
    await expect(group(page)).toBeVisible();
    for (const name of ["System", "Light", "Dark"]) {
      await expect(radio(page, name)).toBeVisible();
      await expect(radio(page, name)).toHaveText(name);
    }
  });

  test("each option changes data-theme and persists across reload", async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: "light" });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "fx07");
    await radio(page, "Dark").click();
    await expect.poll(() => theme(page)).toEqual({ theme: "dark", choice: "dark" });
    await expect(radio(page, "Dark")).toHaveAttribute("aria-checked", "true");
    await page.reload();
    await page.waitForSelector("html:not(.booting)", { state: "attached" });
    await expect.poll(() => theme(page)).toEqual({ theme: "dark", choice: "dark" });
    await radio(page, "Light").click();
    await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "light" });
    await page.reload();
    await page.waitForSelector("html:not(.booting)", { state: "attached" });
    await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "light" });
    await radio(page, "System").click();
    await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "system" });
    await page.reload();
    await page.waitForSelector("html:not(.booting)", { state: "attached" });
    await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "system" });
    expectClean(seen);
    await context.close();
  });

  test("the early script sets the theme before the first paint", async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: "light" });
    await context.addInitScript(() => {
      window.__first = null;
      new MutationObserver((records, observer) => {
        if (document.body) {
          window.__first = document.documentElement.getAttribute("data-theme");
          observer.disconnect();
        }
      }).observe(document, { childList: true, subtree: true });
    });
    const page = await context.newPage();
    await open(page, "fx07");
    expect(await page.evaluate(() => window.__first)).toBe("light");
    await context.close();
  });
});

test.describe("storage failure", () => {
  const variants = {
    "sessionStorage getter throws SecurityError": () => {
      Object.defineProperty(window, "sessionStorage", {
        configurable: true,
        get() { throw new DOMException("The operation is insecure.", "SecurityError"); },
      });
    },
    "setItem throws QuotaExceededError": () => {
      Storage.prototype.setItem = function () {
        throw new DOMException("quota", "QuotaExceededError");
      };
    },
    "getItem throws": () => {
      Storage.prototype.getItem = function () { throw new DOMException("denied", "SecurityError"); };
    },
  };
  for (const [label, script] of Object.entries(variants)) {
    test(label, async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: "dark" });
      await context.addInitScript(script);
      const page = await context.newPage();
      const seen = watch(page);
      await open(page, "fx07");
      await expectRendered(page);
      await expect.poll(() => theme(page)).toEqual({ theme: "dark", choice: "system" });
      await radio(page, "Light").click();
      await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "light" });
      await radio(page, "Dark").click();
      await expect.poll(() => theme(page)).toEqual({ theme: "dark", choice: "dark" });
      await radio(page, "Light").click();
      await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "light" });
      await expectRendered(page);
      expectClean(seen);
      await context.close();
    });
  }
});

test("offline: no network requests and the report renders fully", async ({ browser }) => {
  const context = await browser.newContext({ offline: true });
  await context.route((url) => !/^(file|data|blob|about):/.test(url.href), (route) => route.abort());
  const page = await context.newPage();
  const seen = watch(page);
  await open(page, "fx07");
  await expectRendered(page);
  await radio(page, "Light").click();
  await radio(page, "Dark").click();
  const external = seen.requests.filter((url) => !/^(file|data|blob|about):/.test(url));
  expect(external).toEqual([]);
  expectClean(seen);
  await context.close();
});

test("content is visible when the animation runtime is missing", async ({ browser }) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    Object.defineProperty(window, "Motion", { configurable: true, get() { return undefined; }, set() {} });
  });
  const page = await context.newPage();
  const seen = watch(page);
  await open(page, "fx07");
  await expectRendered(page);
  expectClean(seen);
  await context.close();
});

test.describe("reduced motion", () => {
  test("reduce: no transition and no errors on theme change", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", colorScheme: "dark" });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "fx07");
    const result = await page.evaluate(() => {
      window.NHBTheme.setChoice("light");
      return {
        switching: document.documentElement.classList.contains("theme-switching"),
        duration: getComputedStyle(document.body).transitionDuration,
        theme: document.documentElement.getAttribute("data-theme"),
      };
    });
    // G6: with Motion off no transition is defined at all.
    expect(result.switching).toBe(false);
    expect(result.theme).toBe("light");
    expect(parseFloat(result.duration) * 1000).toBeLessThanOrEqual(1);
    expectClean(seen);
    await context.close();
  });

  test("motion on: the theme change goes through the effects layer without errors", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference", colorScheme: "dark" });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "fx07");
    await expect(page.locator("html")).toHaveAttribute("data-motion", "on");
    await page.evaluate(() => window.NHBTheme.setChoice("light"));
    await expect.poll(() => theme(page).then((value) => value.theme)).toBe("light");
    expectClean(seen);
    await context.close();
  });

  test("without the effects layer a colour transition of at most 240 ms is used", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference", colorScheme: "dark" });
    await context.addInitScript(() => {
      Object.defineProperty(window, "NHBEffects", { configurable: true, get() { return undefined; }, set() {} });
    });
    const page = await context.newPage();
    await open(page, "fx07");
    const result = await page.evaluate(() => {
      window.NHBTheme.setChoice("light");
      const style = getComputedStyle(document.body);
      return {
        switching: document.documentElement.classList.contains("theme-switching"),
        durations: style.transitionDuration.split(",").map((value) => parseFloat(value) * 1000),
      };
    });
    expect(result.switching).toBe(true);
    expect(Math.max(...result.durations)).toBeLessThanOrEqual(240);
    await expect(page.locator("html")).not.toHaveClass(/theme-switching/);
    await context.close();
  });
});

test("keyboard only: tab into the group, arrows move and select, focus is visible", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "dark" });
  const page = await context.newPage();
  const seen = watch(page);
  await open(page, "fx07");
  const onOption = () => page.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-theme-value"));
  let reached = null;
  for (let step = 0; step < 40 && !reached; step += 1) {
    await page.keyboard.press("Tab");
    reached = await onOption();
  }
  expect(reached).toBe("system");
  const ring = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement);
    return { style: style.outlineStyle, width: parseFloat(style.outlineWidth), color: style.outlineColor,
      focus: getComputedStyle(document.documentElement).getPropertyValue("--focus").trim() };
  });
  expect(ring.style).toBe("solid");
  expect(ring.width).toBeGreaterThanOrEqual(2);
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => theme(page)).toEqual({ theme: "light", choice: "light" });
  expect(await onOption()).toBe("light");
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => theme(page)).toEqual({ theme: "dark", choice: "dark" });
  expect(await onOption()).toBe("dark");
  await page.keyboard.press("ArrowRight");
  await expect.poll(async () => (await theme(page)).choice).toBe("system");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await theme(page)).choice).toBe("dark");
  await page.keyboard.press("Home");
  await expect.poll(async () => (await theme(page)).choice).toBe("system");
  await page.keyboard.press("End");
  await expect.poll(async () => (await theme(page)).choice).toBe("dark");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => (await theme(page)).choice).toBe("light");
  await page.keyboard.press("Tab");
  expect(await onOption()).toBeNull();
  await page.keyboard.press("Shift+Tab");
  expect(await onOption()).toBe("light");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("Space");
  await expect.poll(async () => (await theme(page)).choice).toBe("system");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await theme(page)).choice).toBe("light");
  expectClean(seen);
  await context.close();
});

test.describe("axe-core: no automated violations", () => {
  for (const scheme of ["light", "dark"]) {
    test(scheme + " theme", async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: scheme, reducedMotion: "reduce", bypassCSP: true });
      const page = await context.newPage();
      await open(page, "fx07");
      await radio(page, scheme === "light" ? "Light" : "Dark").click();
      await expect.poll(async () => (await theme(page)).theme).toBe(scheme);
      await page.evaluate(AXE);
      const violations = await page.evaluate(async () => {
        const result = await window.axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
        });
        return result.violations.map((v) => ({
          id: v.id, impact: v.impact, help: v.help,
          nodes: v.nodes.slice(0, 6).map((n) => n.target.join(" ") + " :: " + (n.failureSummary || "").replace(/\s+/g, " ").slice(0, 220)),
        }));
      });
      expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
      await context.close();
    });
  }
});

test.describe("hostile fixture renders inert", () => {
  for (const scheme of ["light", "dark"]) {
    test(scheme + " theme", async ({ browser }) => {
      const context = await browser.newContext({ colorScheme: scheme });
      const page = await context.newPage();
      const seen = watch(page);
      await open(page, "fx14");
      await expect(page.locator("html")).not.toHaveClass(/boot-failed/);
      await expect(page.locator("h1")).toBeVisible();
      await expect.poll(async () => (await theme(page)).theme).toBe(scheme);
      const dom = await page.evaluate(() => ({
        handlers: [...document.querySelectorAll("*")].filter((el) => [...el.attributes].some((a) => /^on/i.test(a.name))).length,
        images: document.querySelectorAll("img, iframe, object, embed, link[rel=stylesheet]").length,
        externalScripts: document.querySelectorAll("script[src]").length,
        scripts: document.querySelectorAll("script").length,
      }));
      expect(dom).toEqual({ handlers: 0, images: 0, externalScripts: 0, scripts: 5 });
      expect(seen.dialogs).toEqual([]);
      const external = seen.requests.filter((url) => !/^(file|data|blob|about):/.test(url));
      expect(external).toEqual([]);
      expectClean(seen);
      await context.close();
    });
  }
});
