import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app import indicators as ind
from app.analysis import analyze
from app.main import app
from app.narrative import build, parse_llm
from app.sentiment import score_news


def test_rsi_bounds_and_trend():
    up = pd.Series(np.linspace(1, 100, 100))
    assert ind.rsi(up).iloc[-1] == 100
    rng = np.random.default_rng(0)
    r = ind.rsi(pd.Series(100 + rng.normal(0, 1, 300).cumsum())).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_macd_hist_is_line_minus_signal():
    s = pd.Series(np.sin(np.linspace(0, 20, 300)) * 10 + 100)
    m = ind.macd(s).dropna()
    assert np.allclose(m["hist"], m["macd"] - m["signal"])


def test_max_drawdown():
    assert ind.max_drawdown(pd.Series([100, 120, 60, 90])) == -0.5


def test_news_dedupe_and_link_sanitising(news):
    out = score_news(news, max_age_days=10_000)
    titles = [i["title"] for i in out["items"]]
    assert len(titles) == 3  # the two "beats earnings" headlines collapse into one
    assert all(i["link"] == "" or i["link"].startswith("https://") for i in out["items"])
    assert out["counts"]["negative"] >= 1 and out["counts"]["positive"] >= 1


def test_analyze_shape(market, news, filings):
    a = analyze("DEMO", market, filings, news)
    assert a["meta"]["name"] == "Demo Corp"
    assert len(a["series"]["dates"]) == 252
    assert 0 <= a["technicals"]["score"] <= 100
    assert a["peers"]["rows"][0]["is_subject"]
    assert a["peers"]["medians"]["pe_forward"] == 26  # median of 20,23,26,29,32
    assert {s["name"] for s in a["scorecard"]} >= {"Valuation", "Quality", "Momentum"}
    assert a["filings"]["latest"]["10-K"]["date"] == "2026-07-30"
    assert abs(a["fundamentals"]["dividend"]["yield"] - 0.007) < 1e-9  # percent input normalised
    assert "Demo Corp" in a["llm_briefs"]["fundamentals"]
    json.dumps(a)  # JSON-safe (no NaN / numpy types)


def test_narrative_falls_back_and_accepts_llm(market, news, filings):
    a = analyze("DEMO", market, filings, news)
    fb = build(a, None)
    assert fb["llm_coverage"] == 0 and fb["summary"]["stance"] in ("Constructive", "Neutral", "Cautious")
    llm = {"summary": {"message": {"content": '<think>hmm</think>{"headline": "H", "executive_summary": "E", '
                                              '"bull_case": ["a"], "bear_case": ["b"], "stance": "cautious", '
                                              '"confidence": "high", "watch_items": ["w"]}'}},
           "fundamental": "not json at all", "technical": None}
    n = build(a, llm)
    assert n["summary"]["headline"] == "H" and n["summary"]["stance"] == "Cautious" and n["summary"]["confidence"] == "High"
    assert n["provenance"]["fundamental.valuation"] == "rules"
    assert 0 < n["llm_coverage"] < 1


def test_parse_llm_variants():
    assert parse_llm('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_llm("text before {\"a\": 2} after") == {"a": 2}
    assert parse_llm(None) == {}


def test_api_analyze_and_publish(tmp_path, monkeypatch, market, news, filings):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}
    assert c.get("/market/bad ticker!").status_code == 422
    r = c.post("/analyze", json={"ticker": "DEMO", "market": market, "filings": filings, "news": news})
    assert r.status_code == 200, r.text
    analysis = r.json()["analysis"]
    p = c.post("/publish", json={"analysis": analysis, "llm": {}, "meta": {"model": "test"}})
    assert p.status_code == 200, p.text
    out = p.json()
    folder = tmp_path / out["id"]
    assert (folder / "report.json").exists()
    assert (folder / "report.pdf").exists() and (folder / "report.pdf").stat().st_size > 20_000, out.get("pdf_error")
    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx["reports"][0]["id"] == out["id"]
    assert "llm_briefs" not in json.loads((folder / "report.json").read_text())["analysis"]
