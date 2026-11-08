// Browser tests for the effects module (plan G6). Runs against a harness page built from the real
// EFFECTS_CSS / EFFECTS_JS strings with a strict hash-based CSP. WebGL is not available in every headless
// engine: each test asserts the real-WebGL path when a context can be created and the fallback path otherwise,
// and annotates which one ran.
const fs = require("node:fs");
const { test, expect } = require("@playwright/test");
const { harness } = require("./effects-fixture");

const AXE = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const HERO = "#hero canvas";

function watch(page) {
  const seen = { errors: [], consoleErrors: [], requests: [], dialogs: [] };
  page.on("pageerror", (e) => seen.errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") seen.consoleErrors.push(m.text()); });
  page.on("request", (r) => seen.requests.push(r.url()));
  page.on("dialog", (d) => { seen.dialogs.push(d.message()); d.dismiss(); });
  return seen;
}

function expectClean(seen) {
  expect(seen.errors, "uncaught page errors").toEqual([]);
  expect(seen.consoleErrors, "console errors").toEqual([]);
  expect(seen.dialogs, "dialogs from hostile text").toEqual([]);
  expect(seen.requests.filter((u) => !u.startsWith("file:")), "network requests").toEqual([]);
}

async function open(page, query) {
  await page.goto(harness().url(query));
  await page.waitForSelector("html.js-fx", { state: "attached" });
  await page.waitForTimeout(150);
}

const state = (page, sel = "#hero") => page.locator(sel).getAttribute("data-fx-state");

// Returns true when the real WebGL path runs; false when the fallback runs and WebGL is genuinely unavailable.
async function path(page, testInfo, sel = "#hero") {
  const s = await state(page, sel);
  const canCreate = await page.evaluate(() => !!document.createElement("canvas").getContext("webgl"));
  if (s === "gl") {
    testInfo.annotations.push({ type: "halftone", description: "webgl" });
    return true;
  }
  expect(canCreate, "fallback shown although WebGL can be created").toBe(false);
  expect(s).toBe("fallback");
  testInfo.annotations.push({ type: "halftone", description: "fallback (no WebGL context)" });
  return false;
}

const url = (page, sel = HERO) => page.evaluate((s) => document.querySelector(s).toDataURL(), sel);

const stats = (page, sel = HERO) => page.evaluate((s) => {
  const c = document.querySelector(s);
  const t = document.createElement("canvas");
  t.width = c.width; t.height = c.height;
  const g = t.getContext("2d");
  g.drawImage(c, 0, 0);
  const d = g.getImageData(0, 0, t.width, t.height).data;
  let sum = 0, sum2 = 0, n = 0;
  const levels = new Set();
  for (let i = 0; i < d.length; i += 16) {
    const l = (d[i] + d[i + 1] + d[i + 2]) / 3;
    sum += l; sum2 += l * l; n++; levels.add(d[i] >> 4);
  }
  const mean = sum / n;
  return { w: c.width, h: c.height, mean, sd: Math.sqrt(Math.max(0, sum2 / n - mean * mean)), levels: levels.size, corner: [d[0], d[1], d[2]] };
}, sel);

// Mean luminance in a box around a host-relative CSS-pixel point.
const region = (page, x, y, r, sel = HERO) => page.evaluate(([s, x, y, r]) => {
  const c = document.querySelector(s);
  const k = c.width / c.clientWidth;
  const t = document.createElement("canvas");
  t.width = c.width; t.height = c.height;
  const g = t.getContext("2d");
  g.drawImage(c, 0, 0);
  const x0 = Math.max(0, Math.round((x - r) * k)), y0 = Math.max(0, Math.round((y - r) * k));
  const w = Math.max(1, Math.min(t.width - x0, Math.round(2 * r * k))), h = Math.max(1, Math.min(t.height - y0, Math.round(2 * r * k)));
  const d = g.getImageData(x0, y0, w, h).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += (d[i] + d[i + 1] + d[i + 2]) / 3;
  return sum / (d.length / 4);
}, [sel, x, y, r]);

const opacity = (page, sel) => page.locator(sel).evaluate((e) => getComputedStyle(e).opacity);
const offset = (page) => page.locator("#jsvg .fx-journey__ink").evaluate((e) => parseFloat(e.getAttribute("stroke-dashoffset")));
const scrollTo = (page, y) => page.evaluate((v) => window.scrollTo(0, v), y);
const maxScroll = (page) => page.evaluate(() => document.documentElement.scrollHeight - innerHeight);

test.describe("harness and CSP", () => {
  test("the page runs under a hash-only CSP without errors or requests", async ({ page }, info) => {
    const seen = watch(page);
    await open(page, "motion=on");
    await path(page, info);
    expect(await page.evaluate(() => document.documentElement.getAttribute("data-motion"))).toBe("on");
    await page.mouse.move(300, 200);
    await page.waitForTimeout(300);
    expectClean(seen);
  });

  test("hostile text stays inert", async ({ page }) => {
    const seen = watch(page);
    await open(page, "motion=on");
    await expect(page.locator("#hostile")).toContainText("<img src=x onerror=alert(1)>");
    expect(await page.locator("#hostile img, #hostile script").count()).toBe(0);
    expect(await page.locator("#count-bad").textContent()).toBe("<b>12</b>");
    await scrollTo(page, 1300);
    await page.waitForTimeout(500);
    expect(await page.locator("#count-bad").textContent()).toBe("<b>12</b>");
    expect(await page.locator("#count-bad b").count()).toBe(0);
    expectClean(seen);
  });
});

test.describe("halftone", () => {
  test("renders a non-blank frame on the dark ground and differs across 600 ms with motion on", async ({ page }, info) => {
    const seen = watch(page);
    await open(page, "motion=on");
    await expect(page.locator("#hero canvas.fx-halftone__canvas")).toHaveAttribute("aria-hidden", "true");
    await expect(page.locator("#hero")).toHaveAttribute("aria-hidden", "true");
    if (!(await path(page, info))) {
      await expect(page.locator("#hero .fx-halftone__fallback")).toBeVisible();
      await expect(page.locator(HERO)).toBeHidden();
      expectClean(seen);
      return;
    }
    const s = await stats(page);
    expect(s.sd, "pixel variance").toBeGreaterThan(8);
    expect(s.levels).toBeGreaterThan(3);
    expect(s.corner).toEqual([8, 9, 13]);
    expect(Math.max(s.w, s.h)).toBeLessThanOrEqual(Math.ceil(1280 * 1.5) + 2);
    const a = await url(page);
    await page.waitForTimeout(600);
    const b = await url(page);
    expect(b).not.toBe(a);
    expectClean(seen);
  });

  test("motion off renders one identical frame and requests no animation frame afterwards", async ({ page }, info) => {
    await page.addInitScript(() => {
      window.__raf = 0;
      const o = window.requestAnimationFrame.bind(window);
      window.requestAnimationFrame = (cb) => { window.__raf++; return o(cb); };
    });
    await open(page, "motion=off");
    if (!(await path(page, info))) {
      await expect(page.locator("#hero .fx-halftone__fallback")).toBeVisible();
      return;
    }
    const before = await page.evaluate(() => window.__raf);
    const a = await url(page);
    await page.mouse.move(400, 200);
    await page.waitForTimeout(600);
    const b = await url(page);
    expect(b).toBe(a);
    expect(await page.evaluate(() => window.__raf)).toBe(before);
    expect((await stats(page)).sd).toBeGreaterThan(8);
  });

  test("prefers-reduced-motion defaults motion off and a user can switch it on", async ({ browser }, info) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    const seen = watch(page);
    await open(page, "");
    expect(await page.evaluate(() => NHBEffects.motionEnabled())).toBe(false);
    expect(await page.evaluate(() => document.documentElement.dataset.motion)).toBe("off");
    const gl = await path(page, info);
    const a = gl ? await url(page) : null;
    await page.evaluate(() => NHBEffects.setMotion(true));
    expect(await page.evaluate(() => document.documentElement.dataset.motion)).toBe("on");
    expect(await page.evaluate(() => NHBEffects.motionEnabled())).toBe(true);
    if (gl) {
      await page.waitForTimeout(700);
      expect(await url(page)).not.toBe(a);
      await page.evaluate(() => NHBEffects.setMotion(false));
      await page.waitForTimeout(100);
      const c = await url(page);
      await page.waitForTimeout(500);
      expect(await url(page)).toBe(c);
    }
    expectClean(seen);
    await context.close();
  });

  test("forced-off WebGL shows the fallback panel and nothing throws", async ({ page }) => {
    await page.addInitScript(() => { HTMLCanvasElement.prototype.getContext = function () { return null; }; });
    const seen = watch(page);
    await open(page, "motion=on");
    expect(await state(page)).toBe("fallback");
    await expect(page.locator("#hero .fx-halftone__fallback")).toBeVisible();
    await expect(page.locator(HERO)).toBeHidden();
    expect(await page.locator("#hero .fx-halftone__fallback").getAttribute("aria-hidden")).toBe("true");
    await page.mouse.move(300, 200);
    await page.waitForTimeout(200);
    expectClean(seen);
  });

  test("pointer movement raises the intensity near the cursor and relaxes after it leaves", async ({ page }, info) => {
    await open(page, "motion=on");
    if (!(await path(page, info))) return;
    const near = [640, 200], far = [140, 330];
    await page.mouse.move(640, 700);
    await page.waitForTimeout(1200);
    const n0 = await region(page, near[0], near[1], 110), f0 = await region(page, far[0], far[1], 80);
    await page.mouse.move(near[0], near[1], { steps: 6 });
    await page.waitForTimeout(1200);
    const n1 = await region(page, near[0], near[1], 110), f1 = await region(page, far[0], far[1], 80);
    expect(n1 / n0, "near ratio").toBeGreaterThan(1.1);
    expect(n1 / n0).toBeGreaterThan(f1 / f0 + 0.04);
    await page.mouse.move(640, 700);
    await page.waitForTimeout(1500);
    const n2 = await region(page, near[0], near[1], 110);
    expect(n2).toBeLessThan(n1);
  });

  test("an offscreen host stops rendering and resumes when visible again", async ({ page }, info) => {
    await open(page, "motion=on");
    if (!(await path(page, info))) return;
    await scrollTo(page, await maxScroll(page));
    await page.waitForTimeout(400);
    const a = await url(page);
    await page.waitForTimeout(700);
    expect(await url(page)).toBe(a);
    await scrollTo(page, 0);
    await page.waitForTimeout(700);
    expect(await url(page)).not.toBe(a);
  });

  test("theme changes re-read the palette (static frame, motion off)", async ({ page }, info) => {
    await open(page, "motion=off");
    if (!(await path(page, info))) return;
    expect((await stats(page)).corner).toEqual([8, 9, 13]);
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    await page.waitForTimeout(150);
    expect((await stats(page)).corner).toEqual([252, 252, 253]);
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await page.waitForTimeout(150);
    expect((await stats(page)).corner).toEqual([8, 9, 13]);
  });

  test("more than three hosts: the extra host falls back; a lost context shows the fallback and recovers", async ({ page }, info) => {
    const seen = watch(page);
    await open(page, "motion=on");
    await page.evaluate(() => {
      for (let i = 0; i < 3; i++) {
        const d = document.createElement("div");
        d.setAttribute("data-fx-halftone", "field");
        d.className = "host extra";
        document.querySelector("main").appendChild(d);
      }
      NHBEffects.refresh();
    });
    const states = await page.locator("[data-fx-halftone]").evaluateAll((els) => els.map((e) => e.getAttribute("data-fx-state")));
    expect(states).toHaveLength(4);
    if (await path(page, info)) {
      expect(states.slice(0, 3)).toEqual(["gl", "gl", "gl"]);
      expect(states[3]).toBe("fallback");
      const lost = await page.evaluate(() => {
        const g = document.querySelector("#hero canvas").getContext("webgl");
        const x = g.getExtension("WEBGL_lose_context");
        if (!x) return false;
        window.__lose = x;
        x.loseContext();
        return true;
      });
      if (lost) {
        await expect.poll(() => state(page)).toBe("fallback");
        await expect(page.locator("#hero .fx-halftone__fallback")).toBeVisible();
        await page.evaluate(() => window.__lose.restoreContext());
        await expect.poll(() => state(page)).toBe("gl");
        expect((await stats(page)).sd).toBeGreaterThan(8);
      }
    } else {
      expect(states.every((s) => s === "fallback")).toBe(true);
    }
    expectClean(seen);
  });
});

test.describe("scroll journey", () => {
  test("the ink path draws forward with scroll: monotonic, 0 at the bottom", async ({ page }) => {
    const seen = watch(page);
    await open(page, "motion=on");
    const len = await page.locator("#jsvg .fx-journey__ink").evaluate((e) => parseFloat(e.getAttribute("stroke-dasharray")));
    expect(len).toBeGreaterThan(500);
    expect(await page.locator("#jsvg .fx-journey__base").getAttribute("d")).toBe(await page.locator("#jsvg .fx-journey__ink").getAttribute("d"));
    expect(await page.locator("#jsvg .fx-journey__node").count()).toBe(3);
    const bottom = await maxScroll(page);
    const seq = [];
    const active = [];
    for (let i = 0; i <= 8; i++) {
      await scrollTo(page, Math.round((bottom * i) / 8));
      await page.waitForTimeout(120);
      seq.push(await offset(page));
      active.push(await page.locator("#jsvg .fx-journey__node.is-active").count());
    }
    for (let i = 1; i < seq.length; i++) expect(seq[i], "offsets " + seq).toBeLessThanOrEqual(seq[i - 1] + 0.01);
    expect(seq[0]).toBeGreaterThan(len * 0.5);
    expect(seq[seq.length - 1]).toBe(0);
    for (let i = 1; i < active.length; i++) expect(active[i]).toBeGreaterThanOrEqual(active[i - 1]);
    expect(active[active.length - 1]).toBe(3);
    expect(await page.locator("#jsvg").getAttribute("aria-hidden")).toBe("true");
    expectClean(seen);
  });

  test("a narrow viewport uses the thin left-edge spine; resize recomputes", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 900 });
    await open(page, "motion=on");
    const narrow = await page.locator("#jsvg .fx-journey__ink").getAttribute("d");
    expect(narrow).toMatch(/^M5 0 L5 /);
    expect(narrow).not.toContain("C");
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect.poll(() => page.locator("#jsvg .fx-journey__ink").getAttribute("d")).toContain("C");
  });

  test("motion off: the ink path is fully drawn and every node is active", async ({ page }) => {
    await open(page, "motion=off");
    expect(await offset(page)).toBe(0);
    await scrollTo(page, 0);
    await page.waitForTimeout(150);
    expect(await offset(page)).toBe(0);
    expect(await page.locator("#jsvg .fx-journey__node.is-active").count()).toBe(3);
  });

  test("[data-fx-draw] draws once when 60% in view and ends fully drawn", async ({ page }) => {
    await open(page, "motion=on");
    const hidden = await page.locator("#draw").evaluate((e) => ({ d: e.style.strokeDashoffset, a: e.style.strokeDasharray }));
    expect(parseFloat(hidden.d)).toBeGreaterThan(50);
    await page.locator("#draw").scrollIntoViewIfNeeded();
    await page.waitForTimeout(1100);
    const done = await page.locator("#draw").evaluate((e) => ({ d: e.style.strokeDashoffset, a: e.style.strokeDasharray }));
    expect(done).toEqual({ d: "", a: "" });
  });

  test("[data-fx-draw] stays fully drawn when motion is off", async ({ page }) => {
    await open(page, "motion=off");
    const s = await page.locator("#draw").evaluate((e) => ({ d: e.style.strokeDashoffset, a: e.style.strokeDasharray }));
    expect(s).toEqual({ d: "", a: "" });
  });
});

test.describe("micro-interactions", () => {
  test("count-up reaches the exact final text and keeps the real text for assistive tech", async ({ page }) => {
    await open(page, "motion=on");
    await page.locator("#count").scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    const mid = await page.locator("#count").evaluate((e) => ({
      real: e.querySelector(".fx-sr") && e.querySelector(".fx-sr").textContent,
      cloneHidden: Array.from(e.children).filter((c) => c.getAttribute("aria-hidden") === "true").length,
    }));
    expect(mid).toEqual({ real: "1234", cloneHidden: 1 });
    await page.waitForTimeout(1100);
    expect(await page.locator("#count").evaluate((e) => ({ t: e.textContent, kids: e.childNodes.length, el: e.children.length })))
      .toEqual({ t: "1234", kids: 1, el: 0 });
    expect(await page.evaluate(() => getComputedStyle(document.querySelector("#count")).fontVariantNumeric)).toContain("tabular-nums");
  });

  test("count-up does nothing with motion off", async ({ page }) => {
    await open(page, "motion=off");
    await page.locator("#count").scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    expect(await page.locator("#count").evaluate((e) => ({ t: e.textContent, el: e.children.length }))).toEqual({ t: "1234", el: 0 });
  });

  test("reveal fades up once visible and never hides content without the module", async ({ page }) => {
    await open(page, "motion=on");
    expect(await opacity(page, "#r-far")).toBe("0");
    await page.locator("#r-far").scrollIntoViewIfNeeded();
    await expect.poll(() => opacity(page, "#r-far"), { timeout: 3000 }).toBe("1");
  });

  test("reveal content is visible when js-fx is absent (module never initialised)", async ({ page }) => {
    await page.goto(harness().url("init=manual&motion=on"));
    await page.evaluate(() => document.documentElement.setAttribute("data-motion", "on"));
    expect(await page.evaluate(() => document.documentElement.classList.contains("js-fx"))).toBe(false);
    for (const sel of ["#r-top", "#r-far"]) expect(await opacity(page, sel)).toBe("1");
  });

  test("reveal content is visible when motion is off", async ({ page }) => {
    await open(page, "motion=off");
    for (const sel of ["#r-top", "#r-far"]) expect(await opacity(page, sel)).toBe("1");
  });

  test("scroll progress bar follows the scroll position", async ({ page }) => {
    await open(page, "motion=on");
    await scrollTo(page, await maxScroll(page));
    await page.waitForTimeout(150);
    const p = await page.locator(".fx-progress").evaluate((e) => parseFloat(e.style.getPropertyValue("--fx-progress")));
    expect(p).toBeCloseTo(1, 2);
    await expect(page.locator(".fx-progress")).toHaveAttribute("aria-hidden", "true");
  });

  test("nav indicator follows the section in view and marks the link aria-current", async ({ page }) => {
    await open(page, "motion=on");
    await page.locator("#s2").scrollIntoViewIfNeeded();
    await page.evaluate(() => document.querySelector("#s2").scrollIntoView());
    await expect(page.locator('#nav a[aria-current="true"]')).toHaveText("Two");
    expect(await page.locator('#nav a[aria-current="true"]').count()).toBe(1);
    await expect(page.locator(".fx-nav-indicator")).toHaveClass(/is-on/);
    const x2 = await page.locator(".fx-nav-indicator").evaluate((e) => e.style.getPropertyValue("--fx-nav-x"));
    await page.evaluate(() => document.querySelector("#s3").scrollIntoView());
    await expect(page.locator('#nav a[aria-current="true"]')).toHaveText("Three");
    expect(await page.locator(".fx-nav-indicator").evaluate((e) => e.style.getPropertyValue("--fx-nav-x"))).not.toBe(x2);
  });

  test("magnetic button shifts at most 4px, rests on press and springs back", async ({ page }) => {
    await open(page, "motion=on");
    await page.locator("#mag").scrollIntoViewIfNeeded();
    const box = await page.locator("#mag").boundingBox();
    await page.mouse.move(box.x + box.width - 3, box.y + box.height - 3, { steps: 4 });
    const v = await page.locator("#mag").evaluate((e) => [e.style.getPropertyValue("--fx-mx"), e.style.getPropertyValue("--fx-my")].map(parseFloat));
    expect(Math.abs(v[0])).toBeGreaterThan(1);
    expect(Math.abs(v[0])).toBeLessThanOrEqual(4);
    expect(Math.abs(v[1])).toBeLessThanOrEqual(4);
    await page.mouse.down();
    expect(await page.locator("#mag").evaluate((e) => e.style.getPropertyValue("--fx-mx"))).toBe("0px");
    await page.mouse.up();
    await page.mouse.move(5, 5);
    expect(await page.locator("#mag").evaluate((e) => e.style.getPropertyValue("--fx-mx"))).toBe("");
  });

  test("spotlight follows the pointer; tilt is capped at 3deg", async ({ page }) => {
    await open(page, "motion=on");
    await page.locator("#card").scrollIntoViewIfNeeded();
    const box = await page.locator("#card").boundingBox();
    await page.mouse.move(box.x + box.width - 2, box.y + 2, { steps: 4 });
    const s = await page.locator("#card").evaluate((e) => ({
      x: parseFloat(e.style.getPropertyValue("--fx-x")), ry: parseFloat(e.style.getPropertyValue("--fx-ry")), rx: parseFloat(e.style.getPropertyValue("--fx-rx")),
    }));
    expect(s.x).toBeGreaterThan(box.width * 0.8);
    expect(Math.abs(s.ry)).toBeLessThanOrEqual(3);
    expect(Math.abs(s.rx)).toBeLessThanOrEqual(3);
    expect(Math.abs(s.ry)).toBeGreaterThan(1);
  });

  test("pointer effects are inert with motion off", async ({ page }) => {
    await open(page, "motion=off");
    await page.locator("#mag").scrollIntoViewIfNeeded();
    const box = await page.locator("#mag").boundingBox();
    await page.mouse.move(box.x + box.width - 3, box.y + box.height - 3, { steps: 3 });
    expect(await page.locator("#mag").evaluate((e) => e.style.getPropertyValue("--fx-mx"))).toBe("");
    expect(await page.locator("#mag").evaluate((e) => getComputedStyle(e).translate)).toBe("none");
  });
});

test.describe("animated details", () => {
  for (const motion of ["on", "off"]) {
    test("keyboard operation keeps native semantics (motion " + motion + ")", async ({ page }) => {
      const seen = watch(page);
      await open(page, "motion=" + motion);
      await page.locator("#d1 summary").scrollIntoViewIfNeeded();
      await page.evaluate(() => {
        window.__toggles = 0;
        document.querySelector("#d1").addEventListener("toggle", () => { window.__toggles++; });
      });
      await page.locator("#d1 summary").focus();
      await page.keyboard.press("Enter");
      await expect.poll(() => page.locator("#d1").evaluate((e) => e.open)).toBe(true);
      await page.waitForTimeout(700);
      expect(await page.locator("#d1").evaluate((e) => e.style.overflow)).toBe("");
      const full = await page.locator("#d1").evaluate((e) => e.getBoundingClientRect().height);
      expect(full).toBeGreaterThan(100);
      await expect(page.locator("#d1 summary")).toBeFocused();
      await page.keyboard.press("Space");
      await expect.poll(() => page.locator("#d1").evaluate((e) => e.open)).toBe(false);
      await page.waitForTimeout(700);
      const shut = await page.locator("#d1").evaluate((e) => e.getBoundingClientRect().height);
      expect(shut).toBeLessThan(full - 60);
      expect(await page.evaluate(() => window.__toggles)).toBe(2);
      await page.keyboard.press("Enter");
      await page.keyboard.press("Enter");
      await page.waitForTimeout(800);
      expect(await page.locator("#d1").evaluate((e) => e.open)).toBe(false);
      expectClean(seen);
    });
  }

  test("an interrupted animation reverses cleanly and a details without the attribute stays native", async ({ page }) => {
    await open(page, "motion=on");
    await page.locator("#d1 summary").scrollIntoViewIfNeeded();
    await page.locator("#d1 summary").click();
    await page.waitForTimeout(80);
    await page.locator("#d1 summary").click();
    await page.waitForTimeout(800);
    expect(await page.locator("#d1").evaluate((e) => e.open)).toBe(false);
    await page.locator("#d0 summary").click();
    expect(await page.locator("#d0").evaluate((e) => e.open)).toBe(true);
  });
});

test.describe("theme transition, lifecycle, accessibility", () => {
  for (const motion of ["on", "off"]) {
    test("transitionTheme applies the change exactly once (motion " + motion + ")", async ({ page }) => {
      const seen = watch(page);
      await open(page, "motion=" + motion);
      const n = await page.evaluate(async () => {
        let calls = 0;
        NHBEffects.transitionTheme(() => { calls++; document.documentElement.setAttribute("data-theme", "light"); }, document.querySelector("#nav a"));
        await new Promise((r) => setTimeout(r, 900));
        return calls;
      });
      expect(n).toBe(1);
      expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe("light");
      expectClean(seen);
    });
  }

  test("init is idempotent; destroy removes everything it added", async ({ page }) => {
    await open(page, "motion=on");
    await page.evaluate(() => { NHBEffects.init(document); NHBEffects.init(document.documentElement); });
    expect(await page.locator("#hero canvas").count()).toBe(1);
    expect(await page.locator(".fx-progress").count()).toBe(1);
    expect(await page.locator(".fx-nav-indicator").count()).toBe(1);
    await page.evaluate(() => NHBEffects.destroy());
    expect(await page.locator("#hero canvas, #hero .fx-halftone__fallback, .fx-progress, .fx-nav-indicator, #jsvg *").count()).toBe(0);
    expect(await page.evaluate(() => ({
      js: document.documentElement.classList.contains("js-fx"), m: document.documentElement.getAttribute("data-motion"),
      cur: document.querySelectorAll("[aria-current]").length, hero: document.querySelector("#hero").hasAttribute("data-fx-state"),
    }))).toEqual({ js: false, m: null, cur: 0, hero: false });
    await page.evaluate(() => NHBEffects.init(document, { motion: false }));
    expect(await page.locator("#hero canvas").count()).toBe(1);
  });

  test("the only global is NHBEffects, with the documented API", async ({ page }) => {
    await page.goto(harness().url("init=manual"));
    const keys = await page.evaluate(() => Object.keys(window.NHBEffects).sort());
    expect(keys).toEqual(["destroy", "init", "motionEnabled", "refresh", "setMotion", "transitionTheme"]);
    expect(await page.evaluate(() => document.querySelectorAll("canvas, .fx-progress").length)).toBe(0);
    expect(await page.evaluate(() => document.documentElement.hasAttribute("data-motion"))).toBe(false);
  });

  for (const motion of ["on", "off"]) {
    test("axe-core reports no violations (motion " + motion + ")", async ({ page }) => {
      await open(page, "motion=" + motion);
      await page.evaluate(AXE);
      const result = await page.evaluate(() => window.axe.run(document, { resultTypes: ["violations"] }));
      expect(result.violations.map((v) => v.id + ": " + v.nodes.map((n) => n.target.join(" ")).join(", ")), "axe").toEqual([]);
    });
  }

  test("focus outlines are never removed", async ({ page }) => {
    await open(page, "motion=on");
    await page.locator("#mag").focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    const outline = await page.locator("#mag").evaluate((e) => getComputedStyle(e).outlineStyle);
    expect(outline).not.toBe("none");
  });
});

test.describe("per-word tagline reveal", () => {
  const TEXT = "Know what survives revocation. Rotate in the order that keeps the next secret safe.";
  test("words are real text, muted until they cross the trigger line, then lit once", async ({ page }) => {
    await open(page, "motion=on");
    expect(await page.locator("#words").textContent()).toBe(TEXT);
    expect(await page.locator("#words .fx-w").count()).toBe(TEXT.split(" ").length);
    expect(await page.locator("#words [aria-hidden]").count()).toBe(0);
    expect(await opacity(page, "#words .fx-w >> nth=0")).toBe("0.3");
    await page.evaluate(() => document.querySelector("#words").scrollIntoView({ block: "start" }));
    await expect.poll(() => page.locator("#words .fx-w").evaluateAll((w) => w.filter((e) => getComputedStyle(e).opacity === "1").length), { timeout: 4000 })
      .toBe(TEXT.split(" ").length);
    await scrollTo(page, 0);
    await page.waitForTimeout(700);
    expect(await opacity(page, "#words .fx-w >> nth=0")).toBe("1");
  });

  test("words light in reading order as the line is crossed", async ({ page }) => {
    await open(page, "motion=on");
    const top = await page.locator("#words").evaluate((e) => e.getBoundingClientRect().top + scrollY);
    await page.evaluate((t) => window.scrollTo(0, t - Math.round(innerHeight * 0.5)), top);
    await page.waitForTimeout(900);
    const lit = await page.locator("#words .fx-w").evaluateAll((w) => w.map((e) => e.classList.contains("is-lit")));
    expect(lit.some(Boolean)).toBe(true);
    const firstOff = lit.indexOf(false);
    if (firstOff >= 0) expect(lit.slice(firstOff).some(Boolean), "lit words form a prefix " + lit).toBe(false);
  });

  test("motion off shows the final text at full colour immediately", async ({ page }) => {
    await open(page, "motion=off");
    expect(await page.locator("#words").textContent()).toBe(TEXT);
    const ops = await page.locator("#words .fx-w").evaluateAll((w) => w.map((e) => getComputedStyle(e).opacity));
    expect(new Set(ops)).toEqual(new Set(["1"]));
  });
});

test.describe("floating pill nav (mobile menu)", () => {
  const phone = { width: 390, height: 844 };
  test("opens a full-height panel, staggers links, traps focus, Esc closes", async ({ page }) => {
    const seen = watch(page);
    await page.setViewportSize(phone);
    await open(page, "motion=on");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const panel = page.locator("#pill-panel");
    expect(await panel.evaluate((e) => getComputedStyle(e).visibility)).toBe("hidden");
    await expect(page.locator("#pill-toggle")).toHaveAttribute("aria-expanded", "false");
    await page.locator("#pill-toggle").click();
    await expect(page.locator("#pill-toggle")).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("#pill")).toHaveClass(/is-open/);
    expect(await panel.evaluate((e) => getComputedStyle(e).visibility)).toBe("visible");
    const box = await panel.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(phone.height - 1);
    await expect(page.locator("#pill-panel a").first()).toBeFocused();
    expect(await page.locator("#pill-panel a").evaluateAll((a) => a.map((e) => getComputedStyle(e).transitionDelay)))
      .toEqual(["0s", "0.06s", "0.12s"]);
    await page.waitForTimeout(900);
    expect(await page.locator("#pill-panel a").evaluateAll((a) => a.map((e) => getComputedStyle(e).opacity))).toEqual(["1", "1", "1"]);
    expect(await page.evaluate(() => document.documentElement.classList.contains("fx-menu-open"))).toBe(true);
    expect(await page.locator("#pill-toggle .fx-burger i").first().evaluate((e) => getComputedStyle(e).transform)).toMatch(/^matrix/);
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => !!document.activeElement.closest("#pill"))).toBe(true);
    }
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Shift+Tab");
      expect(await page.evaluate(() => !!document.activeElement.closest("#pill"))).toBe(true);
    }
    await page.evaluate(() => { window.AXE_RESULT = null; });
    await page.evaluate(AXE);
    const result = await page.evaluate(() => window.axe.run(document, { resultTypes: ["violations"] }));
    expect(result.violations.map((v) => v.id), "axe, menu open").toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.locator("#pill-toggle")).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#pill-toggle")).toBeFocused();
    await expect.poll(() => panel.evaluate((e) => getComputedStyle(e).visibility), { timeout: 2000 }).toBe("hidden");
    expect(await page.evaluate(() => document.documentElement.classList.contains("fx-menu-open"))).toBe(false);
    expectClean(seen);
  });

  test("a link closes the menu; leaving the overlay breakpoint closes it too; motion off is instant", async ({ page }) => {
    await page.setViewportSize(phone);
    await open(page, "motion=off");
    await page.locator("#pill-toggle").click();
    expect(await page.locator("#pill-panel a").evaluateAll((a) => a.map((e) => getComputedStyle(e).opacity))).toEqual(["1", "1", "1"]);
    expect(await page.locator("#pill-panel").evaluate((e) => getComputedStyle(e).transitionDuration)).toBe("0s");
    await page.locator("#pill-panel a >> nth=1").click();
    await expect(page.locator("#pill-toggle")).toHaveAttribute("aria-expanded", "false");
    await page.locator("#pill-toggle").click();
    await expect(page.locator("#pill")).toHaveClass(/is-open/);
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(page.locator("#pill")).not.toHaveClass(/is-open/);
    expect(await page.evaluate(() => document.documentElement.classList.contains("fx-menu-open"))).toBe(false);
  });
});
