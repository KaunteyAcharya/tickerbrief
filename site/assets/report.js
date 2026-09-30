(function () {
  "use strict";
  const { el, $, clear } = RR;
  const params = new URLSearchParams(location.search);
  const id = params.get("id");
  const preferred = params.get("src") === "samples" ? "samples" : "reports";

  const charts = []; // {node, build}
  let instances = [];

  // ------------------------------------------------------------------ bootstrap
  async function main() {
    const app = $("#app");
    if (!RR.validId(id)) return fail(app, "Missing or invalid report id.");
    let report = null, base = preferred;
    for (const b of [preferred, preferred === "reports" ? "samples" : "reports"]) {
      try { report = await RR.fetchJSON(`${b}/${id}/report.json`); base = b; break; } catch (e) { /* try next */ }
    }
    if (!report) return fail(app, `Report "${id}" was not found.`);
    render(app, report, base);
  }

  function fail(app, msg) {
    clear(app).append(el("div", { class: "wrap", style: { paddingTop: "30px" } },
      el("div", { class: "card error-box" }, el("h2", {}, "Report unavailable"), el("p", { class: "muted", style: { marginTop: "8px" } }, msg),
        el("a", { href: "index.html" }, "← Back to the library"))));
  }

  // ------------------------------------------------------------------ small builders
  const card = (title, right, ...body) => el("div", { class: "card pad" },
    title || right ? el("div", { class: "card-title" }, title ? el("h3", {}, title) : el("span"), right || null) : null, ...body);
  const chartBox = (cls, build, label) => {
    const node = el("div", { class: `chart ${cls || ""}`, role: "img", "aria-label": label || "chart" });
    charts.push({ node, build });
    return node;
  };
  const kv = (pairs) => el("div", { class: "kv" }, pairs.flatMap(([k, v]) => [el("div", {}, k), el("div", {}, v)]));
  const section = (sid, title, sub, ...body) => el("section", { class: "section", id: sid },
    el("div", { class: "section-head" }, el("h2", {}, title), sub ? el("span", { class: "muted small" }, sub) : null), ...body);
  const bullets = (items) => el("ul", { class: "clean" }, (items || []).map((x) => el("li", {}, x)));

  // ------------------------------------------------------------------ render
  function render(app, R, base) {
    const a = R.analysis, n = R.narrative, m = a.meta, pr = a.price, f = a.fundamentals, t = a.technicals;
    const cur = m.currency || "";
    document.title = `${m.ticker} · ${m.name} — Research Report`;
    if (R.pdf) { const b = $("#pdf-btn"); b.style.display = ""; b.setAttribute("href", `${base}/${R.id}/report.pdf`); }

    const up = RR.isNum(pr.change_1d_pct) && pr.change_1d_pct >= 0;
    const header = el("div", { class: "rhead" }, el("div", { class: "wrap" },
      el("div", { class: "row" },
        el("div", {},
          el("div", { class: "eyebrow" }, `Equity research · ${RR.date(R.generated_at)}`, base === "samples" ? " · sample report" : ""),
          el("h1", {}, m.name),
          el("div", { class: "sub" }, [m.ticker, m.exchange, m.sector, m.industry].filter(Boolean).join(" · "))),
        el("div", {},
          el("div", { class: "price num" }, `${RR.num(pr.last)} `, el("span", { style: { fontSize: "16px", fontWeight: 500 } }, cur)),
          el("div", { class: `chg num ${up ? "up" : "down"}`, style: { textAlign: "right" } },
            `${RR.isNum(pr.change_1d) ? (pr.change_1d >= 0 ? "+" : "") + pr.change_1d.toFixed(2) : ""} (${RR.pct(pr.change_1d_pct, 2, true)}) · ${RR.date(pr.last_date)}`))),
      el("div", { class: "chips" },
        el("span", { class: `chip ${RR.stanceClass(n.summary.stance)}` }, `Stance: ${n.summary.stance}`),
        el("span", { class: "chip dark" }, `Confidence: ${n.summary.confidence}`),
        el("span", { class: "chip dark" }, `Technicals: ${t.bias} (${Math.round(t.score)}/100)`),
        el("span", { class: "chip dark" }, `News: ${a.news.overall}`),
        R.meta && R.meta.model ? el("span", { class: "chip dark" }, `LLM: ${R.meta.model}`) : null)));

    const navItems = [["overview", "Overview"], ["price", "Price & technicals"], ["fundamentals", "Fundamentals"],
      ["peers", "Peers"], ["news", "News"], ["filings", "Filings"], ["method", "Method"]];
    const nav = el("nav", { class: "subnav", "aria-label": "Report sections" }, el("div", { class: "wrap" },
      el("span", { class: "tk" }, m.ticker), navItems.map(([h, l]) => el("a", { href: `#${h}`, "data-sec": h }, l))));

    const body = el("main", { class: "wrap" },
      overview(R, a, n, cur), priceSection(a, n), fundamentalsSection(a, n, cur), peersSection(a, n, cur),
      newsSection(a, n), filingsSection(a, n), methodSection(R, a, n, base));

    clear(app).append(header, nav, body);
    initCharts();
    wireNav(nav);
  }

  // ------------------------------------------------------------------ overview
  function overview(R, a, n, cur) {
    const f = a.fundamentals, pr = a.price;
    const kpis = el("div", { class: "card kpis" }, [
      ["Market cap", RR.money(f.valuation.market_cap), cur],
      ["Forward P/E", RR.mult(f.valuation.pe_forward), `Trailing ${RR.mult(f.valuation.pe_trailing)}`],
      ["EV / EBITDA", RR.mult(f.valuation.ev_to_ebitda), `P/S ${RR.mult(f.valuation.price_to_sales)}`],
      ["Operating margin", RR.pct(f.profitability.operating_margin), `Net ${RR.pct(f.profitability.net_margin)}`],
      ["Revenue growth", RR.pct(f.growth.revenue_growth_yoy), "year over year"],
      ["1-year return", RR.pct(pr.returns["1y"], 1, true), `Max drawdown ${RR.pct(pr.max_drawdown_1y)}`],
    ].map(([l, v, d]) => el("div", { class: "kpi" }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "d" }, d))));

    const sc = card("Scorecard", el("span", { class: "muted small" }, "heuristic · 0–100"),
      ...a.scorecard.map((s) => el("div", { class: "sc-row", title: s.basis },
        el("span", { class: "lbl" }, s.name),
        el("span", { class: "sc-track" }, el("span", { class: "sc-fill", style: { width: `${s.score}%` } })),
        el("span", { class: "val" }, String(Math.round(s.score))))),
      el("div", { class: "caption" }, "Rule-based scores from valuation vs peers, margins, growth, trend, balance sheet and headline tone. Hover a row for its basis."));

    return section("overview", "Overview", `Prices as of ${RR.date(pr.last_date)}`,
      el("div", { class: "grid g-2-1" },
        el("div", { class: "card pad" },
          el("div", { class: "headline" }, n.summary.headline),
          el("p", { class: "lead" }, n.summary.executive_summary),
          el("div", { class: "grid g2", style: { marginTop: "14px" } },
            el("div", { class: "bull" }, el("h3", { style: { marginBottom: "8px" } }, "Bull case"), bullets(n.summary.bull_case)),
            el("div", { class: "bear" }, el("h3", { style: { marginBottom: "8px" } }, "Bear case"), bullets(n.summary.bear_case)))),
        el("div", { class: "grid" }, sc,
          card("What to watch", null, bullets(n.summary.watch_items)))),
      el("div", { style: { marginTop: "16px" } }, kpis),
      el("div", { class: "grid g3", style: { marginTop: "16px" } },
        card("52-week range", null, rangeBar(pr.low_52w, pr.high_52w, pr.last, null, a.meta.currency),
          el("div", { class: "caption" }, `${RR.pct(pr.pct_from_high, 1, true)} from the high · ${RR.pct(pr.pct_from_low, 1, true)} from the low`)),
        analystCard(a),
        card("Returns", null, chartBox("short", returnsChart(pr), "Price returns over 1 month to 1 year"))));
  }

  function rangeBar(lo, hi, last, target, cur) {
    if (!RR.isNum(lo) || !RR.isNum(hi) || hi <= lo) return el("p", { class: "muted" }, "Not available.");
    const vals = [lo, hi, last, target].filter(RR.isNum);
    const min = Math.min(...vals), max = Math.max(...vals), span = max - min;
    const pos = (v) => `${((v - min) / span) * 100}%`;
    return el("div", { class: "range" },
      el("div", { class: "bar" },
        el("div", { class: "fill", style: { left: pos(lo), width: `${((hi - lo) / span) * 100}%` } }),
        RR.isNum(target) ? el("div", { class: "tgt", style: { left: pos(target) }, title: `Mean target ${RR.num(target)}` }) : null,
        el("div", { class: `mark ${(last - min) / span < 0.12 ? "edge-l" : (last - min) / span > 0.88 ? "edge-r" : ""}`, style: { left: pos(last) } }, el("span", {}, RR.num(last)))),
      el("div", { class: "ends num" }, el("span", {}, `Low ${RR.num(lo)}`), el("span", {}, `High ${RR.num(hi)} ${cur || ""}`)));
  }

  function analystCard(a) {
    const an = a.fundamentals.analyst, pr = a.price, rec = a.recommendations;
    const kids = [];
    if (RR.isNum(an.target_low) && RR.isNum(an.target_high)) {
      kids.push(rangeBar(an.target_low, an.target_high, pr.last, an.target_mean, a.meta.currency));
      kids.push(el("div", { class: "legend-inline" },
        el("span", {}, el("i", { style: { background: "var(--ink)" } }), "Last price"),
        el("span", {}, el("i", { style: { background: "var(--s2)" } }), `Mean target ${RR.num(an.target_mean)} (${RR.pct(an.upside_to_mean, 1, true)})`)));
    }
    kids.push(el("p", { class: "small", style: { marginTop: "10px" } },
      `${RR.isNum(an.analysts) ? an.analysts : "No"} analysts · consensus `, el("b", {}, (an.recommendation || "n/a").replace(/_/g, " "))));
    if (rec && Object.values(rec).some(RR.isNum)) kids.push(chartBox("", recChart(rec), "Analyst recommendation distribution"));
    const node = card("Analyst targets", null, ...kids);
    node.querySelectorAll(".chart").forEach((c) => (c.style.height = "150px"));
    return node;
  }

  // ------------------------------------------------------------------ price & technicals
  function priceSection(a, n) {
    const t = a.technicals;
    const rangeSeg = el("div", { class: "seg", role: "group", "aria-label": "Chart range" },
      ["3M", "6M", "1Y"].map((r) => el("button", { type: "button", "aria-pressed": String(r === "1Y"), "data-r": r }, r)));
    rangeSeg.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      [...rangeSeg.children].forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      const days = { "3M": 63, "6M": 126, "1Y": 260 }[b.dataset.r];
      const len = a.series.dates.length;
      const startValue = a.series.dates[Math.max(0, len - days)];
      instances.filter((c) => c.group === "px").forEach((c) => c.dispatchAction({ type: "dataZoom", startValue, endValue: a.series.dates[len - 1] }));
    });
    const signals = el("div", {}, t.signals.map((s) => el("div", { class: "signal" },
      el("span", { class: `dot ${s.signal}`, title: s.signal }),
      el("div", {}, el("b", {}, `${s.name} · ${s.signal}`), el("span", { class: "note" }, s.note)))));
    const crosses = (t.crossovers || []).length
      ? el("p", { class: "small muted", style: { marginTop: "10px" } }, "Recent 50/200 crossovers: ",
        t.crossovers.map((c) => `${c.type} cross ${RR.date(c.date)}`).join(" · "))
      : null;
    return section("price", "Price & technicals", null,
      card("Price, moving averages & volume", rangeSeg, chartBox("tall", priceChart(a), "Candlestick price chart with moving averages and volume"),
        el("div", { class: "caption" }, "Daily candles with 20/50/200-day SMAs and Bollinger bands (20, 2σ). Scroll or drag to zoom; RSI and MACD below stay in sync.")),
      el("div", { class: "grid g2", style: { marginTop: "16px" } },
        card("RSI (14)", null, chartBox("short", rsiChart(a), "Relative strength index")),
        card("MACD (12, 26, 9)", null, chartBox("short", macdChart(a), "MACD line, signal and histogram"))),
      el("div", { class: "grid g2", style: { marginTop: "16px" } },
        card("Trend & momentum", null, el("p", {}, n.technical.trend_and_momentum), el("h3", { style: { margin: "14px 0 6px" } }, "Key levels"),
          el("p", {}, n.technical.key_levels),
          kv([["60-day support", RR.num(t.support_60d)], ["60-day resistance", RR.num(t.resistance_60d)], ["SMA 50 / 200", `${RR.num(t.sma50)} / ${RR.num(t.sma200)}`],
            ["ATR (14)", `${RR.num(t.atr14)} (${RR.pct(t.atr_pct)})`], ["1y volatility", RR.pct(a.price.volatility_1y)]])),
        card(`Signals · score ${Math.round(t.score)}/100`, el("span", { class: `chip ${RR.biasClass(t.bias)}` }, t.bias), signals, crosses)));
  }

  function priceChart(a) {
    const fn = () => {
      const T = RR.tokens(), s = a.series;
      const ohlc = s.dates.map((_, i) => [s.open[i] ?? s.close[i], s.close[i], s.low[i] ?? s.close[i], s.high[i] ?? s.close[i]]);
      const band = s.bb_upper.map((u, i) => (RR.isNum(u) && RR.isNum(s.bb_lower[i]) ? u - s.bb_lower[i] : null));
      const volColors = s.close.map((c, i) => (i && c < s.close[i - 1] ? T.down : T.up));
      const o = RR.baseChart(T);
      return Object.assign(o, {
        legend: Object.assign(o.legend, { data: ["Price", "SMA 20", "SMA 50", "SMA 200", "Bollinger"] }),
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        tooltip: Object.assign(o.tooltip, {
          formatter: (ps) => {
            const i = ps[0].dataIndex, row = (k, v) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${k}</span><b>${v}</b></div>`;
            return `<div style="min-width:170px"><b>${RR.date(s.dates[i])}</b>` + row("Open", RR.num(s.open[i])) + row("High", RR.num(s.high[i])) +
              row("Low", RR.num(s.low[i])) + row("Close", RR.num(s.close[i])) + row("Volume", RR.money(s.volume[i])) +
              row("SMA 20", RR.num(s.sma20[i])) + row("SMA 50", RR.num(s.sma50[i])) + row("SMA 200", RR.num(s.sma200[i])) + "</div>";
          },
        }),
        grid: [{ left: 60, right: 20, top: 34, height: "60%" }, { left: 60, right: 20, top: "76%", height: "14%" }],
        xAxis: [0, 1].map((gi) => RR.axisStyle(T, { type: "category", data: s.dates, gridIndex: gi, boundaryGap: true,
          axisLabel: { show: gi === 1, color: T.muted, fontSize: 11.5, formatter: (v) => RR.date(v).replace(/,? \d{4}$/, "") }, splitLine: { show: false } })),
        yAxis: [RR.axisStyle(T, { scale: true, gridIndex: 0, splitNumber: 5 }),
          RR.axisStyle(T, { gridIndex: 1, splitNumber: 2, axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => RR.moneyAxis(v) } })],
        dataZoom: [{ type: "inside", xAxisIndex: [0, 1], startValue: s.dates[0] }],
        series: [
          { name: "Bollinger", type: "line", data: s.bb_lower, stack: "bb", symbol: "none", lineStyle: { width: 0 }, silent: true, tooltip: { show: false } },
          { name: "Bollinger", type: "line", data: band, stack: "bb", symbol: "none", lineStyle: { width: 0 }, itemStyle: { color: T.axis }, areaStyle: { color: T.grid, opacity: 0.7 }, silent: true },
          { name: "Price", type: "candlestick", data: ohlc, barMaxWidth: 8,
            itemStyle: { color: T.up, color0: T.down, borderColor: T.up, borderColor0: T.down } },
          { name: "SMA 20", type: "line", data: s.sma20, symbol: "none", lineStyle: { width: 1.2, color: T.series[3] }, itemStyle: { color: T.series[3] } },
          { name: "SMA 50", type: "line", data: s.sma50, symbol: "none", lineStyle: { width: 1.6, color: T.series[1] }, itemStyle: { color: T.series[1] } },
          { name: "SMA 200", type: "line", data: s.sma200, symbol: "none", lineStyle: { width: 1.6, color: T.series[6] }, itemStyle: { color: T.series[6] } },
          { name: "Volume", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: s.volume.map((v, i) => ({ value: v, itemStyle: { color: volColors[i], opacity: 0.75 } })) },
        ],
      });
    };
    fn.group = "px";
    return fn;
  }

  function rsiChart(a) {
    const fn = () => {
      const T = RR.tokens(), s = a.series, o = RR.baseChart(T);
      return Object.assign(o, {
        legend: { show: false }, grid: { left: 40, right: 16, top: 12, bottom: 26 },
        xAxis: RR.axisStyle(T, { type: "category", data: s.dates, splitLine: { show: false }, axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => RR.date(v).replace(/,? \d{4}$/, "") } }),
        yAxis: RR.axisStyle(T, { min: 0, max: 100, interval: 10, axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => ([30, 50, 70].includes(v) ? v : "") } }),
        dataZoom: [{ type: "inside" }],
        series: [{ name: "RSI", type: "line", data: s.rsi, symbol: "none", lineStyle: { width: 1.6, color: T.series[0] }, itemStyle: { color: T.series[0] },
          markArea: { silent: true, data: [[{ yAxis: 70, itemStyle: { color: T.down, opacity: 0.08 } }, { yAxis: 100 }], [{ yAxis: 0, itemStyle: { color: T.up, opacity: 0.1 } }, { yAxis: 30 }]] } }],
      });
    };
    fn.group = "px";
    return fn;
  }

  function macdChart(a) {
    const fn = () => {
      const T = RR.tokens(), s = a.series, o = RR.baseChart(T);
      return Object.assign(o, {
        legend: Object.assign(o.legend, { data: ["MACD", "Signal"], right: 0, left: "auto" }), grid: { left: 48, right: 16, top: 22, bottom: 26 },
        xAxis: RR.axisStyle(T, { type: "category", data: s.dates, splitLine: { show: false }, axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => RR.date(v).replace(/,? \d{4}$/, "") } }),
        yAxis: RR.axisStyle(T, { scale: true, splitNumber: 3 }),
        dataZoom: [{ type: "inside" }],
        series: [
          { name: "Histogram", type: "bar", data: s.macd_hist.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? T.up : T.down, opacity: 0.7 } })) },
          { name: "MACD", type: "line", data: s.macd, symbol: "none", lineStyle: { width: 1.5, color: T.series[0] }, itemStyle: { color: T.series[0] } },
          { name: "Signal", type: "line", data: s.macd_signal, symbol: "none", lineStyle: { width: 1.5, color: T.series[1] }, itemStyle: { color: T.series[1] } },
        ],
      });
    };
    fn.group = "px";
    return fn;
  }

  function returnsChart(pr) {
    return () => {
      const T = RR.tokens(), keys = ["1m", "3m", "6m", "ytd", "1y"], o = RR.baseChart(T);
      const vals = keys.map((k) => pr.returns[k]);
      return Object.assign(o, {
        legend: { show: false }, grid: { left: 44, right: 10, top: 20, bottom: 24 },
        tooltip: Object.assign(o.tooltip, { trigger: "item", formatter: (p) => `${p.name}: <b>${RR.pct(p.value, 1, true)}</b>` }),
        xAxis: RR.axisStyle(T, { type: "category", data: keys.map((k) => k.toUpperCase()), splitLine: { show: false } }),
        yAxis: RR.axisStyle(T, { axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => `${Math.round(v * 100)}%` }, splitNumber: 3 }),
        series: [{ type: "bar", barMaxWidth: 26, data: vals.map((v) => ({ value: v, itemStyle: { color: (v || 0) >= 0 ? T.up : T.down, borderRadius: (v || 0) >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] } })),
          label: { show: true, position: "top", color: T.ink2, fontSize: 11, formatter: (p) => RR.pct(p.value, 0, true) } }],
      });
    };
  }

  function recChart(rec) {
    return () => {
      const T = RR.tokens(), o = RR.baseChart(T);
      const keys = [["strongBuy", "Strong buy", "#1c5cab"], ["buy", "Buy", "#86b6ef"], ["hold", "Hold", T.axis], ["sell", "Sell", "#f0a3a3"], ["strongSell", "Strong sell", "#b42323"]];
      return Object.assign(o, {
        legend: { show: false }, grid: { left: 30, right: 8, top: 16, bottom: 22 },
        tooltip: Object.assign(o.tooltip, { trigger: "item", formatter: (p) => `${p.name}: <b>${p.value}</b>` }),
        xAxis: RR.axisStyle(T, { type: "category", data: keys.map((k) => k[1]), splitLine: { show: false }, axisLabel: { color: T.muted, fontSize: 10.5 } }),
        yAxis: RR.axisStyle(T, { minInterval: 1, splitNumber: 2 }),
        series: [{ type: "bar", barMaxWidth: 24, data: keys.map(([k, , c]) => ({ value: rec[k] || 0, itemStyle: { color: c, borderRadius: [4, 4, 0, 0] } })),
          label: { show: true, position: "top", fontSize: 11, color: T.ink2 } }],
      });
    };
  }

  // ------------------------------------------------------------------ fundamentals
  function fundamentalsSection(a, n, cur) {
    const f = a.fundamentals, fin = a.financials.annual, q = a.financials.quarterly;
    const years = fin.years || [];
    const row = (label, arr, fmt) => el("tr", {}, el("td", {}, label), (arr || []).map((v) => el("td", {}, fmt(v))));
    const finTable = years.length ? el("div", { class: "table-scroll" }, el("table", { class: "data" },
      el("thead", {}, el("tr", {}, el("th", {}, "Fiscal year"), years.map((y) => el("th", {}, y)))),
      el("tbody", {},
        row("Revenue", fin.revenue, (v) => RR.money(v)), row("Revenue growth", fin.revenue_growth, (v) => RR.pct(v, 1, true)),
        row("Gross margin", fin.gross_margin, (v) => RR.pct(v)), row("Operating margin", fin.operating_margin, (v) => RR.pct(v)),
        row("Net income", fin.net_income, (v) => RR.money(v)), row("Net margin", fin.net_margin, (v) => RR.pct(v)),
        row("Free cash flow", fin.fcf, (v) => RR.money(v)), row("Diluted EPS", fin.diluted_eps, (v) => RR.num(v))))) : el("p", { class: "muted" }, "Annual statements were not available.");

    return section("fundamentals", "Business & fundamentals", `Figures in ${cur || "reporting currency"}`,
      el("div", { class: "grid g-2-1" },
        card("Business overview", null, el("p", {}, n.fundamental.business_overview),
          el("h3", { style: { margin: "14px 0 6px" } }, "Financial performance"), el("p", {}, n.fundamental.financial_performance),
          el("h3", { style: { margin: "14px 0 6px" } }, "Valuation view"), el("p", {}, n.fundamental.valuation)),
        card("Company", null, kv([["Sector", a.meta.sector || "—"], ["Industry", a.meta.industry || "—"], ["Country", a.meta.country || "—"],
          ["Employees", RR.isNum(a.meta.employees) ? a.meta.employees.toLocaleString() : "—"], ["Exchange", a.meta.exchange || "—"],
          ["Beta", RR.num(f.ownership.beta)], ["Institutional ownership", RR.pct(f.ownership.institutions)], ["Short interest (float)", RR.pct(f.ownership.short_float)]]),
          a.meta.website ? el("p", { style: { marginTop: "10px" } }, RR.extLink(a.meta.website, "Company website ↗")) : null)),
      el("div", { class: "grid g2", style: { marginTop: "16px" } },
        card("Annual revenue, net income & FCF", null, chartBox("mid", annualChart(a), "Annual revenue, net income and free cash flow")),
        card("Margin trend", null, chartBox("mid", marginChart(a), "Gross, operating, net and FCF margins by year"))),
      (q.periods || []).length ? el("div", { style: { marginTop: "16px" } }, card("Quarterly revenue & net income", null, chartBox("mid", quarterlyChart(a), "Quarterly revenue and net income"))) : null,
      el("div", { style: { marginTop: "16px" } }, card("Financial statements (annual)", null, finTable)),
      el("div", { class: "grid g3", style: { marginTop: "16px" } },
        card("Valuation", null, kv([["Trailing P/E", RR.mult(f.valuation.pe_trailing)], ["Forward P/E", RR.mult(f.valuation.pe_forward)], ["PEG", RR.mult(f.valuation.peg, 2)],
          ["EV / EBITDA", RR.mult(f.valuation.ev_to_ebitda)], ["EV / Revenue", RR.mult(f.valuation.ev_to_revenue)], ["Price / Sales", RR.mult(f.valuation.price_to_sales)],
          ["Price / Book", RR.mult(f.valuation.price_to_book)], ["FCF yield", RR.pct(f.valuation.fcf_yield)]])),
        card("Profitability & growth", null, kv([["Gross margin", RR.pct(f.profitability.gross_margin)], ["Operating margin", RR.pct(f.profitability.operating_margin)],
          ["Net margin", RR.pct(f.profitability.net_margin)], ["ROE", RR.pct(f.profitability.roe)], ["ROA", RR.pct(f.profitability.roa)],
          ["Revenue growth", RR.pct(f.growth.revenue_growth_yoy, 1, true)], ["Earnings growth", RR.pct(f.growth.earnings_growth_yoy, 1, true)],
          ["EPS (ttm → fwd)", `${RR.num(f.growth.eps_trailing)} → ${RR.num(f.growth.eps_forward)}`]])),
        card("Balance sheet & cash", null, kv([["Cash", RR.money(f.health.total_cash)], ["Debt", RR.money(f.health.total_debt)], ["Net cash", RR.money(f.health.net_cash)],
          ["Debt / equity", RR.mult(f.health.debt_to_equity, 2)], ["Current ratio", RR.mult(f.health.current_ratio, 2)], ["Free cash flow", RR.money(f.health.free_cash_flow)],
          ["Dividend yield", RR.pct(f.dividend.yield, 2)], ["Payout ratio", RR.pct(f.dividend.payout_ratio)]]))));
  }

  function annualChart(a) {
    return () => {
      const T = RR.tokens(), fin = a.financials.annual, o = RR.baseChart(T);
      const mk = (name, data, c) => ({ name, type: "bar", data, barMaxWidth: 26, barGap: "12%", itemStyle: { color: c, borderRadius: [4, 4, 0, 0] } });
      return Object.assign(o, {
        grid: { left: 60, right: 10, top: 34, bottom: 26 },
        tooltip: Object.assign(o.tooltip, { valueFormatter: (v) => RR.money(v) }),
        xAxis: RR.axisStyle(T, { type: "category", data: fin.years, splitLine: { show: false } }),
        yAxis: RR.axisStyle(T, { axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => RR.moneyAxis(v) } }),
        series: [mk("Revenue", fin.revenue, T.series[0]), mk("Net income", fin.net_income, T.series[1]), mk("Free cash flow", fin.fcf, T.series[2])],
      });
    };
  }

  function marginChart(a) {
    return () => {
      const T = RR.tokens(), fin = a.financials.annual, o = RR.baseChart(T);
      const mk = (name, data, c) => ({ name, type: "line", data, symbol: "circle", symbolSize: 8, lineStyle: { width: 2, color: c }, itemStyle: { color: c, borderColor: T.surface, borderWidth: 2 } });
      return Object.assign(o, {
        grid: { left: 48, right: 14, top: 34, bottom: 26 },
        tooltip: Object.assign(o.tooltip, { valueFormatter: (v) => RR.pct(v) }),
        xAxis: RR.axisStyle(T, { type: "category", data: fin.years, splitLine: { show: false } }),
        yAxis: RR.axisStyle(T, { axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => `${Math.round(v * 100)}%` } }),
        series: [mk("Gross", fin.gross_margin, T.series[0]), mk("Operating", fin.operating_margin, T.series[1]),
          mk("Net", fin.net_margin, T.series[2]), mk("FCF", fin.fcf_margin, T.series[3])],
      });
    };
  }

  function quarterlyChart(a) {
    return () => {
      const T = RR.tokens(), q = a.financials.quarterly, o = RR.baseChart(T);
      return Object.assign(o, {
        grid: { left: 60, right: 10, top: 34, bottom: 26 },
        tooltip: Object.assign(o.tooltip, { valueFormatter: (v) => RR.money(v) }),
        xAxis: RR.axisStyle(T, { type: "category", data: q.labels, splitLine: { show: false } }),
        yAxis: RR.axisStyle(T, { axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => RR.moneyAxis(v) } }),
        series: [
          { name: "Revenue", type: "bar", data: q.revenue, barMaxWidth: 22, itemStyle: { color: T.series[0], borderRadius: [4, 4, 0, 0] } },
          { name: "Net income", type: "bar", data: q.net_income, barMaxWidth: 22, itemStyle: { color: T.series[1], borderRadius: [4, 4, 0, 0] } },
        ],
      });
    };
  }

  // ------------------------------------------------------------------ peers
  function peersSection(a, n, cur) {
    const P = a.peers;
    if (!P.rows || P.rows.length < 2) {
      return section("peers", "Peer comparison", null, card(null, null, el("p", {}, n.fundamental.peer_positioning),
        el("p", { class: "muted" }, "No peer set was available. Pass peers explicitly (e.g. AAPL,GOOGL) when generating the report.")));
    }
    let metric = "pe_forward";
    const select = el("select", { class: "input", style: { height: "34px" }, "aria-label": "Peer metric" },
      P.metrics.map((m) => el("option", { value: m.key, selected: m.key === metric }, m.label)));
    const barNode = chartBox("mid", () => peerBar(a, metric), "Peer comparison bar chart");
    select.addEventListener("change", () => { metric = select.value; const inst = instances.find((c) => c.getDom() === barNode); if (inst) inst.setOption(peerBar(a, metric), true); });

    const pctKeys = new Set(["gross_margin", "operating_margin", "net_margin", "roe", "revenue_growth", "return_1y"]);
    const fmt = (k, v) => (pctKeys.has(k) ? RR.pct(v, 1, k === "return_1y" || k === "revenue_growth") : RR.mult(v));
    const cols = ["pe_forward", "ev_to_ebitda", "price_to_sales", "gross_margin", "operating_margin", "roe", "revenue_growth", "return_1y"];
    const label = Object.fromEntries(P.metrics.map((m) => [m.key, m.label]));
    const table = el("div", { class: "table-scroll" }, el("table", { class: "data" },
      el("thead", {}, el("tr", {}, el("th", {}, "Company"), el("th", {}, "Mkt cap"), cols.map((c) => el("th", {}, label[c])))),
      el("tbody", {},
        P.rows.map((r) => el("tr", { class: r.is_subject ? "subject" : "" },
          el("td", {}, el("b", {}, r.ticker), el("span", { class: "muted small" }, r.name && r.name !== r.ticker ? `  ${r.name}` : "")),
          el("td", {}, RR.money(r.market_cap)), cols.map((c) => el("td", {}, fmt(c, r[c]))))),
        el("tr", { class: "median" }, el("td", {}, "Peer median"), el("td", {}, ""), cols.map((c) => el("td", {}, fmt(c, P.medians[c])))))));

    const rel = el("div", { class: "grid g3", style: { gap: "0 24px" } }, (P.relative || []).map((r) => el("div", { class: "signal" },
      el("span", { class: `dot ${r.favorable ? "bullish" : "bearish"}` }),
      el("div", {}, el("b", {}, r.label),
        el("span", { class: "note" }, `${fmt(r.metric, r.subject)} vs median ${fmt(r.metric, r.peer_median)} — `,
          r.difference_kind === "relative" ? `${RR.pct(Math.abs(r.difference), 0)} ${r.difference > 0 ? "premium" : "discount"}` : `${(r.difference * 100 > 0 ? "+" : "") + (r.difference * 100).toFixed(1)} pts`,
          r.favorable ? " (favourable)" : " (unfavourable)")))));

    return section("peers", "Peer comparison", `Peer set: ${P.source}${P.benchmark ? " · benchmark " + P.benchmark : ""}`,
      card(null, null, el("p", {}, n.fundamental.peer_positioning)),
      el("div", { class: "grid g2", style: { marginTop: "16px" } },
        card("Compare on", select, barNode, el("div", { class: "caption" }, "Subject highlighted; vertical line marks the peer median.")),
        card("Relative performance (1 year)", null, chartBox("mid", relChart(a), "Rebased price performance vs peers and benchmark"),
          el("div", { class: "caption" }, "Weekly closes rebased to 100 at the start of the window."))),
      el("div", { style: { marginTop: "16px" } }, card("Comparison table", null, table)),
      el("div", { style: { marginTop: "16px" } }, card("Versus peer median", el("span", { class: "legend-inline" },
        el("span", {}, el("span", { class: "dot bullish" }), " favourable"), el("span", {}, el("span", { class: "dot bearish" }), " unfavourable")), rel)));
  }

  function peerBar(a, key) {
    const T = RR.tokens(), P = a.peers, o = RR.baseChart(T);
    const pctKeys = new Set(["gross_margin", "operating_margin", "net_margin", "roe", "revenue_growth", "return_1y"]);
    const rows = P.rows.filter((r) => RR.isNum(r[key])).sort((x, y) => x[key] - y[key]);
    const f = (v) => (pctKeys.has(key) ? RR.pct(v, 1) : RR.mult(v));
    const med = P.medians[key];
    return Object.assign(o, {
      legend: { show: false }, grid: { left: 70, right: 56, top: 14, bottom: 26 },
      tooltip: Object.assign(o.tooltip, { trigger: "item", formatter: (p) => `${p.name}: <b>${f(p.value)}</b>` }),
      yAxis: RR.axisStyle(T, { type: "category", data: rows.map((r) => r.ticker), splitLine: { show: false } }),
      xAxis: RR.axisStyle(T, { axisLabel: { color: T.muted, fontSize: 11, formatter: (v) => (pctKeys.has(key) ? `${Math.round(v * 100)}%` : v) } }),
      series: [{ type: "bar", barMaxWidth: 18, data: rows.map((r) => ({ value: r[key], itemStyle: { color: r.is_subject ? T.series[0] : T.muted, opacity: r.is_subject ? 1 : 0.45, borderRadius: 4 } })),
        label: { show: true, position: "right", fontSize: 11, color: T.ink2, formatter: (p) => f(p.value) },
        markLine: RR.isNum(med) ? { symbol: "none", silent: true, lineStyle: { color: T.ink2, type: "solid", width: 1 }, label: { formatter: "median", color: T.muted, fontSize: 10.5 }, data: [{ xAxis: med }] } : undefined }],
    });
  }

  function relChart(a) {
    return () => {
      const T = RR.tokens(), P = a.peers, perf = P.relative_performance || {}, o = RR.baseChart(T);
      const subj = a.meta.ticker, bench = P.benchmark;
      const others = Object.keys(perf).filter((k) => k !== subj && k !== bench).slice(0, 6);
      const order = [subj, ...others, ...(perf[bench] ? [bench] : [])].filter((k) => perf[k]);

      return Object.assign(o, {
        grid: { left: 44, right: 14, top: 50, bottom: 26 }, legend: Object.assign(o.legend, { type: "scroll" }),
        tooltip: Object.assign(o.tooltip, { valueFormatter: (v) => (RR.isNum(v) ? v.toFixed(1) : "—") }),
        xAxis: RR.axisStyle(T, { type: "time", splitLine: { show: false }, axisLabel: { color: T.muted, fontSize: 11, hideOverlap: true, formatter: "{MMM} '{yy}" } }),
        yAxis: RR.axisStyle(T, { scale: true }),
        series: order.map((k, i) => {
          const color = k === subj ? T.series[0] : k === bench ? T.muted : T.series[(i % 7) + 1];
          return { name: k === bench ? `${k} (benchmark)` : k, type: "line", symbol: "none", data: perf[k].map((p) => [p.date, p.value]), connectNulls: true,
            lineStyle: { width: k === subj ? 2.6 : 1.3, color, opacity: k === subj ? 1 : 0.85 }, itemStyle: { color }, z: k === subj ? 10 : 2,
            markLine: i === 0 ? { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: T.axis, type: "solid" }, data: [{ yAxis: 100 }] } : undefined };
        }),
      });
    };
  }

  // ------------------------------------------------------------------ news
  function newsSection(a, n) {
    const N = a.news;
    let filter = "";
    const list = el("div", { class: "news" });
    const drawList = () => {
      clear(list);
      const items = N.items.filter((i) => !filter || i.label === filter);
      if (!items.length) list.append(el("p", { class: "muted" }, "No headlines."));
      items.forEach((i) => {
        const cls = i.label === "positive" ? "pos" : i.label === "negative" ? "neg" : "neu";
        list.append(el("div", { class: "news-item" },
          el("span", { class: `score-pill chip ${cls}`, title: `VADER compound ${i.score}` }, (i.score > 0 ? "+" : "") + i.score.toFixed(2)),
          el("div", {},
            i.link ? el("a", { class: "t", href: i.link, target: "_blank", rel: "noopener noreferrer" }, i.title) : el("span", { class: "t" }, i.title),
            el("div", { class: "m" }, [i.source, i.published ? `${RR.date(i.published)} (${RR.ago(i.published)})` : null, i.feed].filter(Boolean).join(" · ")),
            i.summary && i.summary !== i.title ? el("div", { class: "s" }, i.summary.slice(0, 240)) : null)));
      });
    };
    const seg = el("div", { class: "seg", role: "group", "aria-label": "Filter headlines" },
      [["", "All"], ["positive", "Positive"], ["neutral", "Neutral"], ["negative", "Negative"]].map(([v, l]) =>
        el("button", { type: "button", "aria-pressed": String(v === ""), "data-v": v }, `${l}${v ? ` (${N.counts[v]})` : ` (${N.count})`}`)));
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      filter = b.dataset.v; [...seg.children].forEach((x) => x.setAttribute("aria-pressed", String(x === b))); drawList();
    });
    drawList();
    const tiles = el("div", { class: "grid g3" }, [["positive", "Positive", "pos"], ["neutral", "Neutral", "neu"], ["negative", "Negative", "neg"]].map(([k, l, c]) =>
      el("div", { class: "kpi", style: { padding: "4px 0" } }, el("div", { class: "l" }, l), el("div", { class: "v" }, String(N.counts[k] || 0)),
        el("span", { class: `chip ${c}`, style: { marginTop: "4px" } }, N.count ? RR.pct((N.counts[k] || 0) / N.count, 0) : "—"))));
    return section("news", "News & sentiment", `${N.count} headlines · average score ${RR.isNum(N.average) ? N.average.toFixed(2) : "—"}`,
      el("div", { class: "grid g-2-1" },
        card("Headline tone", el("span", { class: `chip ${RR.biasClass(N.overall)}` }, N.overall), el("p", {}, n.technical.news_sentiment), tiles,
          (N.daily || []).length > 1 ? chartBox("short", newsChart(a), "Daily average headline sentiment") : null,
          el("div", { class: "caption" }, "Scores: VADER compound (−1 to +1) with a finance vocabulary. Headlines deduplicated across Google News, Yahoo Finance RSS and yfinance.")),
        card("Risks & catalysts", null, el("h3", { style: { margin: "4px 0 8px", color: "var(--bad)" } }, "Risks"), bullets(n.technical.risks),
          el("h3", { style: { margin: "14px 0 8px", color: "var(--good)" } }, "Catalysts"), bullets(n.technical.catalysts))),
      el("div", { style: { marginTop: "16px" } }, card("Headlines", seg, list)));
  }

  function newsChart(a) {
    return () => {
      const T = RR.tokens(), d = a.news.daily, o = RR.baseChart(T);
      return Object.assign(o, {
        legend: { show: false }, grid: { left: 36, right: 10, top: 14, bottom: 24 },
        tooltip: Object.assign(o.tooltip, { formatter: (ps) => `${RR.date(d[ps[0].dataIndex].date)}<br>avg <b>${ps[0].value.toFixed(2)}</b> · ${d[ps[0].dataIndex].count} headline(s)` }),
        xAxis: RR.axisStyle(T, { type: "category", data: d.map((x) => x.date), splitLine: { show: false }, axisLabel: { color: T.muted, fontSize: 10.5, formatter: (v) => v.slice(5) } }),
        yAxis: RR.axisStyle(T, { min: -1, max: 1, interval: 0.5 }),
        series: [{ type: "bar", barMaxWidth: 16, data: d.map((x) => ({ value: x.avg, itemStyle: { color: x.avg >= 0.15 ? T.up : x.avg <= -0.15 ? T.down : T.axis, borderRadius: x.avg >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] } })) }],
      });
    };
  }

  // ------------------------------------------------------------------ filings
  function filingsSection(a, n) {
    const F = a.filings;
    if (!F.available) {
      return section("filings", "Regulatory filings", "SEC EDGAR", card(null, null, el("p", {}, n.fundamental.filings_highlights), el("p", { class: "muted" }, F.note || "")));
    }
    const table = el("div", { class: "table-scroll" }, el("table", { class: "data" },
      el("thead", {}, el("tr", {}, el("th", {}, "Filed"), el("th", { class: "l" }, "Form"), el("th", { class: "l" }, "Description"), el("th", {}, "Report date"))),
      el("tbody", {}, F.recent.map((x) => el("tr", {}, el("td", {}, x.date),
        el("td", { class: "l" }, x.url ? RR.extLink(x.url, x.form) : x.form), el("td", { class: "l" }, x.description || ""), el("td", {}, x.report_date || ""))))));
    return section("filings", "Regulatory filings", `SEC EDGAR · CIK ${F.cik || "—"}${F.entity ? " · " + F.entity : ""}`,
      el("div", { class: "grid g-2-1" },
        card("Filing timeline", null, chartBox("mid", filingsChart(a), "Timeline of recent SEC filings by form type")),
        card("Highlights", null, el("p", {}, n.fundamental.filings_highlights),
          kv(Object.entries(F.counts || {}).sort((x, y) => y[1] - x[1]).slice(0, 8).map(([k, v]) => [k, String(v)])))),
      el("div", { style: { marginTop: "16px" } }, card("Recent filings", null, table)));
  }

  function filingsChart(a) {
    return () => {
      const T = RR.tokens(), F = a.filings, o = RR.baseChart(T);
      const forms = Object.entries(F.counts).sort((x, y) => y[1] - x[1]).slice(0, 7).map((x) => x[0]);
      const pts = F.recent.filter((x) => forms.includes(x.form)).map((x) => ({ value: [x.date, x.form], name: x.description || x.form }));
      return Object.assign(o, {
        legend: { show: false }, grid: { left: 70, right: 16, top: 14, bottom: 28 },
        tooltip: Object.assign(o.tooltip, { trigger: "item", formatter: (p) => `<b>${p.value[1]}</b> · ${RR.date(p.value[0])}<br>${String(p.name).replace(/[<>&]/g, "")}` }),
        xAxis: RR.axisStyle(T, { type: "time", splitLine: { show: false }, splitNumber: 5,
          min: (v) => v.min - 20 * 864e5, max: (v) => v.max + 20 * 864e5,
          axisLabel: { color: T.muted, fontSize: 11, hideOverlap: true, formatter: "{MMM} '{yy}" } }),
        yAxis: RR.axisStyle(T, { type: "category", data: forms.slice().reverse() }),
        series: [{ type: "scatter", symbolSize: 12, data: pts, itemStyle: { color: T.series[0], borderColor: T.surface, borderWidth: 2 } }],
      });
    };
  }

  // ------------------------------------------------------------------ method
  function methodSection(R, a, n, base) {
    const prov = Object.entries(n.provenance || {});
    const warnings = (a.meta.data_warnings || []).filter(Boolean);
    return section("method", "Method & provenance", null,
      el("div", { class: "grid g2" },
        card("How this report was made", null,
          el("ol", { class: "clean", style: { paddingLeft: "20px" } },
            el("li", {}, "n8n pulled prices & fundamentals (yfinance), SEC EDGAR filings and RSS headlines in parallel."),
            el("li", {}, "A Python service computed ratios, peer statistics, technical indicators, headline sentiment and the scorecard."),
            el("li", {}, `A local LLM (${(R.meta && R.meta.model) || "none"}) drafted the narrative from those computed figures in three passes: fundamentals, technicals & news, summary.`),
            el("li", {}, "Any section the model did not return in valid form was filled with rule-based text.")),
          kv([["Generated", RR.date(R.generated_at) + " " + (R.generated_at || "").slice(11, 16) + " UTC"], ["Market data fetched", RR.date(a.meta.data_fetched_at)],
            ["LLM coverage", RR.pct(n.llm_coverage, 0)], ["n8n execution", (R.meta && R.meta.execution_id) || "—"], ["Report id", R.id]]),
          el("p", { style: { marginTop: "10px" } }, el("a", { href: `${base}/${R.id}/report.json`, target: "_blank", rel: "noopener" }, "Raw report data (JSON) ↗"))),
        card("Field provenance", el("span", { class: "legend-inline" }, el("span", {}, el("i", { style: { background: "var(--accent)" } }), "LLM"), el("span", {}, el("i", { style: { background: "var(--axis)" } }), "rules")),
          el("div", { class: "prov" }, prov.map(([k, v]) => el("span", { class: v === "llm" ? "llm" : "" }, k))),
          warnings.length ? el("div", { class: "notice", style: { marginTop: "14px" } }, el("b", {}, "Data warnings: "), warnings.join("; ")) : null,
          el("p", { class: "disclaimer", style: { marginTop: "14px" } },
            "Not investment advice. This report is generated automatically for educational purposes from free, unofficial data sources and a small local language model. It may contain errors or stale data."))));
  }

  // ------------------------------------------------------------------ charts lifecycle
  function initCharts() {
    instances.forEach((c) => c.dispose());
    instances = [];
    const dark = RR.currentTheme() === "dark";
    charts.forEach(({ node, build }) => {
      if (!node.isConnected) return;
      const inst = echarts.init(node, null, { renderer: "canvas" });
      inst.setOption(build());
      if (build.group) inst.group = build.group;
      instances.push(inst);
    });
    echarts.connect("px");
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  }
  RR.onThemeChange.push(initCharts);
  let rz = null;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => instances.forEach((c) => c.resize()), 120); });

  function wireNav(nav) {
    const links = [...nav.querySelectorAll("a[data-sec]")];
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) links.forEach((l) => l.classList.toggle("active", l.dataset.sec === e.target.id)); });
    }, { rootMargin: "-40% 0px -55% 0px" });
    links.forEach((l) => { const s = document.getElementById(l.dataset.sec); if (s) obs.observe(s); });
    const hdr = document.querySelector(".rhead");
    new IntersectionObserver(([e]) => nav.classList.toggle("stuck", !e.isIntersecting)).observe(hdr);
  }

  main();
})();
