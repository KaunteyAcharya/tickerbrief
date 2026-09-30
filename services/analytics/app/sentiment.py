"""Headline sentiment: VADER (MIT-licensed) tuned with a small finance vocabulary."""
from __future__ import annotations

import datetime as dt
import html
import re
from email.utils import parsedate_to_datetime
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FINANCE_LEXICON = {
    "beat": 2.0, "beats": 2.0, "tops": 1.6, "surge": 2.2, "surges": 2.2, "soar": 2.4, "soars": 2.4,
    "rally": 1.8, "rallies": 1.8, "jumps": 1.6, "gains": 1.3, "record": 1.2, "upgrade": 2.0,
    "upgraded": 2.0, "outperform": 1.8, "bullish": 2.2, "raises": 1.2, "raised": 1.0, "buyback": 1.2,
    "dividend": 0.6, "strong": 1.2, "growth": 0.8, "profit": 0.9, "partnership": 0.8,
    "miss": -2.0, "misses": -2.0, "missed": -2.0, "plunge": -2.6, "plunges": -2.6, "slump": -2.2,
    "slumps": -2.2, "tumble": -2.2, "tumbles": -2.2, "falls": -1.4, "drops": -1.4, "sinks": -1.8,
    "downgrade": -2.0, "downgraded": -2.0, "underperform": -1.8, "bearish": -2.2, "cuts": -1.3,
    "lawsuit": -1.6, "probe": -1.5, "investigation": -1.6, "recall": -1.6, "layoffs": -1.4,
    "fine": -1.0, "fined": -1.6, "antitrust": -1.2, "warning": -1.5, "weak": -1.3, "loss": -1.4,
    "losses": -1.4, "bankruptcy": -3.0, "fraud": -3.0, "halt": -1.5, "delay": -1.1, "selloff": -2.0,
}

_analyzer: SentimentIntensityAnalyzer | None = None


def analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
        _analyzer.lexicon.update(FINANCE_LEXICON)
    return _analyzer


_TAG = re.compile(r"<[^>]+>")


def strip_html(s: str | None) -> str:
    return html.unescape(_TAG.sub(" ", s or "")).replace("\xa0", " ").strip()


def parse_date(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def label(score: float) -> str:
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


def _norm_title(t: str) -> str:
    # Google News appends " - Publisher"; strip for de-duplication
    t = re.sub(r"\s+-\s+[^-]{2,60}$", "", t)
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def score_news(items: list[dict[str, Any]], max_items: int = 30, max_age_days: int = 45) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    seen: set[str] = set()
    scored: list[dict[str, Any]] = []
    for it in items or []:
        title = strip_html(it.get("title"))
        if not title:
            continue
        key = _norm_title(title)[:90]
        if key in seen:
            continue
        seen.add(key)
        published = parse_date(it.get("published") or it.get("pubDate") or it.get("isoDate"))
        if published and (now - published).days > max_age_days:
            continue
        link = it.get("link") or ""
        if not re.match(r"^https?://", link):
            link = ""
        summary = strip_html(it.get("summary") or it.get("contentSnippet") or it.get("content"))[:400]
        vs = analyzer().polarity_scores(title)
        scored.append({
            "title": title[:300], "link": link, "source": strip_html(it.get("source") or it.get("creator"))[:80] or None,
            "published": published.isoformat() if published else None, "summary": summary,
            "feed": it.get("feed"), "score": round(vs["compound"], 3), "label": label(vs["compound"]),
        })
    scored.sort(key=lambda x: x["published"] or "", reverse=True)
    scored = scored[:max_items]

    n = len(scored)
    counts = {k: sum(1 for s in scored if s["label"] == k) for k in ("positive", "neutral", "negative")}
    avg = round(sum(s["score"] for s in scored) / n, 3) if n else None
    by_day: dict[str, list[float]] = {}
    for s in scored:
        if s["published"]:
            by_day.setdefault(s["published"][:10], []).append(s["score"])
    daily = [{"date": d, "avg": round(sum(v) / len(v), 3), "count": len(v)} for d, v in sorted(by_day.items())]
    return {
        "items": scored, "count": n, "counts": counts, "average": avg,
        "overall": label(avg) if avg is not None else "n/a", "daily": daily,
    }
