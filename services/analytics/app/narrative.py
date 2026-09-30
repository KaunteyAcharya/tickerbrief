"""Merges LLM-drafted sections with deterministic fallbacks so a report is always complete."""
from __future__ import annotations

import json
import re
from typing import Any

from .analysis import fmt_money, fmt_pct, fmt_x

SECTIONS = {
    "fundamental": ["business_overview", "financial_performance", "valuation", "peer_positioning", "filings_highlights"],
    "technical": ["trend_and_momentum", "key_levels", "news_sentiment"],
    "summary": ["headline", "executive_summary"],
}
LISTS = {"technical": ["risks", "catalysts"], "summary": ["bull_case", "bear_case", "watch_items"]}
STANCES = ("Constructive", "Neutral", "Cautious")
CONFIDENCE = ("Low", "Medium", "High")

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def parse_llm(raw: Any) -> dict[str, Any]:
    """Accepts an Ollama /api/chat response, a JSON string or a dict and returns a dict (or {})."""
    if raw is None:
        return {}
    if isinstance(raw, dict) and "message" in raw:
        raw = (raw.get("message") or {}).get("content")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    text = _THINK.sub("", raw).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
    return {}


def _s(x: Any, limit: int = 1800) -> str | None:
    if not isinstance(x, str):
        return None
    x = _THINK.sub("", x).strip()
    return x[:limit] if x else None


def _l(x: Any, n: int = 6) -> list[str] | None:
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return None
    out = [_s(i, 400) for i in x]
    out = [i for i in out if i]
    return out[:n] or None


# ----------------------------------------------------------------------------- fallbacks
def fallback(a: dict[str, Any]) -> dict[str, Any]:
    m, pr, f, t, news = a["meta"], a["price"], a["fundamentals"], a["technicals"], a["news"]
    v, p, g, h = f["valuation"], f["profitability"], f["growth"], f["health"]
    cur = m.get("currency") or ""
    rel = {r["metric"]: r for r in a["peers"].get("relative", [])}
    pe_rel = rel.get("pe_forward")
    fil = a["filings"]
    latest = ", ".join(f"{k} on {x['date']}" for k, x in list(fil.get("latest", {}).items())[:3])
    scores = {s["name"]: s["score"] for s in a["scorecard"]}
    avg_score = sum(scores.values()) / len(scores) if scores else 50
    stance = "Constructive" if avg_score >= 60 else "Cautious" if avg_score < 45 else "Neutral"

    return {
        "fundamental": {
            "business_overview": (m.get("business_summary") or f"{m['name']} operates in {m.get('industry') or 'n/a'}.")[:700],
            "financial_performance": (f"Revenue grew {fmt_pct(g['revenue_growth_yoy'])} year over year with an operating margin of "
                                      f"{fmt_pct(p['operating_margin'])} and net margin of {fmt_pct(p['net_margin'])}. "
                                      f"Return on equity is {fmt_pct(p['roe'])}; trailing free cash flow is {fmt_money(h['free_cash_flow'], cur)}."),
            "valuation": (f"The shares trade at {fmt_x(v['pe_forward'])} forward earnings, {fmt_x(v['ev_to_ebitda'])} EV/EBITDA and "
                          f"{fmt_x(v['price_to_sales'])} sales, with a free-cash-flow yield of {fmt_pct(v['fcf_yield'])}."),
            "peer_positioning": (f"Against the peer median forward P/E of {fmt_x(pe_rel['peer_median'])}, the stock trades at a "
                                 f"{'premium' if pe_rel['difference'] > 0 else 'discount'} of {fmt_pct(abs(pe_rel['difference']))}."
                                 if pe_rel else "Peer valuation data was not available for a like-for-like comparison."),
            "filings_highlights": (f"Most recent filings: {latest}." if latest else (fil.get("note") or "No SEC filings found.")),
        },
        "technical": {
            "trend_and_momentum": (f"Technical bias is {t['bias']} (score {t['score']:.0f}/100). RSI(14) is {t['rsi14'] or 0:.0f}; the stock "
                                   f"returned {fmt_pct(pr['returns']['3m'])} over three months and {fmt_pct(pr['returns']['1y'])} over one year."),
            "key_levels": (f"Near-term support around {t['support_60d']:.2f} and resistance near {t['resistance_60d']:.2f}; "
                           f"the 200-day average sits at {t['sma200'] or 0:.2f}."),
            "news_sentiment": (f"Headline tone is {news['overall']} across {news['count']} recent articles "
                               f"({news['counts']['positive']} positive, {news['counts']['negative']} negative)."),
            "risks": a["flags"]["risks"] or ["No rule-based risk flags triggered."],
            "catalysts": ["Next quarterly earnings release and guidance.", "Changes in analyst estimates and price targets."],
        },
        "summary": {
            "headline": f"{m['name']}: {stance.lower()} view on a {t['bias']} tape",
            "executive_summary": (f"{m['name']} ({m['ticker']}) trades at {pr['last']:.2f} {cur}, {fmt_pct(pr['pct_from_high'])} from its "
                                  f"52-week high. The heuristic scorecard averages {avg_score:.0f}/100, led by "
                                  f"{max(scores, key=scores.get) if scores else 'n/a'}. This summary was generated from rules because the "
                                  "language model output was unavailable."),
            "bull_case": a["flags"]["positives"] or ["No rule-based positives triggered."],
            "bear_case": a["flags"]["risks"] or ["No rule-based risk flags triggered."],
            "stance": stance, "confidence": "Low",
            "watch_items": ["Earnings date and guidance", "Moves through the 200-day moving average"],
        },
    }


def build(a: dict[str, Any], llm: dict[str, Any] | None) -> dict[str, Any]:
    """Combine LLM sections (possibly partial / malformed) with fallbacks. Tracks provenance per field."""
    llm = llm or {}
    fb = fallback(a)
    out: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    for sec in ("fundamental", "technical", "summary"):
        src = parse_llm(llm.get(sec))
        out[sec] = {}
        for k in SECTIONS.get(sec, []):
            val = _s(src.get(k))
            out[sec][k] = val or fb[sec][k]
            provenance[f"{sec}.{k}"] = "llm" if val else "rules"
        for k in LISTS.get(sec, []):
            val = _l(src.get(k))
            out[sec][k] = val or fb[sec][k]
            provenance[f"{sec}.{k}"] = "llm" if val else "rules"
    s = parse_llm(llm.get("summary"))
    stance = str(s.get("stance", "")).strip().capitalize()
    conf = str(s.get("confidence", "")).strip().capitalize()
    out["summary"]["stance"] = stance if stance in STANCES else fb["summary"]["stance"]
    out["summary"]["confidence"] = conf if conf in CONFIDENCE else fb["summary"]["confidence"]
    llm_fields = sum(1 for v in provenance.values() if v == "llm")
    out["provenance"] = provenance
    out["llm_coverage"] = round(llm_fields / len(provenance), 2) if provenance else 0
    return out
