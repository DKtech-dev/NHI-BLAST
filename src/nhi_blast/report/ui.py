"""Markup, styles and the inline application script for the offline report."""

from __future__ import annotations

TEMPLATE = """<!DOCTYPE html>
<html lang="en" class="booting">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#050505">
<title>NHI-Blast report</title>
<style>
__FONT_CSS__
/* The data sections are hydrated from the embedded JSON; keep the shell hidden
   until the first render so nothing below reflows after paint. The boot status is
   the only thing visible, and only while that real render is in progress. */
html.booting body > :not(#boot-status):not(script) { visibility: hidden; }
html.boot-failed body > :not(#boot-status):not(script) { visibility: hidden; }
:root {
  color-scheme: dark;
  --bg: #050505;
  --header: #090909;
  --surface: #111010;
  --surface-2: #171514;
  --raised: #201b19;
  --hover: #29211f;
  --border: #302a27;
  --border-strong: #49403c;
  --ink: #f5f0dc;
  --ink-2: #c7c0b5;
  --muted: #a7a096;
  --accent: #ff382f;
  --accent-hover: #ff5147;
  --accent-ink: #0c0605;
  --accent-soft: #321513;
  --critical: #ff5147;
  --critical-ink: #ff8f88;
  --critical-soft: #321513;
  --high: #f3a06a;
  --high-ink: #f5ad7e;
  --high-soft: #2a1b13;
  --warning: #e9b665;
  --warning-ink: #efc37c;
  --warning-soft: #2a2114;
  --low: #cbbfae;
  --low-ink: #d6ccbd;
  --low-soft: #201b19;
  --positive: #75c99a;
  --neutral-ink: #c7c0b5;
  --neutral-soft: #201b19;
  --R: #c7c0b5;
  --E: #e9b665;
  --Z: #ff5147;
  --graph-edge: #7d736c;
  --node-structure: #857a72;
  --node-workflow: #c7c0b5;
  --node-oidc: #e2d6c2;
  --node-role: #b3a595;
  --node-sink: #9c8c7a;
  --node-credential: #ded1bb;
  --focus: #ff5147;
  --light-color: rgba(255, 81, 71, .08);
  --r-panel: 16px;
  --r-card: 14px;
  --r-banner: 12px;
  --r-control: 10px;
  --r-button: 9px;
  --r-badge: 6px;
  --dur-1: 90ms;
  --dur-2: 140ms;
  --dur-3: 190ms;
  --ease: cubic-bezier(.2, .7, .2, 1);
  --ease-out: cubic-bezier(.16, 1, .3, 1);
  --sans: "Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --serif: "Instrument Serif", "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  --mono: "Geist Mono", ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 400 14px/1.6 var(--sans);
  font-variant-numeric: tabular-nums;
  -webkit-text-size-adjust: 100%;
}
::selection { background: rgba(255, 56, 47, .3); color: var(--ink); }
h1, h2, h3, h4, p, dl, dd, figure { margin: 0; }
h1 {
  font-family: var(--serif);
  font-size: clamp(46px, 5.2vw, 68px);
  font-weight: 400;
  line-height: .98;
  letter-spacing: -.015em;
  color: var(--ink);
}
h2 {
  font-family: var(--serif);
  font-size: 30px;
  font-weight: 400;
  line-height: 1.05;
  letter-spacing: -.01em;
}
h3 { font-size: 14px; font-weight: 600; line-height: 1.4; letter-spacing: -.005em; }
h4 { font-size: 12.5px; font-weight: 500; line-height: 1.4; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 2px; }
a:hover { text-decoration-color: currentColor; }
button { font: inherit; color: inherit; }
.mono, code, pre { font-family: var(--mono); }
.mono { font-size: 12.5px; overflow-wrap: anywhere; }
.muted { color: var(--muted); }
.empty {
  margin: 14px 0; padding: 18px; border: 1px dashed var(--border-strong); border-radius: var(--r-banner);
  background: var(--surface-2); color: var(--muted);
}
.note { margin: 12px 0; padding-left: 12px; border-left: 2px solid var(--warning); color: var(--muted); }
li.note { margin: 4px 0; padding-left: 0; border-left: 0; }
.wrap { max-width: 1160px; margin: 0 auto; padding: 0 24px; }
.skip-link { position: absolute; left: -999px; }
.skip-link:focus {
  left: 16px; top: 12px; z-index: 100; padding: 8px 12px;
  background: var(--surface); color: var(--ink); border: 1px solid var(--border-strong);
  border-radius: var(--r-button);
}
:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
#boot-status { display: none; }
html.booting #boot-status, html.boot-failed #boot-status {
  display: flex; align-items: center; gap: 10px;
  max-width: 1160px; margin: 0 auto; padding: 28px 24px;
  color: var(--muted); font-size: 13px;
}
#boot-status::before {
  content: ""; flex: none; width: 11px; height: 11px;
  border: 1.5px solid var(--accent); border-top-color: transparent; border-radius: 50%;
  animation: boot-spin 800ms linear infinite;
}
html.boot-failed #boot-status { color: var(--critical-ink); }
html.boot-failed #boot-status::before { border-color: var(--critical); border-top-color: transparent; animation: none; }
@keyframes boot-spin { to { transform: rotate(360deg); } }
.viewer-bar { position: sticky; top: 0; z-index: 50; background: var(--header); border-bottom: 1px solid var(--border); }
.viewer-inner { display: flex; align-items: center; gap: 16px; max-width: 1160px; height: 56px; margin: 0 auto; padding: 0 24px; }
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; text-decoration: none; }
.brand-mark { flex: none; width: 22px; height: 22px; color: var(--accent); }
.brand-name { font-size: 14px; font-weight: 600; letter-spacing: .005em; white-space: nowrap; }
.brand-sub { padding-left: 12px; border-left: 1px solid var(--border); color: var(--muted); font-size: 12px; white-space: nowrap; }
.viewer-meta { display: flex; align-items: center; gap: 12px; margin-left: auto; color: var(--muted); font-size: 12px; }
.viewer-chip {
  display: inline-flex; align-items: center; gap: 7px; height: 24px; padding: 0 9px;
  border: 1px solid var(--border); border-radius: var(--r-badge);
  background: var(--surface-2); color: var(--ink-2); font-size: 11px; font-weight: 500; letter-spacing: .04em;
}
.viewer-chip::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: var(--positive); }
.viewer-schema { color: var(--muted); font-size: 11px; }
.page-head {
  position: relative; isolation: isolate; overflow: hidden;
  padding: 54px 0 36px; border-bottom: 1px solid var(--border);
  --atmos-glow-opacity: .6;
  --atmos-glow-shift: 0px;
  --atmos-ring-opacity: .55;
  --atmos-ring-shift: 0px;
}
.page-head::before {
  content: ""; position: absolute; z-index: -1; top: -46%; right: -7%;
  width: min(860px, 74vw); height: 640px;
  background:
    radial-gradient(42% 55% at 58% 46%, rgba(255, 56, 47, .34), transparent 72%),
    radial-gradient(30% 42% at 36% 64%, rgba(148, 18, 12, .42), transparent 74%);
  filter: blur(38px);
  opacity: var(--atmos-glow-opacity);
  transform: rotate(-9deg) scale(1.04) translateY(var(--atmos-glow-shift));
  pointer-events: none;
}
.page-head::after {
  content: ""; position: absolute; z-index: -1; top: -34px; right: -150px;
  width: 640px; height: 520px;
  border: 1px solid rgba(255, 81, 71, .22); border-radius: 50%;
  transform: rotate(-22deg) translateY(var(--atmos-ring-shift));
  opacity: var(--atmos-ring-opacity);
  pointer-events: none;
}
.page-head > .wrap { position: relative; z-index: 1; }
.title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 40px; }
.title-copy { min-width: 0; }
.title-copy::before { content: ""; display: block; width: 46px; height: 2px; margin-bottom: 22px; background: var(--accent); }
.title-copy h1 { max-width: 20ch; text-wrap: balance; }
.source-line { margin-top: 16px; color: var(--muted); font-family: var(--mono); font-size: 11.5px; overflow-wrap: anywhere; }
.head-actions { display: flex; flex: none; flex-direction: column; align-items: stretch; gap: 8px; width: 300px; padding-top: 37px; }
.field-label { color: var(--muted); font-size: 12px; font-weight: 500; }
.field-hint { color: var(--muted); font-size: 11.5px; }
select, input[type="search"] {
  width: 100%; height: 42px; padding: 0 13px;
  border: 1px solid var(--border-strong); border-radius: var(--r-control);
  background: var(--surface-2); color: var(--ink);
  font-family: inherit; font-size: 13.5px;
  transition: border-color var(--dur-2) var(--ease), background-color var(--dur-2) var(--ease);
}
select:hover, input[type="search"]:hover { border-color: var(--muted); }
select:focus-visible, input[type="search"]:focus-visible { border-color: var(--accent); }
select:disabled { background: var(--raised); color: var(--muted); }
input[type="search"]::placeholder { color: var(--muted); }
.button {
  display: inline-flex; align-items: center; justify-content: center;
  height: 34px; padding: 0 14px;
  border: 1px solid var(--border-strong); border-radius: var(--r-button);
  background: var(--surface); color: var(--ink);
  font-size: 13px; font-weight: 500; line-height: 1; text-decoration: none;
  cursor: pointer;
  transition: background-color var(--dur-2) var(--ease), border-color var(--dur-2) var(--ease), color var(--dur-2) var(--ease);
}
.button:hover { border-color: var(--accent); background: var(--hover); }
.button.primary { border-color: var(--accent); background: var(--accent); color: var(--accent-ink); font-weight: 600; }
.button.primary:hover { border-color: var(--accent-hover); background: var(--accent-hover); }
.button.quiet { background: transparent; }
.button.quiet:hover { background: var(--hover); }
.viewer-inner .button { height: 30px; font-size: 12px; }
.head-actions .button { height: 40px; }
#finding-lead { margin-top: 20px; }
.lead {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--sev, var(--border));
  border-radius: var(--r-banner); background: var(--surface);
}
.lead.sev-CRITICAL {
  border-color: rgba(255, 81, 71, .28);
  border-left-color: var(--critical);
  background: linear-gradient(100deg, var(--critical-soft), var(--surface) 58%);
}
.lead-title { font-size: 15px; font-weight: 500; line-height: 1.4; }
.lead-meta { color: var(--muted); font-family: var(--mono); font-size: 11px; }
.lead-link { margin-left: auto; font-size: 12.5px; color: var(--ink-2); white-space: nowrap; }
.lead-link:hover { color: var(--accent); }
.lead-empty {
  padding: 16px 18px; border: 1px dashed var(--border-strong); border-radius: var(--r-banner);
  color: var(--muted);
}
.notice {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  margin-top: 12px; padding: 11px 14px;
  border: 1px solid var(--border); border-left: 3px solid var(--warning);
  border-radius: var(--r-control);
  background: var(--warning-soft); color: var(--warning-ink);
  font-size: 12px;
}
.notice strong { font-weight: 600; }
.nav-bar {
  position: sticky; top: 56px; z-index: 40;
  background: var(--bg); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
}
.nav-bar .wrap { padding-right: 16px; padding-left: 16px; }
.toc { position: relative; display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; }
.toc::-webkit-scrollbar { display: none; }
.toc a {
  position: relative; display: inline-flex; align-items: center; flex: none;
  height: 48px; padding: 0 13px;
  border: 0; border-radius: 8px; color: var(--muted); font-size: 12px; text-decoration: none; white-space: nowrap;
  transition: color var(--dur-2) var(--ease), background-color var(--dur-2) var(--ease);
}
.toc a:hover { background: var(--surface); color: var(--ink); }
.toc a[hidden] { display: none; }
.toc a:focus-visible { outline-offset: -3px; }
.toc a[aria-current="location"] { color: var(--ink); font-weight: 500; }
.nav-indicator {
  position: absolute; left: 0; bottom: -1px; width: 0; height: 2px;
  border-radius: 2px 2px 0 0; background: var(--accent); opacity: 0;
  transition: transform var(--dur-3) var(--ease-out), width var(--dur-3) var(--ease-out), opacity var(--dur-2) var(--ease);
  pointer-events: none;
}
.nav-indicator.is-active { opacity: 1; }
main { padding-bottom: 28px; }
section { position: relative; padding: 54px 0 22px; border-top: 1px solid var(--border); scroll-margin-top: 120px; }
#summary { padding-top: 36px; border-top: 0; }
.section-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.section-head h2::before { content: ""; display: block; width: 24px; height: 2px; margin-bottom: 12px; background: var(--accent); }
.section-meta { color: var(--muted); font-family: var(--mono); font-size: 11px; text-align: right; }
.summary-band {
  position: relative;
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;
  border: 0; background: none;
}
.stat {
  position: relative; z-index: 1; min-width: 0; min-height: 168px;
  padding: 20px; overflow: hidden;
  border: 1px solid var(--border); border-radius: var(--r-card);
  background: var(--surface);
  transition: border-color var(--dur-2) var(--ease), background-color var(--dur-2) var(--ease);
}
.stat:hover { border-color: var(--border-strong); background: var(--surface-2); }
.stat.is-data {
  border-color: rgba(255, 81, 71, .34);
  background: linear-gradient(158deg, #1d1210 0%, var(--surface) 58%);
}
.stat.is-data:hover { border-color: rgba(255, 81, 71, .55); }
.stat.is-data::before {
  content: ""; position: absolute; top: 0; left: 20px; width: 38px; height: 2px; background: var(--accent);
}
.stat-label { display: flex; align-items: center; gap: 8px; color: var(--ink-2); font-size: 12.5px; }
.stat-label .code { height: 19px; min-width: 19px; font-size: 10.5px; }
.stat-value {
  display: block; margin-top: 16px;
  font-family: var(--serif); font-size: 58px; font-weight: 400; line-height: .95; letter-spacing: -.01em;
  color: var(--ink);
}
.stat-value.is-data { color: var(--accent); }
.stat-note { display: block; margin-top: 10px; color: var(--muted); font-size: 12px; }
.summary-brief { max-width: 78ch; margin-top: 16px; color: var(--muted); }
.summary-band[data-light]::after {
  content: ""; position: absolute; inset: 0; z-index: 0; pointer-events: none;
  background: radial-gradient(260px circle at var(--light-x, 50%) var(--light-y, 0%), var(--light-color), transparent 70%);
  opacity: 0;
  transition: opacity var(--dur-2) var(--ease);
}
.summary-band[data-light].is-lit::after { opacity: 1; }
.pill {
  display: inline-flex; align-items: center; height: 21px; padding: 0 8px;
  border: 1px solid var(--pill-border, transparent); border-radius: var(--r-badge);
  background: var(--pill-bg, var(--neutral-soft)); color: var(--pill-ink, var(--neutral-ink));
  font-size: 10px; font-weight: 600; letter-spacing: .07em;
}
.sev-CRITICAL { --sev: var(--critical); --pill-bg: var(--critical-soft); --pill-ink: var(--critical-ink); --pill-border: rgba(255, 81, 71, .42); }
.sev-HIGH { --sev: var(--high); --pill-bg: var(--high-soft); --pill-ink: var(--high-ink); --pill-border: rgba(243, 160, 106, .36); }
.sev-MEDIUM { --sev: var(--warning); --pill-bg: var(--warning-soft); --pill-ink: var(--warning-ink); --pill-border: rgba(233, 182, 101, .32); }
.sev-LOW { --sev: var(--low); --pill-bg: var(--low-soft); --pill-ink: var(--low-ink); --pill-border: rgba(203, 191, 174, .28); }
.sev-INFO { --sev: var(--neutral-ink); --pill-bg: var(--neutral-soft); --pill-ink: var(--neutral-ink); --pill-border: rgba(199, 192, 181, .22); }
.code {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 20px; height: 20px; padding: 0 6px;
  border-radius: var(--r-badge);
  font-family: var(--mono); font-size: 11px; font-weight: 600;
}
.code-R, .status-R { background: var(--raised); color: var(--R); }
.code-E, .status-E { background: var(--warning-soft); color: var(--warning); }
.code-Z, .status-Z { background: var(--accent-soft); color: var(--critical-ink); }
.code-P, .status-P { background: var(--raised); color: var(--muted); }
.survival-rail { display: flex; gap: 3px; height: 12px; overflow: hidden; border-radius: 6px; background: transparent; }
.survival-rail span { display: block; height: 100%; border-radius: 3px; transform-origin: left center; animation: rail-in 320ms var(--ease-out) both; }
@keyframes rail-in { from { opacity: .4; transform: scaleX(.015); } to { opacity: 1; transform: scaleX(1); } }
.seg-R { background: var(--R); }
.seg-E { background: repeating-linear-gradient(135deg, var(--E) 0 4px, #57431f 4px 8px); }
.seg-Z { background: var(--Z); }
.survival-legend { display: flex; flex-wrap: wrap; gap: 8px 26px; margin-top: 14px; color: var(--muted); font-size: 12px; }
.legend-item { display: inline-flex; align-items: center; gap: 8px; }
.legend-swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.legend-count { color: var(--ink); font-weight: 500; }
.outcome-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 26px; }
.outcome {
  position: relative; min-width: 0; padding: 20px;
  border: 1px solid var(--border); border-radius: var(--r-card); background: var(--surface);
}
.outcome::before { content: ""; position: absolute; top: 0; left: 20px; width: 30px; height: 2px; background: var(--outcome-color, var(--R)); }
.outcome-R { --outcome-color: var(--R); }
.outcome-E { --outcome-color: var(--E); }
.outcome-Z { --outcome-color: var(--Z); }
.outcome.is-Z { border-color: rgba(255, 81, 71, .3); background: linear-gradient(160deg, #1b1110, var(--surface) 60%); }
.outcome-head { display: flex; align-items: center; gap: 8px; }
.outcome-title { color: var(--ink-2); font-size: 13.5px; font-weight: 500; }
.outcome-count { margin-left: auto; font-family: var(--serif); font-size: 27px; font-weight: 400; line-height: 1; color: var(--ink); }
.outcome-list { margin: 14px 0 0; padding: 0; list-style: none; }
.outcome-list li { padding: 11px 0; border-top: 1px solid var(--border); }
.outcome-list li:first-child { padding-top: 0; border-top: 0; }
.outcome-list .empty { margin: 0; padding: 0; border: 0; background: none; font-size: 12px; }
.trace-link {
  display: inline-flex; align-items: center; min-height: 24px; padding: 0; border: 0; background: none;
  color: var(--ink); font-family: inherit; font-size: 14px; font-weight: 500; line-height: 1.4;
  text-align: left; text-decoration: underline; text-decoration-color: var(--border-strong); text-underline-offset: 2px;
  cursor: pointer; overflow-wrap: anywhere;
  transition: color var(--dur-2) var(--ease), text-decoration-color var(--dur-2) var(--ease);
}
.trace-link:hover { color: var(--accent); text-decoration-color: currentColor; }
.outcome-meta { display: block; margin-top: 2px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.outcome-where { display: block; margin-top: 1px; color: var(--muted); font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.outcome-more { margin-top: 12px; font-size: 12px; }
.table-hint { margin-top: 28px; color: var(--muted); font-size: 12px; }
.table-heading { display: flex; align-items: center; gap: 8px; margin: 24px 0 8px; }
.table-wrap {
  max-width: 100%; overflow-x: auto;
  border: 1px solid var(--border); border-radius: var(--r-banner); background: var(--surface);
}
.table-wrap:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
.scroll-hint { margin: 0 0 6px; color: var(--muted); font-size: 12px; text-align: right; }
table { width: 100%; min-width: 660px; border-collapse: collapse; table-layout: fixed; font-size: 14px; }
caption {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0;
}
thead th {
  padding: 9px 12px; border-bottom: 1px solid var(--border);
  background: var(--surface-2); color: var(--muted); font-size: 11.5px; font-weight: 500; text-align: left;
  white-space: nowrap;
}
tbody td, tbody th {
  padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top;
  transition: background-color var(--dur-2) var(--ease);
}
tbody tr:hover td, tbody tr:hover th { background: var(--surface-2); }
tbody tr:last-child td, tbody tr:last-child th { border-bottom: 0; }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.wrap, th.wrap { overflow-wrap: anywhere; }
td.nowrap { white-space: nowrap; }
.table-wrap table.wide { min-width: 860px; }
.cell-id { display: block; margin-top: 2px; color: var(--muted); font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.evidence { color: var(--muted); font-size: 12.5px; overflow-wrap: anywhere; }
.evidence-list { margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: 12.5px; }
.evidence-list li { margin: 2px 0; overflow-wrap: anywhere; }
details { margin-top: 10px; }
summary {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--surface-2); color: var(--muted); font-size: 12px; cursor: pointer; list-style: none;
  transition: color var(--dur-2) var(--ease), border-color var(--dur-2) var(--ease), background-color var(--dur-2) var(--ease);
}
summary::-webkit-details-marker { display: none; }
summary::before { content: "+"; display: inline-block; width: 10px; color: var(--accent); font-family: var(--mono); font-weight: 600; }
details[open] summary::before { content: "\2212"; }
summary:hover { color: var(--ink); border-color: var(--border-strong); background: var(--raised); }
details[open] summary { margin-bottom: 10px; color: var(--ink-2); }
.details-body { padding-top: 2px; }
pre {
  margin: 8px 0 0; padding: 12px; overflow-wrap: anywhere; white-space: pre-wrap;
  background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--r-control);
  font-size: 12px; line-height: 1.5;
}
.rotation-group h3 { display: flex; align-items: center; gap: 8px; margin: 24px 0 8px; font-size: 14.5px; }
.steps { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0; overflow: hidden; border: 1px solid var(--border); border-radius: var(--r-card); background: var(--surface); }
.step { position: relative; display: grid; grid-template-columns: 40px minmax(0, 1fr); gap: 14px; padding: 16px 18px; }
.step::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: var(--border); }
.steps .step:first-child::before { display: none; }
.step-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; margin-top: 1px;
  border: 1px solid var(--border-strong); border-radius: 50%;
  color: var(--ink-2); font-family: var(--mono); font-size: 11px;
}
.step-body { min-width: 0; }
.step-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.step-title { font-weight: 600; }
.step-actions { margin: 8px 0 0; padding-left: 18px; }
.step-actions li { margin: 3px 0; }
.step-cred { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.cred-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px;
  border: 1px solid var(--border); border-radius: 7px; background: var(--surface-2);
  color: var(--ink); font-size: 12px;
}
.cred-chip .mono { color: var(--muted); }
.fact-grid {
  display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 22px;
  padding: 18px 20px; border: 1px solid var(--border); border-radius: var(--r-card); background: var(--surface);
}
.fact { min-width: 0; }
.fact-label { display: block; color: var(--muted); font-size: 12px; }
.fact-value { display: block; margin-top: 5px; font-size: 17px; font-weight: 500; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
.text-chip {
  display: inline-flex; align-items: center; padding: 3px 8px;
  border: 1px solid var(--border); border-radius: 7px; background: var(--surface-2);
  font-size: 12px; overflow-wrap: anywhere;
}
.graph-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px; margin-bottom: 12px; }
.graph-legend { display: flex; flex-wrap: wrap; gap: 6px 16px; color: var(--muted); font-size: 12px; }
.graph-legend span { display: inline-flex; align-items: center; gap: 7px; }
.graph-legend i { display: inline-block; width: 24px; border-top: 2px solid currentColor; }
.graph-legend .solid i { color: var(--graph-edge); }
.graph-legend .dashed i { color: var(--warning); border-top-style: dashed; }
.graph-legend .dotted i { color: var(--muted); border-top-style: dotted; }
.graph-legend .entry i { width: 14px; height: 10px; border: 1px dashed var(--accent); border-radius: 3px; }
.graph-actions { display: flex; align-items: center; gap: 5px; }
.graph-actions .button { min-width: 32px; height: 32px; padding: 0 9px; border-radius: 8px; font-family: var(--mono); font-size: 12px; }
#graph-zoom-level { min-width: 56px; }
#graph {
  position: relative; left: 50%;
  width: min(1520px, calc(100vw - 32px));
  margin-left: calc(min(1520px, calc(100vw - 32px)) / -2);
}
.graph-head { width: min(1112px, calc(100vw - 48px)); margin: 0 auto; }
.graph-frame {
  position: relative; overflow: hidden;
  border: 1px solid var(--border); border-radius: var(--r-panel); background: var(--surface);
}
.graph-stage {
  position: relative; height: clamp(28rem, 84vh, 54rem); overflow: hidden;
  cursor: grab; touch-action: pan-y;
  background-color: var(--surface);
  background-image: radial-gradient(circle, rgba(245, 240, 220, .07) 1px, transparent 1px);
  background-size: 18px 18px;
}
.graph-stage:focus-within { outline: 2px solid var(--focus); outline-offset: -2px; }
.graph-stage.is-panning { cursor: grabbing; }
.graph-stage.is-pannable { touch-action: none; }
.graph-viewport { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.graph-viewport.is-animated { transition: transform var(--dur-3) var(--ease-out); }
.graph-svg { display: block; overflow: visible; font-family: var(--sans); }
.gstage-band { fill: var(--surface-2); stroke: var(--border); stroke-width: 1; }
.gstage-title { fill: var(--ink-2); font-size: 12px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; }
.gstage-index { fill: var(--muted); font-family: var(--mono); font-size: 10px; letter-spacing: .04em; }
.gstage-count { fill: var(--muted); font-family: var(--mono); font-size: 12px; }
.gedge-hit { fill: none; stroke: transparent; stroke-width: 16; pointer-events: stroke; cursor: pointer; }
.gedge-line { fill: none; stroke: var(--graph-edge); stroke-width: 1.5; stroke-linecap: round; marker-end: url(#graph-arrow); transition: stroke var(--dur-2) var(--ease), stroke-width var(--dur-2) var(--ease); }
.gedge { transition: opacity var(--dur-2) var(--ease); }
.gedge.conf-assumed .gedge-line { stroke: var(--warning); stroke-dasharray: 7 4; }
.gedge.conf-unknown .gedge-line { stroke: var(--muted); stroke-dasharray: 2 4; }
.gedge:hover .gedge-line, .gedge.is-selected-edge .gedge-line { stroke-width: 2.6; }
.gedge.is-selected-edge .gedge-line { stroke: var(--accent); }
.gedge.is-traced .gedge-line { stroke: var(--accent); stroke-width: 2.6; stroke-dasharray: none; }
.gedge.is-outside { opacity: .35; }
.graph-arrow-head { fill: context-stroke; }
.gnode { cursor: pointer; outline: none; transition: opacity var(--dur-2) var(--ease); }
.gnode-shape { fill: #0f0e0d; stroke: var(--graph-edge); stroke-width: 1.6; transition: stroke var(--dur-2) var(--ease), stroke-width var(--dur-2) var(--ease), fill var(--dur-2) var(--ease); }
.gnode.kind-repository .gnode-shape, .gnode.kind-workflow .gnode-shape, .gnode.kind-job .gnode-shape { stroke: var(--node-workflow); }
.gnode.kind-action-ref .gnode-shape, .gnode.kind-external-target .gnode-shape { stroke: var(--node-structure); }
.gnode.kind-oidc-identity .gnode-shape, .gnode.kind-aws-oidc-provider .gnode-shape { stroke: var(--node-oidc); }
.gnode.kind-aws-role .gnode-shape { stroke: var(--node-role); }
.gnode.kind-sink .gnode-shape { stroke: var(--node-sink); }
.gnode.kind-credential .gnode-shape { stroke: var(--node-credential); }
.gnode-label { fill: var(--ink); font-size: 14px; font-weight: 500; }
.gnode-meta { fill: var(--muted); font-size: 11.5px; }
.gnode-badges { font-size: 9.5px; font-weight: 600; letter-spacing: .06em; }
.badge-entry { fill: var(--accent); }
.badge-critical { fill: var(--critical); }
.badge-sep { fill: var(--muted); }
.gnode-halo { fill: var(--focus); opacity: 0; pointer-events: none; transition: opacity var(--dur-2) var(--ease); }
.gnode-entry-frame { fill: none; stroke: var(--accent); stroke-width: 1.2; stroke-dasharray: 3 3; }
.gnode:hover .gnode-shape { stroke-width: 2.4; }
.gnode:focus .gnode-shape, .gnode:focus-visible .gnode-shape { stroke: var(--focus); stroke-width: 2.8; }
.gnode:focus .gnode-halo, .gnode:focus-visible .gnode-halo { opacity: .14; }
.gnode.is-critical .gnode-shape { stroke-width: 2.2; }
.gnode.is-selected .gnode-shape { stroke: var(--accent); stroke-width: 3; }
.gnode.is-selected .gnode-halo { opacity: .18; }
.gnode.is-neighbor .gnode-shape { stroke-width: 2.4; }
.gnode.is-traced .gnode-shape { stroke: var(--accent); stroke-width: 3; }
.gnode.is-outside { opacity: .45; }
.graph-stage.is-tracing .gnode:not(.is-traced) { opacity: .28; }
.graph-stage.is-tracing .gedge:not(.is-traced) { opacity: .15; }
.graph-stage.has-selection .gnode:not(.is-selected):not(.is-neighbor) { opacity: .42; }
.graph-stage.has-selection .gedge:not(.is-incident) { opacity: .3; }
.graph-empty { fill: var(--muted); font-size: 14px; }
#graph-note { max-width: 92ch; margin-top: 12px; color: var(--muted); font-size: 12px; }
#entity-details { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
#entity-details h3 { margin: 0; }
.entity-sub { margin-top: 3px; color: var(--muted); font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.entity-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.entity-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.entity-block { margin-top: 14px; }
.entity-block h4 { margin-bottom: 4px; color: var(--muted); font-size: 12px; font-weight: 500; }
.entity-links { margin: 0; padding: 0; list-style: none; }
.entity-links li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; padding: 8px 0; border-top: 1px solid var(--border); }
.entity-links li:first-child { border-top: 0; }
.entity-link-meta { color: var(--muted); font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.entity-placeholder { color: var(--muted); }
.toolbar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; margin-bottom: 10px; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field label { color: var(--muted); font-size: 12px; }
.field-search { width: 256px; }
.field-select { width: 170px; }
.toolbar-status { margin-left: auto; padding-bottom: 11px; color: var(--muted); font-size: 12px; }
.toolbar .button { height: 40px; }
.finding {
  margin-top: 10px; padding: 18px 20px 18px 18px;
  border: 1px solid var(--border); border-left: 3px solid var(--sev, var(--border));
  border-radius: var(--r-banner); background: var(--surface);
  transition: background-color var(--dur-2) var(--ease), border-color var(--dur-2) var(--ease);
}
.finding:hover { background: var(--surface-2); border-color: var(--border-strong); border-left-color: var(--sev, var(--border)); }
.finding-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.finding-head h3 { font-size: 15px; font-weight: 600; }
.finding-rule { margin-top: 6px; color: var(--muted); font-family: var(--mono); font-size: 11.5px; overflow-wrap: anywhere; }
.finding-message { margin-top: 8px; }
.finding-meta { margin-top: 6px; color: var(--muted); font-size: 12px; }
.finding-path { margin-top: 8px; color: var(--muted); font-family: var(--mono); font-size: 11.5px; overflow-wrap: anywhere; }
.matrix-summary { margin-bottom: 6px; }
.matrix-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 12px 0; color: var(--muted); font-size: 12px; }
.matrix-legend span { display: inline-flex; align-items: center; gap: 6px; }
.matrix-wrap {
  max-height: 42rem; overflow: auto;
  border: 1px solid var(--border); border-radius: var(--r-banner); background: var(--surface);
}
.matrix { min-width: max-content; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.matrix thead th { position: sticky; top: 0; z-index: 2; background: var(--raised); border-bottom: 1px solid var(--border); }
.matrix tbody th { position: sticky; left: 0; z-index: 1; min-width: 14rem; background: var(--surface); font-weight: 500; }
.matrix thead th:first-child { left: 0; z-index: 3; }
.matrix td { padding: 7px 10px; border-bottom: 1px solid var(--border); text-align: center; }
.matrix .active-row th { box-shadow: inset 2px 0 0 var(--accent); }
button.status {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 26px; height: 26px; padding: 0 6px;
  border: 1px solid transparent; border-radius: var(--r-badge);
  font-family: var(--mono); font-size: 11.5px; font-weight: 600;
  cursor: pointer;
  transition: border-color var(--dur-1) var(--ease), background-color var(--dur-1) var(--ease);
}
button.status:hover { border-color: currentColor; }
.kv { position: relative; }
.kv div { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.kv div:first-child { border-top: 1px solid var(--border); }
.kv dt { color: var(--muted); font-size: 12px; }
.kv dd { margin: 0; overflow-wrap: anywhere; }
#scope-content > .kv {
  padding: 2px 18px; background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--r-banner);
}
#scope-content > .kv div { padding: 11px 0; }
#scope-content > .kv div:first-child { border-top: 0; }
#scope-content > .kv div:last-child { border-bottom: 0; }
#scope-content > h3, #scenario-content > h3, #assumptions-content > h3,
#rotation-content > h3, #trace-content > h3 { margin-bottom: 8px; }
#scope-content > h3:not(:first-child), #scenario-content > h3:not(:first-child),
#assumptions-content > h3:not(:first-child), #rotation-content > h3:not(:first-child),
#trace-content > h3:not(:first-child) { margin-top: 24px; }
ul.plain { margin: 6px 0 0; padding-left: 18px; }
ul.plain li { margin: 3px 0; }
.trace { margin: 14px 0 0; padding: 0 0 0 16px; border-left: 1px solid var(--border-strong); list-style: none; }
.trace li { position: relative; padding: 0 0 12px 12px; }
.trace li::before { content: ""; position: absolute; left: -20px; top: 6px; width: 7px; height: 7px; border: 1px solid var(--border-strong); border-radius: 50%; background: var(--surface); }
.trace .hop { font-size: 14px; font-weight: 500; overflow-wrap: anywhere; }
.trace .muted { margin-top: 2px; font-size: 12px; }
footer { position: relative; margin-top: 36px; padding: 24px 0 44px; color: var(--muted); font-size: 12px; }
footer::before { content: ""; position: absolute; top: 0; left: 24px; right: 24px; height: 1px; background: var(--border); }
.footer-inner { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; }
@media (pointer: coarse) {
  .button, .graph-actions .button, .toolbar .button { min-height: 40px; }
  button.status { min-width: 34px; height: 34px; }
}
@media (max-width: 1000px) {
  .summary-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .outcome-grid { grid-template-columns: minmax(0, 1fr); }
  .title-row { flex-direction: column; gap: 22px; }
  .head-actions { width: 100%; padding-top: 0; }
  .fact-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .page-head { padding-top: 44px; }
  .page-head::before { right: -22%; opacity: .44; }
  .page-head::after { right: -260px; opacity: .4; }
}
@media (max-width: 720px) {
  .toc { scroll-snap-type: x proximity; }
  .toc a { scroll-snap-align: center; height: 44px; padding: 0 10px; }
  .nav-bar .wrap { padding-right: 8px; padding-left: 8px; }
  .section-head { align-items: flex-start; flex-direction: column; gap: 6px; }
  .section-meta { text-align: left; }
  .lead-link { margin-left: 0; }
}
@media (max-width: 560px) {
  .wrap { padding: 0 16px; }
  .viewer-inner { gap: 8px; padding: 0 16px; }
  .brand-sub, .viewer-schema { display: none; }
  .viewer-meta { gap: 8px; }
  h1 { font-size: clamp(36px, 10.6vw, 44px); }
  h2 { font-size: 26px; }
  .page-head { padding: 36px 0 28px; }
  .page-head::before { right: -44%; top: -58%; opacity: .34; }
  .page-head::after { right: -330px; opacity: .3; }
  .title-copy::before { margin-bottom: 16px; }
  .source-line { margin-top: 12px; }
  .head-actions .button { height: 42px; }
  .summary-band { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .stat { min-height: 138px; padding: 16px; }
  .stat-value { margin-top: 12px; font-size: 44px; }
  .stat-label { font-size: 12px; }
  .stat-note { margin-top: 8px; font-size: 11.5px; }
  .outcome { padding: 16px; }
  .step { grid-template-columns: 32px minmax(0, 1fr); gap: 10px; padding: 14px; }
  .field-search, .field-select { width: 100%; }
  .field { flex: 1 1 100%; }
  .toolbar-status { margin-left: 0; padding-bottom: 0; }
  thead th, tbody td, tbody th { padding: 8px; }
  .graph-stage { height: 30rem; }
  .graph-actions { order: 2; }
  .graph-legend { order: 1; }
  .fact-grid { grid-template-columns: minmax(0, 1fr); gap: 16px; }
}
@media (prefers-reduced-motion: reduce) {
  :root { --dur-1: 1ms; --dur-2: 1ms; --dur-3: 1ms; }
  html { scroll-behavior: auto; }
  .survival-rail span, #boot-status::before { animation: none; }
  .summary-band[data-light]::after { display: none; }
}
@page { size: A4 portrait; margin: 13mm 11mm; }
@page graph { size: A3 landscape; margin: 10mm; }
@media print {
  :root {
    color-scheme: light;
    --bg: #fff;
    --header: #fff;
    --surface: #fff;
    --surface-2: #f6f2ea;
    --raised: #eee9df;
    --hover: #fff;
    --border: #b9b0a2;
    --border-strong: #776e62;
    --ink: #141110;
    --ink-2: #3b352e;
    --muted: #4b443c;
    --accent: #a8201a;
    --accent-hover: #a8201a;
    --accent-ink: #fff;
    --accent-soft: #f7e4e1;
    --critical: #a8201a;
    --critical-ink: #7c1712;
    --critical-soft: #f7e4e1;
    --high: #8a4a12;
    --high-ink: #6f3a0c;
    --high-soft: #f6e8da;
    --warning: #6e5200;
    --warning-ink: #5a4300;
    --warning-soft: #f5efd8;
    --low: #4a443d;
    --low-ink: #3a352f;
    --low-soft: #f1eee7;
    --positive: #1f6b43;
    --R: #3a352f;
    --E: #a8770f;
    --Z: #a8201a;
    --graph-edge: #4a443d;
    --node-structure: #5d554c;
    --node-workflow: #2b2722;
    --node-oidc: #6b5f4f;
    --node-role: #6f6252;
    --node-sink: #7a5a3a;
    --node-credential: #4d4438;
    --focus: #a8201a;
    --light-color: transparent;
    --r-panel: 0;
    --r-card: 0;
    --r-banner: 0;
    --r-control: 0;
    --r-button: 0;
    --r-badge: 0;
  }
  .viewer-bar { position: static; background: #fff; border-bottom: 1px solid #000; }
  .viewer-chip { border-color: #999; background: #fff; color: #333; }
  .viewer-chip::before { background: #1f6b43; }
  .viewer-meta, #print-button, .head-actions, .nav-bar, #boot-status, .toolbar, .skip-link, .outcome-more, .scroll-hint, .graph-actions, #graph-note, #entity-details { display: none; }
  .wrap { max-width: none; }
  body { font-size: 10pt; background: #fff; color: #000; }
  h1 { font-size: 26pt; }
  h2 { font-size: 17pt; }
  .page-head { padding-top: 0; border-bottom: 1px solid #000; }
  .page-head::before, .page-head::after { display: none; }
  .title-copy::before { background: #a8201a; }
  .title-copy h1, .source-line, [data-motion-reveal] { opacity: 1 !important; transform: none !important; }
  .source-line { margin-top: 8pt; }
  .lead { border-color: #bbb; }
  .lead.sev-CRITICAL { background: #fff; border-color: #bbb; border-left-color: #a8201a; }
  .lead-link { color: #000; }
  .notice { background: #fff; }
  section { padding-top: 18pt; border-top: 1px solid #ddd; scroll-margin-top: 0; }
  #rotation { break-inside: avoid; }
  h2, h3, h4 { break-after: avoid; }
  .section-head { break-inside: avoid; break-after: avoid; }
  .section-head + div { break-before: avoid; }
  summary { border: 1px solid #bbb; background: #f6f2ea; color: #333; list-style: none; cursor: default; }
  .stat, .step, .outcome, .kv { break-inside: avoid; }
  #survival { break-before: page; }
  .finding { break-inside: auto; }
  .finding-head, .finding-rule, .finding-message { break-after: avoid; }
  .table-wrap { break-inside: auto; }
  #survival .table-wrap, #matrix .table-wrap { break-inside: avoid; }
  thead { break-after: avoid; }
  .outcome-grid, .table-hint, .scroll-hint { display: none; }
  .finding:hover, tbody tr:hover td, tbody tr:hover th { background: transparent; }
  .stat { min-height: 0; background: #fff; border-color: #999; }
  .stat.is-data { background: #fff; border-color: #999; }
  .stat.is-data::before { background: #a8201a; }
  .stat-value { font-size: 30pt; color: #000; }
  .stat-value.is-data { color: #a8201a; }
  .outcome { background: #fff; border-color: #999; }
  .outcome.is-Z { background: #fff; border-color: #999; }
  .step-no { border-color: #777; color: #333; }
  .steps { border-color: #999; }
  .seg-E { background: repeating-linear-gradient(135deg, #b8860b 0 3px, #f3e6c8 3px 6px); }
  .survival-rail span { animation: none; transform: none; opacity: 1; }
  .table-wrap, .matrix-wrap { border-color: #999; background: #fff; overflow: visible; max-height: none; }
  .matrix thead th { background: #eee9df; }
  .matrix tbody th { background: #fff; }
  #graph { page: graph; break-before: page; break-after: page; position: static; left: auto; width: auto; margin-left: 0;
    display: flex; flex-direction: column; min-height: 250mm; }
  .graph-head { width: auto; margin: 0; }
  .graph-frame { overflow: visible; border: 0; border-radius: 0; margin-block: auto; background: #fff; }
  .graph-stage { height: auto; overflow: visible; background: none; cursor: default; }
  .graph-viewport { position: static; transform: none !important; }
  .graph-svg { width: 100% !important; height: auto !important; max-height: 260mm; }
  .gstage-band { fill: #f6f2ea; stroke: #ddd; }
  .gnode-shape { fill: #fff; }
  .gnode.is-outside, .gnode.is-selected, .gnode.is-neighbor, .gnode.is-traced { opacity: 1 !important; }
  .gedge.is-outside, .gedge.is-selected-edge, .gedge.is-traced { opacity: 1 !important; }
  .graph-stage.is-tracing .gnode:not(.is-traced),
  .graph-stage.is-tracing .gedge:not(.is-traced),
  .graph-stage.has-selection .gnode:not(.is-selected):not(.is-neighbor),
  .graph-stage.has-selection .gedge:not(.is-incident) { opacity: 1 !important; }
  .table-wrap, .matrix-wrap { overflow: visible; max-height: none; }
  table, .table-wrap table.wide { min-width: 0; font-size: 8.5pt; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
  th, td { padding: 6px 8px; white-space: normal; overflow-wrap: anywhere; }
  td.nowrap { white-space: normal; }
  a { text-decoration: none; }
}
</style>
<noscript><style>html.booting body > :not(#boot-status):not(script) { visibility: visible; } #boot-status { display: none; }</style></noscript>
</head>
<body>
<div id="boot-status" role="status" aria-live="polite">Reading the embedded report data…</div>
<a class="skip-link" href="#main">Skip to report content</a>
<div class="viewer-bar">
  <div class="viewer-inner">
    <a class="brand" href="#top">
      <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="2.2" fill="currentColor"></circle>
        <path d="M12 5.4a6.6 6.6 0 0 1 0 13.2M12 2.2a9.8 9.8 0 0 1 0 19.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" opacity=".55"></path>
      </svg>
      <span class="brand-name">NHI-Blast</span>
      <span class="brand-sub">Incident exposure report</span>
    </a>
    <div class="viewer-meta">
      <span class="viewer-chip">Offline</span>
      <span class="viewer-schema mono" id="schema-line"></span>
    </div>
    <button type="button" class="button quiet" id="print-button">Print / PDF</button>
  </div>
</div>
<header class="page-head" id="top">
  <div class="wrap">
    <div class="title-row">
      <div class="title-copy">
        <h1>Incident exposure report</h1>
        <p class="source-line" id="source-line"></p>
      </div>
      <div class="head-actions">
        <label class="field-label" for="scenario-picker">Entrypoint</label>
        <select id="scenario-picker"></select>
        <span class="field-hint" id="scenario-count"></span>
        <a class="button primary" href="#rotation">Review rotation order</a>
      </div>
    </div>
    <div id="finding-lead"></div>
  </div>
</header>
<div class="nav-bar">
  <div class="wrap">
    <nav class="toc" aria-label="Report sections">
      <a href="#summary">Summary</a>
      <a href="#survival">Survival panel</a>
      <a href="#rotation">Rotation plan</a>
      <a id="matrix-link" href="#matrix" hidden>Cross-scenario exposure</a>
      <a href="#graph">Graph</a>
      <a href="#findings">Findings</a>
      <a href="#scenario">Scenario</a>
      <a href="#scope">Scope and Limits</a>
      <a href="#assumptions">Assumptions and Unknowns</a>
      <a href="#diagnostics">Diagnostics</a>
      <span class="nav-indicator" aria-hidden="true"></span>
    </nav>
  </div>
</div>
<main id="main">
  <div class="wrap">
    <noscript><p class="notice">This report needs JavaScript enabled to display its embedded data. It makes no network requests.</p></noscript>
    <section id="summary" aria-labelledby="summary-title">
      <div class="section-head">
        <h2 id="summary-title">Summary</h2>
        <p class="section-meta" id="summary-context"></p>
      </div>
      <div class="summary-band" id="summary-grid" data-light></div>
      <p class="summary-brief" id="summary-brief"></p>
    </section>
    <section id="survival" aria-labelledby="survival-title">
      <div class="section-head">
        <h2 id="survival-title">Survival panel</h2>
        <p class="section-meta">R / E / Z as recorded by the analysis</p>
      </div>
      <div id="survival-content"></div>
    </section>
    <section id="rotation" aria-labelledby="rotation-title">
      <div class="section-head">
        <h2 id="rotation-title">Rotation plan</h2>
        <p class="section-meta">Contain, rotate, verify</p>
      </div>
      <div id="rotation-content"></div>
    </section>
    <section id="matrix" aria-labelledby="matrix-title" hidden>
      <div class="section-head">
        <h2 id="matrix-title">Cross-scenario exposure</h2>
        <p class="section-meta">One credential per row, one entrypoint per column</p>
      </div>
      <p class="muted matrix-summary" id="matrix-summary"></p>
      <div class="matrix-legend" role="group" aria-label="Credential status codes">
        <span><b class="code code-R">R</b> ends with the revoked entrypoint</span>
        <span><b class="code code-E">E</b> expires on its own</span>
        <span><b class="code code-Z">Z</b> potentially survives revocation</span>
        <span><b class="code code-P">P</b> potential only through an UNKNOWN-class edge</span>
      </div>
      <div class="toolbar">
        <label class="field-label">
          <input type="checkbox" id="matrix-shared">
          Only credentials listed in more than one scenario
        </label>
      </div>
      <div id="matrix-content"></div>
    </section>
    <section id="graph" aria-labelledby="graph-title">
      <div class="graph-head">
        <div class="section-head">
          <h2 id="graph-title">Graph</h2>
          <p class="section-meta" id="graph-count">Authority paths by stage</p>
        </div>
        <div class="graph-toolbar">
          <div class="graph-legend" role="group" aria-label="Evidence line styles and entrypoints">
            <span class="solid"><i></i>DECLARED / DERIVED</span>
            <span class="dashed"><i></i>ASSUMED</span>
            <span class="dotted"><i></i>UNKNOWN</span>
            <span class="entry"><i></i>ENTRYPOINT</span>
          </div>
          <div class="graph-actions" role="group" aria-label="Graph view controls">
            <button class="button quiet" id="graph-zoom-out" type="button" aria-label="Zoom out">&minus;</button>
            <button class="button quiet" id="graph-zoom-level" type="button" aria-label="Reset zoom to 100 percent">100%</button>
            <button class="button quiet" id="graph-zoom-in" type="button" aria-label="Zoom in">+</button>
            <button class="button quiet" id="graph-fit" type="button">Fit</button>
          </div>
        </div>
      </div>
      <div class="graph-frame">
        <div class="graph-stage" id="graph-stage" role="group"
          aria-label="Authority graph. Keyboard: arrow keys move between nodes, Enter selects, Escape clears.">
          __GRAPH_SVG__
        </div>
      </div>
      <p id="graph-note">The selected entrypoint's reachable path is highlighted; unrelated nodes are dimmed. Tab into the graph; arrow keys move, Enter selects, Escape clears. Drag or pinch to pan and zoom; Ctrl + wheel also zooms; the controls set an exact level. Fit shows the whole graph; dense graphs open at 100% on the first entrypoint. The graph is a visual aid; the scenario, survival and findings sections carry the same evidence as text.</p>
      <div id="entity-details" aria-live="polite"></div>
    </section>
    <section id="findings" aria-labelledby="findings-title">
      <div class="section-head">
        <h2 id="findings-title">Findings</h2>
        <p class="section-meta">Ordered by severity, then rule and identifier</p>
      </div>
      <div class="toolbar" role="group" aria-label="Filter findings">
        <div class="field field-search">
          <label for="finding-search">Filter</label>
          <input type="search" id="finding-search" autocomplete="off" spellcheck="false"
            placeholder="Rule, title, scenario, evidence">
        </div>
        <div class="field field-select">
          <label for="finding-severity">Severity</label>
          <select id="finding-severity"></select>
        </div>
        <div class="field field-select">
          <label for="finding-scenario">Scenario</label>
          <select id="finding-scenario"></select>
        </div>
        <button type="button" class="button quiet" id="finding-clear">Clear filters</button>
        <span id="findings-count" class="toolbar-status" role="status" aria-live="polite"></span>
      </div>
      <div id="findings-content"></div>
    </section>
    <section id="scenario" aria-labelledby="scenario-title">
      <div class="section-head">
        <h2 id="scenario-title">Scenario</h2>
        <p class="section-meta">Start nodes and recorded inputs</p>
      </div>
      <div id="scenario-content"></div>
      <div id="trace-content" aria-live="polite"></div>
    </section>
    <section id="scope" aria-labelledby="scope-title">
      <div class="section-head">
        <h2 id="scope-title">Scope and Limits</h2>
        <p class="section-meta">Inputs, coverage and the analysis boundary</p>
      </div>
      <div id="scope-content"></div>
    </section>
    <section id="assumptions" aria-labelledby="assumptions-title">
      <div class="section-head">
        <h2 id="assumptions-title">Assumptions and Unknowns</h2>
        <p class="section-meta">VERIFY items remain assumed until confirmed</p>
      </div>
      <div id="assumptions-content"></div>
    </section>
    <section id="diagnostics" aria-labelledby="diagnostics-title">
      <div class="section-head">
        <h2 id="diagnostics-title">Diagnostics</h2>
        <p class="section-meta">Parse and analysis messages</p>
      </div>
      <div id="diagnostics-content"></div>
    </section>
  </div>
</main>
<footer>
  <div class="wrap footer-inner">
    <p id="tool-line"></p>
    <p id="repo-line"></p>
    <p>Offline report generated by NHI-Blast. Evidence classes are labels, not proof of exploitation.</p>
  </div>
</footer>
__SCRIPTS__
</body>
</html>
"""

APP_JS = r"""(function () {
  "use strict";
  let bootComplete = false;
  function reportBootFailure() {
    if (bootComplete) { return; }
    bootComplete = true;
    const status = document.getElementById("boot-status");
    if (status) {
      status.textContent =
        "The embedded report data could not be read. Regenerate the report from the NHI-Blast CLI.";
    }
    document.documentElement.classList.remove("booting");
    document.documentElement.classList.add("boot-failed");
  }
  window.addEventListener("error", reportBootFailure);
  const bootFallback = window.setTimeout(reportBootFailure, 4000);
  const report = JSON.parse(document.getElementById("report-data").textContent);
  const nodes = new Map((report.graph.nodes || []).map((item) => [item.id, item]));
  const edges = new Map((report.graph.edges || []).map((item) => [item.id, item]));
  const adjacency = new Map();
  (report.graph.edges || []).forEach((edge) => {
    if (!adjacency.has(edge.src)) { adjacency.set(edge.src, []); }
    adjacency.get(edge.src).push(edge);
  });
  adjacency.forEach((outgoing) => {
    outgoing.sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0);
  });
  const scenarios = report.scenarios || [];
  const severityOrder = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4};
  const findings = (report.findings || []).slice().sort((left, right) => {
    const order = severityOrder[left.severity] - severityOrder[right.severity];
    if (order !== 0) { return order; }
    if (left.rule !== right.rule) { return left.rule < right.rule ? -1 : 1; }
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
  });
  let currentScenarioIndex = 0;
  let graphView = null;
  let graphSelection = null;
  const entryIds = new Set();
  scenarios.forEach((scenario) => {
    (scenario.start_nodes || []).forEach((id) => entryIds.add(id));
  });

  function prefersReducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  const motion = window.Motion && typeof window.Motion.animate === "function"
    ? window.Motion
    : null;
  if (motion && motion.MotionGlobalConfig) {
    motion.MotionGlobalConfig.skipAnimations = prefersReducedMotion();
  }

  function startMotionIntro() {
    if (!motion || prefersReducedMotion()) { return; }
    const head = document.querySelector(".page-head");
    const title = document.querySelector(".title-copy h1");
    const source = document.querySelector(".source-line");
    const ease = [0.22, 1, 0.36, 1];
    if (head) {
      head.style.setProperty("--atmos-glow-opacity", "0");
      head.style.setProperty("--atmos-ring-opacity", "0");
      motion.animate(head, {
        "--atmos-glow-opacity": [0, 0.6],
        "--atmos-glow-shift": ["16px", "0px"],
        "--atmos-ring-opacity": [0, 0.55],
        "--atmos-ring-shift": ["12px", "0px"]
      }, { duration: 1.15, ease });
    }
    if (title) {
      title.style.opacity = "0";
      motion.animate(title, {
        opacity: [0, 1],
        transform: ["translateY(8px)", "translateY(0px)"]
      }, {
        duration: 0.5,
        ease,
        onComplete: () => {
          title.style.opacity = "";
          title.style.transform = "";
        }
      });
    }
    if (source) {
      source.style.opacity = "0";
      motion.animate(source, {
        opacity: [0, 1],
        transform: ["translateY(4px)", "translateY(0px)"]
      }, {
        duration: 0.42,
        delay: 0.08,
        ease,
        onComplete: () => {
          source.style.opacity = "";
          source.style.transform = "";
        }
      });
    }
  }

  function animatePresence(item) {
    if (!motion || prefersReducedMotion()) { return; }
    item.style.opacity = "0";
    motion.animate(item, {
      opacity: [0, 1],
      transform: ["translateY(6px)", "translateY(0px)"]
    }, {
      duration: 0.2,
      ease: [0.22, 1, 0.36, 1],
      onComplete: () => {
        item.style.opacity = "";
        item.style.transform = "";
      }
    });
  }

  function startMotionReveals() {
    if (!motion || !motion.inView || prefersReducedMotion()) { return; }
    const ease = [0.22, 1, 0.36, 1];
    const targets = ["#survival-content", "#rotation-content", "#graph .graph-frame"]
      .map((selector) => document.querySelector(selector))
      .filter((element) => element && element.getBoundingClientRect().top > window.innerHeight * 0.8);
    targets.forEach((element, index) => {
      element.setAttribute("data-motion-reveal", "");
      element.style.opacity = "0";
      const stop = motion.inView(element, () => {
        stop();
        motion.animate(element, {
          opacity: [0, 1],
          transform: ["translateY(14px)", "translateY(0px)"]
        }, {
          duration: 0.5,
          delay: index * 0.05,
          ease,
          onComplete: () => {
            element.style.opacity = "";
            element.style.transform = "";
          }
        });
      }, { amount: 0.12 });
    });
  }

  function clear(container) {
    container.replaceChildren();
  }

  function writeText(item, className, value) {
    const text = String(value);
    if (
      className &&
      /(?:^|\s)(?:mono|wrap|evidence|cell-id|finding-rule)(?:\s|$)/.test(className) &&
      text.length > 18
    ) {
      let start = 0;
      for (let index = 0; index < text.length; index += 1) {
        const separator = ":/#_-".indexOf(text[index]) !== -1;
        const nextIsSeparator = index + 1 < text.length && ":/#_-".indexOf(text[index + 1]) !== -1;
        if (separator && !nextIsSeparator && index + 1 < text.length) {
          item.appendChild(document.createTextNode(text.slice(start, index + 1)));
          item.appendChild(document.createElement("wbr"));
          start = index + 1;
        }
      }
      item.appendChild(document.createTextNode(text.slice(start)));
      return;
    }
    item.textContent = text;
  }

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) { item.className = className; }
    if (text !== undefined && text !== null) { writeText(item, className, text); }
    return item;
  }

  function append(parent, tag, className, text) {
    const item = element(tag, className, text);
    parent.appendChild(item);
    return item;
  }

  function textOf(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function plural(count, singular, pluralForm) {
    return count + " " + (count === 1 ? singular : pluralForm || singular + "s");
  }

  function evidenceLabel(evidence) {
    const cls = textOf(evidence.cls);
    const rule = textOf(evidence.rule);
    const file = textOf(evidence.file);
    const line = evidence.line === undefined || evidence.line === null ? "" : ":" + evidence.line;
    const detail = textOf(evidence.detail);
    const parts = [cls, rule];
    if (file) { parts.push(file + line); }
    if (detail) { parts.push(detail); }
    return parts.filter(Boolean).join(" ");
  }

  function evidenceList(container, evidence) {
    if (!evidence || evidence.length === 0) {
      append(container, "p", "empty", "No evidence record is attached.");
      return;
    }
    const list = append(container, "ul", "evidence-list");
    evidence.forEach((item) => append(list, "li", "evidence", evidenceLabel(item)));
  }

  function nodeLabel(id) {
    const item = nodes.get(id);
    return item ? item.label + " (" + item.id + ")" : textOf(id);
  }

  function nodeEvidence(id) {
    const item = nodes.get(id);
    if (!item || !item.evidence || !item.evidence.length) { return ""; }
    return evidenceLabel(item.evidence[0]);
  }

  function addColumns(table, widths) {
    const columns = append(table, "colgroup");
    widths.forEach((width) => {
      append(columns, "col").style.width = width;
    });
  }

  function watchOverflow(scroll) {
    const hint = element("p", "scroll-hint", "Scroll sideways for all columns");
    hint.hidden = true;
    scroll.parentNode.insertBefore(hint, scroll);
    let resize = null;
    let mutations = null;
    const sync = () => {
      if (!scroll.isConnected) {
        if (resize) { resize.disconnect(); }
        if (mutations) { mutations.disconnect(); }
        return;
      }
      const more = scroll.scrollWidth - scroll.clientWidth > 2;
      const atEnd = scroll.scrollLeft + scroll.clientWidth >= scroll.scrollWidth - 2;
      hint.hidden = !more || atEnd;
    };
    scroll.addEventListener("scroll", sync, { passive: true });
    if (window.ResizeObserver) {
      resize = new ResizeObserver(sync);
      resize.observe(scroll);
    }
    if (window.MutationObserver && scroll.firstElementChild) {
      mutations = new MutationObserver(sync);
      mutations.observe(scroll.firstElementChild, { childList: true, subtree: true });
    }
    sync();
  }

  function tableRegion(container, caption) {
    const scroll = append(container, "div", "table-wrap");
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", caption);
    const table = append(scroll, "table");
    watchOverflow(scroll);
    return table;
  }

  function addTable(container, caption, headings, rows, aligns, widths) {
    if (!rows.length) {
      append(container, "p", "empty", "No entries.");
      return;
    }
    const table = tableRegion(container, caption);
    table.className = headings.length >= 6 ? "wide" : "";
    append(table, "caption", "", caption);
    if (widths) { addColumns(table, widths); }
    const head = append(table, "thead");
    const headRow = append(head, "tr");
    headings.forEach((heading, index) => {
      const numeric = aligns && aligns[index] === "num";
      const cell = append(headRow, "th", numeric ? "num" : "", heading);
      cell.scope = "col";
    });
    const body = append(table, "tbody");
    rows.forEach((row) => {
      const tr = append(body, "tr");
      row.forEach((value, index) => {
        const align = aligns && aligns[index] ? aligns[index] : "";
        const suffix = align === "num" ? " num" : align === "nowrap" ? " nowrap" : "";
        const cell = append(tr, "td", "wrap" + suffix);
        if (value && typeof value === "object" && typeof value.nodeType === "number") {
          cell.appendChild(value);
        } else {
          writeText(cell, cell.className, textOf(value));
        }
      });
    });
  }

  function credentialCell(id) {
    const item = nodes.get(id);
    const wrap = element("div");
    wrap.appendChild(traceButton(id, item ? item.label : id));
    const line = append(wrap, "span", "cell-id");
    String(id).split(/([/_.:])/).forEach((part) => {
      if (!part) { return; }
      line.appendChild(document.createTextNode(part));
      if (/^[/_.:]$/.test(part)) { line.appendChild(document.createElement("wbr")); }
    });
    return wrap;
  }

  function joinParts(parts) {
    return parts.map(textOf).filter((part) => part.length > 0).join(" · ");
  }

  function nodeWhere(id) {
    const item = nodes.get(id);
    if (!item || !item.attrs) { return ""; }
    if (item.attrs.job) { return textOf(item.attrs.job).replace(/^job:/, ""); }
    return textOf(item.attrs.sink);
  }

  function credentialHeading(id) {
    const item = nodes.get(id);
    const label = item ? item.label : textOf(id);
    const job = item && item.attrs ? textOf(item.attrs.job) : "";
    if (!job) { return label; }
    const path = job.replace(/^job:/, "");
    return label + " · " + path.slice(path.lastIndexOf("/") + 1);
  }

  function renderSourceLine() {
    const digest = textOf(report.inputs.digest);
    const short = digest.length > 12 ? digest.slice(0, 12) + "…" : digest;
    const when = report.generated_at ? "generated " + report.generated_at : "snapshot · no timestamp";
    document.getElementById("source-line").textContent =
      report.inputs.repo_slug + " · inputs digest " + short + " · " + when;
  }

  function renderScope() {
    const target = document.getElementById("scope-content");
    clear(target);
    const details = append(target, "dl", "kv");
    [
      ["Repository", report.inputs.repo_slug, false],
      ["Repository identity source", report.inputs.repo_slug_source, false],
      ["Inputs digest", report.inputs.digest, true],
      ["Tool", report.tool.name + " " + report.tool.version, false],
      ["Generated at", report.generated_at || "Not recorded (deterministic artifact)", false]
    ].forEach((pair) => {
      const row = append(details, "div");
      append(row, "dt", "", pair[0]);
      append(row, "dd", pair[2] ? "mono" : "", pair[1]);
    });
    append(target, "h3", "", "Limits");
    if (report.scope_and_limits && report.scope_and_limits.length) {
      const limits = append(target, "ul", "plain");
      report.scope_and_limits.forEach((item) => append(limits, "li", "", item));
    } else {
      append(target, "p", "empty", "No scope limits are recorded.");
    }
    append(target, "h3", "", "Input files");
    addTable(
      target,
      "Input files",
      ["Path", "Kind", "SHA-256"],
      (report.inputs.files || []).map((item) => [
        item.path,
        item.kind,
        element("span", "mono", item.sha256)
      ]),
      ["", "nowrap", ""],
      ["42%", "22%", "36%"]
    );
    append(target, "h3", "", "Data files");
    addTable(
      target,
      "Platform data files",
      ["Name", "Verified", "Entries", "Source"],
      (report.data_files || []).map((item) => [
        item.name,
        item.verified_on,
        item.entry_count,
        element("span", "mono", item.source_url)
      ]),
      ["", "nowrap", "num", ""],
      ["20%", "16%", "11%", "53%"]
    );
  }

  let lastMetrics = {};
  let firstSummaryRender = true;

  const readoutAnimations = new WeakMap();

  function animateReadout(item, from, to) {
    if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) {
      item.textContent = String(to);
      return;
    }
    const running = readoutAnimations.get(item);
    if (running) { running.stop(); }
    if (!motion || prefersReducedMotion()) {
      item.textContent = String(to);
      return;
    }
    const control = motion.animate(from, to, {
      duration: 0.19,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (value) => {
        item.textContent = String(Math.round(value));
      },
      onComplete: () => {
        item.textContent = String(to);
        readoutAnimations.delete(item);
      }
    });
    readoutAnimations.set(item, control);
  }

  function renderSummary(scenario) {
    const target = document.getElementById("summary-grid");
    const brief = document.getElementById("summary-brief");
    const context = document.getElementById("summary-context");
    clear(target);
    clear(brief);
    if (context) { clear(context); }
    const partition = scenario ? scenario.partition : {R: [], E: [], Z: []};
    const total = partition.R.length + partition.E.length + partition.Z.length;
    const critical = findings.filter((finding) => finding.severity === "CRITICAL").length;
    const metrics = [
      {
        label: "Potentially surviving",
        code: "Z",
        value: scenario ? partition.Z.length : null,
        note: scenario ? "of " + plural(total, "listed credential") : "no entrypoint selected",
        data: true
      },
      {
        label: "Ends with entrypoint",
        code: "R",
        value: scenario ? partition.R.length : null,
        note: "end when it is revoked",
        data: false
      },
      {
        label: "Expires on its own",
        code: "E",
        value: scenario ? partition.E.length : null,
        note: "expire without rotation",
        data: false
      },
      {
        label: "Findings",
        code: "",
        value: findings.length,
        note: findings.length
          ? (critical ? critical + " critical" : "none critical") +
            (scenarios.length > 1 ? " · all entrypoints" : "")
          : "none recorded",
        data: false
      }
    ];
    metrics.forEach((metric) => {
      const card = append(target, "div", "stat" + (metric.data ? " is-data" : ""));
      const label = append(card, "span", "stat-label");
      if (metric.code) { append(label, "span", "code code-" + metric.code, metric.code); }
      append(label, "span", "", metric.label);
      const value = append(card, "strong", "stat-value" + (metric.data ? " is-data" : ""));
      const previous = lastMetrics[metric.code || "findings"];
      if (typeof metric.value === "number") {
        value.textContent = String(metric.value);
        if (!firstSummaryRender && previous !== undefined && previous !== metric.value) {
          animateReadout(value, previous, metric.value);
        }
      } else {
        value.textContent = "—";
      }
      lastMetrics[metric.code || "findings"] = metric.value;
      append(card, "span", "stat-note", metric.note);
    });
    firstSummaryRender = false;
    if (context) {
      context.textContent = scenario
        ? scenario.selector
        : "No entrypoint scenario is available";
    }
    if (!scenario) {
      brief.textContent =
        "No entrypoint scenario is available in this report. The counts describe the parsed graph and findings only.";
      return;
    }
    const unresolved = (scenario.unresolved_inputs || []).length;
    const parts = ["Selected entrypoint " + scenario.selector + "."];
    if (scenario.truncated) {
      parts.push("The traversal was truncated at the configured limit; the counts are a lower bound.");
    }
    if (unresolved) {
      parts.push("The result is a lower bound: " + plural(unresolved, "input") + " could not be resolved.");
    } else if (!scenario.truncated) {
      parts.push("All inputs were resolved.");
    }
    brief.textContent = parts.join(" ");
  }

  function renderLead(scenario) {
    const target = document.getElementById("finding-lead");
    clear(target);
    if (!scenarios.length) {
      const notice = append(target, "p", "notice");
      append(notice, "strong", "", "No entrypoint scenario");
      append(
        notice,
        "span",
        "",
        "Survival and rotation are unavailable in this report. The graph, findings and scope are still shown."
      );
    }
    if (!findings.length) {
      if (scenarios.length) {
        append(target, "p", "lead-empty", "No findings were generated for this report.");
      }
      return;
    }
    const scoped = scenario
      ? findings.filter((finding) => !finding.scenario || finding.scenario === scenario.selector)
      : findings;
    const finding = scoped[0] || findings[0];
    const row = append(target, "div", "lead sev-" + finding.severity);
    append(row, "span", "pill sev-" + finding.severity, finding.severity);
    append(row, "span", "lead-title", finding.title);
    append(
      row,
      "span",
      "lead-meta",
      finding.rule + (finding.scenario ? " · " + finding.scenario : "")
    );
    const link = element("a", "lead-link", findings.length === 1 ? "View the finding" : "All " + plural(findings.length, "finding"));
    link.href = "#findings";
    row.appendChild(link);
  }

  function renderScenarioPicker() {
    const picker = document.getElementById("scenario-picker");
    clear(picker);
    const items = report.scenarios || [];
    if (!items.length) {
      const option = append(picker, "option", "", "No scenarios selected");
      option.value = "";
      picker.disabled = true;
    } else {
      picker.disabled = false;
      items.forEach((scenario, index) => {
        const option = append(picker, "option", "", scenario.selector);
        option.value = String(index);
      });
      picker.addEventListener("change", () => {
        selectScenario(Number(picker.value));
      });
    }
    selectScenario(0);
  }

  function selectScenario(index) {
    currentScenarioIndex = index;
    const picker = document.getElementById("scenario-picker");
    if (picker && !picker.disabled) { picker.value = String(index); }
    const scenario = scenarios[index] || null;
    const count = document.getElementById("scenario-count");
    if (count) {
      count.textContent = scenarios.length
        ? (index + 1) + " of " + plural(scenarios.length, "entrypoint")
        : "No entrypoints";
    }
    renderLead(scenario);
    renderSummary(scenario);
    renderScenario(index);
    renderMatrix();
  }

  function renderScenario(index) {
    const scenario = scenarios[index];
    const target = document.getElementById("scenario-content");
    clear(target);
    renderTrace(null);
    if (!scenario) {
      append(target, "p", "empty", "No scenario is available.");
      renderSurvival(null);
      renderRotation(null);
      renderGraph(null);
      return;
    }
    const facts = append(target, "div", "fact-grid");
    const start = append(facts, "div", "fact");
    append(start, "span", "fact-label", "Start nodes");
    const chips = append(start, "div", "chip-row");
    (scenario.start_nodes || []).forEach((id) => {
      const item = nodes.get(id);
      const chip = append(chips, "span", "text-chip", item ? item.label : id);
      chip.title = id;
    });
    [
      ["UNKNOWN-class potential edges", scenario.potential.length],
      ["Unresolved inputs", (scenario.unresolved_inputs || []).length],
      ["Traversal truncated", scenario.truncated ? "yes" : "no"]
    ].forEach((pair) => {
      const fact = append(facts, "div", "fact");
      append(fact, "span", "fact-label", pair[0]);
      append(fact, "span", "fact-value", pair[1]);
    });
    if (scenario.notes && scenario.notes.length) {
      append(target, "h3", "", "Notes");
      const notes = append(target, "ul", "plain");
      scenario.notes.forEach((note) => append(notes, "li", "note", note));
    }
    renderSurvival(scenario);
    renderRotation(scenario);
    renderGraph(scenario);
  }

  function traceButton(id, text) {
    const item = nodes.get(id);
    const label = text || (item ? item.label : textOf(id));
    const button = element("button", "trace-link", label);
    button.type = "button";
    button.title = "Trace one shortest path from this scenario's entrypoint";
    button.setAttribute("aria-label", "Trace a path from the entrypoint to " + nodeLabel(id));
    button.addEventListener("click", () => traceTo(id));
    return button;
  }

  function renderSurvival(scenario) {
    const target = document.getElementById("survival-content");
    clear(target);
    if (!scenario) {
      append(target, "p", "empty", "No scenario partition is available.");
      return;
    }
    const partition = scenario.partition;
    const total = partition.R.length + partition.E.length + partition.Z.length;
    if (!total) {
      append(target, "p", "empty", "No credentials are listed in this scenario.");
      return;
    }
    const rail = append(target, "div", "survival-rail");
    rail.setAttribute("role", "img");
    rail.setAttribute(
      "aria-label",
      "Credential outcomes: " + partition.R.length + " end with the entrypoint, " +
        partition.E.length + " expire on their own, " + partition.Z.length +
        " potentially survive revocation."
    );
    [
      ["R", partition.R.length],
      ["E", partition.E.length],
      ["Z", partition.Z.length]
    ].forEach((pair) => {
      if (!pair[1]) { return; }
      const segment = append(rail, "span", "seg-" + pair[0]);
      segment.style.width = (pair[1] / total * 100).toFixed(4) + "%";
      segment.title = plural(pair[1], "credential") + " in " + pair[0];
    });
    const legend = append(target, "div", "survival-legend");
    [
      ["R", "Ends with entrypoint", partition.R.length],
      ["E", "Expires on its own", partition.E.length],
      ["Z", "Potentially survives revocation", partition.Z.length]
    ].forEach((pair) => {
      const item = append(legend, "span", "legend-item");
      append(item, "i", "legend-swatch seg-" + pair[0]);
      append(item, "span", "", pair[1]);
      append(item, "span", "legend-count", pair[2]);
    });
    const grid = append(target, "div", "outcome-grid");
    renderOutcome(grid, "R", "Ends with entrypoint", partition.R.map((id) => ({
      id,
      label: nodes.get(id) ? nodes.get(id).label : id,
      meta: joinParts([
        nodes.get(id) ? textOf(nodes.get(id).attrs.credential_kind) : "",
        nodes.get(id) ? textOf(nodes.get(id).attrs.lifetime) : ""
      ]),
      where: nodeWhere(id)
    })));
    renderOutcome(grid, "E", "Expires on its own", partition.E.map((entry) => ({
      id: entry.credential,
      label: nodes.get(entry.credential) ? nodes.get(entry.credential).label : entry.credential,
      meta: joinParts([
        nodes.get(entry.credential) ? textOf(nodes.get(entry.credential).attrs.credential_kind) : "",
        "TTL " + entry.ttl_seconds + " s"
      ]),
      where: nodeWhere(entry.credential)
    })));
    renderOutcome(grid, "Z", "Potentially survives revocation", partition.Z.map((entry) => ({
      id: entry.credential,
      label: nodes.get(entry.credential) ? nodes.get(entry.credential).label : entry.credential,
      meta: joinParts([
        entry.lifetime,
        entry.survival_window,
        "criticality " + entry.criticality
      ]),
      where: nodeWhere(entry.credential)
    })));
    append(
      target,
      "p",
      "table-hint",
      "Select a credential name to trace one shortest directed path from this scenario's entrypoint."
    );
    const headingR = append(target, "h3", "table-heading");
    append(headingR, "span", "code code-R", "R");
    append(headingR, "span", "", "Credentials that end with the revoked entrypoint");
    headingR.id = "survival-r";
    addTable(
      target,
      "Credentials that end with the revoked entrypoint",
      ["Credential", "Kind", "Lifetime", "Evidence"],
      partition.R.map((id) => [
        credentialCell(id),
        nodes.get(id) ? textOf(nodes.get(id).attrs.credential_kind) : "",
        nodes.get(id) ? textOf(nodes.get(id).attrs.lifetime) : "",
        nodeEvidence(id)
      ]),
      ["", "nowrap", "nowrap", ""],
      ["38%", "15%", "14%", "33%"]
    );
    const headingE = append(target, "h3", "table-heading");
    append(headingE, "span", "code code-E", "E");
    append(headingE, "span", "", "Credentials that expire on their own");
    headingE.id = "survival-e";
    addTable(
      target,
      "Credentials that expire on their own",
      ["Credential", "TTL (seconds)", "Kind", "Evidence"],
      partition.E.map((entry) => [
        credentialCell(entry.credential),
        entry.ttl_seconds,
        nodes.get(entry.credential) ? textOf(nodes.get(entry.credential).attrs.credential_kind) : "",
        nodeEvidence(entry.credential)
      ]),
      ["", "num", "nowrap", ""],
      ["36%", "12%", "16%", "36%"]
    );
    const headingZ = append(target, "h3", "table-heading");
    append(headingZ, "span", "code code-Z", "Z");
    append(headingZ, "span", "", "Credentials that survive revocation");
    headingZ.id = "survival-z";
    addTable(
      target,
      "Credentials that survive revocation",
      ["Credential", "Depth", "Lifetime", "Survival window", "Criticality", "Evidence"],
      partition.Z.map((entry) => [
        credentialCell(entry.credential),
        entry.depth,
        entry.lifetime,
        entry.survival_window,
        entry.criticality,
        nodeEvidence(entry.credential)
      ]),
      ["", "num", "nowrap", "nowrap", "num", ""],
      ["28%", "7%", "12%", "16%", "11%", "26%"]
    );
  }

  function renderOutcome(grid, code, title, entries) {
    const column = append(grid, "div", "outcome outcome-" + code + (code === "Z" ? " is-Z" : ""));
    const head = append(column, "div", "outcome-head");
    append(head, "span", "code code-" + code, code);
    append(head, "span", "outcome-title", title);
    append(head, "span", "outcome-count", entries.length);
    const list = append(column, "ul", "outcome-list");
    if (!entries.length) {
      append(list, "li", "empty", "None listed.");
      return;
    }
    entries.slice(0, 4).forEach((entry) => {
      const item = append(list, "li");
      item.appendChild(traceButton(entry.id, entry.label));
      if (entry.meta) { append(item, "span", "outcome-meta", entry.meta); }
      if (entry.where) { append(item, "span", "outcome-where", entry.where); }
    });
    if (entries.length > 4) {
      const more = append(column, "p", "outcome-more");
      const link = append(more, "a", "", "+ " + (entries.length - 4) + " more in the table");
      link.href = "#survival-" + code.toLowerCase();
    }
  }

  function shortestPath(starts, target) {
    if (!starts || !starts.length) { return null; }
    if (starts.includes(target)) { return []; }
    const depth = new Map();
    const previous = new Map();
    const queue = [];
    starts.slice().sort().forEach((id) => {
      if (depth.has(id)) { return; }
      depth.set(id, 0);
      queue.push(id);
    });
    for (let head = 0; head < queue.length; head += 1) {
      const current = queue[head];
      const outgoing = adjacency.get(current) || [];
      for (const edge of outgoing) {
        if (depth.has(edge.dst)) { continue; }
        depth.set(edge.dst, depth.get(current) + 1);
        previous.set(edge.dst, edge);
        if (edge.dst === target) {
          const path = [];
          let cursor = target;
          while (previous.has(cursor)) {
            const step = previous.get(cursor);
            path.push(step);
            cursor = step.src;
          }
          return path.reverse();
        }
        queue.push(edge.dst);
      }
    }
    return null;
  }

  function clearGraphTrace() {
    if (!graphView) { return; }
    graphView.stage.classList.remove("is-tracing");
    graphView.nodes.forEach((node) => node.classList.remove("is-traced"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-traced"));
  }

  function highlightGraphTrace(path) {
    if (!graphView) { return; }
    clearGraphTrace();
    graphView.stage.classList.add("is-tracing");
    const tracedEdges = new Set(path.map((edge) => edge.id));
    const tracedNodes = new Set();
    path.forEach((edge) => {
      tracedNodes.add(edge.src);
      tracedNodes.add(edge.dst);
    });
    tracedNodes.forEach((id) => {
      const node = graphView.nodes.get(id);
      if (node) { node.classList.add("is-traced"); }
    });
    tracedEdges.forEach((id) => {
      const edge = graphView.edges.get(id);
      if (edge) { edge.classList.add("is-traced"); }
    });
  }

  function renderTrace(path, targetId) {
    const target = document.getElementById("trace-content");
    clear(target);
    if (!targetId) {
      clearGraphTrace();
      return;
    }
    append(target, "h3", "", "Path trace: " + nodeLabel(targetId));
    append(
      target,
      "p",
      "muted",
      "One shortest directed path in the report graph. This is a visual aid; " +
        "R/E/Z membership comes from the analysis, not from this trace."
    );
    if (path === null) {
      append(
        target,
        "p",
        "empty",
        "No directed path from the selected entrypoint to this entity is recorded."
      );
      clearGraphTrace();
      return;
    }
    if (!path.length) {
      append(target, "p", "empty", "This entity is itself a start node of the scenario.");
      clearGraphTrace();
      return;
    }
    const hasUnknown = path.some((edge) => edge.confidence === "unknown");
    if (hasUnknown) {
      append(
        target,
        "p",
        "note",
        "This trace includes UNKNOWN-class edges; it is a potential path only."
      );
    }
    const list = append(target, "ol", "trace");
    path.forEach((edge) => {
      const item = append(list, "li");
      const hop = append(item, "p", "hop mono");
      hop.textContent = nodeLabel(edge.src) + " -> " + nodeLabel(edge.dst);
      append(item, "p", "muted", edge.kind + " edge; confidence " + edge.confidence);
      const evidence = append(item, "div");
      evidenceList(evidence, (edge.evidence || []).slice(0, 1));
    });
    const clearButton = element("button", "button quiet", "Clear trace");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => renderTrace(null, null));
    append(target, "p").appendChild(clearButton);
    highlightGraphTrace(path);
  }

  function traceTo(targetId) {
    const scenario = scenarios[currentScenarioIndex] || null;
    if (!scenario) {
      renderTrace(null, null);
      return;
    }
    renderTrace(shortestPath(scenario.start_nodes || [], targetId), targetId);
    const target = document.getElementById("trace-content");
    if (target) { target.scrollIntoView({block: "nearest"}); }
  }

  function renderSteps(container, label, steps) {
    const group = append(container, "div", "rotation-group");
    const heading = append(group, "h3", "", label);
    append(heading, "span", "section-meta", plural((steps || []).length, "step"));
    if (!steps || !steps.length) {
      append(group, "p", "empty", "No steps.");
      return;
    }
    const list = append(group, "div", "steps");
    steps.forEach((step) => {
      const row = append(list, "div", "step");
      append(row, "span", "step-no", String(step.order).padStart(2, "0"));
      const body = append(row, "div", "step-body");
      const head = append(body, "div", "step-head");
      append(head, "span", "step-title", "Step " + step.order);
      if (step.generation !== null && step.generation !== undefined) {
        append(head, "span", "pill", "generation " + step.generation);
      }
      if (step.batch) { append(head, "span", "pill", "batch"); }
      if (step.depends_on && step.depends_on.length) {
        append(body, "p", "muted", "Depends on: " + step.depends_on.join(", "));
      }
      const actions = append(body, "ol", "step-actions");
      (step.actions || []).forEach((action) => append(actions, "li", "", action));
      if (step.credentials && step.credentials.length) {
        const chips = append(body, "div", "step-cred");
        step.credentials.forEach((credential) => {
          const chip = append(chips, "span", "cred-chip", credential.label);
          append(chip, "span", "mono", credential.id);
        });
      }
      const details = append(body, "details");
      append(details, "summary", "", "Evidence");
      const evidence = append(details, "div", "details-body");
      evidenceList(evidence, step.evidence || []);
    });
  }

  function renderRotation(scenario) {
    const target = document.getElementById("rotation-content");
    clear(target);
    if (!scenario) {
      append(target, "p", "empty", "No rotation plan is available.");
      return;
    }
    const plan = scenario.rotation_plan;
    renderSteps(target, "Containment", plan.containment);
    renderSteps(target, "Rotation", plan.rotation);
    renderSteps(target, "Verify", plan.verify);
    if (plan.notes && plan.notes.length) {
      append(target, "h3", "", "Plan notes");
      const notes = append(target, "ul", "plain");
      plan.notes.forEach((note) => append(notes, "li", "note", note));
    }
  }

  function renderFindingCard(target, finding) {
    const card = append(target, "article", "finding sev-" + finding.severity);
    const head = append(card, "div", "finding-head");
    append(head, "span", "pill sev-" + finding.severity, finding.severity);
    append(head, "h3", "", finding.title);
    append(
      card,
      "p",
      "finding-rule",
      finding.rule + " " + finding.id + " · confidence " + finding.confidence
    );
    append(card, "p", "finding-message", finding.message);
    if (finding.scenario) { append(card, "p", "finding-meta", "Scenario: " + finding.scenario); }
    if (finding.assumptions && finding.assumptions.length) {
      append(card, "p", "finding-meta", "Assumptions: " + finding.assumptions.join(", "));
    }
    const details = append(card, "details");
    append(details, "summary", "", "Evidence and path");
    const body = append(details, "div", "details-body");
    evidenceList(body, finding.evidence || []);
    if (finding.path && finding.path.length) {
      append(body, "p", "finding-path", finding.path.map(nodeLabel).join(" -> "));
    }
  }

  function findingHaystack(finding) {
    const parts = [
      finding.title,
      finding.rule,
      finding.id,
      finding.severity,
      finding.message,
      finding.scenario,
      (finding.assumptions || []).join(" "),
      (finding.path || []).map(nodeLabel).join(" "),
      (finding.evidence || []).map(evidenceLabel).join(" ")
    ];
    return parts.map(textOf).join(" ").toLowerCase();
  }

  function renderFindings() {
    const target = document.getElementById("findings-content");
    const search = document.getElementById("finding-search");
    const severity = document.getElementById("finding-severity");
    const scenarioSelect = document.getElementById("finding-scenario");
    const count = document.getElementById("findings-count");
    const clearButton = document.getElementById("finding-clear");

    const severityNames = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
    clear(severity);
    const allSeverities = append(severity, "option", "", "All severities");
    allSeverities.value = "";
    severityNames.forEach((name) => {
      const option = append(severity, "option", "", name);
      option.value = name;
    });

    const scenarioNames = Array.from(
      new Set(findings.map((finding) => textOf(finding.scenario)).filter(Boolean))
    ).sort();
    clear(scenarioSelect);
    const allScenarios = append(scenarioSelect, "option", "", "All scenarios");
    allScenarios.value = "";
    scenarioNames.forEach((name) => {
      const option = append(scenarioSelect, "option", "", name);
      option.value = name;
    });

    function apply() {
      clear(target);
      const needle = search.value.trim().toLowerCase();
      const wantedSeverity = severity.value;
      const wantedScenario = scenarioSelect.value;
      const matches = findings.filter((finding) => {
        if (wantedSeverity && finding.severity !== wantedSeverity) { return false; }
        if (wantedScenario && textOf(finding.scenario) !== wantedScenario) { return false; }
        return !needle || findingHaystack(finding).includes(needle);
      });
      if (!matches.length) {
        append(
          target,
          "p",
          "empty",
          findings.length
            ? "No findings match the current filters."
            : "No findings were generated."
        );
      } else {
        matches.forEach((finding) => renderFindingCard(target, finding));
      }
      count.textContent = matches.length + " of " + plural(findings.length, "finding") + " shown.";
    }

    search.addEventListener("input", apply);
    severity.addEventListener("change", apply);
    scenarioSelect.addEventListener("change", apply);
    if (clearButton) {
      clearButton.addEventListener("click", () => {
        search.value = "";
        severity.value = "";
        scenarioSelect.value = "";
        apply();
        search.focus();
      });
    }
    apply();
  }

  function scenarioCredentialStatuses(scenario) {
    const statuses = new Map();
    function add(id, code) {
      if (!id) { return; }
      const current = statuses.get(id);
      if (!current) {
        statuses.set(id, [code]);
      } else if (!current.includes(code)) {
        current.push(code);
      }
    }
    const partition = scenario.partition || {R: [], E: [], Z: []};
    (partition.R || []).forEach((id) => add(id, "R"));
    (partition.E || []).forEach((entry) => add(entry.credential, "E"));
    (partition.Z || []).forEach((entry) => add(entry.credential, "Z"));
    (scenario.potential_nodes || []).forEach((id) => {
      const node = nodes.get(id);
      if (node && node.kind === "CREDENTIAL") { add(id, "P"); }
    });
    return statuses;
  }

  function statusLabel(code) {
    if (code === "R") { return "ends with the revoked entrypoint"; }
    if (code === "E") { return "expires on its own"; }
    if (code === "Z") { return "potentially survives revocation"; }
    return "potential only through an UNKNOWN-class edge";
  }

  function renderMatrix() {
    const items = scenarios;
    const section = document.getElementById("matrix");
    const link = document.getElementById("matrix-link");
    const target = document.getElementById("matrix-content");
    const summary = document.getElementById("matrix-summary");
    const toggle = document.getElementById("matrix-shared");
    clear(target);
    clear(summary);
    if (scenarios.length < 2) {
      section.hidden = true;
      link.hidden = true;
      return;
    }
    section.hidden = false;
    link.hidden = false;
    const statuses = items.map(scenarioCredentialStatuses);
    const allIds = new Set();
    statuses.forEach((map) => map.forEach((_, id) => allIds.add(id)));
    const ids = Array.from(allIds).sort();
    const visible = toggle.checked
      ? ids.filter((id) => statuses.filter((map) => map.has(id)).length > 1)
      : ids;
    const sharedSurvivors = ids.filter(
      (id) => statuses.filter((map) => (map.get(id) || []).includes("Z")).length > 1
    ).length;
    const unique = ids.filter(
      (id) => statuses.filter((map) => map.has(id)).length === 1
    ).length;
    let widestIndex = -1;
    let widestCount = -1;
    statuses.forEach((map, index) => {
      if (map.size > widestCount) {
        widestCount = map.size;
        widestIndex = index;
      }
    });
    if (ids.length) {
      summary.textContent =
        plural(ids.length, "credential") + (ids.length === 1 ? " is" : " are") +
        " listed across " + plural(items.length, "scenario") + "; " +
        sharedSurvivors + " potentially survive revocation in more than one scenario; " +
        unique + (unique === 1 ? " appears" : " appear") + " in only one. Widest listed coverage: " +
        (widestIndex >= 0 ? items[widestIndex].selector : "none") +
        " (" + plural(Math.max(widestCount, 0), "credential") + ").";
    } else {
      summary.textContent = "No credentials are listed in any scenario.";
    }
    append(
      target,
      "p",
      "muted",
      "R/E/Z come from the analysis. P marks a credential that appears only on UNKNOWN-class " +
        "potential edges in that scenario. Select a status to switch scenario and trace a path."
    );
    if (!ids.length) {
      append(target, "p", "empty", "No credentials are listed in any scenario.");
      return;
    }
    if (!visible.length) {
      append(
        target,
        "p",
        "empty",
        "No credential is listed in more than one scenario."
      );
      return;
    }
    const wrap = append(target, "div", "table-wrap matrix-wrap");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", "Cross-scenario credential exposure matrix");
    const table = append(wrap, "table", "matrix");
    append(
      table,
      "caption",
      "",
      "Credential status by scenario. R = ends with the revoked entrypoint; " +
        "E = expires on its own; Z = potentially survives revocation; " +
        "P = potential only through an UNKNOWN-class edge."
    );
    const headRow = append(append(table, "thead"), "tr");
    const corner = append(headRow, "th", "", "Scenario");
    corner.scope = "col";
    visible.forEach((id) => {
      const cell = append(headRow, "th", "", credentialHeading(id));
      cell.scope = "col";
      cell.title = id;
    });
    const body = append(table, "tbody");
    items.forEach((scenario, index) => {
      const row = append(body, "tr", index === currentScenarioIndex ? "active-row" : "");
      const rowHead = append(row, "th", "wrap", scenario.selector);
      rowHead.scope = "row";
      visible.forEach((id) => {
        const cell = append(row, "td");
        const codes = statuses[index].get(id);
        if (!codes || !codes.length) {
          cell.textContent = "-";
          cell.setAttribute("aria-label", "Not listed in this scenario");
          return;
        }
        const button = element("button", "status status-" + codes[0], codes.join("+"));
        button.type = "button";
        button.title = codes.map(statusLabel).join("; ");
        button.setAttribute(
          "aria-label",
          nodeLabel(id) + ": " + codes.map(statusLabel).join("; ") +
            " in scenario " + scenario.selector
        );
        button.addEventListener("click", () => {
          selectScenario(index);
          traceTo(id);
        });
        cell.appendChild(button);
      });
    });
    watchOverflow(wrap);
  }

  function renderAssumptions() {
    const target = document.getElementById("assumptions-content");
    clear(target);
    const assumptions = report.assumptions || [];
    if (assumptions.length) {
      append(target, "h3", "", "Assumptions");
      const caption = "Assumptions attached to this report";
      const table = tableRegion(target, caption);
      append(table, "caption", "", caption);
      addColumns(table, ["16%", "36%", "10%", "38%"]);
      const head = append(append(table, "thead"), "tr");
      ["ID", "Statement", "Verify", "Used by"].forEach((heading) => {
        const cell = append(head, "th", "", heading);
        cell.scope = "col";
      });
      const body = append(table, "tbody");
      assumptions.forEach((assumption) => {
        const row = append(body, "tr");
        append(row, "td", "mono nowrap", assumption.id);
        append(row, "td", "wrap", assumption.statement);
        append(row, "td", "", assumption.verify ? "yes" : "no");
        append(row, "td", "mono wrap", (assumption.used_by || []).join(", "));
      });
    } else {
      append(target, "p", "empty", "No assumptions were recorded.");
    }
    append(target, "h3", "", "Unknown inputs");
    const items = report.scenarios || [];
    if (!items.some((item) => item.unresolved_inputs.length)) {
      append(target, "p", "empty", "No unresolved inputs are recorded.");
    }
    items.forEach((scenario) => {
      if (!scenario.unresolved_inputs.length) { return; }
      append(target, "h4", "", scenario.selector);
      const list = append(target, "ul", "plain");
      scenario.unresolved_inputs.forEach((item) => append(list, "li", "mono wrap", item));
    });
  }

  function renderDiagnostics() {
    const target = document.getElementById("diagnostics-content");
    clear(target);
    const diagnostics = (report.diagnostics || []).slice();
    if (!diagnostics.length) {
      append(target, "p", "empty", "No diagnostics were recorded.");
      return;
    }
    const caption = "Parse and analysis diagnostics";
    const table = tableRegion(target, caption);
    append(table, "caption", "", caption);
    addColumns(table, ["10%", "14%", "48%", "28%"]);
    const head = append(append(table, "thead"), "tr");
    ["Level", "Code", "Message", "Location"].forEach((heading) => {
      const cell = append(head, "th", "", heading);
      cell.scope = "col";
    });
    const body = append(table, "tbody");
    diagnostics.forEach((item) => {
      const row = append(body, "tr");
      append(row, "td", "", item.level);
      append(row, "td", "mono", item.code);
      append(row, "td", "wrap", item.message);
      append(row, "td", "mono wrap", textOf(item.file) +
        (item.line === undefined || item.line === null ? "" : ":" + item.line));
    });
  }

  function humanKind(kind) {
    return textOf(kind).replace(/_/g, " ").toLowerCase();
  }

  function showGraphPlaceholder() {
    const target = document.getElementById("entity-details");
    clear(target);
    append(
      target,
      "p",
      "entity-placeholder",
      "Select a node or edge to inspect its full identifier, evidence and relationships."
    );
  }

  function setGraphTabStop(target) {
    if (!graphView) { return; }
    graphView.nodes.forEach((node) => node.setAttribute("tabindex", node === target ? "0" : "-1"));
  }

  function selectGraphNode(id, options) {
    const item = nodes.get(id);
    if (!item || !graphView) { return; }
    clearGraphTrace();
    graphSelection = {type: "node", id: id};
    graphView.stage.classList.add("has-selection");
    graphView.nodes.forEach((node) => node.classList.remove("is-selected", "is-neighbor"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-selected-edge", "is-incident"));
    const selected = graphView.nodes.get(id);
    if (!selected) {
      graphView.stage.classList.remove("has-selection");
      showNode(id);
      return;
    }
    selected.classList.add("is-selected");
    setGraphTabStop(selected);
    (report.graph.edges || []).forEach((edge) => {
      if (edge.src !== id && edge.dst !== id) { return; }
      const other = graphView.nodes.get(edge.src === id ? edge.dst : edge.src);
      if (other) { other.classList.add("is-neighbor"); }
      const edgeElement = graphView.edges.get(edge.id);
      if (edgeElement) { edgeElement.classList.add("is-incident"); }
    });
    if (options && options.focus) { selected.focus({preventScroll: true}); }
    showNode(id);
  }

  function selectGraphEdge(id) {
    const item = edges.get(id);
    if (!item || !graphView) { return; }
    clearGraphTrace();
    graphSelection = {type: "edge", id: id};
    graphView.stage.classList.add("has-selection");
    graphView.nodes.forEach((node) => node.classList.remove("is-selected", "is-neighbor"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-selected-edge", "is-incident"));
    const selected = graphView.edges.get(id);
    if (!selected) {
      graphView.stage.classList.remove("has-selection");
      showEdge(id);
      return;
    }
    selected.classList.add("is-selected-edge");
    [item.src, item.dst].forEach((nodeId) => {
      const node = graphView.nodes.get(nodeId);
      if (node) { node.classList.add("is-neighbor"); }
    });
    showEdge(id);
  }

  function clearGraphSelection() {
    graphSelection = null;
    if (graphView) {
      graphView.stage.classList.remove("has-selection");
      graphView.nodes.forEach((node) => node.classList.remove("is-selected", "is-neighbor"));
      graphView.edges.forEach((edge) => edge.classList.remove("is-selected-edge", "is-incident"));
    }
    showGraphPlaceholder();
  }

  function showEvidenceBlock(target, evidence) {
    const block = append(target, "div", "entity-block");
    append(block, "h4", "", "Evidence");
    evidenceList(block, evidence || []);
  }

  function attributeRows(item) {
    const attrs = item.attrs || {};
    return Object.keys(attrs).sort().map((key) => {
      const value = attrs[key];
      let text;
      if (value === null || value === undefined) {
        text = "null";
      } else if (Array.isArray(value)) {
        text = value.length
          ? value.map((entry) => (typeof entry === "object" ? JSON.stringify(entry) : String(entry))).join(", ")
          : "none";
      } else if (typeof value === "object") {
        text = JSON.stringify(value);
      } else {
        text = String(value);
      }
      if (text.length > 220) { text = text.slice(0, 217) + "…"; }
      return [key, text];
    });
  }

  function showAttributes(target, item) {
    const rows = attributeRows(item);
    const block = append(target, "div", "entity-block");
    append(block, "h4", "", "Attributes");
    if (!rows.length) {
      append(block, "p", "empty", "No attributes are recorded.");
      return;
    }
    const list = append(block, "dl", "kv");
    rows.forEach(([key, value]) => {
      const row = append(list, "div");
      append(row, "dt", "mono", key);
      append(row, "dd", "mono", value);
    });
    const details = append(block, "details");
    append(details, "summary", "", "Full attributes (JSON)");
    const pre = append(details, "pre");
    pre.textContent = JSON.stringify(item.attrs || {}, null, 2);
  }

  function relationshipRow(list, edge, otherId, direction) {
    const item = append(list, "li");
    const other = nodes.get(otherId);
    const button = element("button", "trace-link", other ? other.label : otherId);
    button.type = "button";
    button.title = "Select " + nodeLabel(otherId);
    button.addEventListener("click", () => selectGraphNode(otherId, {focus: true}));
    item.appendChild(button);
    append(item, "span", "entity-link-meta", edge.kind + " " + direction + " · confidence " + edge.confidence);
    const edgeButton = element("button", "trace-link", "edge evidence");
    edgeButton.type = "button";
    edgeButton.title = "Show the evidence for this edge";
    edgeButton.addEventListener("click", () => selectGraphEdge(edge.id));
    item.appendChild(edgeButton);
  }

  function showRelationships(target, id) {
    const block = append(target, "div", "entity-block");
    append(block, "h4", "", "Relationships");
    const outgoing = (report.graph.edges || []).filter((edge) => edge.src === id);
    const incoming = (report.graph.edges || []).filter((edge) => edge.dst === id);
    if (!outgoing.length && !incoming.length) {
      append(block, "p", "empty", "No edges touch this entity.");
      return;
    }
    const list = append(block, "ul", "entity-links");
    outgoing.forEach((edge) => relationshipRow(list, edge, edge.dst, "to"));
    incoming.forEach((edge) => relationshipRow(list, edge, edge.src, "from"));
  }

  function entityActions(target, id) {
    const actions = append(target, "div", "entity-actions");
    const trace = element("button", "button quiet", "Trace from the selected entrypoint");
    trace.type = "button";
    trace.addEventListener("click", () => traceTo(id));
    actions.appendChild(trace);
    const clearButton = element("button", "button quiet", "Clear selection");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => {
      clearGraphSelection();
      clearGraphTrace();
    });
    actions.appendChild(clearButton);
  }

  function showNode(id) {
    const item = nodes.get(id);
    if (!item) { showGraphPlaceholder(); return; }
    const target = document.getElementById("entity-details");
    clear(target);
    append(target, "h3", "", item.label);
    append(target, "p", "entity-sub", humanKind(item.kind) + " · " + item.id);
    const tags = append(target, "div", "entity-tags");
    append(tags, "span", "text-chip", humanKind(item.kind));
    if (entryIds.has(id)) { append(tags, "span", "text-chip", "Entrypoint"); }
    if (item.attrs && Number(item.attrs.criticality) >= 80) {
      append(tags, "span", "text-chip", "Critical resource");
    }
    entityActions(target, id);
    showEvidenceBlock(target, item.evidence);
    showRelationships(target, id);
    showAttributes(target, item);
    animatePresence(target);
  }

  function showEdge(id) {
    const item = edges.get(id);
    if (!item) { return; }
    const target = document.getElementById("entity-details");
    clear(target);
    append(target, "h3", "", humanKind(item.kind) + " edge");
    append(target, "p", "entity-sub", item.src + " -> " + item.dst);
    const tags = append(target, "div", "entity-tags");
    append(tags, "span", "text-chip", "Confidence " + item.confidence);
    if (item.lifetime) { append(tags, "span", "text-chip", "Lifetime " + item.lifetime); }
    const actions = append(target, "div", "entity-actions");
    [["Source", item.src], ["Target", item.dst]].forEach(([label, nodeId]) => {
      const button = element("button", "button quiet", label + ": " + (nodes.get(nodeId) || {label: nodeId}).label);
      button.type = "button";
      button.addEventListener("click", () => selectGraphNode(nodeId, {focus: true}));
      actions.appendChild(button);
    });
    const clearButton = element("button", "button quiet", "Clear selection");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => {
      clearGraphSelection();
      clearGraphTrace();
    });
    actions.appendChild(clearButton);
    if (item.confidence === "unknown") {
      append(
        target,
        "p",
        "note",
        "UNKNOWN-class edges are potential only; they do not contribute to R, E or Z."
      );
    }
    animatePresence(target);
    showEvidenceBlock(target, item.evidence);
    append(
      target,
      "p",
      "muted",
      "Edge confidence is the weakest evidence class recorded on this edge."
    );
    showAttributes(target, item);
  }

  function moveGraphFocus(current, horizontal, vertical) {
    if (!graphView) { return; }
    const centre = (node) => ({
      x: Number(node.getAttribute("data-x")) + Number(node.getAttribute("data-width")) / 2,
      y: Number(node.getAttribute("data-y")) + Number(node.getAttribute("data-height")) / 2
    });
    const origin = centre(current);
    let best = null;
    let bestScore = Infinity;
    graphView.nodes.forEach((candidate) => {
      if (candidate === current) { return; }
      const point = centre(candidate);
      const dx = point.x - origin.x;
      const dy = point.y - origin.y;
      const primary = dx * horizontal + dy * vertical;
      if (primary <= 4) { return; }
      const secondary = Math.abs(dx * vertical - dy * horizontal);
      const score = primary + secondary * 1.6;
      if (score < bestScore) { bestScore = score; best = candidate; }
    });
    if (best) {
      setGraphTabStop(best);
      best.focus({preventScroll: true});
    }
  }

  function applyGraphTransform(animate) {
    if (!graphView) { return; }
    graphView.viewport.classList.toggle(
      "is-animated",
      Boolean(animate) && !prefersReducedMotion()
    );
    graphView.viewport.style.transform =
      "translate(" + graphView.x + "px, " + graphView.y + "px) scale(" + graphView.scale + ")";
    const rect = graphView.stage.getBoundingClientRect();
    const pannable =
      graphView.width * graphView.scale > rect.width + 1 ||
      graphView.height * graphView.scale > rect.height + 1;
    graphView.stage.classList.toggle("is-pannable", pannable);
    const level = document.getElementById("graph-zoom-level");
    if (level) {
      const percent = Math.round(graphView.scale * 100);
      level.textContent = percent + "%";
      level.setAttribute(
        "aria-label",
        "Zoom " + percent + " percent. Activate to reset to 100 percent."
      );
    }
  }

  function clampGraphView() {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    const width = graphView.width * graphView.scale;
    const height = graphView.height * graphView.scale;
    if (width <= rect.width) {
      graphView.x = (rect.width - width) / 2;
    } else {
      graphView.x = Math.min(0, Math.max(rect.width - width, graphView.x));
    }
    if (height <= rect.height) {
      graphView.y = (rect.height - height) / 2;
    } else {
      graphView.y = Math.min(0, Math.max(rect.height - height, graphView.y));
    }
  }

  function fitGraph(animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    if (!rect.width || !rect.height) { return; }
    const pad = rect.width < 640 ? 16 : 28;
    const scale = Math.min(
      (rect.width - pad * 2) / graphView.width,
      (rect.height - pad * 2) / graphView.height,
      1.2
    );
    graphView.scale = Math.max(0.08, scale);
    graphView.x = (rect.width - graphView.width * graphView.scale) / 2;
    graphView.y = (rect.height - graphView.height * graphView.scale) / 2;
    graphView.adjusted = false;
    applyGraphTransform(animate);
  }

  function initialGraphView(animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    if (!rect.width || !rect.height) { return; }
    const pad = rect.width < 640 ? 16 : 28;
    const fit = Math.min(
      (rect.width - pad * 2) / graphView.width,
      (rect.height - pad * 2) / graphView.height,
      1.2
    );
    if (fit >= 0.62) { fitGraph(animate); return; }
    const scenario = scenarios[currentScenarioIndex] || null;
    const candidates = (scenario && scenario.start_nodes) || Array.from(entryIds);
    let anchor = null;
    for (const id of candidates) {
      const node = graphView.nodes.get(id);
      if (node) { anchor = node; break; }
    }
    graphView.scale = 1;
    const centerX = anchor
      ? Number(anchor.getAttribute("data-x")) + Number(anchor.getAttribute("data-width")) / 2
      : graphView.width / 2;
    const centerY = anchor
      ? Number(anchor.getAttribute("data-y")) + Number(anchor.getAttribute("data-height")) / 2
      : graphView.height / 2;
    graphView.x = rect.width / 2 - centerX;
    graphView.y = rect.height / 2 - centerY;
    graphView.adjusted = true;
    clampGraphView();
    applyGraphTransform(animate);
  }

  function zoomAt(clientX, clientY, factor, animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    const pointX = clientX === null || clientX === undefined ? rect.width / 2 : clientX - rect.left;
    const pointY = clientY === null || clientY === undefined ? rect.height / 2 : clientY - rect.top;
    const next = Math.min(3, Math.max(0.08, graphView.scale * factor));
    if (next === graphView.scale) { return; }
    const ratio = next / graphView.scale;
    graphView.x = pointX - (pointX - graphView.x) * ratio;
    graphView.y = pointY - (pointY - graphView.y) * ratio;
    graphView.scale = next;
    graphView.adjusted = true;
    clampGraphView();
    applyGraphTransform(animate);
  }

  function resetGraphZoom(animate) {
    if (!graphView) { return; }
    const rect = graphView.stage.getBoundingClientRect();
    graphView.scale = 1;
    graphView.x = (rect.width - graphView.width) / 2;
    graphView.y = (rect.height - graphView.height) / 2;
    graphView.adjusted = true;
    clampGraphView();
    applyGraphTransform(animate);
  }

  function applyGraphFocus(scenario) {
    if (!graphView) { return; }
    graphView.nodes.forEach((node) => node.classList.remove("is-outside"));
    graphView.edges.forEach((edge) => edge.classList.remove("is-outside"));
    const focus = new Set();
    if (scenario) {
      const queue = (scenario.start_nodes || []).slice();
      queue.forEach((id) => focus.add(id));
      while (queue.length) {
        const id = queue.shift();
        (adjacency.get(id) || []).forEach((edge) => {
          if (!focus.has(edge.dst)) {
            focus.add(edge.dst);
            queue.push(edge.dst);
          }
        });
      }
    }
    if (!focus.size) { return; }
    graphView.nodes.forEach((node, id) => {
      if (!focus.has(id)) { node.classList.add("is-outside"); }
    });
    graphView.edges.forEach((edgeElement, id) => {
      const item = edges.get(id);
      if (item && !focus.has(item.src)) {
        edgeElement.classList.add("is-outside");
      }
    });
  }

  function updateGraphCount() {
    const target = document.getElementById("graph-count");
    if (!target) { return; }
    const totalNodes = (report.graph.nodes || []).length;
    const totalEdges = (report.graph.edges || []).length;
    const drawnNodes = graphView ? graphView.nodes.size : totalNodes;
    const drawnEdges = graphView ? graphView.edges.size : totalEdges;
    if (drawnNodes < totalNodes) {
      target.textContent = "Rendering " + drawnNodes + " of " + totalNodes + " nodes · " +
        drawnEdges + " of " + totalEdges + " edges";
      return;
    }
    target.textContent = plural(totalNodes, "node") + " · " + plural(totalEdges, "edge") + " · grouped by authority stage";
  }

  function renderGraph(scenario) {
    applyGraphFocus(scenario);
    clearGraphTrace();
    if (graphSelection) {
      clearGraphSelection();
    } else {
      showGraphPlaceholder();
    }
    updateGraphCount();
  }

  function endGraphPointer(event) {
    if (!graphView) { return; }
    graphView.pointers.delete(event.pointerId);
    if (graphView.stage.hasPointerCapture(event.pointerId)) {
      graphView.stage.releasePointerCapture(event.pointerId);
    }
    if (graphView.pointers.size === 0) {
      const tap = graphView.tap && !graphView.moved && event.type === "pointerup";
      graphView.panning = false;
      graphView.pinch = null;
      graphView.moved = false;
      graphView.tap = null;
      graphView.stage.classList.remove("is-panning");
      if (tap) { selectAt(event.clientX, event.clientY); }
    } else if (graphView.pointers.size === 1) {
      graphView.panning = false;
      graphView.pinch = null;
    }
  }

  function selectAt(clientX, clientY) {
    const hit = document.elementFromPoint(clientX, clientY);
    if (!hit || !graphView.stage.contains(hit)) { return; }
    const node = hit.closest ? hit.closest(".gnode") : null;
    if (node) { selectGraphNode(node.getAttribute("data-id"), {focus: false}); return; }
    const edge = hit.closest ? hit.closest(".gedge") : null;
    if (edge) { selectGraphEdge(edge.getAttribute("data-id")); return; }
    clearGraphSelection();
  }

  function bindGraphEvents() {
    const stage = graphView.stage;
    const svg = graphView.svg;
    stage.addEventListener("dblclick", (event) => {
      const hit = document.elementFromPoint(event.clientX, event.clientY);
      const node = hit && hit.closest ? hit.closest(".gnode") : null;
      if (node) { return; }
      zoomAt(event.clientX, event.clientY, 1.5, true);
    });
    svg.addEventListener("keydown", (event) => {
      const current = event.target.closest ? event.target.closest(".gnode") : null;
      if (!current) { return; }
      if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
        event.preventDefault();
        selectGraphNode(current.getAttribute("data-id"), {focus: true});
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        clearGraphSelection();
        clearGraphTrace();
        return;
      }
      if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        const all = Array.from(graphView.nodes.values());
        const target = event.key === "Home" ? all[0] : all[all.length - 1];
        if (target) { setGraphTabStop(target); target.focus({preventScroll: true}); }
        return;
      }
      const directions = {
        ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]
      };
      const direction = directions[event.key];
      if (direction) {
        event.preventDefault();
        moveGraphFocus(current, direction[0], direction[1]);
      }
    });
    stage.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse" && event.button !== 0) { return; }
      graphView.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (graphView.pointers.size === 1) {
        graphView.panning = true;
        graphView.panStart = {x: event.clientX, y: event.clientY, x0: graphView.x, y0: graphView.y};
        graphView.moved = false;
        graphView.tap = true;
        stage.setPointerCapture(event.pointerId);
      } else if (graphView.pointers.size === 2) {
        const points = Array.from(graphView.pointers.values());
        graphView.pinch = {distance: Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)};
        graphView.tap = false;
        graphView.panning = false;
      }
    });
    stage.addEventListener("pointermove", (event) => {
      if (!graphView.pointers.has(event.pointerId)) { return; }
      graphView.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      if (graphView.pointers.size >= 2 && graphView.pinch) {
        const points = Array.from(graphView.pointers.values());
        const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
        if (graphView.pinch.distance > 0 && distance > 0) {
          const factor = distance / graphView.pinch.distance;
          zoomAt(
            (points[0].x + points[1].x) / 2,
            (points[0].y + points[1].y) / 2,
            factor,
            false
          );
          graphView.pinch.distance = distance;
        }
        return;
      }
      if (!graphView.panning || !graphView.panStart) { return; }
      const dx = event.clientX - graphView.panStart.x;
      const dy = event.clientY - graphView.panStart.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) {
        graphView.moved = true;
        stage.classList.add("is-panning");
      }
      graphView.x = graphView.panStart.x0 + dx;
      graphView.y = graphView.panStart.y0 + dy;
      graphView.adjusted = true;
      clampGraphView();
      applyGraphTransform(false);
    });
    stage.addEventListener("pointerup", endGraphPointer);
    stage.addEventListener("pointercancel", endGraphPointer);
    stage.addEventListener("wheel", (event) => {
      if (!event.ctrlKey && !event.metaKey) { return; }
      event.preventDefault();
      zoomAt(event.clientX, event.clientY, event.deltaY < 0 ? 1.12 : 0.9, false);
    }, {passive: false});
  }

  function initGraph() {
    const svg = document.getElementById("graph-svg");
    const stage = document.getElementById("graph-stage");
    if (!svg || !stage) { return; }
    const viewport = svg.querySelector(".graph-viewport");
    const nodeElements = new Map();
    svg.querySelectorAll(".gnode").forEach((node) => {
      const id = node.getAttribute("data-id");
      if (id !== null) { nodeElements.set(id, node); }
    });
    const edgeElements = new Map();
    svg.querySelectorAll(".gedge").forEach((edge) => {
      const id = edge.getAttribute("data-id");
      if (id !== null) { edgeElements.set(id, edge); }
    });
    const width = Number(svg.getAttribute("data-width")) || (svg.viewBox.baseVal && svg.viewBox.baseVal.width) || 640;
    const height = Number(svg.getAttribute("data-height")) || (svg.viewBox.baseVal && svg.viewBox.baseVal.height) || 160;
    graphView = {
      svg: svg,
      stage: stage,
      viewport: viewport,
      nodes: nodeElements,
      edges: edgeElements,
      width: width,
      height: height,
      scale: 1,
      x: 0,
      y: 0,
      adjusted: false,
      pointers: new Map(),
      panning: false,
      pinch: null,
      panStart: null,
      moved: false,
      tap: false
    };
    svg.style.width = width + "px";
    svg.style.height = height + "px";
    if (!nodeElements.size) {
      ["graph-zoom-out", "graph-zoom-level", "graph-zoom-in", "graph-fit"].forEach((id) => {
        const control = document.getElementById(id);
        if (control) { control.disabled = true; }
      });
      showGraphPlaceholder();
      updateGraphCount();
      return;
    }
    const first = nodeElements.values().next().value;
    if (first) { first.setAttribute("tabindex", "0"); }
    bindGraphEvents();
    initialGraphView(false);
    window.requestAnimationFrame(() => initialGraphView(false));
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => {
        if (graphView && !graphView.adjusted) { fitGraph(false); }
      });
    }
    if (window.ResizeObserver) {
      const observer = new window.ResizeObserver(() => {
        if (!graphView) { return; }
        if (!graphView.adjusted) {
          fitGraph(false);
        } else {
          clampGraphView();
          applyGraphTransform(false);
        }
      });
      observer.observe(stage);
    }
    applyGraphFocus(scenarios[currentScenarioIndex] || null);
    showGraphPlaceholder();
    updateGraphCount();
  }

  function bindSectionNav() {
    const nav = document.querySelector(".toc");
    if (!nav) { return; }
    const bar = document.querySelector(".nav-bar");
    const entries = [];
    nav.querySelectorAll('a[href^="#"]').forEach((link) => {
      if (link.hidden) { return; }
      const target = document.getElementById(link.getAttribute("href").slice(1));
      if (!target || target.hidden) { return; }
      entries.push({ id: target.id, link: link, target: target });
    });
    if (!entries.length) { return; }
    const indicator = nav.querySelector(".nav-indicator");
    const placeIndicator = (link) => {
      if (!indicator) { return; }
      indicator.style.width = link.offsetWidth + "px";
      indicator.style.transform = "translateX(" + link.offsetLeft + "px)";
      indicator.classList.add("is-active");
    };
    let current = "";
    const setCurrent = (id) => {
      if (!id || id === current) { return; }
      current = id;
      entries.forEach((entry) => {
        if (entry.id === id) {
          entry.link.setAttribute("aria-current", "location");
        } else {
          entry.link.removeAttribute("aria-current");
        }
      });
      const active = entries.find((entry) => entry.id === id);
      if (!active) { return; }
      placeIndicator(active.link);
      if (nav.scrollWidth > nav.clientWidth + 2) {
        const navRect = nav.getBoundingClientRect();
        const linkRect = active.link.getBoundingClientRect();
        if (linkRect.left < navRect.left || linkRect.right > navRect.right) {
          active.link.scrollIntoView({
            behavior: prefersReducedMotion() ? "auto" : "smooth",
            block: "nearest",
            inline: "center"
          });
        }
      }
    };
    const update = () => {
      const navBottom = bar ? bar.getBoundingClientRect().bottom : 0;
      const line = navBottom + 28;
      let active = entries[0].id;
      entries.forEach((entry) => {
        if (entry.target.getBoundingClientRect().top <= line) {
          active = entry.id;
        }
      });
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
        active = entries[entries.length - 1].id;
      }
      setCurrent(active);
    };
    let frame = 0;
    const schedule = () => {
      if (frame) { return; }
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        update();
      });
    };
    const reposition = () => {
      const entry = entries.find((item) => item.id === current);
      if (entry) { placeIndicator(entry.link); }
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", () => { schedule(); reposition(); });
    if (document.fonts && document.fonts.ready) { document.fonts.ready.then(reposition); }
    update();
  }

  function bindPointerLighting() {
    if (prefersReducedMotion()) { return; }
    if (!window.matchMedia || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      return;
    }
    document.querySelectorAll("[data-light]").forEach((target) => {
      let frame = 0;
      let point = null;
      const paint = () => {
        frame = 0;
        if (!point) { return; }
        const rect = target.getBoundingClientRect();
        target.style.setProperty("--light-x", Math.round(point.x - rect.left) + "px");
        target.style.setProperty("--light-y", Math.round(point.y - rect.top) + "px");
      };
      target.addEventListener("pointermove", (event) => {
        if (event.pointerType && event.pointerType !== "mouse") { return; }
        point = {x: event.clientX, y: event.clientY};
        target.classList.add("is-lit");
        if (!frame) { frame = window.requestAnimationFrame(paint); }
      });
      target.addEventListener("pointerleave", () => {
        if (frame) { window.cancelAnimationFrame(frame); frame = 0; }
        point = null;
        target.classList.remove("is-lit");
      });
    });
  }

  document.getElementById("schema-line").textContent = "schema " + report.schema;
  document.getElementById("tool-line").textContent =
    report.tool.name + " " + report.tool.version + " · report schema " + report.schema;
  document.getElementById("repo-line").textContent = "Repository " + report.inputs.repo_slug;
  renderSourceLine();
  renderScope();
  renderFindings();
  renderAssumptions();
  renderDiagnostics();
  document.getElementById("matrix-shared").addEventListener("change", renderMatrix);
  document.getElementById("graph-zoom-in").addEventListener("click", () => zoomAt(null, null, 1.25, true));
  document.getElementById("graph-zoom-out").addEventListener("click", () => zoomAt(null, null, 0.8, true));
  document.getElementById("graph-zoom-level").addEventListener("click", () => resetGraphZoom(true));
  document.getElementById("graph-fit").addEventListener("click", () => fitGraph(true));
  renderScenarioPicker();
  initGraph();
  bindSectionNav();
  bindPointerLighting();
  const printOpened = [];
  window.addEventListener("beforeprint", () => {
    printOpened.length = 0;
    document.querySelectorAll("details:not([open])").forEach((item) => {
      item.open = true;
      printOpened.push(item);
    });
    document.querySelectorAll("[data-motion-reveal]").forEach((item) => {
      item.style.opacity = "1";
      item.style.transform = "none";
    });
  });
  window.addEventListener("afterprint", () => {
    printOpened.forEach((item) => { item.open = false; });
    printOpened.length = 0;
  });
  document.getElementById("print-button").addEventListener("click", () => window.print());
  bootComplete = true;
  window.clearTimeout(bootFallback);
  startMotionIntro();
  startMotionReveals();
  window.requestAnimationFrame(() => {
    document.documentElement.classList.remove("booting");
  });
}).call(window);
"""
