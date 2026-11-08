// Builds a tiny harness page from the real EFFECTS_CSS / EFFECTS_JS strings (src/nhi_blast/report/effects.py).
// The page carries a strict CSP with sha256 hashes for every inline script and style, like the report does.
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const root = path.resolve(__dirname, "..", "..");

function python() {
  if (process.env.NHB_PYTHON) return process.env.NHB_PYTHON;
  const venv = process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : "python";
}

const hash = (text) => "'sha256-" + crypto.createHash("sha256").update(text, "utf8").digest("base64") + "'";
const LF = (text) => text.replace(/\r\n/g, "\n");

const LAYOUT = [
  "html{scroll-behavior:auto}",
  "body{margin:0;background:#08090d;color:#e6e9f0;font:16px/1.5 system-ui,sans-serif}",
  "a{color:#9db8ff}a:focus-visible,summary:focus-visible,button:focus-visible{outline:2px solid #9db8ff;outline-offset:2px}",
  "header{position:sticky;top:0;background:#0d0f14;z-index:5;padding:8px 24px}",
  "nav[data-fx-nav] a{display:inline-block;padding:8px 14px}",
  ".host{height:420px}",
  ".journey{position:relative;padding-left:120px;margin-right:40px}",
  ".journey section{min-height:700px}",
  ".card{display:block;padding:24px;border:1px solid #2a2f3a;max-width:360px;margin:16px 0}",
  "button{padding:10px 18px;background:#1c2230;color:#e6e9f0;border:1px solid #3a4152}",
  "details{border:1px solid #2a2f3a;padding:8px 12px;max-width:480px}",
  "footer{padding:20px 24px;height:20px}",
  "#pill-toggle{position:relative;z-index:10;padding:8px 12px;color:#e6e9f0;background:transparent;border:1px solid #3a4152;border-radius:8px}",
  "#pill-panel{display:flex;gap:16px}",
  "@media (max-width:699px){#pill-panel{flex-direction:column;padding:96px 24px 24px;background:#08090d;position:fixed;inset:0}}",
  "#pill-panel a{font-size:24px}",
  "@media (min-width:700px){#pill{display:none}}",
  "@media (max-width:699px){#nav{display:none}.journey{padding-left:24px;margin-right:16px}}",
  "h2[data-fx-words]{max-width:680px;font-size:36px;line-height:40px;margin:0 0 24px}",
].join("\n");

function body() {
  return [
    '<header><div data-fx-pillnav id="pill"><button type="button" id="pill-toggle" data-fx-pillnav-toggle aria-expanded="false" aria-controls="pill-panel" aria-label="Menu"></button>',
    '<div id="pill-panel" data-fx-pillnav-panel><a href="#s1">One</a><a href="#s2">Two</a><a href="#s3">Three</a></div></div>',
    '<nav data-fx-nav id="nav" aria-label="Sections"><a href="#s1">One</a><a href="#s2">Two</a><a href="#s3">Three</a></nav></header>',
    "<main>",
    '<div id="hero" data-fx-halftone="hero" class="host"></div>',
    "<h1>Effects harness</h1>",
    '<p id="hostile">&lt;img src=x onerror=alert(1)&gt; &lt;script&gt;alert(2)&lt;/script&gt;</p>',
    '<div class="journey" id="journey"><svg data-fx-journey id="jsvg" aria-hidden="true"></svg>',
    '<section id="s1"><h2 data-fx-stop>Entrypoint</h2><p data-fx-reveal id="r-top">Reveal near the top.</p>',
    '<a class="card" data-fx-spotlight data-fx-tilt id="card" href="#s1">Spotlight and tilt card</a>',
    '<button type="button" data-fx-magnetic id="mag">Magnetic</button></section>',
    '<section id="s2"><h2 data-fx-stop>Reachability</h2><h2 id="words" data-fx-words>Know what survives revocation. Rotate in the order that keeps the next secret safe.</h2>',
    '<p><span id="count" data-fx-count>1234</span> findings</p>',
    '<p><span id="count-bad" data-fx-count>&lt;b&gt;12&lt;/b&gt;</span></p>',
    '<details data-fx-disclosure id="d1"><summary>More detail</summary><p>One.</p><p>Two.</p><p>Three.</p><p>Four.</p></details>',
    '<details id="d0"><summary>Plain</summary><p>Not animated.</p></details></section>',
    '<section id="s3"><h2 data-fx-stop>Revocation</h2>',
    '<svg width="240" height="40" role="img" aria-label="rule"><path id="draw" data-fx-draw d="M4 20 L120 8 L236 20" fill="none" stroke="#9db8ff" stroke-width="2"/></svg>',
    '<p data-fx-reveal data-fx-delay="80" id="r-far">Reveal far down.</p></section>',
    "</div></main>",
    "<footer>end</footer>",
  ].join("\n");
}

const INIT = [
  "var q=new URLSearchParams(location.search),m=q.get('motion');",
  "if(q.get('init')!=='manual')NHBEffects.init(document,{motion:m==='on'?true:m==='off'?false:null});",
].join("");

function build() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "nhb-effects-"));
  const script = "import sys\nfrom nhi_blast.report.effects import EFFECTS_CSS, EFFECTS_JS\n"
    + "open(sys.argv[1], 'w', encoding='utf-8', newline='').write(EFFECTS_CSS)\n"
    + "open(sys.argv[2], 'w', encoding='utf-8', newline='').write(EFFECTS_JS)\n";
  const css = path.join(dir, "effects.css");
  const js = path.join(dir, "effects.js");
  const result = spawnSync(python(), ["-c", script, css, js], {
    cwd: root, encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" },
  });
  if (result.status !== 0) throw new Error("could not export effects strings: " + result.stdout + result.stderr);
  const style = LF(fs.readFileSync(css, "utf8")) + "\n" + LAYOUT;
  const effects = LF(fs.readFileSync(js, "utf8"));
  const csp = "default-src 'none'; script-src " + hash(effects) + " " + hash(INIT) + "; style-src " + hash(style);
  const html = [
    '<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">',
    '<meta http-equiv="Content-Security-Policy" content="' + csp + '">',
    "<title>Effects harness</title><style>" + style + "</style></head><body>",
    body(),
    "<script>" + effects + "</script>",
    "<script>" + INIT + "</script>",
    "</body></html>",
  ].join("\n");
  fs.writeFileSync(path.join(dir, "harness.html"), html);
  return { dir, effects, style, url: (query) => pathToFileURL(path.join(dir, "harness.html")).href + (query ? "?" + query : "") };
}

let cached = null;
module.exports = { harness: () => cached || (cached = build()) };
