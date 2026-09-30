/* Shared helpers. All report text is inserted with textContent (never innerHTML) so RSS/LLM text can't inject markup. */
(function () {
  "use strict";

  const RR = (window.RR = {});

  // ---------- DOM ----------
  RR.el = function (tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else if (k === "href") { const u = RR.safeUrl(v); if (u) node.setAttribute("href", u); }
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  };
  RR.$ = (sel, root) => (root || document).querySelector(sel);
  RR.clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };
  RR.safeUrl = function (u) {
    if (!u) return null;
    const s = String(u).trim();
    if (/^https?:\/\//i.test(s)) return s;
    if (/^(\.\/|\/|[A-Za-z0-9_\-]+(\.html|\/))/.test(s) && !/^[a-z]+:/i.test(s)) return s; // same-site relative
    return null;
  };
  RR.extLink = (href, text) => RR.el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text);

  // ---------- formatting ----------
  const NA = "—";
  RR.isNum = (x) => typeof x === "number" && isFinite(x);
  RR.money = function (x, cur) {
    if (!RR.isNum(x)) return NA;
    const a = Math.abs(x), s = x < 0 ? "-" : "";
    const units = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
    for (const [d, u] of units) if (a >= d) return `${s}${(a / d).toFixed(2)}${u}${cur ? " " + cur : ""}`;
    return `${s}${a.toFixed(2)}${cur ? " " + cur : ""}`;
  };
  RR.moneyAxis = function (x) {
    if (!RR.isNum(x) || x === 0) return "0";
    const a = Math.abs(x), s = x < 0 ? "-" : "";
    for (const [d, u] of [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]]) if (a >= d) return `${s}${+(a / d).toFixed(1)}${u}`;
    return `${s}${+a.toFixed(1)}`;
  };
  RR.pct = (x, nd = 1, sign = false) => (!RR.isNum(x) ? NA : `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(nd)}%`);
  RR.mult = (x, nd = 1) => (!RR.isNum(x) ? NA : `${x.toFixed(nd)}×`);
  RR.num = (x, nd = 2) => (!RR.isNum(x) ? NA : x.toLocaleString(undefined, { minimumFractionDigits: nd, maximumFractionDigits: nd }));
  RR.date = (iso) => {
    if (!iso) return NA;
    const d = new Date(iso);
    return isNaN(d) ? String(iso).slice(0, 10) : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };
  RR.ago = (iso) => {
    const d = new Date(iso); if (isNaN(d)) return "";
    const s = (Date.now() - d.getTime()) / 1000;
    if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} d ago`;
  };
  RR.signClass = (x) => (!RR.isNum(x) ? "" : x >= 0 ? "up" : "down");
  RR.stanceClass = (s) => ({ Constructive: "pos", Neutral: "neu", Cautious: "neg" }[s] || "neu");
  RR.biasClass = (s) => ({ bullish: "pos", positive: "pos", neutral: "neu", bearish: "neg", negative: "neg" }[s] || "neu");

  // ---------- data ----------
  RR.fetchJSON = async function (url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText} (${url})`);
    return r.json();
  };
  RR.validId = (id) => typeof id === "string" && /^[A-Za-z0-9._\-]{3,60}$/.test(id) && !id.includes("..");

  // ---------- theme ----------
  const THEME_KEY = "rr-theme";
  function storedTheme() { try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; } }
  RR.applyTheme = function (t) {
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  };
  RR.currentTheme = () => {
    const t = document.documentElement.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  };
  RR.applyTheme(storedTheme());
  RR.onThemeChange = [];
  RR.toggleTheme = function () {
    const next = RR.currentTheme() === "dark" ? "light" : "dark";
    RR.applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* private mode */ }
    RR.onThemeChange.forEach((fn) => fn());
  };
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => RR.onThemeChange.forEach((fn) => fn()));
  document.addEventListener("click", (e) => { if (e.target.closest("[data-theme-toggle]")) RR.toggleTheme(); });

  // ---------- chart tokens (read live from CSS so both themes stay in sync) ----------
  RR.tokens = function () {
    const cs = getComputedStyle(document.documentElement);
    const v = (n) => cs.getPropertyValue(n).trim();
    return {
      ink: v("--ink"), ink2: v("--ink-2"), muted: v("--muted"), grid: v("--grid"), axis: v("--axis"), surface: v("--surface"),
      surface2: v("--surface-2"), up: v("--up"), down: v("--down"), accent: v("--accent"),
      series: ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"].map(v),
      font: v("--font"),
    };
  };
  RR.baseChart = function (t) {
    return {
      animationDuration: 400,
      textStyle: { fontFamily: t.font, color: t.ink2 },
      grid: { left: 56, right: 18, top: 28, bottom: 30, containLabel: false },
      tooltip: {
        trigger: "axis", backgroundColor: t.surface, borderColor: t.axis, borderWidth: 1, textStyle: { color: t.ink, fontSize: 12.5 },
        axisPointer: { type: "line", lineStyle: { color: t.axis }, crossStyle: { color: t.axis } }, confine: true,
      },
      legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 12, itemHeight: 4, textStyle: { color: t.ink2, fontSize: 12 } },
    };
  };
  RR.axisStyle = function (t, extra) {
    return Object.assign({
      axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 11.5 }, splitLine: { lineStyle: { color: t.grid } },
    }, extra || {});
  };
})();
