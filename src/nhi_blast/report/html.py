"""Single-file offline HTML report with a restrictive CSP (spec 13.4)."""

from __future__ import annotations

import base64
import hashlib
import json
from functools import cache
from importlib import resources
from pathlib import Path

from nhi_blast.core.models import Report
from nhi_blast.report.model_json import report_dict

_ASSET_NAMES = ("cytoscape.min.js", "dagre.min.js", "cytoscape-dagre.js")
_DATA_OPEN = '<script type="application/json" id="report-data">'

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>NHI-Blast report</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #f6f8fb;
  --surface: #ffffff;
  --surface-2: #eef2f7;
  --ink: #0f172a;
  --muted: #526071;
  --line: #d7dee8;
  --accent: #0b6bcb;
  --critical: #b42318;
  --high: #c02a1a;
  --medium: #8a5a00;
  --low: #076a83;
  --info: #526071;
  --radius: 10px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0c121c;
    --surface: #141d2a;
    --surface-2: #1c2939;
    --ink: #edf3fb;
    --muted: #a5b4c7;
    --line: #2b3a4e;
    --accent: #75b7ff;
    --critical: #ff8b80;
    --high: #ff9b8f;
    --medium: #f3c969;
    --low: #76d4e8;
    --info: #a5b4c7;
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  overflow-wrap: break-word;
}
a { color: var(--accent); }
header {
  background: linear-gradient(120deg, #0d2747, #0b5b7c 65%, #0c7075);
  color: #f5fbff;
  padding: 2.2rem clamp(1rem, 4vw, 3rem) 1.8rem;
}
header h1 { margin: 0 0 .25rem; font-size: clamp(1.75rem, 4vw, 2.5rem); letter-spacing: -.02em; }
header p { margin: .2rem 0; color: #d7edff; max-width: 70rem; }
nav.toc { display: flex; flex-wrap: wrap; gap: .4rem 1rem; margin-top: 1rem; }
nav.toc a { color: #eaf7ff; font-weight: 600; text-decoration-thickness: 1px; }
main { max-width: 1180px; margin: 0 auto; padding: 1.5rem clamp(.75rem, 3vw, 2rem) 4rem; }
section {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: clamp(1rem, 2.5vw, 1.6rem);
  margin: 1.2rem 0;
  box-shadow: 0 8px 24px rgb(15 23 42 / .04);
}
h2 { margin: 0 0 .9rem; font-size: 1.35rem; letter-spacing: -.01em; }
h3 { margin: 1.25rem 0 .5rem; font-size: 1.04rem; }
h4 { margin: 1rem 0 .35rem; font-size: .96rem; }
p { margin: .45rem 0; }
.muted { color: var(--muted); }
.mono, code, pre { font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace; }
.mono { overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--surface-2); padding: .75rem; border-radius: 8px; }
dd { margin-left: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: .75rem; }
.metric { background: var(--surface-2); border-radius: 9px; padding: .8rem .9rem; }
.metric strong { display: block; font-size: 1.65rem; line-height: 1.15; }
.metric span { color: var(--muted); font-size: .86rem; }
.controls { display: flex; align-items: center; gap: .7rem; flex-wrap: wrap; margin-bottom: .8rem; }
select, input[type="search"] {
  color: var(--ink); background: var(--surface); border: 1px solid var(--line);
  border-radius: 8px; padding: .5rem .6rem; max-width: min(100%, 46rem);
}
input[type="search"] { min-width: min(100%, 18rem); }
.control-check { display: inline-flex; align-items: center; gap: .45rem; }
button.link-button {
  background: none; border: 0; padding: 0; margin: 0; font: inherit;
  color: var(--accent); text-decoration: underline; cursor: pointer; text-align: left;
}
button.link-button:hover { text-decoration-thickness: 2px; }
.trace { display: grid; gap: .55rem; padding-left: 1.35rem; }
.trace li { padding: .45rem .6rem; border-left: 3px solid var(--line); }
.trace .hop { font-weight: 650; }
.status {
  display: inline-block; min-width: 1.6rem; border-radius: 6px; padding: .05rem .35rem;
  font-weight: 750; font-size: .78rem; border: 1px solid currentColor;
}
button.status { background: var(--surface); cursor: pointer; font: inherit; font-weight: 750; }
.status-R { color: var(--critical); }
.status-E { color: var(--medium); }
.status-Z { color: var(--low); }
.status-P { color: var(--info); }
.matrix-wrap { max-height: 38rem; }
.matrix { border-collapse: separate; border-spacing: 0; font-size: .82rem; }
.matrix thead th { position: sticky; top: 0; z-index: 2; background: var(--surface-2); }
.matrix tbody th { position: sticky; left: 0; z-index: 1; background: var(--surface); min-width: 12rem; }
.matrix thead th:first-child { left: 0; z-index: 3; }
.matrix td { text-align: center; }
.matrix .active-row th { box-shadow: inset 3px 0 0 var(--accent); }
.table-wrap { max-width: 100%; overflow-x: auto; }
.table-wrap:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
table { width: 100%; border-collapse: collapse; margin: .6rem 0 1.1rem; font-size: .9rem; }
th, td { border-bottom: 1px solid var(--line); padding: .48rem .55rem; text-align: left; vertical-align: top; }
th { background: var(--surface-2); font-weight: 650; }
td.wrap { overflow-wrap: anywhere; }
.evidence { color: var(--muted); font-size: .82rem; overflow-wrap: anywhere; }
.badge {
  display: inline-block; border-radius: 999px; padding: .08rem .52rem;
  font-size: .74rem; font-weight: 750; letter-spacing: .04em;
  border: 1px solid currentColor;
}
.sev-CRITICAL { color: var(--critical); }
.sev-HIGH { color: var(--high); }
.sev-MEDIUM { color: var(--medium); }
.sev-LOW { color: var(--low); }
.sev-INFO { color: var(--info); }
.finding { border-left: 4px solid var(--line); padding: .65rem .85rem; margin: .9rem 0; background: var(--surface-2); border-radius: 0 8px 8px 0; color: var(--ink); }
.finding.sev-CRITICAL { border-left-color: var(--critical); }
.finding.sev-HIGH { border-left-color: var(--high); }
.finding.sev-MEDIUM { border-left-color: var(--medium); }
.finding.sev-LOW { border-left-color: var(--low); }
.finding.sev-INFO { border-left-color: var(--info); }
.finding h3 { margin: 0 0 .25rem; }
.finding-rule { color: var(--muted); font-size: .82rem; }
.evidence-list { margin: .35rem 0; padding-left: 1.25rem; }
.evidence-list li { margin: .18rem 0; }
.legend { display: flex; gap: .9rem; flex-wrap: wrap; color: var(--muted); font-size: .82rem; margin: .35rem 0 .7rem; }
.legend i { display: inline-block; width: 1.5rem; border-top: 3px solid currentColor; vertical-align: middle; margin-right: .3rem; }
.legend .solid { color: #3f6d91; }
.legend .dashed { color: #9a6700; border-top-style: dashed; }
.legend .dotted { color: #9b3d9b; border-top-style: dotted; }
@media (prefers-color-scheme: dark) {
  .legend .solid { color: #7fb4d9; }
  .legend .dashed { color: #f3c969; }
  .legend .dotted { color: #dca6ea; }
}
#graph-canvas {
  width: 100%; height: clamp(26rem, 58vh, 48rem);
  border: 1px solid var(--line); border-radius: 9px; background: var(--surface);
}
#entity-details { margin-top: .8rem; border-top: 1px solid var(--line); padding-top: .8rem; }
.steps { display: grid; grid-template-columns: minmax(0, 1fr); gap: .7rem; }
.step { border: 1px solid var(--line); border-radius: 8px; padding: .7rem .85rem; min-width: 0; }
.step header { all: unset; display: block; font-weight: 700; }
ul, ol { padding-left: 1.35rem; }
li { margin: .22rem 0; }
.note { border-left: 3px solid var(--accent); padding-left: .7rem; color: var(--muted); }
.empty { color: var(--muted); font-style: italic; }
.skip-link { position: absolute; left: -999px; }
.skip-link:focus { left: 1rem; top: 1rem; z-index: 10; background: white; color: black; padding: .5rem; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
caption { text-align: left; font-weight: 650; padding: .25rem 0 .45rem; }
footer { max-width: 1180px; margin: 0 auto; padding: 0 1rem 2rem; color: var(--muted); font-size: .82rem; }
@media (max-width: 560px) {
  header { padding: 1.4rem .85rem 1.2rem; }
  main { padding: .8rem .55rem 2.5rem; }
  section { padding: .85rem; border-radius: 9px; }
  table { font-size: .82rem; }
  th, td { padding: .35rem .3rem; }
}
@media print {
  :root { --bg: #fff; --surface: #fff; --surface-2: #f7f7f7; --ink: #000; --muted: #333; --line: #bbb; }
  header { background: #fff; color: #000; border-bottom: 2px solid #000; }
  header p { color: #333; }
  nav.toc { display: none; }
  body { font-size: 10.5pt; }
  section { break-inside: avoid; box-shadow: none; }
  #graph-canvas { height: 24cm; }
}
</style>
</head>
<body>
<a class="skip-link" href="#main">Skip to report content</a>
<header>
  <h1>NHI-Blast</h1>
  <p id="tool-line"></p>
  <p id="repo-line"></p>
  <nav class="toc" aria-label="Report sections">
    <a href="#scope">Scope and Limits</a>
    <a href="#summary">Summary</a>
    <a href="#scenario">Scenario</a>
    <a href="#graph">Graph</a>
    <a href="#survival">Survival panel</a>
    <a id="matrix-link" href="#matrix" hidden>Cross-scenario exposure</a>
    <a href="#rotation">Rotation plan</a>
    <a href="#findings">Findings</a>
    <a href="#assumptions">Assumptions and Unknowns</a>
    <a href="#diagnostics">Diagnostics</a>
  </nav>
</header>
<main id="main">
  <noscript><p>This report needs JavaScript enabled to display its embedded data. No network access is used.</p></noscript>
  <section id="scope" aria-labelledby="scope-title">
    <h2 id="scope-title">Scope and Limits</h2>
    <div id="scope-content"></div>
  </section>
  <section id="summary" aria-labelledby="summary-title">
    <h2 id="summary-title">Summary</h2>
    <div class="summary-grid" id="summary-grid"></div>
    <p class="note" id="summary-brief"></p>
  </section>
  <section id="scenario" aria-labelledby="scenario-title">
    <h2 id="scenario-title">Scenario</h2>
    <div class="controls">
      <label for="scenario-picker">Entrypoint</label>
      <select id="scenario-picker"></select>
    </div>
    <div id="scenario-content"></div>
    <div id="trace-content" aria-live="polite"></div>
  </section>
  <section id="graph" aria-labelledby="graph-title">
    <h2 id="graph-title">Graph</h2>
    <div class="legend" role="group" aria-label="Evidence line styles">
      <span class="solid"><i></i>DECLARED / DERIVED</span>
      <span class="dashed"><i></i>ASSUMED</span>
      <span class="dotted"><i></i>UNKNOWN</span>
    </div>
    <div id="graph-canvas" role="img" aria-label="Authority graph, a visual aid" aria-describedby="graph-note"></div>
    <p class="muted" id="graph-note">The graph is a visual aid. The scenario, survival and findings sections contain the same evidence as text. Pointer selection shows node or edge details below; the graph canvas is not keyboard operable.</p>
    <div id="entity-details" aria-live="polite"></div>
  </section>
  <section id="survival" aria-labelledby="survival-title">
    <h2 id="survival-title">Survival panel</h2>
    <div id="survival-content"></div>
  </section>
  <section id="matrix" aria-labelledby="matrix-title" hidden>
    <h2 id="matrix-title">Cross-scenario exposure</h2>
    <p class="muted" id="matrix-summary"></p>
    <div class="controls">
      <label class="control-check" for="matrix-shared">
        <input type="checkbox" id="matrix-shared">
        Only credentials listed in more than one scenario
      </label>
    </div>
    <div id="matrix-content"></div>
  </section>
  <section id="rotation" aria-labelledby="rotation-title">
    <h2 id="rotation-title">Rotation plan</h2>
    <div id="rotation-content"></div>
  </section>
  <section id="findings" aria-labelledby="findings-title">
    <h2 id="findings-title">Findings</h2>
    <div class="controls" role="group" aria-label="Filter findings">
      <label for="finding-search">Filter</label>
      <input type="search" id="finding-search" autocomplete="off" spellcheck="false"
        placeholder="Rule, title, scenario, evidence">
      <label for="finding-severity">Severity</label>
      <select id="finding-severity"></select>
      <label for="finding-scenario">Scenario</label>
      <select id="finding-scenario"></select>
      <span id="findings-count" class="muted" role="status" aria-live="polite"></span>
    </div>
    <div id="findings-content"></div>
  </section>
  <section id="assumptions" aria-labelledby="assumptions-title">
    <h2 id="assumptions-title">Assumptions and Unknowns</h2>
    <div id="assumptions-content"></div>
  </section>
  <section id="diagnostics" aria-labelledby="diagnostics-title">
    <h2 id="diagnostics-title">Diagnostics</h2>
    <div id="diagnostics-content"></div>
  </section>
</main>
<footer>
  <p>Offline report generated by NHI-Blast. Evidence classes are labels, not proof of exploitation.</p>
</footer>
__SCRIPTS__
</body>
</html>
"""

_APP_JS = r"""(function () {
  "use strict";
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
  let currentScenarioIndex = 0;
  let activeGraph = null;
  const severityOrder = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4};
  const nodeColour = {
    REPOSITORY: "#64748b",
    WORKFLOW: "#2563eb",
    JOB: "#0f766e",
    ACTION_REF: "#7c3aed",
    CREDENTIAL: "#c2410c",
    OIDC_IDENTITY: "#0369a1",
    AWS_OIDC_PROVIDER: "#4338ca",
    AWS_ROLE: "#b91c1c",
    SINK: "#a16207",
    EXTERNAL_TARGET: "#475569"
  };

  function clear(container) {
    container.replaceChildren();
  }

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) { item.className = className; }
    if (text !== undefined && text !== null) { item.textContent = String(text); }
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
      append(container, "p", "muted", "No evidence record is attached.");
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

  function addTable(container, caption, headings, rows) {
    if (!rows.length) {
      append(container, "p", "empty", "No entries.");
      return;
    }
    const scroll = append(container, "div", "table-wrap");
    scroll.tabIndex = 0;
    scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", caption);
    const table = append(scroll, "table");
    append(table, "caption", "", caption);
    const head = append(table, "thead");
    const headRow = append(head, "tr");
    headings.forEach((heading) => {
      const cell = append(headRow, "th", "", heading);
      cell.scope = "col";
    });
    const body = append(table, "tbody");
    rows.forEach((row) => {
      const tr = append(body, "tr");
      row.forEach((value) => {
        const cell = append(tr, "td", "wrap");
        if (value && typeof value === "object" && typeof value.nodeType === "number") {
          cell.appendChild(value);
        } else {
          cell.textContent = textOf(value);
        }
      });
    });
  }

  function renderScope() {
    const target = document.getElementById("scope-content");
    clear(target);
    const details = append(target, "dl");
    [
      ["Repository", report.inputs.repo_slug],
      ["Repository identity source", report.inputs.repo_slug_source],
      ["Inputs digest", report.inputs.digest],
      ["Tool", report.tool.name + " " + report.tool.version],
      ["Generated at", report.generated_at || "not recorded"]
    ].forEach((pair) => {
      append(details, "dt", "muted", pair[0]);
      append(details, "dd", "mono", pair[1]);
    });
    append(target, "h3", "", "Limits");
    const limits = append(target, "ul");
    (report.scope_and_limits || []).forEach((item) => append(limits, "li", "", item));
    append(target, "h3", "", "Inputs");
    addTable(
      target,
      "Input files",
      ["Path", "Kind", "SHA-256"],
      (report.inputs.files || []).map((item) => [item.path, item.kind, item.sha256])
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
        item.source_url
      ])
    );
  }

  function renderSummary(scenario) {
    const target = document.getElementById("summary-grid");
    const brief = document.getElementById("summary-brief");
    clear(target);
    clear(brief);
    const partition = scenario ? scenario.partition : {R: [], E: [], Z: []};
    const findings = report.findings || [];
    const metrics = [
      [report.graph.nodes.length, "graph nodes"],
      [report.graph.edges.length, "graph edges"],
      [findings.length, "findings"],
      [scenario ? partition.R.length : "-", "in R for selected entrypoint"],
      [scenario ? partition.E.length : "-", "in E for selected entrypoint"],
      [scenario ? partition.Z.length : "-", "in Z for selected entrypoint"]
    ];
    metrics.forEach((metric) => {
      const card = append(target, "div", "metric");
      append(card, "strong", "", metric[0]);
      append(card, "span", "", metric[1]);
    });
    if (!scenario) {
      brief.textContent =
        "No scenario is available. The counts above describe the parsed graph and findings only.";
      return;
    }
    brief.textContent =
      "Scenario " + scenario.selector + ": " + partition.R.length +
      " credential(s) are listed in R (they end with the revoked entrypoint), " +
      partition.E.length + " in E (they expire on their own), and " + partition.Z.length +
      " in Z (they potentially survive until rotated or revoked separately). " +
      scenario.potential.length + " UNKNOWN-class edge(s) are reported as potential only.";
  }

  function renderScenarioPicker() {
    const picker = document.getElementById("scenario-picker");
    clear(picker);
    const scenarios = report.scenarios || [];
    if (!scenarios.length) {
      const option = append(picker, "option", "", "No scenarios selected");
      option.value = "";
      picker.disabled = true;
    } else {
      picker.disabled = false;
      scenarios.forEach((scenario, index) => {
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
    const scenario = (report.scenarios || [])[index] || null;
    renderSummary(scenario);
    renderScenario(index);
    renderMatrix();
  }

  function renderScenario(index) {
    const scenarios = report.scenarios || [];
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
    append(target, "p", "", "Selected entrypoint: " + scenario.selector);
    append(target, "h3", "", "Start nodes");
    const starts = append(target, "ul");
    scenario.start_nodes.forEach((id) => append(starts, "li", "mono", nodeLabel(id)));
    append(
      target,
      "p",
      "muted",
      "UNKNOWN-class potential edges: " + scenario.potential.length +
        "; unresolved inputs: " + scenario.unresolved_inputs.length +
        "; truncated: " + (scenario.truncated ? "yes" : "no")
    );
    if (scenario.notes && scenario.notes.length) {
      append(target, "h3", "", "Notes");
      const notes = append(target, "ul");
      scenario.notes.forEach((note) => append(notes, "li", "note", note));
    }
    renderSurvival(scenario);
    renderRotation(scenario);
    renderGraph(scenario);
  }

  function traceButton(id) {
    const button = element("button", "link-button", nodeLabel(id));
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
    append(
      target,
      "p",
      "muted",
      "Select a credential name to trace one shortest directed path from this scenario's entrypoint."
    );
    const partition = scenario.partition;
    append(target, "h3", "", "R - ends with the revoked entrypoint");
    addTable(
      target,
      "Credentials that end with the revoked entrypoint",
      ["Credential", "Kind", "Lifetime", "Evidence"],
      partition.R.map((id) => {
        const item = nodes.get(id);
        return [
          traceButton(id),
          item ? textOf(item.attrs.credential_kind) : "",
          item ? textOf(item.attrs.lifetime) : "",
          nodeEvidence(id)
        ];
      })
    );
    append(target, "h3", "", "E - expires on its own");
    addTable(
      target,
      "Credentials that expire on their own",
      ["Credential", "TTL (seconds)", "Kind", "Evidence"],
      partition.E.map((entry) => {
        const item = nodes.get(entry.credential);
        return [
          traceButton(entry.credential),
          entry.ttl_seconds,
          item ? textOf(item.attrs.credential_kind) : "",
          nodeEvidence(entry.credential)
        ];
      })
    );
    append(target, "h3", "", "Z - survives revocation");
    addTable(
      target,
      "Credentials that survive revocation",
      ["Credential", "Depth", "Lifetime", "Survival window", "Criticality", "Evidence"],
      partition.Z.map((entry) => [
        traceButton(entry.credential),
        entry.depth,
        entry.lifetime,
        entry.survival_window,
        entry.criticality,
        nodeEvidence(entry.credential)
      ])
    );
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
      append(
        item,
        "p",
        "muted",
        edge.kind + " edge; confidence " + edge.confidence
      );
      const evidence = append(item, "div");
      evidenceList(evidence, (edge.evidence || []).slice(0, 1));
    });
    const clearButton = element("button", "link-button", "Clear trace");
    clearButton.type = "button";
    clearButton.addEventListener("click", () => renderTrace(null, null));
    append(target, "p").appendChild(clearButton);
    highlightGraphTrace(path);
  }

  function traceTo(targetId) {
    const scenario = (report.scenarios || [])[currentScenarioIndex] || null;
    if (!scenario) {
      renderTrace(null, null);
      return;
    }
    renderTrace(shortestPath(scenario.start_nodes || [], targetId), targetId);
    const target = document.getElementById("trace-content");
    if (target) { target.scrollIntoView({block: "nearest"}); }
  }

  function renderSteps(container, label, steps) {
    append(container, "h3", "", label);
    if (!steps || !steps.length) {
      append(container, "p", "empty", "No steps.");
      return;
    }
    const list = append(container, "div", "steps");
    steps.forEach((step) => {
      const card = append(list, "div", "step");
      append(card, "header", "", "Step " + step.order +
        (step.generation === null || step.generation === undefined ? "" : ", generation " + step.generation) +
        (step.batch ? ", batch" : ""));
      if (step.depends_on && step.depends_on.length) {
        append(card, "p", "muted", "Depends on: " + step.depends_on.join(", "));
      }
      const actions = append(card, "ol");
      (step.actions || []).forEach((action) => append(actions, "li", "", action));
      (step.credentials || []).forEach((credential) => {
        append(card, "p", "mono", credential.label + " (" + credential.id + ")");
      });
      const evidence = append(card, "div");
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
      const notes = append(target, "ul");
      plan.notes.forEach((note) => append(notes, "li", "note", note));
    }
  }

  function renderFindingCard(target, finding) {
    const card = append(target, "article", "finding sev-" + finding.severity);
    const title = append(card, "h3");
    append(title, "span", "badge sev-" + finding.severity, finding.severity);
    title.appendChild(document.createTextNode(" " + finding.title));
    append(card, "p", "finding-rule mono", finding.rule + " " + finding.id +
      " - confidence " + finding.confidence);
    append(card, "p", "", finding.message);
    if (finding.scenario) { append(card, "p", "muted", "Scenario: " + finding.scenario); }
    if (finding.assumptions && finding.assumptions.length) {
      append(card, "p", "muted", "Assumptions: " + finding.assumptions.join(", "));
    }
    const evidence = append(card, "div");
    evidenceList(evidence, finding.evidence || []);
    if (finding.path && finding.path.length) {
      append(card, "p", "mono muted", finding.path.map(nodeLabel).join(" -> "));
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
    const findings = (report.findings || []).slice().sort((left, right) => {
      const order = severityOrder[left.severity] - severityOrder[right.severity];
      if (order !== 0) { return order; }
      if (left.rule !== right.rule) { return left.rule < right.rule ? -1 : 1; }
      return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
    });

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
    const scenarios = report.scenarios || [];
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
    const statuses = scenarios.map(scenarioCredentialStatuses);
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
        ids.length + " credential(s) are listed across " + scenarios.length + " scenarios; " +
        sharedSurvivors + " potentially survive revocation in more than one scenario; " +
        unique + " appear in only one. Widest listed coverage: " +
        (widestIndex >= 0 ? scenarios[widestIndex].selector : "none") +
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
      const cell = append(headRow, "th", "", nodeLabel(id));
      cell.scope = "col";
      cell.title = id;
    });
    const body = append(table, "tbody");
    scenarios.forEach((scenario, index) => {
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
  }

  function renderAssumptions() {
    const target = document.getElementById("assumptions-content");
    clear(target);
    const assumptions = report.assumptions || [];
    if (assumptions.length) {
      append(target, "h3", "", "Assumptions");
      const table = append(target, "table");
      append(table, "caption", "", "Assumptions attached to this report");
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
    }
    append(target, "h3", "", "Unknown inputs");
    const scenarios = report.scenarios || [];
    if (!scenarios.some((item) => item.unresolved_inputs.length)) {
      append(target, "p", "empty", "No unresolved inputs are recorded.");
    }
    scenarios.forEach((scenario) => {
      if (!scenario.unresolved_inputs.length) { return; }
      append(target, "h4", "", scenario.selector);
      const list = append(target, "ul");
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
    const table = append(target, "table");
    append(table, "caption", "", "Parse and analysis diagnostics");
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
    showEvidencePanel(item.label, item.kind + " - " + item.id, item.evidence);
    const target = document.getElementById("entity-details");
    const trace = element("button", "link-button", "Trace from the selected entrypoint");
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
      item.src + " -> " + item.dst + " - confidence " + item.confidence,
      item.evidence
    );
  }

  function renderGraph(scenario) {
    const container = document.getElementById("graph-canvas");
    const details = document.getElementById("entity-details");
    activeGraph = null;
    clear(details);
    if (!window.cytoscape) {
      clear(container);
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
    const elements = [];
    (report.graph.nodes || []).forEach((item) => {
      elements.push({
        group: "nodes",
        data: {
          id: item.id,
          label: item.label,
          kind: item.kind,
          colour: nodeColour[item.kind] || "#64748b",
          opacity: focus.size && !focus.has(item.id) ? 0.3 : 1
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
          label: item.kind
        }
      });
    });
    if (!elements.length) {
      clear(container);
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
            "background-color": "data(colour)",
            "color": "#eef6ff",
            "font-size": "10px",
            "font-weight": "600",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "wrap",
            "text-max-width": "105px",
            "width": "34px",
            "height": "34px",
            "opacity": "data(opacity)",
            "border-width": 1,
            "border-color": "#ffffff"
          }
        },
        {
          selector: "edge",
          style: {
            "width": 1.6,
            "line-color": "#60758c",
            "target-arrow-color": "#60758c",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "line-style": "data(lineStyle)",
            "label": "data(kind)",
            "font-size": "8px",
            "color": "#526071",
            "text-rotation": "autorotate"
          }
        },
        { selector: "node.dimmed", style: {"opacity": 0.12} },
        { selector: "edge.dimmed", style: {"opacity": 0.12, "text-opacity": 0} },
        { selector: "node.traced", style: {"border-width": 4, "border-color": "#0b6bcb"} },
        {
          selector: "edge.traced",
          style: {
            "width": 3.2,
            "line-color": "#0b6bcb",
            "target-arrow-color": "#0b6bcb",
            "color": "#0b6bcb"
          }
        }
      ],
      layout: {name: "dagre", rankDir: "LR", animate: false, fit: true, padding: 24}
    });
    activeGraph = cy;
    cy.on("tap", "node", (event) => showNode(event.target.data("id")));
    cy.on("tap", "edge", (event) => showEdge(event.target.data("id")));
  }

  document.getElementById("tool-line").textContent =
    report.tool.name + " " + report.tool.version + " - report schema " + report.schema;
  document.getElementById("repo-line").textContent =
    "Repository " + report.inputs.repo_slug;
  renderScope();
  renderFindings();
  renderAssumptions();
  renderDiagnostics();
  document.getElementById("matrix-shared").addEventListener("change", renderMatrix);
  renderScenarioPicker();
}).call(window);
"""


@cache
def _asset_texts() -> dict[str, str]:
    base = resources.files("nhi_blast.report.assets")
    manifest = json.loads(base.joinpath("MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "nhi-blast-assets/1":
        msg = "unsupported report asset manifest format"
        raise RuntimeError(msg)
    entries = {str(entry["name"]): entry for entry in manifest.get("assets", ())}
    if set(entries) != set(_ASSET_NAMES):
        msg = "report asset manifest does not pin the expected assets"
        raise RuntimeError(msg)
    texts: dict[str, str] = {}
    for name in _ASSET_NAMES:
        payload = base.joinpath("vendor", name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entries[name].get("sha256"):
            msg = f"report asset hash mismatch: {name}"
            raise RuntimeError(msg)
        texts[name] = payload.decode("utf-8")
    return texts


def _script_hash(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _embedded_json(report: Report) -> str:
    text = json.dumps(
        report_dict(report),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _inline_scripts(data: str, assets: dict[str, str]) -> str:
    for name in _ASSET_NAMES:
        if "</script" in assets[name]:
            msg = f"vendored script contains a closing script tag: {name}"
            raise RuntimeError(msg)
    blocks = [
        f"{_DATA_OPEN}{data}</script>",
        *(f"<script>{assets[name]}</script>" for name in _ASSET_NAMES),
        f"<script>{_APP_JS}</script>",
    ]
    return "\n".join(blocks)


def html_report(report: Report) -> str:
    """Render one deterministic, self-contained HTML document."""
    data = _embedded_json(report)
    assets = _asset_texts()
    scripts = _inline_scripts(data, assets)
    bodies = [data, *(assets[name] for name in _ASSET_NAMES), _APP_JS]
    hashes = " ".join(f"'sha256-{_script_hash(body)}'" for body in bodies)
    csp = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"script-src {hashes}; base-uri 'none'; form-action 'none'"
    )
    document = _TEMPLATE.replace("__CSP__", csp)
    document = document.replace("__SCRIPTS__", scripts)
    return document.rstrip() + "\n"


def write_html(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_report(report), encoding="utf-8", newline="\n")


__all__ = ["html_report", "write_html"]
