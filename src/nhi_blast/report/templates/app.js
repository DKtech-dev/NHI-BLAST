(function () {
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
  try {
    if (window.NHBTheme && typeof window.NHBTheme.mount === "function") {
      window.NHBTheme.mount(document.getElementById("theme-switch-host"));
      window.NHBTheme.mountMotion(document.getElementById("motion-switch-host"));
    }
  } catch (error) {
    // The theme control is optional chrome; the report content must not depend on it.
  }
  const report = JSON.parse(document.getElementById("report-data").textContent);
  const nodes = new Map((report.graph.nodes || []).map((item) => [item.id, item]));
  const edges = new Map((report.graph.edges || []).map((item) => [item.id, item]));
  const adjacency = new Map();
  (report.graph.edges || []).forEach((edge) => {
    if (!adjacency.has(edge.src)) { adjacency.set(edge.src, []); }
    adjacency.get(edge.src).push(edge);
    const sc = edge.attrs && edge.attrs.session_credential;
    if (sc && nodes.has(sc) && sc !== edge.dst) { adjacency.get(edge.src).push(Object.assign({}, edge, { dst: sc })); }
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
  function motionEnabled() {
    return window.NHBTheme ? window.NHBTheme.getMotion() : !prefersReducedMotion();
  }

  const presenceAnimations = new Map();
  function clearPresence(item) {
    const running = presenceAnimations.get(item);
    if (running) { running.cancel(); presenceAnimations.delete(item); }
    item.style.opacity = "";
    item.style.transform = "";
  }
  function syncMotion(on) {
    if (motion && motion.MotionGlobalConfig) { motion.MotionGlobalConfig.skipAnimations = !on; }
    if (!on) { Array.from(presenceAnimations.keys()).forEach(clearPresence); }
  }
  syncMotion(motionEnabled());
  if (window.NHBTheme) { window.NHBTheme.subscribeMotion(syncMotion); }

  function animatePresence(item) {
    clearPresence(item);
    if (!motion || !motionEnabled()) { return; }
    item.style.opacity = "0";
    const control = motion.animate(item, {
      opacity: [0, 1],
      transform: ["translateY(6px)", "translateY(0px)"]
    }, {
      duration: 0.2,
      ease: [0.22, 1, 0.36, 1],
      onComplete: () => {
        presenceAnimations.delete(item);
        item.style.opacity = "";
        item.style.transform = "";
      }
    });
    presenceAnimations.set(item, control);
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

  function safeId(value) {
    return textOf(value).replace(/[^A-Za-z0-9_-]/g, "_");
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

  function fallbackCopy(text) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let done = false;
    try { done = document.execCommand("copy"); } catch (error) { done = false; }
    area.remove();
    return done;
  }

  function copyText(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text).then(() => true, () => fallbackCopy(text));
    }
    return Promise.resolve(fallbackCopy(text));
  }

  function copyButton(parent, text, label) {
    const button = append(parent, "button", "copy-button");
    button.setAttribute("type", "button");
    button.setAttribute("aria-label", label);
    const icon = svgNode(button, "svg", { "class": "icon", "aria-hidden": "true", focusable: "false" });
    const use = svgNode(icon, "use", { href: "#i-copy" });
    const word = append(button, "span", "", "Copy");
    const status = append(parent, "span", "sr-only");
    status.setAttribute("role", "status");
    let timer = 0;
    button.addEventListener("click", () => {
      copyText(text).then((done) => {
        word.textContent = done ? "Copied" : "Copy failed";
        use.setAttribute("href", done ? "#i-check" : "#i-info");
        status.textContent = done ? "Copied to the clipboard." : "The browser blocked copying. Select the text instead.";
        if (window.NHBTheme && typeof window.NHBTheme.toast === "function") {
          window.NHBTheme.toast(done ? label + " copied to clipboard" : "Unable to copy automatically");
        }
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          word.textContent = "Copy";
          use.setAttribute("href", "#i-copy");
          status.textContent = "";
        }, 1800);
      });
    });
    return button;
  }

  function renderSourceLine() {
    const target = document.getElementById("source-line");
    clear(target);
    const digest = textOf(report.inputs.digest);
    const files = (report.inputs.files || []).length;
    const verified = (report.data_files || []).map((item) => textOf(item.verified_on)).filter(Boolean).sort();
    const facts = [
      ["Repository", textOf(report.inputs.repo_slug), null],
      ["Inputs", plural(files, "file"), null],
      verified.length ? ["Data verified", verified[verified.length - 1], null] : null,
      ["Schema", textOf(report.schema), null],
      ["Snapshot", report.generated_at ? "generated " + report.generated_at : "no timestamp", null],
      ["Digest", digest.length > 12 ? digest.slice(0, 12) + "…" : digest, digest]
    ].filter(Boolean);
    facts.forEach((fact) => {
      const item = append(target, "li", "scan-fact");
      append(item, "span", "k", fact[0]);
      append(item, "span", "v", fact[1]);
      if (fact[2]) { copyButton(item, fact[2], "Copy inputs digest"); }
    });
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
    if (!motion || !motionEnabled() || window.NHBEffects) {
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
        note: "job end or token expiry",
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
          ? (scenarios.length > 1 ? "across all entrypoints" : "in this report")
          : "none recorded",
        data: false
      },
      {
        label: "Critical findings",
        code: "critical",
        value: findings.length ? critical : null,
        note: findings.length ? "of " + plural(findings.length, "finding") : "none recorded",
        data: false,
        tone: "is-critical"
      }
    ];
    metrics.forEach((metric) => {
      const card = append(target, "div", "stat" + (metric.data ? " is-data" : ""));
      const label = append(card, "span", "stat-label");
      if (metric.code && metric.code.length === 1) { append(label, "span", "code code-" + metric.code, metric.code); }
      append(label, "span", "", metric.label);
      const value = append(
        card, "strong", "stat-value" + (metric.data ? " is-data" : "") + (metric.tone ? " " + metric.tone : "")
      );
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
  }

  function renderFindingsLink() {
    const link = document.getElementById("all-findings");
    if (!link) { return; }
    link.hidden = !findings.length;
    link.textContent = findings.length === 1 ? "View the finding" : "All " + plural(findings.length, "finding");
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
    renderFindingsLink();
    renderHeroDiagram(scenario);
    renderSummary(scenario);
    renderScenario(index);
    renderMatrix();
    if (effectsReady) { refreshEffects(); }
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
    renderTimeline(target, scenario);
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
    if (target) {
      revealDisclosure(target);
      target.scrollIntoView({block: "nearest"});
    }
  }

  function renderProcess(container, entries) {
    const list = append(container, "ol", "steps cols-" + Math.min(entries.length, 4));
    entries.forEach((entry) => {
      const step = entry.step;
      const row = append(list, "li", "step");
      append(row, "span", "step-no", String(step.order).padStart(2, "0"));
      const link = svgNode(row, "svg", {
        "class": "step-link", viewBox: "0 0 100 100", preserveAspectRatio: "none",
        "aria-hidden": "true", focusable: "false"
      });
      svgNode(link, "path", { "class": "sl-h", "data-fx-draw": "", d: "M0 50 H100" });
      svgNode(link, "path", { "class": "sl-v", "data-fx-draw": "", d: "M50 0 V100" });
      const body = append(row, "div", "step-body");
      const head = append(body, "div", "step-head");
      append(head, "span", "step-title", "Step " + step.order);
      append(head, "span", "pill phase-pill", entry.phase);
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
    const entries = [];
    [["Containment", plan.containment], ["Rotation", plan.rotation], ["Verify", plan.verify]].forEach((phase) => {
      (phase[1] || []).forEach((step) => entries.push({ phase: phase[0], step: step }));
    });
    if (entries.length) {
      renderProcess(target, entries);
    } else {
      append(target, "p", "empty", "No steps.");
    }
    if (plan.notes && plan.notes.length) {
      append(target, "h3", "notes-title", "Plan notes");
      const notes = append(target, "ul", "notes-list");
      plan.notes.forEach((note) => append(notes, "li", "note", note));
    }
  }

  function findingCopyButton(parent, text, caption, ariaLabel, toastLabel) {
    const btn = append(parent, "button", "finding-copy-btn", caption);
    btn.type = "button";
    btn.setAttribute("aria-label", ariaLabel);
    let timer = 0;
    btn.addEventListener("click", () => {
      copyText(text).then((done) => {
        btn.textContent = done ? "Copied" : "Copy failed";
        if (window.NHBTheme && typeof window.NHBTheme.toast === "function") {
          window.NHBTheme.toast(done ? toastLabel + " copied to clipboard" : "Unable to copy automatically");
        }
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          btn.textContent = caption;
        }, 1800);
      });
    });
    return btn;
  }

  function renderFindingCard(target, finding) {
    const card = append(target, "article", "finding sev-" + finding.severity);
    const head = append(card, "div", "finding-head");
    append(head, "span", "pill sev-" + finding.severity, finding.severity);
    append(head, "h3", "", finding.title);
    const actions = append(head, "div", "finding-actions");
    const summaryText = "[" + textOf(finding.severity) + "] " + textOf(finding.rule) + " (" +
      textOf(finding.id) + "): " + textOf(finding.title) + " - " + textOf(finding.message);
    findingCopyButton(actions, textOf(finding.id), "Copy ID", "Copy ID " + textOf(finding.id), "Finding ID");
    findingCopyButton(actions, summaryText, "Copy summary", "Copy summary " + textOf(finding.id), "Finding summary");
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

  function isTypingElement(el) {
    if (!el) { return false; }
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(el.isContentEditable);
  }

  function renderFindings() {
    const target = document.getElementById("findings-content");
    const search = document.getElementById("findings-search") || document.getElementById("finding-search");
    const severity = document.getElementById("finding-severity");
    const pillGroup = document.getElementById("finding-severity-pills");
    const pills = pillGroup ? Array.from(pillGroup.querySelectorAll(".sev-pill")) : [];
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

    function syncPills(value) {
      pills.forEach((pill) => {
        const active = (pill.getAttribute("data-severity") || "") === value;
        pill.classList.toggle("is-active", active);
        pill.setAttribute("aria-pressed", active ? "true" : "false");
      });
    }

    function resetFilters(focusSearch) {
      search.value = "";
      severity.value = "";
      scenarioSelect.value = "";
      syncPills("");
      apply();
      if (focusSearch) { search.focus(); }
    }

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
      if (!matches.length && !findings.length && completenessGaps().length) {
        const note = append(target, "p", "empty empty-scope");
        note.appendChild(document.createTextNode("No findings in the analysed scope - see "));
        const link = append(note, "a", "", "Analysis completeness");
        link.setAttribute("href", "#completeness");
      } else if (!matches.length) {
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
      count.textContent = "Showing " + matches.length + " of " + plural(findings.length, "finding");
      if (effectsReady) {
        count.classList.remove("is-bump");
        void count.offsetWidth;
        count.classList.add("is-bump");
        refreshEffects();
      }
    }

    search.addEventListener("input", apply);
    severity.addEventListener("change", () => {
      syncPills(severity.value);
      apply();
    });
    pills.forEach((pill) => {
      pill.addEventListener("click", () => {
        const next = pill.getAttribute("data-severity") || "";
        severity.value = next;
        syncPills(next);
        apply();
      });
    });
    scenarioSelect.addEventListener("change", apply);
    if (clearButton) {
      clearButton.addEventListener("click", () => resetFilters(true));
    }
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey) {
        if (isTypingElement(document.activeElement)) { return; }
        event.preventDefault();
        search.focus();
        search.scrollIntoView({ block: "nearest" });
        return;
      }
      if (event.key === "Escape") {
        const navBar = document.getElementById("nav-bar");
        if (navBar && navBar.classList.contains("is-open")) { return; }
        if (document.activeElement === search) {
          if (search.value) {
            search.value = "";
            apply();
          } else {
            search.blur();
          }
          return;
        }
        if (isTypingElement(document.activeElement)) { return; }
        if (search.value || severity.value || scenarioSelect.value) {
          resetFilters(false);
        }
        if (graphSelection) {
          clearGraphSelection();
          clearGraphTrace();
        }
      }
    });
    syncPills("");
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
        row.setAttribute("id", "assumption-" + safeId(assumption.id));
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
    const seenCodes = new Set();
    diagnostics.forEach((item) => {
      const row = append(body, "tr");
      if (!seenCodes.has(item.code)) {
        seenCodes.add(item.code);
        row.setAttribute("id", "diagnostic-" + safeId(item.code));
      }
      append(row, "td", "", item.level);
      append(row, "td", "mono", item.code);
      append(row, "td", "wrap", item.message);
      append(row, "td", "mono wrap", textOf(item.file) +
        (item.line === undefined || item.line === null ? "" : ":" + item.line));
    });
  }

  const FAMILY_LABELS = __FAMILY_LABELS__;
  const COMPLETENESS_GROUPS = [
    { key: "partially_analysed", label: "Partially analysed", collapsed: false },
    { key: "not_provided", label: "Not provided", collapsed: false },
    { key: "not_supported", label: "Not supported", collapsed: false },
    { key: "analysed", label: "Analysed", collapsed: true },
    { key: "not_applicable", label: "Not applicable", collapsed: true }
  ];
  const GAP_STATUSES = ["partially_analysed", "not_provided", "not_supported"];

  function completenessItems() {
    const block = report.completeness;
    return block && Array.isArray(block.items) ? block.items : [];
  }

  function completenessGaps() {
    return completenessItems().filter((item) => GAP_STATUSES.indexOf(item.status) !== -1);
  }

  function statusBadge(parent, status, label) {
    const badge = append(parent, "span", "cmp-status cmp-status-" + safeId(status), label);
    return badge;
  }

  function completenessLinks(parent, title, values, prefix) {
    if (!values || !values.length) { return; }
    const row = append(parent, "div", "cmp-fact");
    append(row, "dt", "", title);
    const cell = append(row, "dd", "cmp-links");
    values.forEach((value) => {
      const targetId = prefix + safeId(value);
      if (document.getElementById(targetId)) {
        const link = append(cell, "a", "", value);
        link.setAttribute("href", "#" + targetId);
      } else {
        append(cell, "span", "", value);
      }
    });
  }

  function renderCompletenessItem(list, item) {
    const row = append(list, "li", "cmp-item");
    const head = append(row, "div", "cmp-item-head");
    const label = FAMILY_LABELS[item.family] || textOf(item.family);
    append(head, "h4", "cmp-family", label);
    const group = COMPLETENESS_GROUPS.find((entry) => entry.key === item.status);
    statusBadge(head, item.status, group ? group.label : textOf(item.status).replace(/_/g, " "));
    if (item.explanation) { append(row, "p", "cmp-explanation", item.explanation); }
    const facts = append(row, "dl", "cmp-facts");
    const sources = item.sources || [];
    if (sources.length) {
      const fact = append(facts, "div", "cmp-fact");
      append(fact, "dt", "", "Sources");
      const cell = append(fact, "dd");
      const listing = append(cell, "ul", "cmp-sources");
      const addSource = (target, source) => {
        const entry = append(target, "li");
        append(entry, "span", "mono", textOf(source.path));
        append(entry, "span", "cmp-hash", "sha256 " + textOf(source.sha256).slice(0, 12));
      };
      sources.slice(0, 3).forEach((source) => addSource(listing, source));
      if (sources.length > 3) {
        const more = append(cell, "details");
        append(more, "summary", "", plural(sources.length - 3, "more source"));
        const rest = append(more, "ul", "cmp-sources");
        sources.slice(3).forEach((source) => addSource(rest, source));
      }
    }
    completenessLinks(facts, "Diagnostics", item.diagnostics, "diagnostic-");
    completenessLinks(facts, "Assumptions", item.assumptions, "assumption-");
    if (!facts.childNodes.length) { facts.remove(); }
  }

  function renderCompleteness() {
    const items = completenessItems();
    const section = document.getElementById("completeness");
    const link = document.getElementById("completeness-link");
    if (!items.length) { return; }
    section.hidden = false;
    link.hidden = false;
    const target = document.getElementById("completeness-content");
    clear(target);
    const counts = append(target, "ul", "cmp-counts");
    counts.setAttribute("aria-label", "Items by status");
    const known = new Set(COMPLETENESS_GROUPS.map((entry) => entry.key));
    const buckets = new Map(COMPLETENESS_GROUPS.map((entry) => [entry.key, []]));
    const other = [];
    items.forEach((item) => {
      if (known.has(item.status)) { buckets.get(item.status).push(item); } else { other.push(item); }
    });
    COMPLETENESS_GROUPS.forEach((entry) => {
      const entryRow = append(counts, "li");
      statusBadge(entryRow, entry.key, entry.label);
      append(entryRow, "span", "cmp-count-num", String(buckets.get(entry.key).length));
    });
    append(
      target,
      "p",
      "cmp-note",
      "Not provided and not supported mean the report says nothing about that family, not that " +
        "nothing is there. Partially analysed results are a lower bound. A status lists which " +
        "inputs were read; it is not a score and not a verdict."
    );
    const groups = COMPLETENESS_GROUPS.map((entry) => ({
      label: entry.label, collapsed: entry.collapsed, items: buckets.get(entry.key)
    }));
    if (other.length) { groups.push({ label: "Other status", collapsed: false, items: other }); }
    groups.forEach((groupInfo) => {
      if (!groupInfo.items.length) { return; }
      const group = append(target, "div", "cmp-group");
      append(group, "h3", "", groupInfo.label + " (" + groupInfo.items.length + ")");
      let host = group;
      if (groupInfo.collapsed) {
        host = append(group, "details");
        append(host, "summary", "", "Show " + plural(groupInfo.items.length, "item"));
      }
      const list = append(host, "ul", "cmp-list");
      groupInfo.items.forEach((item) => renderCompletenessItem(list, item));
    });
  }

  function revealDisclosure(item) {
    let node = item;
    while (node) {
      if (node.tagName === "DETAILS") { node.open = true; }
      node = node.parentElement;
    }
    if (item && item.classList && item.classList.contains("section-disclosure")) {
      const own = item.querySelector("details.disclosure");
      if (own) { own.open = true; }
    }
  }

  function revealHash() {
    const id = window.location.hash.slice(1);
    const target = id ? document.getElementById(id) : null;
    if (target) {
      revealDisclosure(target);
      target.scrollIntoView();
    }
  }

  const svgNamespace = document.querySelector(".brand-mark").namespaceURI;

  function svgNode(parent, tag, attributes, text) {
    const node = document.createElementNS(svgNamespace, tag);
    Object.keys(attributes || {}).forEach((name) => node.setAttribute(name, String(attributes[name])));
    if (text !== undefined && text !== null) { node.textContent = text; }
    if (parent) { parent.appendChild(node); }
    return node;
  }

  function inputTileCounts() {
    const files = (report.inputs && report.inputs.files) || [];
    const count = (kinds) => files.filter((file) => kinds.indexOf(file.kind) !== -1).length;
    return [
      { label: "Workflows", lines: ["Workflows"], value: count(["workflow"]) },
      { label: "Composite actions", lines: ["Composite", "actions"], value: count(["composite_action"]) },
      { label: "Terraform", lines: ["Terraform", "files"], value: count(["tf_json", "tf_hcl"]) },
      { label: "IAM policy files", lines: ["IAM policy", "files"], value: count(["iam_json"]) }
    ].filter((tile) => tile.value > 0);
  }

  const narrowDiagram = window.matchMedia ? window.matchMedia("(max-width: 560px)") : null;

  function drawTile(svg, layout, x, top, width, height, lines, value, valueClass, code) {
    const group = svgNode(svg, "g", { "class": "hd-tile-group", "data-fx-tilt": "" });
    svgNode(group, "rect", { "class": "hd-tile-shadow", x: x, y: top + 4, width: width, height: height, rx: 12 });
    svgNode(group, "rect", { "class": "hd-tile", x: x, y: top, width: width, height: height, rx: 12 });
    const shown = value === null ? "—" : String(value);
    if (layout === "row") {
      svgNode(group, "text", { "class": "hd-value " + valueClass, x: x + 16, y: top + height / 2 + 11 }, shown);
      lines.forEach((line, row) => {
        svgNode(group, "text", {
          "class": "hd-label", x: x + 62,
          y: top + height / 2 + (lines.length > 1 ? (row ? 15 : -3) : 5)
        }, line);
      });
    } else {
      svgNode(group, "text", { "class": "hd-value " + valueClass, x: x + 14, y: top + 38 }, shown);
      lines.forEach((line, row) => {
        svgNode(group, "text", { "class": "hd-label", x: x + 14, y: top + 58 + row * 16 }, line);
      });
    }
    if (code) {
      svgNode(group, "text", { "class": "hd-code", x: x + width - 12, y: top + 20, "text-anchor": "end" }, code);
    }
  }

  function renderHeroDiagram(scenario) {
    const host = document.getElementById("hero-diagram-host");
    const caption = document.getElementById("hero-diagram-text");
    if (!host || !caption) { return; }
    clear(host);
    const tiles = inputTileCounts();
    const partition = scenario ? scenario.partition : null;
    const outputs = [
      { code: "R", lines: ["Ends with", "entrypoint"], value: partition ? partition.R.length : null },
      { code: "E", lines: ["Expires on", "its own"], value: partition ? partition.E.length : null },
      { code: "Z", lines: ["Potentially", "survives"], value: partition ? partition.Z.length : null }
    ];
    const narrow = Boolean(narrowDiagram && narrowDiagram.matches);
    const defs = (svg) => {
      const holder = svgNode(svg, "defs");
      const fill = svgNode(holder, "linearGradient", { id: "hd-core-fill", x1: "0", y1: "0", x2: "1", y2: "1" });
      svgNode(fill, "stop", { offset: "0", style: "stop-color: var(--accent)" });
      svgNode(fill, "stop", { offset: "1", style: "stop-color: var(--accent-hover)" });
    };
    const core = (svg, cx, cy, radius) => {
      svgNode(svg, "circle", { cx: cx, cy: cy, r: radius, fill: "url(#hd-core-fill)" });
      svgNode(svg, "text", { "class": "hd-core-text", x: cx, y: cy + 2, "text-anchor": "middle" }, "NHI-Blast");
      svgNode(svg, "text", { "class": "hd-core-sub", x: cx, y: cy + 18, "text-anchor": "middle" }, "offline scan");
    };
    const line = (svg, d) => svgNode(svg, "path", { "class": "hd-line", "data-fx-draw": "", d: d });
    if (!narrow) {
      const cx = 230;
      const cy = 200;
      const radius = 42;
      const place = (count, index) => (400 * (index + 1)) / (count + 1);
      const svg = svgNode(host, "svg", {
        "class": "hero-svg", viewBox: "0 0 460 400", role: "img",
        "aria-labelledby": "hero-diagram-text", focusable: "false"
      });
      defs(svg);
      [64, 92, 124].forEach((ring) => svgNode(svg, "circle", { "class": "hd-orbit", cx: cx, cy: cy, r: ring }));
      tiles.forEach((item, index) => {
        const y = place(tiles.length, index);
        line(svg, "M156 " + y + " C 176 " + y + ", 172 " + cy + ", " + (cx - radius) + " " + cy);
      });
      outputs.forEach((item, index) => {
        const y = place(outputs.length, index);
        line(svg, "M" + (cx + radius) + " " + cy + " C 284 " + cy + ", 288 " + y + ", 304 " + y);
      });
      core(svg, cx, cy, radius);
      tiles.forEach((item, index) => {
        drawTile(svg, "row", 8, place(tiles.length, index) - 32, 148, 64, item.lines, item.value, "", "");
      });
      outputs.forEach((item, index) => {
        drawTile(svg, "row", 304, place(outputs.length, index) - 32, 148, 64, item.lines, item.value, "hd-value-" + item.code, item.code);
      });
    } else {
      const rows = Math.max(1, Math.ceil(tiles.length / 2));
      const inputsBottom = rows * 64 + (rows - 1) * 16;
      const cy = inputsBottom + 64;
      const outputsTop = cy + 80;
      const svg = svgNode(host, "svg", {
        "class": "hero-svg", viewBox: "0 0 320 " + (outputsTop + 84), role: "img",
        "aria-labelledby": "hero-diagram-text", focusable: "false"
      });
      defs(svg);
      [64, 92].forEach((ring) => svgNode(svg, "circle", { "class": "hd-orbit", cx: 160, cy: cy, r: ring }));
      tiles.forEach((item, index) => {
        const column = tiles.length === 1 ? 0.5 : index % 2;
        const x = tiles.length === 1 ? 84 : column * 168;
        const top = Math.floor(index / 2) * 80;
        line(svg, "M" + (x + 76) + " " + (top + 64) + " C " + (x + 76) + " " + (top + 100) + ", 160 " + (cy - 78) + ", 160 " + (cy - 40));
      });
      outputs.forEach((item, index) => {
        const x = index * 112;
        line(svg, "M160 " + (cy + 40) + " C 160 " + (cy + 62) + ", " + (x + 48) + " " + (outputsTop - 30) + ", " + (x + 48) + " " + outputsTop);
      });
      core(svg, 160, cy, 40);
      tiles.forEach((item, index) => {
        const x = tiles.length === 1 ? 84 : (index % 2) * 168;
        drawTile(svg, "row", x, Math.floor(index / 2) * 80, 152, 64, item.lines, item.value, "", "");
      });
      outputs.forEach((item, index) => {
        drawTile(svg, "column", index * 112, outputsTop, 96, 84, item.lines, item.value, "hd-value-" + item.code, item.code);
      });
    }
    const read = tiles.length
      ? tiles.map((item) => item.value + " " + item.label.toLowerCase()).join(", ")
      : "no input files";
    caption.textContent = "Diagram. Inputs read: " + read + ". " + (scenario
      ? "For entrypoint " + scenario.selector + ": " + partition.R.length + " end with the entrypoint (R), " +
        partition.E.length + " expire on their own (E), " + partition.Z.length +
        " potentially survive revocation (Z)."
      : "No entrypoint scenario is available, so no R, E or Z counts are shown.");
  }

  if (narrowDiagram && narrowDiagram.addEventListener) {
    narrowDiagram.addEventListener("change", () => {
      renderHeroDiagram(scenarios[currentScenarioIndex] || null);
      if (effectsReady) { refreshEffects(); }
    });
  }

  function ttlText(seconds) {
    const n = Number(seconds);
    if (!Number.isFinite(n) || n <= 0) { return textOf(seconds) + " s"; }
    if (n % 86400 === 0) { return (n / 86400) + (n === 86400 ? " day" : " days"); }
    if (n % 3600 === 0) { return (n / 3600) + " h"; }
    if (n % 60 === 0) { return (n / 60) + " min"; }
    return n + " s";
  }

  function renderTimeline(container, scenario) {
    const partition = scenario.partition;
    const nodeLabelOf = (id) => (nodes.get(id) ? nodes.get(id).label : textOf(id));
    const attrOf = (id, name) => (nodes.get(id) && nodes.get(id).attrs ? textOf(nodes.get(id).attrs[name]) : "");
    const wrap = append(container, "div", "timeline");
    wrap.setAttribute("data-fx-reveal", "");
    const head = append(wrap, "div", "tl-head");
    append(head, "h3", "", "Survival timeline");
    append(
      head,
      "p",
      "tl-caption",
      "Marks follow the order of events after revocation. Distances between marks are not to scale. " +
        "R and E marks show job end or token expiry. Z bands indicate potential survival after revocation; " +
        "each row states its recorded survival window, not a shared expiry time."
    );
    const jobX = 16;
    const ttls = partition.E.map((entry) => Number(entry.ttl_seconds)).filter((value) => value > 0);
    const longest = ttls.length ? Math.max.apply(null, ttls) : 0;
    const xTtl = (seconds) => (longest > 0
      ? 24 + 60 * (Math.log(1 + seconds / 60) / Math.log(1 + longest / 60))
      : 60);
    const axis = append(wrap, "div", "tl-axis");
    axis.setAttribute("aria-hidden", "true");
    const tick = (text, left, extra) => {
      const item = append(axis, "span", "tl-tick" + (extra ? " " + extra : ""), text);
      item.style.left = left + "%";
    };
    tick("Revoked now", 0, "is-first");
    tick("Job ends", jobX, "");
    Array.from(new Set(ttls)).sort((left, right) => left - right).forEach((seconds) => {
      tick(ttlText(seconds), xTtl(seconds), "");
    });
    tick("After revocation", 100, "is-last");
    const detail = element("p", "tl-detail", "Hover or focus a row for its details. The tables below hold the same rows.");
    detail.setAttribute("role", "status");
    const group = (code, title, entries, build) => {
      if (!entries.length) { return; }
      const section = append(wrap, "div", "tl-group");
      const heading = append(section, "div", "tl-group-title");
      append(heading, "span", "code code-" + code, code);
      append(heading, "span", "", title + " (" + entries.length + ")");
      const list = append(section, "ul", "tl-list");
      list.style.listStyle = "none";
      list.style.margin = "0";
      list.style.padding = "0";
      entries.slice(0, 8).forEach((entry) => {
        const row = append(list, "li", "tl-row");
        const summary = build(row, entry);
        row.setAttribute("tabindex", "0");
        row.setAttribute("aria-label", summary);
        const show = () => {
          detail.textContent = summary;
          row.classList.add("is-active");
        };
        const hide = () => row.classList.remove("is-active");
        row.addEventListener("mouseenter", show);
        row.addEventListener("focus", show);
        row.addEventListener("mouseleave", hide);
        row.addEventListener("blur", hide);
      });
      if (entries.length > 8) {
        append(section, "p", "tl-more", "+ " + (entries.length - 8) + " more in the table below");
      }
    };
    const track = (row, name) => {
      append(row, "span", "tl-name", name).title = name;
      const lane = append(row, "div", "tl-track");
      const job = append(lane, "span", "tl-job");
      job.style.left = jobX + "%";
      return lane;
    };
    group("R", "Ends with the entrypoint", partition.R, (row, id) => {
      const lane = track(row, nodeLabelOf(id));
      const mark = append(lane, "span", "tl-mark");
      mark.style.left = jobX + "%";
      return nodeLabelOf(id) + ". Ends with the entrypoint, when the job ends. " +
        [attrOf(id, "credential_kind"), attrOf(id, "lifetime")].filter(Boolean).join(", ");
    });
    group("E", "Expires on its own", partition.E, (row, entry) => {
      const lane = track(row, nodeLabelOf(entry.credential));
      const x = xTtl(Number(entry.ttl_seconds));
      const bar = append(lane, "span", "tl-bar tl-bar-e");
      bar.style.width = x + "%";
      const label = append(lane, "span", "tl-ttl", "up to " + ttlText(entry.ttl_seconds));
      label.style.left = x + "%";
      return nodeLabelOf(entry.credential) + ". Expires on its own, up to " + ttlText(entry.ttl_seconds) + ". " +
        attrOf(entry.credential, "credential_kind");
    });
    group("Z", "Potentially survives revocation", partition.Z, (row, entry) => {
      const lane = track(row, nodeLabelOf(entry.credential));
      const windowText = entry.survival_window || "Survival window not recorded";
      append(row.querySelector(".tl-name"), "span", "tl-window", windowText);
      const bounded = entry.lifetime === "persistent_rotating";
      append(lane, "span", "tl-bar tl-bar-z" + (bounded ? " is-bounded" : "")).style.width = bounded ? "84%" : "100%";
      if (!bounded) {
        const arrow = svgNode(lane, "svg", { "class": "tl-arrow", "aria-hidden": "true", focusable: "false" });
        svgNode(arrow, "use", { href: "#i-arrow-right", fill: "currentColor" });
      }
      return nodeLabelOf(entry.credential) + ". Potentially survives entrypoint revocation if the path was exercised. " +
        [windowText, entry.lifetime, "criticality " + entry.criticality].filter(Boolean).join(", ");
    });
    wrap.appendChild(detail);
  }

  function bindTagline() {
    const text = document.getElementById("tagline-text");
    if (!text) { return; }
    const words = text.textContent.trim().split(/\s+/);
    clear(text);
    const spans = words.map((word, index) => {
      const span = append(text, "span", "tl-w", word);
      if (index < words.length - 1) { text.appendChild(document.createTextNode(" ")); }
      return span;
    });
    const syncClass = () => {
      text.classList.toggle("js-words", document.documentElement.getAttribute("data-motion") === "on");
    };
    syncClass();
    new MutationObserver(syncClass).observe(document.documentElement, { attributes: true, attributeFilter: ["data-motion"] });
    if (!("IntersectionObserver" in window)) {
      spans.forEach((span) => span.classList.add("is-on"));
      return;
    }
    const observer = new IntersectionObserver((records) => {
      let order = 0;
      records
        .filter((record) => {
          const top = record.rootBounds ? record.rootBounds.top : 0;
          return record.isIntersecting || record.boundingClientRect.bottom < top;
        })
        .sort((left, right) => spans.indexOf(left.target) - spans.indexOf(right.target))
        .forEach((record) => {
          record.target.style.setProperty("--wd", Math.min(order * 40, 360) + "ms");
          record.target.classList.add("is-on");
          observer.unobserve(record.target);
          order += 1;
        });
    }, { rootMargin: "0px 0px -30% 0px", threshold: 0 });
    spans.forEach((span) => observer.observe(span));
  }

  let effectsReady = false;

  function tagAll(selector, name, value, stagger) {
    document.querySelectorAll(selector).forEach((item, index) => {
      if (!item.hasAttribute(name)) { item.setAttribute(name, value); }
      if (stagger && !item.hasAttribute("data-fx-delay")) {
        item.setAttribute("data-fx-delay", String(Math.min((index % 6) * 70, 420)));
      }
    });
  }

  function decorate() {
    tagAll("details", "data-fx-disclosure", "");
    const readable = ".guide-card, .stat, .outcome, .notes-list li, .evidence-guide, .class-list li";
    tagAll(readable, "data-fx-readable", "", true);
    tagAll(readable, "data-fx-reveal", "", true);
    tagAll(".hero-figure, .guide-card, .outcome, .finding, .cmp-list, .tl-detail", "data-fx-spotlight", "");
    tagAll(".button.primary", "data-fx-magnetic", "");
  }

  function refreshEffects() {
    decorate();
    const fx = window.NHBEffects;
    if (fx && typeof fx.refresh === "function") {
      try { fx.refresh(); } catch (error) { /* the effects layer is decoration only */ }
    }
  }

  function startEffects() {
    decorate();
    const fx = window.NHBEffects;
    if (fx && typeof fx.init === "function") {
      try {
        fx.init(document.documentElement, { motion: window.NHBTheme ? window.NHBTheme.getMotion() : null });
        effectsReady = true;
      } catch (error) { /* the effects layer is decoration only */ }
    }
  }

  function renderFooter() {
    document.getElementById("footer-schema").textContent = "schema " + report.schema;
    document.getElementById("footer-digest").textContent = textOf(report.inputs.digest);
    const list = document.getElementById("footer-data");
    clear(list);
    const files = report.data_files || [];
    if (!files.length) { append(list, "li", "", "No data files recorded."); }
    files.forEach((item) => {
      const row = append(list, "li");
      append(row, "span", "", item.name);
      append(row, "span", "muted", " · verified " + item.verified_on);
    });
    const copyHost = document.getElementById("footer-copy-host");
    if (copyHost) { clear(copyHost); copyButton(copyHost, textOf(report.inputs.digest), "Copy inputs digest from the footer"); }
    document.getElementById("footer-completeness").hidden = !completenessItems().length;
    document.getElementById("footer-print").addEventListener("click", () => window.print());
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
    const incoming = (report.graph.edges || []).filter((edge) => edge.dst === id || (edge.attrs && edge.attrs.session_credential === id));
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
      Boolean(animate) && motionEnabled()
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


  function renderGraphTable(scenario) {
    var panel = document.getElementById("graph-table-panel");
    var toggle = document.getElementById("graph-table-toggle");
    if (!panel || !toggle) return;
    if (!toggle.dataset.wired) {
      toggle.dataset.wired = "1";
      toggle.addEventListener("click", function () {
        var open = panel.hasAttribute("hidden");
        if (open) {
          panel.removeAttribute("hidden");
          toggle.setAttribute("aria-expanded", "true");
          toggle.textContent = "Hide table";
        } else {
          panel.setAttribute("hidden", "");
          toggle.setAttribute("aria-expanded", "false");
          toggle.textContent = "Table view";
        }
      });
    }
    panel.textContent = "";
    var graphNodes = (report.graph && report.graph.nodes) ? report.graph.nodes : [];
    var graphEdges = (report.graph && report.graph.edges) ? report.graph.edges : [];
    var nodeMap = Object.create(null);
    graphNodes.forEach(function (n) { nodeMap[n.id] = n; });
    var cRank = { declared: 0, derived: 1, assumed: 2, unknown: 3 };
    function deriveNodeConfidence(n) {
      var ev = n && n.evidence ? n.evidence : [];
      var w = "", wr = -1;
      for (var i = 0; i < ev.length; i += 1) {
        var c = ev[i] && ev[i].cls ? String(ev[i].cls).toLowerCase() : "";
        var r = c ? (c in cRank ? cRank[c] : 99) : -1;
        if (r > wr) { wr = r; w = c; }
      }
      return w || "-";
    }

    function makeTable(heading, headers, rows) {
      var h = document.createElement("h3");
      h.textContent = heading;
      panel.appendChild(h);
      var table = document.createElement("table");
      var thead = document.createElement("thead");
      var trH = document.createElement("tr");
      headers.forEach(function (label) {
        var th = document.createElement("th");
        th.scope = "col";
        th.textContent = label;
        trH.appendChild(th);
      });
      thead.appendChild(trH);
      table.appendChild(thead);
      var tbody = document.createElement("tbody");
      rows.forEach(function (cols) {
        var tr = document.createElement("tr");
        cols.forEach(function (val) {
          var td = document.createElement("td");
          td.textContent = String(val == null ? "" : val);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      panel.appendChild(table);
    }

    makeTable(
      "Nodes (" + graphNodes.length + ")",
      ["Kind", "Label", "Identifier", "Confidence"],
      graphNodes.map(function (n) { return [n.kind, n.label || n.id, n.id, deriveNodeConfidence(n)]; })
    );
    makeTable(
      "Edges (" + graphEdges.length + ")",
      ["From", "Relation", "To", "Confidence", "Lifetime"],
      graphEdges.map(function (e) {
        var s = nodeMap[e.src] ? (nodeMap[e.src].label || e.src) : e.src;
        var d = nodeMap[e.dst] ? (nodeMap[e.dst].label || e.dst) : e.dst;
        return [s, e.kind, d, e.confidence || "", e.lifetime || ""];
      })
    );
  }

  function renderContainmentSim(scenario) {
    var host = document.getElementById("containment-sim");
    if (!host) return;
    host.textContent = "";
    if (!scenario || !scenario.partition) return;
    var p = scenario.partition;
    var rCount = (p.R || []).length;
    var eItems = p.E || [];
    var zItems = p.Z || [];
    function resolveEntryRole(item) {
      var cid = item && item.credential ? String(item.credential) : "";
      var cn = cid ? nodes.get(cid) : null;
      var a = cn && cn.attrs ? cn.attrs : null;
      if (a && a.role_name) { var rn = String(a.role_name); return { key: rn, label: rn }; }
      if (a && a.role) {
        var rid = String(a.role);
        var rNode = nodes.get(rid);
        return { key: rid, label: rNode && rNode.label ? String(rNode.label) : rid };
      }
      var lbl = cn && cn.label ? String(cn.label) : cid;
      return { key: lbl, label: lbl };
    }

    var roles = [];
    var seenRoles = Object.create(null);
    eItems.forEach(function (item) {
      var resolved = resolveEntryRole(item);
      if (resolved.key && !seenRoles[resolved.key]) {
        seenRoles[resolved.key] = true;
        roles.push(resolved);
      }
    });
    if (!roles.length && !zItems.length) return;

    var head = document.createElement("div");
    head.className = "containment-sim-head";
    var title = document.createElement("h3");
    title.textContent = "Interactive containment preview";
    var badge = document.createElement("span");
    badge.className = "containment-preview-badge";
    badge.id = "containment-preview-badge";
    badge.setAttribute("role", "status");
    badge.setAttribute("aria-live", "polite");
    head.appendChild(title);
    head.appendChild(badge);
    host.appendChild(head);

    var list = document.createElement("div");
    list.className = "containment-sim-list";
    var state = { roles: Object.create(null), creds: Object.create(null) };

    function updatePreview() {
      var remE = eItems.filter(function (item) {
        var resolved = resolveEntryRole(item);
        return !state.roles[resolved.key];
      }).length;
      var remZ = zItems.filter(function (item) {
        var cid = item.credential || "";
        return !state.creds[cid];
      }).length;
      badge.textContent = "Preview R=" + rCount + " / E=" + remE + " / Z=" + remZ;
    }

    roles.forEach(function (roleEntry) {
      var label = document.createElement("label");
      label.className = "containment-sim-item";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.setAttribute("data-sim-kind", "revoke-role");
      cb.setAttribute("data-sim-target", roleEntry.key);
      cb.addEventListener("change", function () {
        state.roles[roleEntry.key] = cb.checked;
        updatePreview();
      });
      var span = document.createElement("span");
      span.textContent = "Revoke OIDC trust / sessions for " + roleEntry.label;
      label.appendChild(cb);
      label.appendChild(span);
      list.appendChild(label);
    });

    zItems.forEach(function (item) {
      var cid = item.credential || "";
      if (!cid) return;
      var label = document.createElement("label");
      label.className = "containment-sim-item";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.setAttribute("data-sim-kind", "rotate-secret");
      cb.setAttribute("data-sim-target", cid);
      cb.addEventListener("change", function () {
        state.creds[cid] = cb.checked;
        updatePreview();
      });
      var span = document.createElement("span");
      span.textContent = "Rotate persistent credential " + cid;
      label.appendChild(cb);
      label.appendChild(span);
      list.appendChild(label);
    });

    host.appendChild(list);

    var cmdText = "nhi-blast whatif report.json --auto-plan --format json --format md --format html";
    var cmdBox = document.createElement("div");
    cmdBox.className = "containment-sim-cmd";
    var code = document.createElement("code");
    code.id = "containment-sim-cli";
    code.textContent = cmdText;
    var copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "button quiet";
    copyBtn.textContent = "Copy CLI";
    copyBtn.addEventListener("click", function () {
      copyText(cmdText).then(function (ok) {
        copyBtn.textContent = ok ? "Copied" : "Copy failed";
        if (window.NHBTheme && typeof window.NHBTheme.toast === "function") {
          window.NHBTheme.toast(ok ? "CLI command copied to clipboard" : "Unable to copy automatically");
        }
        setTimeout(function () { copyBtn.textContent = "Copy CLI"; }, 1800);
      });
    });
    cmdBox.appendChild(code);
    cmdBox.appendChild(copyBtn);
    host.appendChild(cmdBox);

    var note = document.createElement("p");
    note.className = "containment-sim-note";
    note.textContent = "Preview only — run the CLI what-if command above for exact stepwise custody and residual path evaluation.";
    host.appendChild(note);
    updatePreview();
  }

  function renderGraph(scenario) {
    renderGraphTable(scenario);
    renderContainmentSim(scenario);
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
    const track = nav.querySelector(".toc-track") || nav;
    const bar = document.querySelector(".nav-bar");
    const toggle = document.getElementById("nav-toggle");
    const currentLabel = document.getElementById("nav-current");
    const phone = window.matchMedia ? window.matchMedia("(max-width: 760px)") : null;
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
      const left = link.offsetLeft + 12;
      const width = Math.max(link.offsetWidth - 24, 8);
      indicator.style.transform = "translateX(" + left + "px) scaleX(" + width + ")";
      indicator.classList.add("is-active");
    };
    const updateFades = () => {
      const overflowing = track.scrollWidth > track.clientWidth + 2;
      track.style.setProperty("--fade-l", overflowing && track.scrollLeft > 2 ? "24px" : "0px");
      track.style.setProperty(
        "--fade-r",
        overflowing && track.scrollLeft + track.clientWidth < track.scrollWidth - 2 ? "24px" : "0px"
      );
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
      if (currentLabel) { currentLabel.textContent = active.link.textContent; }
      placeIndicator(active.link);
      if (track.scrollWidth > track.clientWidth + 2 && !(phone && phone.matches)) {
        const left = active.link.offsetLeft - (track.clientWidth - active.link.offsetWidth) / 2;
        track.scrollTo({ left: Math.max(left, 0), behavior: motionEnabled() ? "smooth" : "auto" });
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
      updateFades();
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", () => { schedule(); reposition(); });
    track.addEventListener("scroll", updateFades, { passive: true });
    if (document.fonts && document.fonts.ready) { document.fonts.ready.then(reposition); }

    const setOpen = (open) => {
      if (!bar || !toggle) { return; }
      bar.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.documentElement.classList.toggle("nav-locked", open);
      if (open) {
        const first = nav.querySelector("a:not([hidden])");
        if (first) { first.focus(); }
      }
    };
    if (toggle) {
      toggle.addEventListener("click", () => setOpen(!bar.classList.contains("is-open")));
      nav.addEventListener("click", (event) => {
        if (event.target && event.target.closest && event.target.closest("a")) { setOpen(false); }
      });
      document.addEventListener("keydown", (event) => {
        if (!bar.classList.contains("is-open")) { return; }
        if (event.key === "Escape") {
          setOpen(false);
          toggle.focus();
          return;
        }
        if (event.key !== "Tab") { return; }
        // The cycle is explicit: browsers differ on whether links are Tab stops.
        const stops = [toggle].concat(Array.from(nav.querySelectorAll("a:not([hidden])")));
        const at = stops.indexOf(document.activeElement);
        const step = event.shiftKey ? -1 : 1;
        const next = stops[(at + step + stops.length) % stops.length];
        event.preventDefault();
        next.focus();
      });
      if (phone && phone.addEventListener) {
        phone.addEventListener("change", () => { if (!phone.matches) { setOpen(false); } });
      }
    }
    updateFades();
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
  renderCompleteness();
  renderFooter();
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
  });
  window.addEventListener("afterprint", () => {
    printOpened.forEach((item) => { item.open = false; });
    printOpened.length = 0;
  });
  document.getElementById("print-button").addEventListener("click", () => window.print());
  document.addEventListener("click", (event) => {
    const link = event.target && event.target.closest ? event.target.closest('a[href^="#"]') : null;
    if (!link || link.getAttribute("href").length < 2) { return; }
    const target = document.getElementById(link.getAttribute("href").slice(1));
    if (target) { revealDisclosure(target); }
  });
  window.addEventListener("hashchange", revealHash);
  if (window.location.hash.length > 1) { revealHash(); }
  bootComplete = true;
  window.clearTimeout(bootFallback);
  bindTagline();
  window.requestAnimationFrame(() => {
    document.documentElement.classList.remove("booting");
    startEffects();
  });
}).call(window);
