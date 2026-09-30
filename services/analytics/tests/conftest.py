import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _walk(n, start, seed, drift=0.0006, vol=0.015):
    rng = np.random.default_rng(seed)
    return start * np.exp(np.cumsum(rng.normal(drift, vol, n)))


def make_market(ticker="DEMO", n=500, seed=7):
    end = dt.date(2026, 9, 30)
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    days = days[::-1]
    close = _walk(n, 100, seed)
    rng = np.random.default_rng(seed + 1)
    history = [{"date": day.isoformat(), "open": c * (1 + rng.normal(0, 0.004)), "high": c * 1.01, "low": c * 0.99,
                "close": c, "volume": float(rng.integers(5e6, 2e7))} for day, c in zip(days, close)]

    def weekly(seed_):
        w = _walk(60, 50, seed_, 0.002, 0.03)
        fr = [end - dt.timedelta(weeks=59 - i) for i in range(60)]
        return [{"date": f.isoformat(), "close": float(v)} for f, v in zip(fr, w)]

    info = {
        "longName": "Demo Corp", "shortName": "Demo", "currency": "USD", "sector": "Technology",
        "industry": "Software - Infrastructure", "country": "United States", "website": "https://example.com",
        "longBusinessSummary": "Demo Corp builds cloud software.", "marketCap": 2.5e12, "enterpriseValue": 2.4e12,
        "trailingPE": 34.0, "forwardPE": 29.0, "trailingPegRatio": 2.1, "priceToBook": 11.0,
        "priceToSalesTrailing12Months": 12.0, "enterpriseToEbitda": 22.0, "grossMargins": 0.69,
        "operatingMargins": 0.44, "profitMargins": 0.36, "returnOnEquity": 0.33, "revenueGrowth": 0.15,
        "earningsGrowth": 0.12, "trailingEps": 12.0, "forwardEps": 14.0, "freeCashflow": 7e10, "totalCash": 8e10,
        "totalDebt": 6e10, "debtToEquity": 35.0, "currentRatio": 1.3, "targetMeanPrice": float(close[-1]) * 1.12,
        "targetHighPrice": float(close[-1]) * 1.4, "targetLowPrice": float(close[-1]) * 0.8,
        "recommendationKey": "buy", "numberOfAnalystOpinions": 40, "dividendYield": 0.7, "beta": 0.9,
    }
    peers = [{"ticker": f"PEER{i}", "info": {"shortName": f"Peer {i}", "marketCap": 1e12 / (i + 1),
                                            "forwardPE": 20 + 3 * i, "trailingPE": 25 + 3 * i, "enterpriseToEbitda": 15 + i,
                                            "priceToSalesTrailing12Months": 6 + i, "grossMargins": 0.5 + 0.03 * i,
                                            "operatingMargins": 0.25 + 0.02 * i, "profitMargins": 0.2, "returnOnEquity": 0.2 + 0.02 * i,
                                            "revenueGrowth": 0.08 + 0.01 * i},
              "weekly": weekly(20 + i)} for i in range(5)]
    return {
        "ticker": ticker, "fetched_at": "2026-09-30T20:00:00+00:00", "info": info, "history": history,
        "financials": {
            "annual": {"periods": ["2023-06-30", "2024-06-30", "2025-06-30", "2026-06-30"],
                       "revenue": [2.1e11, 2.45e11, 2.8e11, 3.2e11], "gross_profit": [1.45e11, 1.7e11, 1.93e11, 2.2e11],
                       "operating_income": [8.8e10, 1.09e11, 1.2e11, 1.4e11], "net_income": [7.2e10, 8.8e10, 1.0e11, 1.15e11],
                       "ebitda": [1.05e11, 1.3e11, 1.5e11, 1.75e11], "diluted_eps": [9.7, 11.8, 13.4, 15.5],
                       "operating_cf": [8.7e10, 1.18e11, 1.36e11, 1.5e11], "capex": [-2.8e10, -4.4e10, -6.4e10, -8e10],
                       "fcf": [5.9e10, 7.4e10, 7.2e10, 7.0e10]},
            "quarterly": {"periods": ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"],
                          "revenue": [7.5e10, 7.9e10, 8.1e10, 8.6e10], "net_income": [2.7e10, 2.8e10, 2.9e10, 3.1e10],
                          "operating_income": [3.3e10, 3.5e10, 3.6e10, 3.8e10]},
        },
        "recommendations": {"strongBuy": 12, "buy": 25, "hold": 6, "sell": 1, "strongSell": 0},
        "peers": peers, "peer_source": "curated", "benchmark": {"ticker": "SPY", "weekly": weekly(99)},
        "yahoo_news": [], "errors": [],
    }


NEWS = [
    {"title": "Demo Corp beats earnings estimates, raises guidance - Reuters", "link": "https://example.com/a",
     "published": "Tue, 29 Sep 2026 14:00:00 GMT", "source": "Reuters"},
    {"title": "Demo Corp shares slump after antitrust probe announced", "link": "https://example.com/b",
     "published": "2026-09-27T10:00:00Z", "source": "Bloomberg"},
    {"title": "Demo Corp beats earnings estimates, raises guidance - Yahoo", "link": "javascript:alert(1)",
     "published": "2026-09-29T15:00:00Z"},
    {"title": "Demo Corp to present at investor conference", "link": "https://example.com/c",
     "published": "2026-09-25T10:00:00Z"},
]

FILINGS = {"cik": "0000000001", "entity": "DEMO CORP", "recent": [
    {"date": "2026-07-30", "form": "10-K", "description": "Annual report", "url": "https://www.sec.gov/x"},
    {"date": "2026-04-28", "form": "10-Q", "description": "Quarterly report", "url": "https://www.sec.gov/y"},
    {"date": "2026-04-28", "form": "8-K", "description": "Results of operations", "url": "https://www.sec.gov/z"},
]}


@pytest.fixture
def market():
    return make_market()


@pytest.fixture
def news():
    return [dict(n) for n in NEWS]


@pytest.fixture
def filings():
    return dict(FILINGS)
