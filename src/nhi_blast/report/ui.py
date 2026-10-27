"""Markup, styles and the inline application script for the offline report."""

from __future__ import annotations

TEMPLATE = """<!DOCTYPE html>
<html lang="en" class="booting">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#f4f5f7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d0e10" media="(prefers-color-scheme: dark)">
<title>NHI-Blast report</title>
<style>
__FONT_CSS__
/* The data sections are hydrated from the embedded JSON; keep the page hidden
   until the first render so nothing below reflows after paint. */
html.booting body { visibility: hidden; }
:root {
  color-scheme: light dark;
  --bg: #f4f5f7;
  --surface: #ffffff;
  --raised: #f1f3f5;
  --ink: #14171c;
  --muted: #5f6670;
  --border: #e1e4e8;
  --rule: #eceef1;
  --control: #cfd4da;
  --accent: #141414;
  --accent-ink: #ffffff;
  --data: #1d5fbf;
  --data-ink: #173f80;
  --data-soft: #e9f0fb;
  --critical: #b42318;
  --critical-ink: #8d1c13;
  --critical-soft: #fdecea;
  --high: #b54708;
  --high-ink: #8a3500;
  --high-soft: #fdf0e6;
  --warning: #8a5300;
  --warning-ink: #6f4300;
  --warning-soft: #fbf3df;
  --low: #0b6b7a;
  --low-ink: #075461;
  --low-soft: #e7f2f4;
  --positive: #226b3a;
  --positive-ink: #19552f;
  --positive-soft: #e7f4ea;
  --neutral-ink: #343a42;
  --neutral-soft: #eef0f2;
  --R: #2b3038;
  --E: #98a0aa;
  --Z: #1d5fbf;
  --graph-edge: #98a0aa;
  --node-structure: #78808b;
  --node-workflow: #3f4650;
  --node-oidc: #0b6b7a;
  --node-role: #7a4c0e;
  --node-sink: #92400e;
  --focus: #1d5fbf;
  --radius: 8px;
  --radius-control: 6px;
  --mono: "Geist Mono", ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d0e10;
    --surface: #15171a;
    --raised: #1b1e22;
    --ink: #f1f3f5;
    --muted: #a3a9b2;
    --border: #2a2e34;
    --rule: #23262b;
    --control: #3c4149;
    --accent: #e8eaed;
    --accent-ink: #111317;
    --data: #7aa9ff;
    --data-ink: #b7d2ff;
    --data-soft: #16233a;
    --critical: #ff8f85;
    --critical-ink: #ffc0ba;
    --critical-soft: #301716;
    --high: #ffb27a;
    --high-ink: #ffc9a3;
    --high-soft: #2f1d10;
    --warning: #e5b75e;
    --warning-ink: #f0cf8a;
    --warning-soft: #2a2315;
    --low: #6fc7d4;
    --low-ink: #a3e0e8;
    --low-soft: #10262a;
    --positive: #7fd09a;
    --positive-ink: #a7e2ba;
    --positive-soft: #13251a;
    --neutral-ink: #d6d9de;
    --neutral-soft: #23262a;
    --R: #c3c8d0;
    --E: #8b939d;
    --Z: #7aa9ff;
    --graph-edge: #7b838d;
    --node-structure: #9aa1aa;
    --node-workflow: #c3c8d0;
    --node-oidc: #6fc7d4;
    --node-role: #d8a75a;
    --node-sink: #f0b574;
    --focus: #7aa9ff;
  }
}
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 400 14px/1.5 "Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-variant-numeric: tabular-nums;
  -webkit-text-size-adjust: 100%;
}
::selection { background: var(--data-soft); color: var(--data-ink); }
h1, h2, h3, h4, p, dl, dd, figure { margin: 0; }
h1 { font-size: 24px; font-weight: 600; line-height: 1.2; letter-spacing: -.02em; }
h2 { font-size: 16px; font-weight: 600; line-height: 1.3; letter-spacing: -.01em; }
h3 { font-size: 14px; font-weight: 600; line-height: 1.4; }
h4 { font-size: 14px; font-weight: 500; line-height: 1.4; }
a { color: inherit; text-decoration: underline; text-decoration-color: var(--control); text-underline-offset: 2px; }
a:hover { text-decoration-color: currentColor; }
button { font: inherit; color: inherit; }
.mono, code, pre { font-family: var(--mono); }
.mono { font-size: 13px; overflow-wrap: anywhere; }
.muted { color: var(--muted); }
.empty { margin: 12px 0; color: var(--muted); }
.note { margin: 12px 0; padding-left: 12px; border-left: 2px solid var(--warning); color: var(--muted); }
.wrap { max-width: 1136px; margin: 0 auto; padding: 0 24px; }
.skip-link { position: absolute; left: -999px; }
.skip-link:focus { left: 16px; top: 12px; z-index: 100; padding: 8px 12px; background: var(--surface); color: var(--ink); border: 1px solid var(--control); border-radius: var(--radius-control); }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.viewer-bar { position: sticky; top: 0; z-index: 50; background: var(--surface); border-bottom: 1px solid var(--rule); }
.viewer-inner { display: flex; align-items: center; gap: 16px; max-width: 1136px; height: 48px; margin: 0 auto; padding: 0 24px; }
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; text-decoration: none; }
.brand-mark { flex: none; width: 20px; height: 20px; color: var(--ink); }
.brand-name { font-size: 14px; font-weight: 600; letter-spacing: -.01em; white-space: nowrap; }
.brand-sub { padding-left: 12px; border-left: 1px solid var(--border); color: var(--muted); font-size: 12px; white-space: nowrap; }
.viewer-meta { display: flex; align-items: center; gap: 12px; margin-left: auto; color: var(--muted); font-size: 12px; }
.viewer-chip { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 8px; border-radius: 4px; background: var(--raised); color: var(--muted); }
.viewer-chip::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--positive); }
.viewer-schema { color: var(--muted); }
.page-head { padding-top: 32px; border-bottom: 1px solid var(--rule); }
.title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 32px; }
.title-copy { min-width: 0; }
.source-line { margin-top: 5px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.head-actions { display: flex; flex: none; flex-direction: column; align-items: stretch; gap: 6px; width: 280px; }
.field-label { color: var(--muted); font-size: 12px; }
.field-hint { color: var(--muted); font-size: 12px; }
select, input[type="search"] {
  width: 100%; height: 36px; padding: 0 10px;
  border: 1px solid var(--control); border-radius: var(--radius-control);
  background: var(--surface); color: var(--ink);
  font-family: inherit; font-size: 14px;
}
select:disabled { background: var(--raised); color: var(--muted); }
input[type="search"]::placeholder { color: var(--muted); }
.button {
  display: inline-flex; align-items: center; justify-content: center;
  height: 32px; padding: 0 12px;
  border: 1px solid var(--control); border-radius: var(--radius-control);
  background: var(--surface); color: var(--ink);
  font-size: 14px; font-weight: 500; line-height: 1; text-decoration: none;
  cursor: pointer;
}
.button:hover { background: var(--raised); }
.button.primary { border-color: var(--accent); background: var(--accent); color: var(--accent-ink); }
.button.primary:hover { background: var(--accent); opacity: .88; }
.button.quiet { background: transparent; }
.button.quiet:hover { background: var(--raised); }
.viewer-inner .button { height: 30px; font-size: 12px; }
.finding-lead { margin-top: 20px; }
.lead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 11px 0; border-top: 1px solid var(--rule); }
.lead-title { font-weight: 500; }
.lead-meta { color: var(--muted); font-size: 12px; }
.lead-link { margin-left: auto; font-size: 12px; white-space: nowrap; }
.lead-empty { padding: 11px 0; border-top: 1px solid var(--rule); color: var(--muted); }
.notice {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  margin-top: 12px; padding: 9px 12px;
  border: 1px solid var(--border); border-left: 3px solid var(--warning);
  border-radius: var(--radius-control);
  background: var(--warning-soft); color: var(--warning-ink);
  font-size: 12px;
}
.notice strong { font-weight: 600; }
.toc { display: flex; flex-wrap: wrap; gap: 0 18px; padding: 14px 0 16px; }
.toc a { padding: 4px 0; border-bottom: 1px solid transparent; color: var(--muted); font-size: 12px; text-decoration: none; }
.toc a:hover, .toc a:focus-visible { border-bottom-color: var(--ink); color: var(--ink); }
main { padding-bottom: 24px; }
section { position: relative; padding: 32px 0 8px; scroll-margin-top: 64px; }
section::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: var(--rule); }
#summary { padding-top: 28px; }
#summary::before { display: none; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.section-meta { color: var(--muted); font-size: 12px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.stat { min-width: 0; padding: 14px 18px 15px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
.stat.is-data { border-top: 2px solid var(--data); }
.stat-label { display: block; color: var(--muted); font-size: 12px; }
.stat-value { display: block; margin-top: 2px; font-size: 30px; font-weight: 500; line-height: 1.1; letter-spacing: -.02em; }
.stat-value.is-data { color: var(--data); }
.stat-note { display: block; margin-top: 2px; color: var(--muted); font-size: 12px; }
.summary-brief { max-width: 78ch; margin-top: 16px; color: var(--muted); }
.pill {
  display: inline-flex; align-items: center; height: 20px; padding: 0 7px;
  border-radius: 999px;
  background: var(--pill-bg, var(--neutral-soft)); color: var(--pill-ink, var(--neutral-ink));
  font-size: 12px; font-weight: 500; letter-spacing: .01em;
}
.sev-CRITICAL { --sev: var(--critical); --pill-bg: var(--critical-soft); --pill-ink: var(--critical-ink); }
.sev-HIGH { --sev: var(--high); --pill-bg: var(--high-soft); --pill-ink: var(--high-ink); }
.sev-MEDIUM { --sev: var(--warning); --pill-bg: var(--warning-soft); --pill-ink: var(--warning-ink); }
.sev-LOW { --sev: var(--low); --pill-bg: var(--low-soft); --pill-ink: var(--low-ink); }
.sev-INFO { --sev: var(--neutral-ink); --pill-bg: var(--neutral-soft); --pill-ink: var(--neutral-ink); }
.code {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 20px; height: 20px; padding: 0 5px;
  border-radius: 4px;
  font-family: var(--mono); font-size: 12px; font-weight: 500;
}
.code-R, .status-R { background: var(--neutral-soft); color: var(--neutral-ink); }
.code-E, .status-E { background: var(--warning-soft); color: var(--warning-ink); }
.code-Z, .status-Z { background: var(--data-soft); color: var(--data-ink); }
.code-P, .status-P { background: var(--neutral-soft); color: var(--muted); }
.survival-rail { display: flex; gap: 2px; height: 12px; overflow: hidden; border-radius: 2px; background: var(--rule); }
.survival-rail span { display: block; height: 100%; }
.seg-R { background: var(--R); }
.seg-E { background: var(--E); }
.seg-Z { background: var(--Z); }
.survival-legend { display: flex; flex-wrap: wrap; gap: 6px 24px; margin-top: 10px; color: var(--muted); font-size: 12px; }
.legend-item { display: inline-flex; align-items: center; gap: 7px; }
.legend-swatch { display: inline-block; width: 8px; height: 8px; border-radius: 2px; }
.legend-count { color: var(--ink); font-weight: 500; }
.outcome-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; margin-top: 24px; }
.outcome { position: relative; min-width: 0; padding-top: 12px; }
.outcome::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--rule); }
.outcome.is-Z::before { background: var(--data); }
.outcome-head { display: flex; align-items: center; gap: 8px; }
.outcome-title { font-weight: 500; }
.outcome-count { margin-left: auto; font-size: 16px; font-weight: 500; }
.outcome-list { margin: 10px 0 0; padding: 0; list-style: none; }
.outcome-list li { padding: 10px 0; border-top: 1px solid var(--rule); }
.outcome-list li:first-child { padding-top: 0; border-top: 0; }
.outcome-list .empty { margin: 0; font-size: 12px; }
.trace-link {
  display: inline-flex; align-items: center; min-height: 24px; padding: 0; border: 0; background: none;
  color: var(--ink); font-family: inherit; font-size: 14px; font-weight: 500; line-height: 1.4;
  text-align: left; text-decoration: underline; text-decoration-color: var(--control); text-underline-offset: 2px;
  cursor: pointer; overflow-wrap: anywhere;
}
.trace-link:hover { text-decoration-color: currentColor; }
.outcome-meta { display: block; margin-top: 2px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.outcome-where { display: block; margin-top: 1px; color: var(--muted); font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.outcome-more { margin-top: 10px; font-size: 12px; }
.table-hint { margin-top: 28px; color: var(--muted); font-size: 12px; }
.table-heading { display: flex; align-items: center; gap: 8px; margin: 24px 0 6px; }
.table-wrap { max-width: 100%; overflow-x: auto; }
.table-wrap:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.scroll-hint { margin: 0 0 6px; color: var(--muted); font-size: 12px; text-align: right; }
table { width: 100%; min-width: 660px; border-collapse: collapse; table-layout: fixed; font-size: 14px; }
caption { padding: 0 0 8px; color: var(--muted); font-size: 12px; text-align: left; }
thead th {
  padding: 8px 12px; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
  background: var(--raised); color: var(--muted); font-size: 12px; font-weight: 500; text-align: left;
  white-space: nowrap;
}
tbody td, tbody th {
  padding: 9px 12px; border-bottom: 1px solid var(--rule); text-align: left; vertical-align: top;
}
tbody tr:last-child td, tbody tr:last-child th { border-bottom: 1px solid var(--border); }
td.num, th.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.wrap, th.wrap { overflow-wrap: anywhere; }
td.nowrap { white-space: nowrap; }
.table-wrap table.wide { min-width: 860px; }
.cell-id { display: block; margin-top: 2px; color: var(--muted); font-family: var(--mono); font-size: 13px; overflow-wrap: anywhere; }
.evidence { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.evidence-list { margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-size: 13px; }
.evidence-list li { margin: 2px 0; overflow-wrap: anywhere; }
details { margin-top: 10px; }
summary { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; cursor: pointer; }
summary:hover { color: var(--ink); }
details[open] summary { margin-bottom: 6px; }
.details-body { padding-top: 2px; }
pre {
  margin: 8px 0 0; padding: 10px; overflow-wrap: anywhere; white-space: pre-wrap;
  background: var(--raised); border: 1px solid var(--rule); border-radius: var(--radius-control);
  font-size: 12px; line-height: 1.5;
}
.rotation-group h3 { display: flex; align-items: center; gap: 8px; margin: 20px 0 4px; }
.steps { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0; }
.step { position: relative; display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 16px; padding: 14px 0; }
.step::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: var(--rule); }
.steps .step:first-child::before { display: none; }
.step-no { padding-top: 2px; color: var(--muted); font-family: var(--mono); font-size: 12px; }
.step-body { min-width: 0; }
.step-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.step-title { font-weight: 600; }
.step-actions { margin: 6px 0 0; padding-left: 18px; }
.step-actions li { margin: 2px 0; }
.step-cred { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.cred-chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 7px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); color: var(--ink); font-size: 12px; }
.cred-chip .mono { color: var(--muted); }
.fact-grid { position: relative; display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 24px; padding: 14px 0; border-bottom: 1px solid var(--rule); }
.fact-grid::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: var(--rule); }
.fact { min-width: 0; }
.fact-label { display: block; color: var(--muted); font-size: 12px; }
.fact-value { display: block; margin-top: 3px; font-size: 16px; font-weight: 500; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.text-chip { display: inline-flex; align-items: center; padding: 2px 7px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); font-size: 12px; overflow-wrap: anywhere; }
.graph-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.graph-actions { display: flex; align-items: center; gap: 6px; }
.graph-actions .button { height: 28px; padding: 0 9px; font-family: var(--mono); font-size: 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); }
.legend i { display: inline-block; width: 22px; border-top: 2px solid currentColor; }
.legend .solid i { color: var(--graph-edge); }
.legend .dashed i { color: var(--warning); border-top-style: dashed; }
.legend .dotted i { color: var(--muted); border-top-style: dotted; }
#graph-canvas { width: 100%; height: clamp(28rem, 60vh, 48rem); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
#graph-note { margin-top: 10px; color: var(--muted); font-size: 12px; }
#entity-details { margin-top: 12px; }
#entity-details h3 { margin-top: 0; }
#entity-details .mono { color: var(--muted); }
.toolbar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; margin-bottom: 8px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { color: var(--muted); font-size: 12px; }
.field-search { width: 256px; }
.field-select { width: 170px; }
.toolbar-status { margin-left: auto; padding-bottom: 10px; color: var(--muted); font-size: 12px; }
.toolbar .button { height: 36px; }
.finding { padding: 16px 0 16px 16px; border-left: 3px solid var(--sev, var(--border)); border-bottom: 1px solid var(--rule); }
.finding-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.finding-head h3 { font-weight: 600; }
.finding-rule { margin-top: 5px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.finding-message { margin-top: 6px; }
.finding-meta { margin-top: 6px; color: var(--muted); font-size: 12px; }
.finding-path { margin-top: 8px; color: var(--muted); font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.matrix-summary { margin-bottom: 6px; }
.matrix-legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 12px 0; color: var(--muted); font-size: 12px; }
.matrix-legend span { display: inline-flex; align-items: center; gap: 6px; }
.matrix-wrap { max-height: 42rem; overflow: auto; }
.matrix { min-width: max-content; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.matrix thead th { position: sticky; top: 0; z-index: 2; background: var(--raised); }
.matrix tbody th { position: sticky; left: 0; z-index: 1; min-width: 14rem; background: var(--bg); font-weight: 500; }
.matrix thead th:first-child { left: 0; z-index: 3; }
.matrix td { padding: 7px 10px; text-align: center; }
.matrix .active-row th { box-shadow: inset 2px 0 0 var(--data); }
button.status {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 24px; height: 24px; padding: 0 6px;
  border: 1px solid transparent; border-radius: 4px;
  font-family: var(--mono); font-size: 12px; font-weight: 500;
  cursor: pointer;
}
button.status:hover { border-color: currentColor; }
.kv { position: relative; }
.kv::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: var(--rule); }
.kv div { display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 16px; padding: 9px 0; border-bottom: 1px solid var(--rule); }
.kv dt { color: var(--muted); font-size: 12px; }
.kv dd { margin: 0; overflow-wrap: anywhere; }
ul.plain { margin: 6px 0 0; padding-left: 18px; }
ul.plain li { margin: 3px 0; }
.trace { margin: 12px 0 0; padding: 0 0 0 16px; border-left: 1px solid var(--border); list-style: none; }
.trace li { position: relative; padding: 0 0 12px 12px; }
.trace li::before { content: ""; position: absolute; left: -20px; top: 6px; width: 7px; height: 7px; border: 1px solid var(--control); border-radius: 50%; background: var(--surface); }
.trace .hop { font-size: 14px; font-weight: 500; overflow-wrap: anywhere; }
.trace .muted { margin-top: 2px; font-size: 12px; }
footer { position: relative; margin-top: 32px; padding: 20px 0 40px; color: var(--muted); font-size: 12px; }
footer::before { content: ""; position: absolute; top: 0; left: 24px; right: 24px; height: 1px; background: var(--rule); }
.footer-inner { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; }
@media (max-width: 1000px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .outcome-grid { grid-template-columns: minmax(0, 1fr); gap: 0; }
  .outcome { padding: 16px 0; }
  .outcome::before { height: 1px; background: var(--border); }
  .outcome.is-Z::before { background: var(--data); }
  .title-row { flex-direction: column; gap: 20px; }
  .head-actions { width: 100%; }
  .fact-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .wrap { padding: 0 16px; }
  .viewer-inner { gap: 8px; padding: 0 16px; }
  .brand-sub, .viewer-schema { display: none; }
  .viewer-meta { gap: 8px; }
  .page-head { padding-top: 24px; }
  .head-actions .button { height: 36px; }
  .summary-grid { gap: 8px; }
  .stat { padding: 12px 14px; }
  .lead-link { margin-left: 0; }
  .field-search, .field-select { width: 100%; }
  .field { flex: 1 1 100%; }
  .toolbar-status { margin-left: 0; padding-bottom: 0; }
  thead th, tbody td, tbody th { padding: 8px; }
  #graph-canvas { height: 28rem; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
}
@media print {
  :root { color-scheme: light; --bg: #fff; --surface: #fff; --raised: #f7f7f7; --ink: #000; --muted: #333; --border: #bbb; --rule: #ddd; --data: #0b4a9e; --data-ink: #0b4a9e; --data-soft: #eef3fb; }
  .viewer-bar { position: static; border-bottom: 1px solid #000; }
  .viewer-meta, #print-button, .head-actions, .toc, .toolbar, .skip-link, .outcome-more, .scroll-hint { display: none; }
  body { font-size: 10.5pt; }
  section { break-inside: auto; }
  .stat, .finding, .step, .table-wrap, .outcome { break-inside: avoid; }
  #graph-canvas { height: 18cm; }
  a { text-decoration: none; }
}
</style>
<noscript><style>html.booting body { visibility: visible; }</style></noscript>
</head>
<body>
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
    </nav>
  </div>
</header>
<main id="main">
  <div class="wrap">
    <noscript><p class="notice">This report needs JavaScript enabled to display its embedded data. It makes no network requests.</p></noscript>
    <section id="summary" aria-labelledby="summary-title">
      <div class="section-head">
        <h2 id="summary-title">Summary</h2>
        <p class="section-meta" id="summary-context"></p>
      </div>
      <div class="summary-grid" id="summary-grid"></div>
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
      <div class="section-head">
        <h2 id="graph-title">Graph</h2>
        <p class="section-meta">Click a node or edge for its evidence</p>
      </div>
      <div class="graph-toolbar">
        <div class="legend" role="group" aria-label="Evidence line styles">
          <span class="solid"><i></i>DECLARED / DERIVED</span>
          <span class="dashed"><i></i>ASSUMED</span>
          <span class="dotted"><i></i>UNKNOWN</span>
        </div>
        <div class="graph-actions">
          <button class="button quiet" id="graph-zoom-out" type="button">Zoom out</button>
          <button class="button quiet" id="graph-zoom-in" type="button">Zoom in</button>
          <button class="button quiet" id="graph-fit" type="button">Fit</button>
          <p class="section-meta">Layout runs locally in this file</p>
        </div>
      </div>
      <div id="graph-canvas" role="img" aria-label="Authority graph, a visual aid" aria-describedby="graph-note"></div>
      <p id="graph-note">The graph is a visual aid. The scenario, survival and findings sections contain the same evidence as text. Pointer selection shows node or edge details below; use the zoom controls for a closer look. The graph canvas is not keyboard operable.</p>
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
  const bootFallback = window.setTimeout(() => {
    document.documentElement.classList.remove("booting");
  }, 4000);
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
  let activeGraph = null;

  function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function clear(container) {
    container.replaceChildren();
  }

  function writeText(item, className, value) {
    const text = String(value);
    if (
      className &&
      /(?:^|\s)(?:mono|wrap|evidence|cell-id|finding-rule)(?:\s|$)/.test(className) &&
      text.length > 10
    ) {
      let start = 0;
      for (let index = 0; index < text.length; index += 1) {
        if (":/#_-".indexOf(text[index]) !== -1 && index + 1 < text.length) {
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
    append(wrap, "span", "cell-id", id);
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
      undefined,
      ["46%", "14%", "40%"]
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
        value: scenario ? partition.Z.length : "—",
        note: scenario ? "of " + total + " listed credential(s)" : "no entrypoint selected",
        data: true
      },
      {
        label: "Ends with entrypoint",
        value: scenario ? partition.R.length : "—",
        note: "end when it is revoked",
        data: false
      },
      {
        label: "Expires on its own",
        value: scenario ? partition.E.length : "—",
        note: "expire without rotation",
        data: false
      },
      {
        label: "Findings",
        value: findings.length,
        note: findings.length ? (critical ? critical + " critical" : "none critical") : "none recorded",
        data: false
      }
    ];
    metrics.forEach((metric) => {
      const card = append(target, "div", "stat" + (metric.data ? " is-data" : ""));
      append(card, "span", "stat-label", metric.label);
      append(card, "strong", "stat-value" + (metric.data ? " is-data" : ""), metric.value);
      append(card, "span", "stat-note", metric.note);
    });
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
      parts.push("The result is a lower bound: " + unresolved + " input(s) could not be resolved.");
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
    const finding = findings[0];
    const row = append(target, "div", "lead");
    append(row, "span", "pill sev-" + finding.severity, finding.severity);
    append(row, "span", "lead-title", finding.title);
    append(
      row,
      "span",
      "lead-meta",
      finding.rule + (finding.scenario ? " · " + finding.scenario : "")
    );
    const link = element("a", "lead-link", "All " + findings.length + " findings");
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
        ? (index + 1) + " of " + scenarios.length + " entrypoint(s)"
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
      segment.title = pair[1] + " credential(s) in " + pair[0];
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
      undefined,
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
      ["", "num", "", ""],
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
      ["", "num", "", "", "num", ""],
      ["32%", "8%", "13%", "17%", "12%", "18%"]
    );
  }

  function renderOutcome(grid, code, title, entries) {
    const column = append(grid, "div", "outcome" + (code === "Z" ? " is-Z" : ""));
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
    if (!activeGraph) { return; }
    activeGraph.elements().removeClass("dimmed traced");
  }

  function highlightGraphTrace(path) {
    if (!activeGraph) { return; }
    clearGraphTrace();
    const tracedEdges = new Set(path.map((edge) => edge.id));
    const tracedNodes = new Set();
    path.forEach((edge) => {
      tracedNodes.add(edge.src);
      tracedNodes.add(edge.dst);
    });
    activeGraph.elements().addClass("dimmed");
    activeGraph.edges().filter((edge) => tracedEdges.has(edge.id()))
      .removeClass("dimmed").addClass("traced");
    activeGraph.nodes().filter((node) => tracedNodes.has(node.id()))
      .removeClass("dimmed").addClass("traced");
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
    append(heading, "span", "section-meta", (steps || []).length + " step(s)");
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
      count.textContent = matches.length + " of " + findings.length + " findings shown.";
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
        ids.length + " credential(s) are listed across " + items.length + " scenarios; " +
        sharedSurvivors + " potentially survive revocation in more than one scenario; " +
        unique + " appear in only one. Widest listed coverage: " +
        (widestIndex >= 0 ? items[widestIndex].selector : "none") +
        " (" + Math.max(widestCount, 0) + " credential(s)).";
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
      addColumns(table, ["12%", "42%", "8%", "38%"]);
      const head = append(append(table, "thead"), "tr");
      ["ID", "Statement", "Verify", "Used by"].forEach((heading) => {
        const cell = append(head, "th", "", heading);
        cell.scope = "col";
      });
      const body = append(table, "tbody");
      assumptions.forEach((assumption) => {
        const row = append(body, "tr");
        append(row, "td", "mono", assumption.id);
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

  function showEvidencePanel(title, subtitle, evidence) {
    const target = document.getElementById("entity-details");
    clear(target);
    append(target, "h3", "", title);
    if (subtitle) { append(target, "p", "mono muted", subtitle); }
    evidenceList(target, evidence || []);
  }

  function showNode(id) {
    const item = nodes.get(id);
    if (!item) { return; }
    showEvidencePanel(item.label, item.kind + " · " + item.id, item.evidence);
    const target = document.getElementById("entity-details");
    const trace = element("button", "button quiet", "Trace from the selected entrypoint");
    trace.type = "button";
    trace.addEventListener("click", () => traceTo(id));
    append(target, "p").appendChild(trace);
    const pre = append(target, "pre");
    pre.textContent = JSON.stringify(item.attrs || {}, null, 2);
  }

  function showEdge(id) {
    const item = edges.get(id);
    if (!item) { return; }
    showEvidencePanel(
      item.kind + " edge",
      item.src + " -> " + item.dst + " · confidence " + item.confidence,
      item.evidence
    );
  }

  function categoryFor(kind) {
    if (kind === "CREDENTIAL") { return {token: "credential", shape: "diamond", size: 48}; }
    if (kind === "SINK") { return {token: "sink", shape: "round-rectangle", size: 50}; }
    if (kind === "AWS_ROLE") { return {token: "role", shape: "hexagon", size: 50}; }
    if (kind === "OIDC_IDENTITY" || kind === "AWS_OIDC_PROVIDER") {
      return {token: "oidc", shape: kind === "AWS_OIDC_PROVIDER" ? "hexagon" : "ellipse", size: 42};
    }
    if (kind === "WORKFLOW" || kind === "JOB") {
      return {token: "workflow", shape: "ellipse", size: kind === "JOB" ? 42 : 40};
    }
    return {token: "structure", shape: "ellipse", size: 40};
  }

  function zoomGraph(factor) {
    if (!activeGraph) { return; }
    const level = Math.max(0.2, Math.min(3, activeGraph.zoom() * factor));
    activeGraph.zoom({
      level: level,
      renderedPosition: { x: activeGraph.width() / 2, y: activeGraph.height() / 2 }
    });
  }

  function renderGraph(scenario) {
    const container = document.getElementById("graph-canvas");
    const details = document.getElementById("entity-details");
    if (activeGraph) {
      activeGraph.destroy();
      activeGraph = null;
    }
    clear(container);
    clear(details);
    if (!window.cytoscape) {
      append(container, "p", "empty", "The graph renderer is unavailable.");
      return;
    }
    const focus = new Set();
    if (scenario) {
      scenario.start_nodes.forEach((id) => focus.add(id));
      scenario.potential_nodes.forEach((id) => focus.add(id));
      scenario.partition.R.forEach((id) => focus.add(id));
      scenario.partition.E.forEach((entry) => focus.add(entry.credential));
      scenario.partition.Z.forEach((entry) => focus.add(entry.credential));
    }
    const fill = cssVar("--surface", "#ffffff");
    const ink = cssVar("--ink", "#14171c");
    const edgeColour = cssVar("--graph-edge", "#98a0aa");
    const focusColour = cssVar("--data", "#1d5fbf");
    const elements = [];
    (report.graph.nodes || []).forEach((item) => {
      const category = categoryFor(item.kind);
      elements.push({
        group: "nodes",
        data: {
          id: item.id,
          label: item.label,
          kind: item.kind,
          fill: fill,
          stroke: cssVar("--node-" + category.token, edgeColour),
          shape: category.shape,
          size: category.size,
          opacity: focus.size && !focus.has(item.id) ? 0.42 : 1
        }
      });
    });
    (report.graph.edges || []).forEach((item) => {
      const lineStyle = item.confidence === "unknown" ? "dotted" :
        item.confidence === "assumed" ? "dashed" : "solid";
      elements.push({
        group: "edges",
        data: {
          id: item.id,
          source: item.src,
          target: item.dst,
          kind: item.kind,
          confidence: item.confidence,
          lineStyle: lineStyle,
          opacity: focus.size && !(focus.has(item.src) && focus.has(item.dst)) ? 0.25 : 0.8
        }
      });
    });
    if (!elements.length) {
      append(container, "p", "empty", "The graph is empty.");
      return;
    }
    try { window.cytoscape.use(window.cytoscapeDagre); } catch (error) { /* cose fallback */ }
    const cy = window.cytoscape({
      container: container,
      elements: elements,
      style: [
        {
          selector: "node",
          style: {
            "label": "data(label)",
            "background-color": "data(fill)",
            "border-width": 2,
            "border-color": "data(stroke)",
            "color": ink,
            "font-family": "Geist",
            "font-size": "12px",
            "font-weight": 500,
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "ellipsis",
            "text-max-width": "96px",
            "text-background-color": fill,
            "text-background-opacity": 0.9,
            "text-background-padding": "2px",
            "text-background-shape": "roundrectangle",
            "shape": "data(shape)",
            "width": "data(size)",
            "height": "data(size)",
            "opacity": "data(opacity)"
          }
        },
        {
          selector: "edge",
          style: {
            "width": 1.4,
            "line-color": edgeColour,
            "target-arrow-color": edgeColour,
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.7,
            "curve-style": "bezier",
            "line-style": "data(lineStyle)",
            "opacity": "data(opacity)"
          }
        },
        { selector: "node.dimmed", style: {"opacity": 0.2} },
        { selector: "edge.dimmed", style: {"opacity": 0.14} },
        { selector: "node.traced", style: {"border-width": 3, "border-color": focusColour} },
        {
          selector: "edge.traced",
          style: {
            "width": 2.4,
            "line-color": focusColour,
            "target-arrow-color": focusColour,
            "opacity": 0.95
          }
        }
      ],
      layout: {
        name: "dagre",
        rankDir: "LR",
        animate: false,
        fit: true,
        padding: 24,
        nodeSep: 28,
        edgeSep: 12,
        rankSep: 64
      }
    });
    activeGraph = cy;
    cy.on("tap", "node", (event) => showNode(event.target.data("id")));
    cy.on("tap", "edge", (event) => showEdge(event.target.data("id")));
    document.fonts.ready.then(() => {
      if (activeGraph === cy) {
        cy.resize();
        cy.style().update();
      }
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
  document.getElementById("graph-zoom-in").addEventListener("click", () => zoomGraph(1.25));
  document.getElementById("graph-zoom-out").addEventListener("click", () => zoomGraph(0.8));
  document.getElementById("graph-fit").addEventListener("click", () => {
    if (activeGraph) { activeGraph.fit(activeGraph.elements(), 28); }
  });
  renderScenarioPicker();
  document.getElementById("print-button").addEventListener("click", () => window.print());
  window.clearTimeout(bootFallback);
  window.requestAnimationFrame(() => {
    document.documentElement.classList.remove("booting");
  });
}).call(window);
"""
