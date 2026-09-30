"""Turns raw market / filings / news data into a structured analysis + compact LLM briefs."""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

import numpy as np
import pandas as pd

from . import indicators as ind
from .sentiment import score_news
from .util import clean, num, pct_change, safe_div

CHART_DAYS = 252  # ~1 trading year shown in charts


# ----------------------------------------------------------------------------- helpers
def _first(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def _median(vals: list[float | None]) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return statistics.median(v) if v else None


def _clip(x: float, lo: float = 5, hi: float = 95) -> float:
    return float(max(lo, min(hi, x)))


def _lin(x: float | None, bad: float, good: float) -> float | None:
    """Map x linearly so that `bad` -> 0 and `good` -> 100 (works for reversed scales)."""
    if x is None:
        return None
    return _clip((x - bad) / (good - bad) * 100, 0, 100)


def _avg(vals: list[float | None], default: float = 50.0) -> float:
    v = [x for x in vals if x is not None]
    return _clip(sum(v) / len(v)) if v else default


def fmt_money(x: float | None, cur: str | None = "") -> str:
    if x is None:
        return "n/a"
    sign = "-" if x < 0 else ""
    x = abs(x)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if x >= div:
            return f"{sign}{x / div:,.2f}{suf} {cur or ''}".strip()
    return f"{sign}{x:,.2f} {cur or ''}".strip()


def fmt_pct(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def fmt_x(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}x"


# ----------------------------------------------------------------------------- price & technicals
def _frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(history)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    return df


def _ret(close: pd.Series, days: int) -> float | None:
    if len(close) <= days:
        return None
    return pct_change(float(close.iloc[-1]), float(close.iloc[-1 - days]))


def price_and_technicals(df: pd.DataFrame) -> tuple[dict, dict, dict]:
    c, h, l = df["close"], df["high"].fillna(df["close"]), df["low"].fillna(df["close"])
    df = df.assign(
        sma20=ind.sma(c, 20), sma50=ind.sma(c, 50), sma200=ind.sma(c, 200), rsi=ind.rsi(c),
        atr=ind.atr(h, l, c),
    ).join(ind.macd(c)).join(ind.bollinger(c))
    last = df.iloc[-1]
    last_close = float(last["close"])
    prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else None

    one_year = df.iloc[-CHART_DAYS:]
    ytd = df[df.index >= pd.Timestamp(dt.date(df.index[-1].year, 1, 1))]
    hi52, lo52 = float(one_year["high"].max()), float(one_year["low"].min())

    price = {
        "last": last_close,
        "last_date": df.index[-1].strftime("%Y-%m-%d"),
        "change_1d": None if prev_close is None else last_close - prev_close,
        "change_1d_pct": pct_change(last_close, prev_close),
        "high_52w": hi52, "low_52w": lo52,
        "pct_from_high": pct_change(last_close, hi52),
        "pct_from_low": pct_change(last_close, lo52),
        "range_position": safe_div(last_close - lo52, hi52 - lo52),
        "returns": {
            "1m": _ret(c, 21), "3m": _ret(c, 63), "6m": _ret(c, 126),
            "ytd": pct_change(last_close, float(ytd["close"].iloc[0])) if len(ytd) > 1 else None,
            "1y": _ret(c, 252),
        },
        "volatility_1y": ind.annualized_vol(one_year["close"]),
        "max_drawdown_1y": ind.max_drawdown(one_year["close"]),
        "avg_volume_3m": num(df["volume"].iloc[-63:].mean()),
    }

    # --- signals -------------------------------------------------------------
    signals: list[dict[str, Any]] = []

    def add(name, value, signal, note):
        signals.append({"name": name, "value": value, "signal": signal, "note": note})

    sma50, sma200, rsi_v = num(last["sma50"]), num(last["sma200"]), num(last["rsi"])
    if sma50:
        add("Price vs 50-day SMA", pct_change(last_close, sma50),
            "bullish" if last_close > sma50 else "bearish",
            f"Price is {'above' if last_close > sma50 else 'below'} the 50-day average ({sma50:,.2f}).")
    if sma200:
        add("Price vs 200-day SMA", pct_change(last_close, sma200),
            "bullish" if last_close > sma200 else "bearish",
            f"Price is {'above' if last_close > sma200 else 'below'} the 200-day average ({sma200:,.2f}).")
    if sma50 and sma200:
        add("50/200-day trend", pct_change(sma50, sma200), "bullish" if sma50 > sma200 else "bearish",
            "Golden-cross regime (50 > 200)." if sma50 > sma200 else "Death-cross regime (50 < 200).")
    if rsi_v is not None:
        sig = "bearish" if rsi_v >= 70 else "bullish" if rsi_v <= 30 else "neutral"
        note = ("Overbought (>= 70)." if rsi_v >= 70 else "Oversold (<= 30)." if rsi_v <= 30
                else "Neutral zone (30-70).")
        add("RSI (14)", rsi_v, sig, note)
    hist = num(last["hist"])
    if hist is not None:
        add("MACD histogram", hist, "bullish" if hist > 0 else "bearish",
            "MACD is above its signal line." if hist > 0 else "MACD is below its signal line.")
    r3 = price["returns"]["3m"]
    if r3 is not None:
        add("3-month momentum", r3, "bullish" if r3 > 0.03 else "bearish" if r3 < -0.03 else "neutral",
            f"{fmt_pct(r3)} over ~63 trading days.")
    bb_u, bb_l = num(last["bb_upper"]), num(last["bb_lower"])
    pct_b = safe_div(last_close - bb_l, bb_u - bb_l) if bb_u and bb_l else None
    if pct_b is not None:
        add("Bollinger %B", pct_b, "bearish" if pct_b > 1 else "bullish" if pct_b < 0 else "neutral",
            "Above upper band (stretched)." if pct_b > 1 else "Below lower band (washed out)." if pct_b < 0
            else "Inside the bands.")

    weights = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}
    tech_score = (sum(weights[s["signal"]] for s in signals) / len(signals) * 100) if signals else 50.0

    # crossovers within the last year
    crosses = []
    both = df[["sma50", "sma200"]].dropna().iloc[-CHART_DAYS:]
    if len(both) > 2:
        above = (both["sma50"] > both["sma200"]).astype(int)
        chg = above.diff().fillna(0)
        for d, v in chg[chg != 0].items():
            crosses.append({"date": d.strftime("%Y-%m-%d"), "type": "golden" if v > 0 else "death"})

    recent = df.iloc[-60:]
    technicals = {
        "sma20": num(last["sma20"]), "sma50": sma50, "sma200": sma200, "rsi14": rsi_v,
        "macd": num(last["macd"]), "macd_signal": num(last["signal"]), "macd_hist": hist,
        "bb_upper": bb_u, "bb_lower": bb_l, "pct_b": pct_b, "atr14": num(last["atr"]),
        "atr_pct": safe_div(num(last["atr"]), last_close),
        "support_60d": float(recent["low"].min()), "resistance_60d": float(recent["high"].max()),
        "signals": signals, "score": round(tech_score, 1), "crossovers": crosses[-4:],
        "bias": "bullish" if tech_score >= 60 else "bearish" if tech_score <= 40 else "neutral",
    }

    view = df.iloc[-CHART_DAYS:]

    def col(name, nd=4):
        return [None if pd.isna(v) else round(float(v), nd) for v in view[name]]

    series = {
        "dates": [d.strftime("%Y-%m-%d") for d in view.index],
        "open": col("open"), "high": col("high"), "low": col("low"), "close": col("close"),
        "volume": [None if pd.isna(v) else int(v) for v in view["volume"]],
        "sma20": col("sma20"), "sma50": col("sma50"), "sma200": col("sma200"),
        "bb_upper": col("bb_upper"), "bb_lower": col("bb_lower"),
        "rsi": col("rsi", 2), "macd": col("macd"), "macd_signal": col("signal"), "macd_hist": col("hist"),
    }
    return price, technicals, series


# ----------------------------------------------------------------------------- fundamentals
def fundamentals(info: dict[str, Any], price_last: float) -> dict[str, Any]:
    g = lambda k: num(info.get(k))  # noqa: E731
    # yfinance has reported dividendYield both as a fraction and as a percent over time,
    # so prefer deriving it from the dividend rate and price.
    div_y = safe_div(g("dividendRate"), price_last) if g("dividendRate") else g("dividendYield")
    if div_y is not None and not g("dividendRate") and div_y > 0.2:
        div_y = div_y / 100
    target = g("targetMeanPrice")
    de = g("debtToEquity")
    return {
        "valuation": {
            "market_cap": g("marketCap"), "enterprise_value": g("enterpriseValue"),
            "pe_trailing": g("trailingPE"), "pe_forward": g("forwardPE"),
            "peg": _first(g("trailingPegRatio"), g("pegRatio")), "price_to_book": g("priceToBook"),
            "price_to_sales": g("priceToSalesTrailing12Months"), "ev_to_ebitda": g("enterpriseToEbitda"),
            "ev_to_revenue": g("enterpriseToRevenue"),
            "fcf_yield": safe_div(g("freeCashflow"), g("marketCap")),
        },
        "profitability": {
            "gross_margin": g("grossMargins"), "operating_margin": g("operatingMargins"),
            "net_margin": g("profitMargins"), "ebitda_margin": g("ebitdaMargins"),
            "roe": g("returnOnEquity"), "roa": g("returnOnAssets"),
        },
        "growth": {
            "revenue_growth_yoy": g("revenueGrowth"), "earnings_growth_yoy": g("earningsGrowth"),
            "earnings_growth_qoq": g("earningsQuarterlyGrowth"),
            "eps_trailing": g("trailingEps"), "eps_forward": g("forwardEps"),
            "eps_forward_growth": pct_change(g("forwardEps"), g("trailingEps")) if (g("trailingEps") or 0) > 0 else None,
        },
        "health": {
            "total_cash": g("totalCash"), "total_debt": g("totalDebt"),
            "net_cash": (g("totalCash") - g("totalDebt")) if g("totalCash") is not None and g("totalDebt") is not None else None,
            # yfinance reports D/E in percent (e.g. 35.2 == 0.352x)
            "debt_to_equity": de / 100 if de is not None else None,
            "current_ratio": g("currentRatio"), "quick_ratio": g("quickRatio"),
            "free_cash_flow": g("freeCashflow"), "operating_cash_flow": g("operatingCashflow"),
        },
        "dividend": {"yield": div_y, "rate": g("dividendRate"), "payout_ratio": g("payoutRatio")},
        "analyst": {
            "target_mean": target, "target_median": g("targetMedianPrice"),
            "target_high": g("targetHighPrice"), "target_low": g("targetLowPrice"),
            "upside_to_mean": pct_change(target, price_last),
            "recommendation": info.get("recommendationKey"), "recommendation_mean": g("recommendationMean"),
            "analysts": g("numberOfAnalystOpinions"),
        },
        "ownership": {
            "insiders": g("heldPercentInsiders"), "institutions": g("heldPercentInstitutions"),
            "short_float": g("shortPercentOfFloat"), "beta": g("beta"),
        },
    }


def financial_tables(fin: dict[str, Any]) -> dict[str, Any]:
    a = dict(fin.get("annual") or {})
    periods = a.get("periods", [])
    rev = a.get("revenue", [None] * len(periods))

    def margin(key):
        return [safe_div(x, r) for x, r in zip(a.get(key, [None] * len(periods)), rev)]

    a["years"] = [p[:4] for p in periods]
    a["gross_margin"] = margin("gross_profit")
    a["operating_margin"] = margin("operating_income")
    a["net_margin"] = margin("net_income")
    a["fcf_margin"] = margin("fcf")
    a["revenue_growth"] = [None] + [pct_change(rev[i], rev[i - 1]) for i in range(1, len(rev))]
    # keep only years that have revenue
    keep = [i for i, r in enumerate(rev) if r is not None]
    a = {k: ([v[i] for i in keep] if isinstance(v, list) and len(v) == len(periods) else v) for k, v in a.items()}

    q = dict(fin.get("quarterly") or {})
    qp = q.get("periods", [])
    q["labels"] = [f"{p[:4]} Q{(int(p[5:7]) - 1) // 3 + 1}" for p in qp]
    q["net_margin"] = [safe_div(n, r) for n, r in zip(q.get("net_income", []), q.get("revenue", []))]
    return {"annual": a, "quarterly": q}


# ----------------------------------------------------------------------------- peers
PEER_METRICS = [
    # key, label, info-field, higher_is_better
    ("pe_forward", "Forward P/E", "forwardPE", False),
    ("pe_trailing", "Trailing P/E", "trailingPE", False),
    ("ev_to_ebitda", "EV / EBITDA", "enterpriseToEbitda", False),
    ("price_to_sales", "Price / Sales", "priceToSalesTrailing12Months", False),
    ("gross_margin", "Gross margin", "grossMargins", True),
    ("operating_margin", "Operating margin", "operatingMargins", True),
    ("net_margin", "Net margin", "profitMargins", True),
    ("roe", "Return on equity", "returnOnEquity", True),
    ("revenue_growth", "Revenue growth", "revenueGrowth", True),
    ("return_1y", "1-year return", None, True),
]


def _weekly_series(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    s = pd.Series([r["close"] for r in history], index=pd.to_datetime([r["date"] for r in history]))
    w = s.resample("W-FRI").last().dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "close": float(v)} for d, v in w.items()]


def _ret_1y(weekly: list[dict[str, Any]]) -> float | None:
    if len(weekly) < 40:
        return None
    return pct_change(weekly[-1]["close"], weekly[max(0, len(weekly) - 53)]["close"])


def peers_block(ticker: str, info: dict[str, Any], history: list[dict[str, Any]], market: dict[str, Any]) -> dict[str, Any]:
    subj_weekly = _weekly_series(history)
    rows = []

    def row(sym, name, inf, weekly, is_subject):
        r = {"ticker": sym, "name": name or sym, "is_subject": is_subject,
             "market_cap": num(inf.get("marketCap")),
             "price": num(_first(inf.get("currentPrice"), inf.get("regularMarketPrice")))}
        for key, _, field, _ in PEER_METRICS:
            r[key] = _ret_1y(weekly) if key == "return_1y" else num(inf.get(field)) if field else None
        # negative P/E-type multiples are not meaningful for comparison
        for k in ("pe_forward", "pe_trailing", "ev_to_ebitda"):
            if r[k] is not None and (r[k] <= 0 or r[k] > 400):
                r[k] = None
        return r

    rows.append(row(ticker, info.get("shortName") or info.get("longName"), info, subj_weekly, True))
    for p in market.get("peers", []):
        inf = p.get("info") or {}
        rows.append(row(p["ticker"], inf.get("shortName") or inf.get("longName"), inf, p.get("weekly") or [], False))

    peer_rows = [r for r in rows if not r["is_subject"]]
    subject = rows[0]
    medians, relative = {}, []
    for key, lbl, _, hib in PEER_METRICS:
        med = _median([r[key] for r in peer_rows])
        medians[key] = med
        sv = subject[key]
        if med is not None and sv is not None and med != 0:
            is_multiple = key.startswith(("pe_", "ev_", "price_"))
            relative.append({
                "metric": key, "label": lbl, "subject": sv, "peer_median": med,
                # multiples: % premium/discount; ratios: percentage-point gap
                "difference": (sv - med) / abs(med) if is_multiple else sv - med,
                "difference_kind": "relative" if is_multiple else "points",
                "favorable": bool((sv > med) if hib else (sv < med)), "higher_is_better": hib})

    # relative performance (rebased to 100) over the last ~52 weeks
    perf = {}
    cutoff = (pd.Timestamp(subj_weekly[-1]["date"]) - pd.Timedelta(weeks=52)).strftime("%Y-%m-%d") if subj_weekly else ""

    def rebase(weekly):
        w = [x for x in weekly if x["date"] >= cutoff]
        if len(w) < 10:
            return None
        base = w[0]["close"]
        return [{"date": x["date"], "value": round(x["close"] / base * 100, 2)} for x in w]

    for sym, weekly in [(ticker, subj_weekly)] + [(p["ticker"], p.get("weekly") or []) for p in market.get("peers", [])] \
            + [(market.get("benchmark", {}).get("ticker", "Benchmark"), market.get("benchmark", {}).get("weekly") or [])]:
        rb = rebase(weekly)
        if rb:
            perf[sym] = rb

    return {"rows": rows, "medians": medians, "relative": relative,
            "metrics": [{"key": k, "label": lbl, "higher_is_better": hib} for k, lbl, _, hib in PEER_METRICS],
            "source": market.get("peer_source", "none"), "relative_performance": perf,
            "benchmark": market.get("benchmark", {}).get("ticker")}


# ----------------------------------------------------------------------------- scorecard & flags
def scorecard(f: dict, peers: dict, tech: dict, price: dict, news: dict) -> list[dict[str, Any]]:
    v, p, g, h = f["valuation"], f["profitability"], f["growth"], f["health"]
    med = peers.get("medians", {})

    def vs_median(x, m):  # lower multiple than peers -> higher score
        if x is None or m in (None, 0):
            return None
        return _clip(50 + (m - x) / m * 100, 0, 100)

    valuation = _avg([
        vs_median(v["pe_forward"], med.get("pe_forward")) if med.get("pe_forward") else _lin(v["pe_forward"], 45, 10),
        vs_median(v["ev_to_ebitda"], med.get("ev_to_ebitda")) if med.get("ev_to_ebitda") else _lin(v["ev_to_ebitda"], 30, 6),
        _lin(v["peg"], 3.0, 0.8),
        _lin(v["fcf_yield"], 0.0, 0.07),
    ])
    quality = _avg([_lin(p["operating_margin"], 0.0, 0.35), _lin(p["roe"], 0.0, 0.30),
                    _lin(p["gross_margin"], 0.15, 0.70), _lin(p["net_margin"], 0.0, 0.25)])
    growth = _avg([_lin(g["revenue_growth_yoy"], -0.05, 0.25), _lin(g["earnings_growth_yoy"], -0.10, 0.30),
                   _lin(g["eps_forward_growth"], -0.05, 0.25)])
    momentum = _avg([tech.get("score"), _lin(price["returns"].get("6m"), -0.25, 0.30),
                     _lin(price["returns"].get("1y"), -0.30, 0.40)])
    health = _avg([_lin(h["debt_to_equity"], 2.0, 0.0), _lin(h["current_ratio"], 0.7, 2.0),
                   100.0 if (h["free_cash_flow"] or 0) > 0 else 20.0 if h["free_cash_flow"] is not None else None,
                   100.0 if (h["net_cash"] or 0) > 0 else 40.0 if h["net_cash"] is not None else None])
    sentiment = _clip(50 + (news.get("average") or 0) * 100, 5, 95) if news.get("count") else 50.0
    items = [("Valuation", valuation, "Multiples vs peers, PEG, FCF yield"),
             ("Quality", quality, "Margins and returns on capital"),
             ("Growth", growth, "Revenue / earnings growth"),
             ("Momentum", momentum, "Trend signals and 6-12m returns"),
             ("Financial health", health, "Leverage, liquidity, cash generation"),
             ("News sentiment", sentiment, "Recent headline tone")]
    return [{"name": n, "score": round(s, 0), "basis": b} for n, s, b in items]


def flags(f: dict, tech: dict, price: dict, peers: dict, news: dict) -> dict[str, list[str]]:
    pos, neg = [], []
    v, p, g, h, a = f["valuation"], f["profitability"], f["growth"], f["health"], f["analyst"]
    if (h["debt_to_equity"] or 0) > 1.5:
        neg.append(f"High leverage: debt/equity {fmt_x(h['debt_to_equity'])}.")
    if h["free_cash_flow"] is not None and h["free_cash_flow"] < 0:
        neg.append("Negative free cash flow over the trailing twelve months.")
    elif h["free_cash_flow"]:
        pos.append(f"Generates positive free cash flow ({fmt_money(h['free_cash_flow'])}).")
    if h["net_cash"] is not None and h["net_cash"] > 0:
        pos.append(f"Net cash position of {fmt_money(h['net_cash'])}.")
    if (p["operating_margin"] or 0) > 0.25:
        pos.append(f"Strong operating margin ({fmt_pct(p['operating_margin'])}).")
    if p["operating_margin"] is not None and p["operating_margin"] < 0:
        neg.append("Operating at a loss.")
    if (g["revenue_growth_yoy"] or 0) > 0.15:
        pos.append(f"Double-digit revenue growth ({fmt_pct(g['revenue_growth_yoy'])} YoY).")
    if g["revenue_growth_yoy"] is not None and g["revenue_growth_yoy"] < 0:
        neg.append(f"Revenue is shrinking ({fmt_pct(g['revenue_growth_yoy'])} YoY).")
    rsi = tech.get("rsi14")
    if rsi is not None and rsi >= 70:
        neg.append(f"Technically overbought (RSI {rsi:.0f}).")
    if rsi is not None and rsi <= 30:
        pos.append(f"Technically oversold (RSI {rsi:.0f}) — potential mean-reversion setup.")
    if tech.get("sma200") and price["last"] < tech["sma200"]:
        neg.append("Trading below its 200-day moving average.")
    if (price.get("max_drawdown_1y") or 0) < -0.30:
        neg.append(f"Deep drawdown in the past year ({fmt_pct(price['max_drawdown_1y'])}).")
    med_pe = peers.get("medians", {}).get("pe_forward")
    if v["pe_forward"] and med_pe:
        prem = v["pe_forward"] / med_pe - 1
        if prem > 0.25:
            neg.append(f"Valuation premium: forward P/E {v['pe_forward']:.1f} vs peer median {med_pe:.1f}.")
        elif prem < -0.20:
            pos.append(f"Valuation discount: forward P/E {v['pe_forward']:.1f} vs peer median {med_pe:.1f}.")
    if a["upside_to_mean"] is not None:
        (pos if a["upside_to_mean"] > 0.10 else neg if a["upside_to_mean"] < -0.05 else []).append(
            f"Consensus target implies {fmt_pct(a['upside_to_mean'])} vs last price.")
    if news.get("counts", {}).get("negative", 0) > news.get("counts", {}).get("positive", 0) + 2:
        neg.append("Headline flow skews negative.")
    return {"positives": pos[:6], "risks": neg[:6]}


# ----------------------------------------------------------------------------- filings
def filings_block(filings: dict[str, Any] | None) -> dict[str, Any]:
    filings = filings or {}
    items = [x for x in filings.get("recent", []) if x.get("form")]
    counts: dict[str, int] = {}
    for x in items:
        counts[x["form"]] = counts.get(x["form"], 0) + 1
    latest = {}
    for form in ("10-K", "10-Q", "20-F", "6-K", "8-K", "40-F"):
        hit = next((x for x in items if x["form"] == form), None)
        if hit:
            latest[form] = hit
    return {"available": bool(items), "cik": filings.get("cik"), "entity": filings.get("entity"),
            "sic": filings.get("sic"), "fiscal_year_end": filings.get("fiscal_year_end"),
            "recent": items[:25], "counts": counts, "latest": latest,
            "note": filings.get("note") or (None if items else "No SEC EDGAR filings found for this symbol (non-US listing?).")}


# ----------------------------------------------------------------------------- LLM briefs
def llm_briefs(a: dict[str, Any]) -> dict[str, str]:
    m, pr, f, t = a["meta"], a["price"], a["fundamentals"], a["technicals"]
    cur = m.get("currency") or ""
    v, p, g, h, an = f["valuation"], f["profitability"], f["growth"], f["health"], f["analyst"]
    fin = a["financials"]["annual"]
    years = fin.get("years", [])
    fin_lines = [f"  {y}: revenue {fmt_money(r, cur)}, op margin {fmt_pct(om)}, net income {fmt_money(ni, cur)}, FCF {fmt_money(fc, cur)}"
                 for y, r, om, ni, fc in zip(years, fin.get("revenue", []), fin.get("operating_margin", []),
                                             fin.get("net_income", []), fin.get("fcf", []))]
    peer_lines = []
    for r in a["peers"]["rows"][:7]:
        peer_lines.append(f"  {r['ticker']}{' (subject)' if r['is_subject'] else ''}: fwd P/E {fmt_x(r['pe_forward'])}, "
                          f"EV/EBITDA {fmt_x(r['ev_to_ebitda'])}, op margin {fmt_pct(r['operating_margin'])}, "
                          f"rev growth {fmt_pct(r['revenue_growth'])}, 1y return {fmt_pct(r['return_1y'])}")
    fil = a["filings"]
    fil_lines = [f"  {x['date']} {x['form']}: {x.get('description') or ''}".rstrip() for x in fil.get("recent", [])[:8]]

    company = (f"Company: {m['name']} ({m['ticker']}), {m.get('sector') or 'n/a'} / {m.get('industry') or 'n/a'}, "
               f"{m.get('country') or ''}. Currency {cur}. Data as of {pr['last_date']}.\n"
               f"Business: {(m.get('business_summary') or 'n/a')[:900]}\n")
    fundamentals_txt = company + (
        f"Price {pr['last']:.2f} {cur}; market cap {fmt_money(v['market_cap'], cur)}; EV {fmt_money(v['enterprise_value'], cur)}.\n"
        f"Valuation: trailing P/E {fmt_x(v['pe_trailing'])}, forward P/E {fmt_x(v['pe_forward'])}, PEG {fmt_x(v['peg'], 2)}, "
        f"EV/EBITDA {fmt_x(v['ev_to_ebitda'])}, P/S {fmt_x(v['price_to_sales'])}, P/B {fmt_x(v['price_to_book'])}, FCF yield {fmt_pct(v['fcf_yield'])}.\n"
        f"Profitability: gross {fmt_pct(p['gross_margin'])}, operating {fmt_pct(p['operating_margin'])}, net {fmt_pct(p['net_margin'])}, "
        f"ROE {fmt_pct(p['roe'])}, ROA {fmt_pct(p['roa'])}.\n"
        f"Growth: revenue YoY {fmt_pct(g['revenue_growth_yoy'])}, earnings YoY {fmt_pct(g['earnings_growth_yoy'])}, "
        f"forward EPS growth {fmt_pct(g['eps_forward_growth'])}.\n"
        f"Balance sheet: cash {fmt_money(h['total_cash'], cur)}, debt {fmt_money(h['total_debt'], cur)}, D/E {fmt_x(h['debt_to_equity'], 2)}, "
        f"current ratio {fmt_x(h['current_ratio'], 2)}, FCF {fmt_money(h['free_cash_flow'], cur)}.\n"
        f"Analysts: {int(an['analysts'] or 0)} covering, consensus '{an['recommendation'] or 'n/a'}', mean target "
        f"{an['target_mean'] if an['target_mean'] is not None else 'n/a'} ({fmt_pct(an['upside_to_mean'])} vs price).\n"
        "Annual financials:\n" + ("\n".join(fin_lines) or "  n/a") + "\n"
        f"Peer comparison (peer source: {a['peers']['source']}):\n" + ("\n".join(peer_lines) or "  n/a") + "\n"
        "Recent SEC filings:\n" + ("\n".join(fil_lines) or "  none (non-US listing or not found)")
    )

    sig_lines = [f"  {s['name']}: {s['signal']} - {s['note']}" for s in t["signals"]]
    news = a["news"]
    head_lines = [f"  [{n['label']} {n['score']:+.2f}] {n['published'][:10] if n['published'] else ''} {n['title']}"
                  for n in news["items"][:12]]
    technical_txt = company + (
        f"Price {pr['last']:.2f} {cur} ({fmt_pct(pr['change_1d_pct'])} 1d). Returns: 1m {fmt_pct(pr['returns']['1m'])}, "
        f"3m {fmt_pct(pr['returns']['3m'])}, 6m {fmt_pct(pr['returns']['6m'])}, YTD {fmt_pct(pr['returns']['ytd'])}, "
        f"1y {fmt_pct(pr['returns']['1y'])}.\n"
        f"52-week range {pr['low_52w']:.2f} - {pr['high_52w']:.2f} ({fmt_pct(pr['pct_from_high'])} from high). "
        f"1y volatility {fmt_pct(pr['volatility_1y'])}, max drawdown {fmt_pct(pr['max_drawdown_1y'])}.\n"
        f"SMA20 {t['sma20'] or 0:.2f}, SMA50 {t['sma50'] or 0:.2f}, SMA200 {t['sma200'] or 0:.2f}, RSI14 {t['rsi14'] or 0:.1f}, "
        f"ATR {fmt_pct(t['atr_pct'])} of price. 60-day support {t['support_60d']:.2f}, resistance {t['resistance_60d']:.2f}.\n"
        f"Technical score {t['score']:.0f}/100 ({t['bias']}). Signals:\n" + "\n".join(sig_lines) + "\n"
        f"News sentiment: {news['overall']} (avg {news['average'] if news['average'] is not None else 'n/a'}) across {news['count']} headlines "
        f"({news['counts']['positive']} positive / {news['counts']['neutral']} neutral / {news['counts']['negative']} negative).\n"
        "Headlines:\n" + ("\n".join(head_lines) or "  none") + "\n"
        "Rule-based risk flags: " + ("; ".join(a["flags"]["risks"]) or "none") + "\n"
        "Rule-based positives: " + ("; ".join(a["flags"]["positives"]) or "none")
    )
    score_line = ", ".join(f"{s['name']} {s['score']:.0f}" for s in a["scorecard"])
    summary_txt = (company + f"Scorecard (0-100, heuristic): {score_line}.\n"
                   f"Key stats: price {pr['last']:.2f} {cur}, fwd P/E {fmt_x(v['pe_forward'])}, op margin {fmt_pct(p['operating_margin'])}, "
                   f"rev growth {fmt_pct(g['revenue_growth_yoy'])}, 1y return {fmt_pct(pr['returns']['1y'])}, technical bias {t['bias']}, "
                   f"news {news['overall']}.\n")
    return {"fundamentals": fundamentals_txt, "technicals": technical_txt, "summary": summary_txt}


# ----------------------------------------------------------------------------- main entry
def analyze(ticker: str, market: dict[str, Any], filings: dict[str, Any] | None = None,
            news: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    info = market.get("info") or {}
    df = _frame(market["history"])
    if len(df) < 30:
        raise ValueError("Not enough price history to analyse (need at least 30 trading days).")
    price, tech, series = price_and_technicals(df)
    f = fundamentals(info, price["last"])
    fin = financial_tables(market.get("financials") or {})
    peers = peers_block(ticker, info, market["history"], market)
    news_block = score_news((news or []) + (market.get("yahoo_news") or []))
    fil = filings_block(filings)

    meta = {
        "ticker": ticker.upper(), "name": info.get("longName") or info.get("shortName") or ticker.upper(),
        "exchange": info.get("fullExchangeName") or info.get("exchange"), "currency": info.get("currency"),
        "sector": info.get("sector"), "industry": info.get("industry"), "country": info.get("country"),
        "website": info.get("website") if str(info.get("website") or "").startswith("http") else None,
        "employees": num(info.get("fullTimeEmployees")),
        "business_summary": info.get("longBusinessSummary"),
        "data_fetched_at": market.get("fetched_at"),
        "analysed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data_warnings": market.get("errors", []),
    }
    out = {
        "meta": meta, "price": price, "technicals": tech, "series": series, "fundamentals": f,
        "financials": fin, "recommendations": market.get("recommendations"), "peers": peers,
        "news": news_block, "filings": fil,
    }
    out["scorecard"] = scorecard(f, peers, tech, price, news_block)
    out["flags"] = flags(f, tech, price, peers, news_block)
    out["llm_briefs"] = llm_briefs(out)
    return clean(out)
