"""Market data collection via yfinance (unofficial Yahoo Finance API, no key needed)."""
from __future__ import annotations

import datetime as dt
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
import yfinance as yf

from .util import clean, num

log = logging.getLogger("analytics.market")

INFO_FIELDS = [
    "longName", "shortName", "symbol", "exchange", "fullExchangeName", "quoteType", "currency",
    "financialCurrency", "sector", "industry", "industryKey", "country", "city", "website",
    "longBusinessSummary", "fullTimeEmployees",
    "currentPrice", "regularMarketPrice", "previousClose", "regularMarketChangePercent",
    "marketCap", "enterpriseValue", "sharesOutstanding", "floatShares",
    "trailingPE", "forwardPE", "trailingPegRatio", "pegRatio", "priceToBook",
    "priceToSalesTrailing12Months", "enterpriseToEbitda", "enterpriseToRevenue",
    "grossMargins", "operatingMargins", "profitMargins", "ebitdaMargins",
    "returnOnEquity", "returnOnAssets", "revenueGrowth", "earningsGrowth",
    "earningsQuarterlyGrowth", "totalRevenue", "ebitda", "netIncomeToCommon",
    "freeCashflow", "operatingCashflow", "totalCash", "totalDebt",
    "debtToEquity", "currentRatio", "quickRatio",
    "trailingEps", "forwardEps", "bookValue",
    "dividendYield", "dividendRate", "payoutRatio",
    "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage", "twoHundredDayAverage",
    "averageVolume", "targetMeanPrice", "targetMedianPrice", "targetHighPrice", "targetLowPrice",
    "recommendationKey", "recommendationMean", "numberOfAnalystOpinions",
    "heldPercentInsiders", "heldPercentInstitutions", "shortPercentOfFloat",
]

PEER_FIELDS = [
    "longName", "shortName", "currency", "currentPrice", "regularMarketPrice", "marketCap",
    "trailingPE", "forwardPE", "enterpriseToEbitda", "priceToSalesTrailing12Months", "priceToBook",
    "grossMargins", "operatingMargins", "profitMargins", "returnOnEquity",
    "revenueGrowth", "earningsGrowth", "debtToEquity", "dividendYield", "beta",
]

# Hand-picked peer groups used when Yahoo's industry list is not a good fit
# (e.g. Indian listings, where the industry API returns US companies).
CURATED_PEERS: dict[str, list[str]] = {
    # India - IT services
    **{t: ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS"]
       for t in ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS"]},
    # India - private & PSU banks
    **{t: ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"]
       for t in ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"]},
    # India - energy / conglomerates
    "RELIANCE.NS": ["ONGC.NS", "IOC.NS", "BPCL.NS", "ADANIENT.NS"],
    # India - autos
    **{t: ["TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS"]
       for t in ["TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS"]},
    # US - mega-cap tech (Yahoo's industry lists split these oddly)
    "AAPL": ["MSFT", "GOOGL", "AMZN", "META", "DELL", "HPQ"],
    "MSFT": ["AAPL", "GOOGL", "AMZN", "ORCL", "CRM", "ADBE"],
    "GOOGL": ["MSFT", "META", "AMZN", "AAPL", "SNAP"],
    "GOOG": ["MSFT", "META", "AMZN", "AAPL", "SNAP"],
    "META": ["GOOGL", "SNAP", "PINS", "RDDT", "MSFT"],
    "AMZN": ["WMT", "MSFT", "GOOGL", "BABA", "SHOP"],
    "NVDA": ["AMD", "AVGO", "INTC", "QCOM", "TSM"],
    "TSLA": ["GM", "F", "RIVN", "TM", "BYDDY"],
}

INDIA_SUFFIXES = (".NS", ".BO")


def _history_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None) if getattr(df.index, "tz", None) else pd.to_datetime(df.index)
    rows = []
    for ts, r in df.iterrows():
        rows.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": num(r.get("Open")), "high": num(r.get("High")),
            "low": num(r.get("Low")), "close": num(r.get("Close")),
            "volume": num(r.get("Volume")),
        })
    return [r for r in rows if r["close"] is not None]


def _statement(df: pd.DataFrame | None, rows: dict[str, list[str]], limit: int) -> dict[str, Any]:
    """Pick named rows from a yfinance statement (columns = period end dates, newest first)."""
    if df is None or getattr(df, "empty", True):
        return {"periods": []}
    cols = sorted(df.columns, key=lambda c: pd.Timestamp(c))[-limit:]
    out: dict[str, Any] = {"periods": [pd.Timestamp(c).strftime("%Y-%m-%d") for c in cols]}
    for key, candidates in rows.items():
        series = None
        for name in candidates:
            if name in df.index:
                series = df.loc[name]
                break
        out[key] = [num(series[c]) if series is not None else None for c in cols]
    return out


INCOME_ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "diluted_eps": ["Diluted EPS"],
}
CASHFLOW_ROWS = {
    "operating_cf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
}


def _news(t: yf.Ticker) -> list[dict[str, Any]]:
    items = []
    try:
        for n in (t.news or [])[:20]:
            c = n.get("content", n)
            url = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
            provider = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher")
            pub = c.get("pubDate") or c.get("displayTime")
            if not pub and c.get("providerPublishTime"):
                pub = dt.datetime.fromtimestamp(c["providerPublishTime"], dt.timezone.utc).isoformat()
            if c.get("title"):
                items.append({"title": c.get("title"), "link": url, "published": pub,
                              "source": provider or "Yahoo Finance", "summary": c.get("summary") or "",
                              "feed": "yfinance"})
    except Exception as e:  # noqa: BLE001
        log.warning("news failed: %s", e)
    return items


def _peer_list(ticker: str, info: dict[str, Any], user_peers: list[str] | None) -> tuple[list[str], str]:
    if user_peers:
        return [p for p in user_peers if p and p.upper() != ticker.upper()][:6], "user"
    if ticker.upper() in CURATED_PEERS:
        return [p for p in CURATED_PEERS[ticker.upper()] if p.upper() != ticker.upper()][:6], "curated"
    if ticker.upper().endswith(INDIA_SUFFIXES):
        return [], "none"
    key = info.get("industryKey")
    if key:
        try:
            top = yf.Industry(key).top_companies
            if top is not None and not top.empty:
                syms = [s for s in top.index.tolist() if s.upper() != ticker.upper()]
                return syms[:6], "industry"
        except Exception as e:  # noqa: BLE001
            log.warning("industry peers failed for %s: %s", key, e)
    return [], "none"


def _weekly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    s = pd.Series([r["close"] for r in rows], index=pd.to_datetime([r["date"] for r in rows]))
    w = s.resample("W-FRI").last().dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "close": float(v)} for d, v in w.items()]


def _peer(sym: str, period: str) -> dict[str, Any]:
    t = yf.Ticker(sym)
    out: dict[str, Any] = {"ticker": sym}
    try:
        info = t.info or {}
        out["info"] = {k: info.get(k) for k in PEER_FIELDS}
    except Exception as e:  # noqa: BLE001
        out["info"] = {}
        out["error"] = f"info: {e}"
    try:
        out["weekly"] = _weekly(_history_rows(t.history(period=period, auto_adjust=True)))
    except Exception as e:  # noqa: BLE001
        out["weekly"] = []
        out["error"] = f"history: {e}"
    return out


def benchmark_for(ticker: str) -> str:
    if ticker.upper().endswith(INDIA_SUFFIXES):
        return "^NSEI"
    return os.getenv("DEFAULT_BENCHMARK", "SPY")


def fetch_market(ticker: str, peers: list[str] | None = None, period: str | None = None) -> dict[str, Any]:
    period = period or os.getenv("HISTORY_PERIOD", "2y")
    ticker = ticker.upper().strip()
    errors: list[str] = []
    t = yf.Ticker(ticker)

    try:
        raw_info = t.info or {}
    except Exception as e:  # noqa: BLE001
        raw_info = {}
        errors.append(f"info: {e}")
    info = {k: raw_info.get(k) for k in INFO_FIELDS}

    try:
        history = _history_rows(t.history(period=period, auto_adjust=False))
    except Exception as e:  # noqa: BLE001
        history = []
        errors.append(f"history: {e}")
    if not history:
        raise ValueError(f"No price history returned for '{ticker}'. Check the symbol (e.g. MSFT, INFY.NS).")

    def safe(fn, label):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{label}: {e}")
            return None

    annual = _statement(safe(lambda: t.income_stmt, "income_stmt"), INCOME_ROWS, 4)
    annual_cf = _statement(safe(lambda: t.cashflow, "cashflow"), CASHFLOW_ROWS, 4)
    quarterly = _statement(safe(lambda: t.quarterly_income_stmt, "quarterly_income_stmt"),
                           {"revenue": INCOME_ROWS["revenue"], "net_income": INCOME_ROWS["net_income"],
                            "operating_income": INCOME_ROWS["operating_income"]}, 8)
    # align cash flow onto income periods
    if annual_cf.get("periods"):
        cf_map = {p: i for i, p in enumerate(annual_cf["periods"])}
        for k in CASHFLOW_ROWS:
            annual[k] = [annual_cf[k][cf_map[p]] if p in cf_map else None for p in annual.get("periods", [])]

    rec = safe(lambda: t.recommendations_summary, "recommendations")
    rec_summary = None
    if rec is not None and not getattr(rec, "empty", True):
        r0 = rec.iloc[0].to_dict()
        rec_summary = {k: num(r0.get(k)) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"]}

    peer_syms, peer_source = _peer_list(ticker, raw_info, peers)
    bench = benchmark_for(ticker)
    with ThreadPoolExecutor(max_workers=4) as pool:
        peer_data = list(pool.map(lambda s: _peer(s, "1y"), peer_syms + [bench]))
    bench_data = peer_data.pop() if peer_data else {"ticker": bench, "weekly": []}
    peer_data = [p for p in peer_data if p.get("info") or p.get("weekly")]

    return clean({
        "ticker": ticker,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "info": info,
        "history": history,
        "financials": {"annual": annual, "quarterly": quarterly},
        "recommendations": rec_summary,
        "peers": peer_data,
        "peer_source": peer_source,
        "benchmark": {"ticker": bench, "weekly": bench_data.get("weekly", [])},
        "yahoo_news": _news(t),
        "errors": errors,
    })
