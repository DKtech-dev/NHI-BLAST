// Renders the README artwork with the locally installed Chrome over CDP.
// Usage: node render.mjs --html banner.html --out banner-dark.png \
//   --width 1600 --height 600 --scheme dark [--dpr 1] [--scroll graph]
import { spawn } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const htmlPath = resolve(option("html"));
const outPath = resolve(option("out"));
const width = Number(option("width", 1600));
const height = Number(option("height", 600));
const dpr = Number(option("dpr", 1));
const scheme = option("scheme", "dark");
const scroll = option("scroll", "");
const crop = option("crop", "");
const settle = Number(option("settle", 1200));

const chromeCandidates = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].filter(Boolean);
const chromePath = chromeCandidates.find((candidate) => existsSync(candidate));
if (!chromePath) throw new Error("no Chrome or Edge binary found");

const fontDir = resolve(dirname(htmlPath), "../../src/nhi_blast/report/assets/fonts");
const fontData = (name) =>
  `data:font/woff2;base64,${readFileSync(join(fontDir, name)).toString("base64")}`;

const raw = args.includes("--raw");
let pagePath = htmlPath;
let tempHtml = null;
if (!raw) {
  let document = readFileSync(htmlPath, "utf8");
  const css = readFileSync(join(dirname(htmlPath), "identity.css"), "utf8");
  document = document.replace(
    '<link rel="stylesheet" href="identity.css">',
    `<style>\n${css}\n</style>`,
  );
  document = document
    .replaceAll("__GEIST_WOFF2__", fontData("geist-latin.woff2"))
    .replaceAll("__GEIST_MONO_WOFF2__", fontData("geist-mono-latin.woff2"))
    .replaceAll("__SERIF_WOFF2__", fontData("instrument-serif-latin.woff2"));
  if (document.includes("__REPORT_CROP__")) {
    if (!crop) throw new Error("this page requires --crop <report-crop.png>");
    const cropData =
      "data:image/png;base64," +
      readFileSync(resolve(crop)).toString("base64");
    document = document.replaceAll("__REPORT_CROP__", cropData);
  }
  tempHtml = join(
    dirname(htmlPath),
    `.render-${process.pid}${extname(htmlPath)}`,
  );
  writeFileSync(tempHtml, document, "utf8");
  pagePath = tempHtml;
}

const userDataDir = join(tmpdir(), `nhi-blast-render-${process.pid}`);
const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--allow-file-access-from-files",
    "--user-data-dir=" + userDataDir,
    "--remote-debugging-port=0",
    "about:blank",
  ],
  { stdio: "ignore" },
);

const cleanup = async () => {
  chrome.kill();
  await Promise.race([
    new Promise((resolvePromise) => chrome.once("exit", resolvePromise)),
    sleep(3000),
  ]);
  if (tempHtml) rmSync(tempHtml, { force: true });
  try {
    rmSync(userDataDir, { recursive: true, force: true, maxRetries: 5 });
  } catch {
    // Chrome can hold the profile briefly on Windows; the temp directory is disposable.
  }
};

class Cdp {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 0;
    this.pending = new Map();
    this.waiters = new Map();
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== undefined) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      const waiters = this.waiters.get(message.method);
      if (!waiters) return;
      this.waiters.delete(message.method);
      for (const waiter of waiters) waiter(message.params);
    };
  }

  send(method, params = {}, sessionId) {
    const id = ++this.nextId;
    return new Promise((resolvePromise, rejectPromise) => {
      this.pending.set(id, { resolve: resolvePromise, reject: rejectPromise });
      this.socket.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }

  once(method) {
    return new Promise((resolvePromise) => {
      const waiters = this.waiters.get(method) ?? [];
      waiters.push(resolvePromise);
      this.waiters.set(method, waiters);
    });
  }
}

try {
  const activePortFile = join(userDataDir, "DevToolsActivePort");
  for (let attempt = 0; attempt < 150; attempt += 1) {
    if (existsSync(activePortFile)) break;
    await sleep(100);
  }
  const [port, browserPath] = readFileSync(activePortFile, "utf8")
    .trim()
    .split("\n");
  const socket = new WebSocket(`ws://127.0.0.1:${port}${browserPath}`);
  await new Promise((resolvePromise, rejectPromise) => {
    socket.onopen = resolvePromise;
    socket.onerror = rejectPromise;
  });
  const cdp = new Cdp(socket);

  const { targetId } = await cdp.send("Target.createTarget", {
    url: "about:blank",
  });
  const { sessionId } = await cdp.send("Target.attachToTarget", {
    targetId,
    flatten: true,
  });
  const session = (method, params = {}) => cdp.send(method, params, sessionId);

  await session("Page.enable");
  await session("Runtime.enable");
  await session("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: dpr,
    mobile: false,
  });
  await session("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: scheme }],
  });

  const params = new URLSearchParams({ scheme });
  const url = pathToFileURL(pagePath).href + "?" + params.toString();
  const loaded = cdp.once("Page.loadEventFired");
  await session("Page.navigate", { url });
  await loaded;
  await session("Runtime.evaluate", {
    expression: "document.fonts.ready.then(() => true)",
    awaitPromise: true,
    returnByValue: true,
  });
  await sleep(settle);

  if (scroll) {
    const script = /^\d+$/.test(scroll)
      ? `window.scrollTo(0, ${scroll})`
      : `document.getElementById(${JSON.stringify(scroll)})?.scrollIntoView({block: "start"})`;
    await session("Runtime.evaluate", { expression: script });
    await sleep(600);
  }

  const { data } = await session("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  writeFileSync(outPath, Buffer.from(data, "base64"));
  console.log(`${outPath} ${width * dpr}x${height * dpr}`);
} finally {
  await cleanup();
}
