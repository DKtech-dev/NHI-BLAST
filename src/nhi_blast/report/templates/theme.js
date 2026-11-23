(function () {
  "use strict";
  var KEY = "nhb-theme";
  var CHOICES = ["system", "light", "dark"];
  var LABELS = {system: "System", light: "Light", dark: "Dark"};
  var CHROME = {light: "#fcfcfd", dark: "#0e1116"};
  var root = document.documentElement;
  var memory = new Map();
  var subscribers = [];
  var timer = 0;
  var toastTimer = 0;

  function sessionStore() {
    try { return window.sessionStorage; } catch (error) { return null; }
  }
  var safeStorage = {
    get: function (key) {
      if (memory.has(key)) { return memory.get(key); }
      try {
        var store = sessionStore();
        return store ? store.getItem(key) : null;
      } catch (error) {
        return null;
      }
    },
    set: function (key, value) {
      memory.set(key, value);
      try {
        var store = sessionStore();
        if (store) { store.setItem(key, value); }
      } catch (error) {
        // Storage is a convenience; the in-memory copy keeps the choice for this page view.
      }
    }
  };

  function query(text) {
    try { return window.matchMedia ? window.matchMedia(text) : null; } catch (error) { return null; }
  }
  var darkQuery = query("(prefers-color-scheme: dark)");
  var motionQuery = query("(prefers-reduced-motion: reduce)");

  var stored = safeStorage.get(KEY);
  var choice = CHOICES.indexOf(stored) >= 0 ? stored : "system";
  var MOTION_KEY = "nhb-motion";
  var motionStored = safeStorage.get(MOTION_KEY);
  var motionChoice = motionStored === "on" || motionStored === "off" ? motionStored : null;
  var motionOn = motionChoice ? motionChoice === "on" : !(motionQuery && motionQuery.matches);
  var motionSubscribers = [];

  function resolve() {
    if (choice === "light" || choice === "dark") { return choice; }
    return darkQuery && darkQuery.matches ? "dark" : "light";
  }

  function apply() {
    var theme = resolve();
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-theme-choice", choice);
    root.setAttribute("data-motion", motionOn ? "on" : "off");
    var chrome = document.querySelector('meta[name="theme-color"]');
    if (chrome) { chrome.setAttribute("content", CHROME[theme]); }
    subscribers.forEach(function (notify) { notify(theme, choice); });
  }

  function setChoice(next) {
    if (CHOICES.indexOf(next) < 0) { return; }
    var before = root.getAttribute("data-theme");
    choice = next;
    safeStorage.set(KEY, next);
    var fx = window.NHBEffects;
    var viaEffects = motionOn && fx && typeof fx.transitionTheme === "function";
    if (resolve() !== before && motionOn && !viaEffects) {
      root.classList.add("theme-switching");
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { root.classList.remove("theme-switching"); }, 260);
    }
    if (viaEffects) {
      fx.transitionTheme(apply, document.querySelector(".theme-switch"));
    } else {
      apply();
    }
  }

  function applyMotion(next) {
    motionOn = Boolean(next);
    root.setAttribute("data-motion", motionOn ? "on" : "off");
    var fx = window.NHBEffects;
    if (fx && typeof fx.setMotion === "function") { fx.setMotion(motionOn); }
    motionSubscribers.forEach(function (notify) { notify(motionOn); });
  }

  function setMotion(next) {
    motionChoice = next ? "on" : "off";
    safeStorage.set(MOTION_KEY, motionChoice);
    applyMotion(next);
  }

  function onSystemMotionChange() {
    if (motionChoice === null) { applyMotion(!(motionQuery && motionQuery.matches)); }
  }
  if (motionQuery) {
    if (typeof motionQuery.addEventListener === "function") {
      motionQuery.addEventListener("change", onSystemMotionChange);
    } else if (typeof motionQuery.addListener === "function") {
      motionQuery.addListener(onSystemMotionChange);
    }
  }

  function mountMotion(host) {
    if (!host || host.querySelector(".motion-switch")) { return; }
    var button = document.createElement("button");
    button.setAttribute("type", "button");
    button.setAttribute("role", "switch");
    button.className = "motion-switch";
    var track = document.createElement("span");
    track.className = "motion-track";
    track.setAttribute("aria-hidden", "true");
    var label = document.createElement("span");
    label.className = "motion-label";
    label.textContent = "Motion";
    var state = document.createElement("span");
    state.className = "motion-state";
    button.appendChild(track);
    button.appendChild(label);
    button.appendChild(state);
    function sync() {
      button.setAttribute("aria-checked", motionOn ? "true" : "false");
      state.textContent = motionOn ? "On" : "Off";
    }
    button.addEventListener("click", function () { setMotion(!motionOn); });
    motionSubscribers.push(sync);
    sync();
    host.appendChild(button);
  }

  function onSystemChange() {
    if (choice === "system") { apply(); }
  }
  if (darkQuery) {
    if (typeof darkQuery.addEventListener === "function") {
      darkQuery.addEventListener("change", onSystemChange);
    } else if (typeof darkQuery.addListener === "function") {
      darkQuery.addListener(onSystemChange);
    }
  }

  function mount(host) {
    if (!host || host.querySelector(".theme-switch")) { return; }
    var group = document.createElement("div");
    group.className = "theme-switch";
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-label", "Colour theme");
    var options = CHOICES.map(function (value) {
      var button = document.createElement("button");
      button.setAttribute("type", "button");
      button.setAttribute("role", "radio");
      button.setAttribute("data-theme-value", value);
      button.className = "theme-option";
      var icon = document.createElement("span");
      icon.className = "theme-icon theme-icon-" + value;
      icon.setAttribute("aria-hidden", "true");
      var label = document.createElement("span");
      label.className = "theme-label";
      label.textContent = LABELS[value];
      button.appendChild(icon);
      button.appendChild(label);
      group.appendChild(button);
      return button;
    });
    function sync() {
      options.forEach(function (button) {
        var selected = button.getAttribute("data-theme-value") === choice;
        button.setAttribute("aria-checked", selected ? "true" : "false");
        button.setAttribute("tabindex", selected ? "0" : "-1");
      });
    }
    group.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest(".theme-option") : null;
      if (button && group.contains(button)) { setChoice(button.getAttribute("data-theme-value")); }
    });
    group.addEventListener("keydown", function (event) {
      var current = event.target && event.target.closest ? event.target.closest(".theme-option") : null;
      var index = options.indexOf(current);
      if (index < 0) { return; }
      var target = -1;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") { target = (index + 1) % options.length; }
      else if (event.key === "ArrowLeft" || event.key === "ArrowUp") { target = (index + options.length - 1) % options.length; }
      else if (event.key === "Home") { target = 0; }
      else if (event.key === "End") { target = options.length - 1; }
      else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setChoice(current.getAttribute("data-theme-value"));
        return;
      }
      if (target < 0) { return; }
      event.preventDefault();
      setChoice(options[target].getAttribute("data-theme-value"));
      options[target].focus();
    });
    subscribers.push(sync);
    sync();
    host.appendChild(group);
  }

  function ensureToast() {
    var existing = document.getElementById("nhb-toast");
    if (existing) { return existing; }
    if (!document.body) { return null; }
    var el = document.createElement("div");
    el.id = "nhb-toast";
    el.className = "nhb-toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.setAttribute("aria-atomic", "true");
    document.body.appendChild(el);
    return el;
  }

  function showToast(message) {
    var el = ensureToast();
    if (!el) { return; }
    el.textContent = String(message || "");
    el.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      el.classList.remove("is-visible");
    }, 2200);
  }

  function fallbackCopy(text) {
    if (!document.body) { return false; }
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    area.style.pointerEvents = "none";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (error) { ok = false; }
    area.remove();
    return ok;
  }

  function copyText(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallbackCopy(text); });
    }
    return Promise.resolve(fallbackCopy(text));
  }

  function wireCompanionControls() {
    var host = document.getElementById("companion-theme-host");
    if (host) { mount(host); }
    document.addEventListener("click", function (event) {
      var target = event.target && event.target.closest ? event.target.closest("[data-copy-target], [data-copy-text], [data-action='print']") : null;
      if (!target) { return; }
      if (target.getAttribute("data-action") === "print") {
        window.print();
        return;
      }
      var text = target.getAttribute("data-copy-text");
      if (text === null) {
        var refId = target.getAttribute("data-copy-target");
        var refEl = refId ? document.getElementById(refId) : null;
        text = refEl ? refEl.textContent : "";
      }
      if (!text) { return; }
      var label = target.getAttribute("data-copy-label") || "Snippet";
      var original = target.getAttribute("data-copy-orig") || target.textContent;
      target.setAttribute("data-copy-orig", original);
      copyText(text).then(function (ok) {
        target.textContent = ok ? "Copied" : "Copy failed";
        showToast(ok ? label + " copied to clipboard" : "Unable to copy automatically");
        window.setTimeout(function () {
          target.textContent = original;
        }, 1800);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireCompanionControls);
  } else {
    wireCompanionControls();
  }

  apply();
  window.NHBTheme = Object.freeze({
    mount: mount,
    mountMotion: mountMotion,
    setChoice: setChoice,
    setMotion: setMotion,
    getMotion: function () { return motionOn; },
    subscribeMotion: function (notify) { motionSubscribers.push(notify); },
    getChoice: function () { return choice; },
    getTheme: resolve,
    toast: showToast,
    copy: copyText
  });
}).call(window);
