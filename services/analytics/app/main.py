"""Analytics service: market data, analysis and report publishing for the n8n workflow."""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .analysis import analyze
from .market import fetch_market
from .publish import publish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="Research Report Analytics", version="1.0.0", docs_url="/docs", redoc_url=None)

TICKER_RE = re.compile(r"^[A-Za-z0-9.\-^=&]{1,20}$")


def _check_ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not TICKER_RE.match(t):
        raise HTTPException(422, f"Invalid ticker symbol: {t!r}")
    return t


class AnalyzeIn(BaseModel):
    ticker: str
    market: dict[str, Any]
    filings: dict[str, Any] | None = None
    news: list[dict[str, Any]] | None = None


class PublishIn(BaseModel):
    analysis: dict[str, Any]
    llm: dict[str, Any] | None = Field(default=None, description="Raw LLM outputs keyed fundamental/technical/summary")
    meta: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/market/{ticker}")
def market(ticker: str, peers: str = Query("", description="Comma-separated peer tickers (optional)")) -> dict[str, Any]:
    t = _check_ticker(ticker)
    peer_list = [_check_ticker(p) for p in peers.split(",") if p.strip()][:8]
    try:
        return {"market": fetch_market(t, peer_list or None)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/analyze")
def analyze_route(body: AnalyzeIn) -> dict[str, Any]:
    t = _check_ticker(body.ticker)
    if not body.market.get("history"):
        raise HTTPException(422, "market.history is empty")
    try:
        return {"analysis": analyze(t, body.market, body.filings, body.news)}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/publish")
def publish_route(body: PublishIn) -> dict[str, Any]:
    if "meta" not in body.analysis or "ticker" not in body.analysis.get("meta", {}):
        raise HTTPException(422, "analysis payload is missing meta.ticker")
    return publish(body.analysis, body.llm, body.meta)
