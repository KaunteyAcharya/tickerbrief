"""Static SVG charts (matplotlib) for the PDF report. Palette matches the web site."""
from __future__ import annotations

import base64
import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
UP, DOWN, NEUTRAL = "#1baf7a", "#e34948", "#c3c2b7"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
    "legend.frameon": False, "legend.fontsize": 7, "svg.fonttype": "none",
})


def _svg(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def price_chart(a: dict[str, Any]) -> str:
    s = a["series"]
    d = pd.to_datetime(s["dates"])
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(7.2, 3.4), sharex=True, gridspec_kw={"height_ratios": [3.2, 1], "hspace": 0.08})
    lower = [x if x is not None else float("nan") for x in s["bb_lower"]]
    upper = [x if x is not None else float("nan") for x in s["bb_upper"]]
    ax.fill_between(d, lower, upper, color=GRID, alpha=0.6, linewidth=0, label="Bollinger (20, 2σ)")
    ax.plot(d, s["close"], color=INK, linewidth=1.4, label="Close")
    for key, col, lbl in (("sma50", SERIES[1], "SMA 50"), ("sma200", SERIES[6], "SMA 200")):
        ax.plot(d, [x if x is not None else float("nan") for x in s[key]], color=col, linewidth=1.1, label=lbl)
    ax.legend(loc="upper left", ncol=4)
    ax.set_ylabel(a["meta"].get("currency") or "")
    closes = s["close"]
    colors = [UP if i == 0 or (closes[i] or 0) >= (closes[i - 1] or 0) else DOWN for i in range(len(closes))]
    axv.bar(d, [v or 0 for v in s["volume"]], color=colors, width=1.0, linewidth=0)
    axv.set_ylabel("Volume")
    axv.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x / 1e6:.0f}M"))
    axv.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    return _svg(fig)


def momentum_chart(a: dict[str, Any]) -> str:
    s = a["series"]
    d = pd.to_datetime(s["dates"])
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 2.6), sharex=True, gridspec_kw={"hspace": 0.15})
    ax1.axhspan(70, 100, color=DOWN, alpha=0.06, linewidth=0)
    ax1.axhspan(0, 30, color=UP, alpha=0.08, linewidth=0)
    ax1.plot(d, [x if x is not None else float("nan") for x in s["rsi"]], color=SERIES[0], linewidth=1.1)
    ax1.set_ylim(0, 100)
    ax1.set_yticks([30, 50, 70])
    ax1.set_ylabel("RSI 14")
    hist = [x or 0 for x in s["macd_hist"]]
    ax2.bar(d, hist, color=[UP if h >= 0 else DOWN for h in hist], width=1.0, linewidth=0)
    ax2.plot(d, [x if x is not None else float("nan") for x in s["macd"]], color=SERIES[0], linewidth=1.0, label="MACD")
    ax2.plot(d, [x if x is not None else float("nan") for x in s["macd_signal"]], color=SERIES[1], linewidth=1.0, label="Signal")
    ax2.legend(loc="upper left", ncol=2)
    ax2.set_ylabel("MACD")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    return _svg(fig)


def financials_chart(a: dict[str, Any]) -> str | None:
    f = a["financials"]["annual"]
    years = f.get("years") or []
    if not years:
        return None
    fig, ax = plt.subplots(figsize=(3.5, 2.3))
    x = range(len(years))
    w = 0.38
    rev = [(v or 0) / 1e9 for v in f.get("revenue", [])]
    ni = [(v or 0) / 1e9 for v in f.get("net_income", [])]
    ax.bar([i - w / 2 - 0.01 for i in x], rev, width=w, color=SERIES[0], label="Revenue")
    ax.bar([i + w / 2 + 0.01 for i in x], ni, width=w, color=SERIES[1], label="Net income")
    ax.set_xticks(list(x), years)
    ax.set_ylabel(f"Billions {a['meta'].get('currency') or ''}")
    ax.legend(loc="upper left")
    ax.grid(axis="x", visible=False)
    return _svg(fig)


def relative_chart(a: dict[str, Any]) -> str | None:
    perf = a["peers"].get("relative_performance") or {}
    if not perf:
        return None
    fig, ax = plt.subplots(figsize=(3.5, 2.3))
    subject = a["meta"]["ticker"]
    bench = a["peers"].get("benchmark")
    order = [subject] + [k for k in perf if k not in (subject, bench)] + ([bench] if bench in perf else [])
    for i, k in enumerate(order[:8]):
        if k not in perf:
            continue
        pts = perf[k]
        color = INK if k == subject else MUTED if k == bench else SERIES[(i) % len(SERIES)]
        lw = 1.8 if k == subject else 0.9
        ax.plot(pd.to_datetime([p["date"] for p in pts]), [p["value"] for p in pts], color=color, linewidth=lw,
                label=k, linestyle="-", alpha=1 if k in (subject, bench) else 0.85)
    ax.axhline(100, color=AXIS, linewidth=0.8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_ylabel("Rebased = 100")
    ax.legend(loc="upper left", ncol=2, fontsize=6)
    return _svg(fig)


def peer_bar_chart(a: dict[str, Any], key: str = "pe_forward", label: str = "Forward P/E") -> str | None:
    rows = [r for r in a["peers"]["rows"] if r.get(key) is not None]
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: r[key])
    fig, ax = plt.subplots(figsize=(3.5, 0.3 * len(rows) + 0.6))
    ax.barh([r["ticker"] for r in rows], [r[key] for r in rows],
            color=[SERIES[0] if r["is_subject"] else AXIS for r in rows], height=0.6)
    med = a["peers"]["medians"].get(key)
    if med:
        ax.axvline(med, color=INK2, linewidth=0.8)
        ax.text(med, len(rows) - 0.4, f" peer median {med:.1f}", fontsize=6, color=INK2, va="bottom")
    ax.set_xlabel(label)
    ax.grid(axis="y", visible=False)
    return _svg(fig)


def scorecard_chart(a: dict[str, Any]) -> str:
    sc = a["scorecard"][::-1]
    fig, ax = plt.subplots(figsize=(3.5, 2.1))
    ax.barh([s["name"] for s in sc], [100] * len(sc), color=GRID, height=0.55)
    ax.barh([s["name"] for s in sc], [s["score"] for s in sc], color=SERIES[0], height=0.55)
    for i, s in enumerate(sc):
        ax.text(s["score"] + 2, i, f"{s['score']:.0f}", va="center", fontsize=7, color=INK)
    ax.set_xlim(0, 105)
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([])
    return _svg(fig)


def sentiment_chart(a: dict[str, Any]) -> str | None:
    daily = a["news"].get("daily") or []
    if len(daily) < 2:
        return None
    fig, ax = plt.subplots(figsize=(3.5, 2.1))
    d = pd.to_datetime([x["date"] for x in daily])
    vals = [x["avg"] for x in daily]
    ax.bar(d, vals, color=[UP if v >= 0.15 else DOWN if v <= -0.15 else NEUTRAL for v in vals], width=0.8)
    ax.axhline(0, color=AXIS, linewidth=0.8)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Avg headline score")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.setp(ax.get_xticklabels(), rotation=0)
    return _svg(fig)


def all_charts(a: dict[str, Any]) -> dict[str, str | None]:
    out = {}
    for name, fn in (("price", price_chart), ("momentum", momentum_chart), ("financials", financials_chart),
                     ("relative", relative_chart), ("peers", peer_bar_chart), ("scorecard", scorecard_chart),
                     ("sentiment", sentiment_chart)):
        try:
            out[name] = fn(a)
        except Exception:  # noqa: BLE001 - a missing chart should never break the PDF
            out[name] = None
    return out
