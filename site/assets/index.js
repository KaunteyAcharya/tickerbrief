(function () {
  "use strict";
  const { el, $, clear } = RR;
  let all = [];
  let stance = "";

  function sparkline(values, color) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "spark");
    svg.setAttribute("viewBox", "0 0 100 30");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    const v = (values || []).filter(RR.isNum);
    if (v.length < 2) return svg;
    const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
    const pts = v.map((y, i) => `${(i / (v.length - 1)) * 100},${28 - ((y - min) / span) * 26}`);
    const area = document.createElementNS(ns, "path");
    area.setAttribute("d", `M0,30 L${pts.join(" L")} L100,30 Z`);
    area.setAttribute("fill", color);
    area.setAttribute("opacity", "0.10");
    const line = document.createElementNS(ns, "polyline");
    line.setAttribute("points", pts.join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "1.6");
    line.setAttribute("vector-effect", "non-scaling-stroke");
    svg.append(area, line);
    return svg;
  }

  function card(r) {
    const t = RR.tokens();
    const first = (r.spark || [])[0], last = (r.spark || []).slice(-1)[0];
    const color = RR.isNum(first) && RR.isNum(last) && last < first ? t.down : t.up;
    const href = `report.html?id=${encodeURIComponent(r.id)}${r._base === "samples" ? "&src=samples" : ""}`;
    return el("a", { class: "card rcard", href },
      el("div", { class: "top" },
        el("div", {},
          el("div", { class: "tk" }, r.ticker, " ", r._base === "samples" ? el("span", { class: "badge-sample" }, "sample") : null),
          el("div", { class: "nm", title: r.name }, r.name || "")),
        el("div", { class: "px" },
          el("div", { class: "p num" }, `${RR.num(r.price)} ${r.currency || ""}`),
          el("div", { class: `small num ${RR.signClass(r.change_1d_pct)}` }, `${RR.pct(r.change_1d_pct, 2, true)} 1d`))),
      sparkline(r.spark, color),
      el("div", { class: "hl" }, r.headline || ""),
      el("div", { style: { display: "flex", gap: "6px", flexWrap: "wrap" } },
        el("span", { class: `chip ${RR.stanceClass(r.stance)}` }, r.stance || "n/a"),
        el("span", { class: `chip ${RR.biasClass(r.technical_bias)}` }, `Technicals: ${r.technical_bias || "n/a"}`),
        RR.isNum(r.score_avg) ? el("span", { class: "chip ghost" }, `Score ${r.score_avg}`) : null),
      el("div", { class: "foot" },
        el("span", {}, r.sector || ""),
        el("span", { title: r.generated_at }, `${RR.date(r.generated_at)} · ${RR.ago(r.generated_at)}`)));
  }

  function render() {
    const box = clear($("#reports"));
    const q = ($("#search").value || "").toLowerCase().trim();
    const items = all.filter((r) => (!stance || r.stance === stance) &&
      (!q || [r.ticker, r.name, r.sector, r.industry].some((x) => (x || "").toLowerCase().includes(q))));
    if (!all.length) {
      box.append(el("div", { class: "card empty", style: { gridColumn: "1 / -1" } },
        el("h3", {}, "No reports yet"), el("p", { style: { marginTop: "8px" } }, "Generate your first report above, or run the workflow from the n8n editor.")));
      return;
    }
    if (!items.length) { box.append(el("div", { class: "empty", style: { gridColumn: "1 / -1" } }, "No reports match your filters.")); return; }
    items.forEach((r) => box.append(card(r)));
  }

  async function load() {
    const box = clear($("#reports"));
    for (let i = 0; i < 3; i++) box.append(el("div", { class: "card pad" }, el("div", { class: "skeleton" }), el("div", { class: "skeleton" }), el("div", { class: "skeleton", style: { width: "60%" } })));
    const lists = await Promise.all(["reports", "samples"].map((base) =>
      RR.fetchJSON(`${base}/index.json`).then((d) => (d.reports || []).map((r) => Object.assign(r, { _base: base }))).catch(() => [])));
    all = lists.flat().filter((r) => RR.validId(r.id)).sort((a, b) => (b.generated_at || "").localeCompare(a.generated_at || ""));
    render();
  }

  // ---------- generate ----------
  const STAGES = ["Market data", "SEC filings", "News", "Analysis", "LLM drafting", "PDF + publish"];
  let timer = null;

  function setStatus(kind, ...nodes) {
    const s = clear($("#gen-status"));
    s.className = "gen-status show";
    if (kind === "busy") s.append(el("span", { class: "spinner", "aria-hidden": "true" }));
    s.append(...nodes);
  }

  async function generate(ev) {
    ev.preventDefault();
    const ticker = $("#ticker").value.trim().toUpperCase();
    const peers = $("#peers").value.split(",").map((p) => p.trim().toUpperCase()).filter(Boolean).slice(0, 8).join(",");
    if (!/^[A-Z0-9.\-^=&]{1,20}$/.test(ticker)) { setStatus("err", el("span", { class: "down" }, "Enter a valid ticker symbol.")); return; }
    const btn = $("#gen-btn");
    btn.disabled = true;
    const started = Date.now();
    const elapsed = el("b", { class: "num" }, "0s");
    const stages = el("span", { class: "steps" }, STAGES.map((s) => el("span", {}, s)));
    setStatus("busy", el("span", {}, `Running workflow for ${ticker} · `), elapsed, stages);
    timer = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000);
      elapsed.textContent = s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
      // rough guide only: data stages are quick, LLM drafting dominates
      const idx = s < 6 ? 0 : s < 10 ? 1 : s < 13 ? 2 : s < 18 ? 3 : 4;
      [...stages.children].forEach((c, i) => c.classList.toggle("on", i === idx));
    }, 500);
    try {
      const r = await fetch("api/generate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, peers, source: "site" }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok || body.ok === false) throw new Error(body.error || body.message || `Workflow returned HTTP ${r.status}`);
      [...stages.children].forEach((c) => c.classList.add("on"));
      setStatus("ok", el("span", { class: "up" }, "✓ Report ready. "), el("a", { href: `report.html?id=${encodeURIComponent(body.id)}` }, `Open ${ticker} report →`));
      await load();
      if (RR.validId(body.id)) setTimeout(() => { window.location.href = `report.html?id=${encodeURIComponent(body.id)}`; }, 900);
    } catch (e) {
      setStatus("err", el("span", { class: "down" }, `Could not generate the report: ${e.message}. `),
        el("span", { class: "muted" }, "Is the stack running (docker compose ps) and the workflow published in n8n?"));
    } finally {
      clearInterval(timer);
      btn.disabled = false;
    }
  }

  $("#gen-form").addEventListener("submit", generate);
  $("#search").addEventListener("input", render);
  $("#stance-filter").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    stance = b.dataset.v;
    [...$("#stance-filter").children].forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    render();
  });
  RR.onThemeChange.push(render);
  // the n8n form workflow redirects here with ?error=... when generation fails
  const err = new URLSearchParams(location.search).get("error");
  if (err) setStatus("err", el("span", { class: "down" }, `Report generation failed: ${err.slice(0, 300)}`));
  load();
})();
