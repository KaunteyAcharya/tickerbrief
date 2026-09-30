"""Writes a finished report (JSON for the web site + PDF) and maintains the report index."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import charts
from .analysis import fmt_money, fmt_pct, fmt_x
from .narrative import build as build_narrative

TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
_lock = threading.Lock()


def reports_dir() -> Path:
    p = Path(os.getenv("REPORTS_DIR", "./reports"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_id(ticker: str, when: dt.datetime) -> str:
    base = re.sub(r"[^A-Za-z0-9.\-]", "_", ticker.upper())[:20]
    return f"{base}-{when.strftime('%Y%m%d-%H%M%S')}"


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.chmod(tmp, 0o644)  # mkstemp creates 0600; the nginx container must be able to read it
    os.replace(tmp, path)


def render_pdf(report: dict[str, Any], out: Path) -> None:
    from weasyprint import HTML  # imported lazily: heavy import

    a, n = report["analysis"], report["narrative"]
    cur = a["meta"].get("currency") or ""

    def money(v, short=False):
        return fmt_money(v, "" if short else cur)

    def pct(v, sign=False):
        if v is None:
            return "n/a"
        return f"{v * 100:+.1f}%" if sign else fmt_pct(v)

    def num(v):
        return "n/a" if v is None else f"{v:,.2f}"

    html = _env.get_template("report.html.j2").render(
        m=a["meta"], pr=a["price"], t=a["technicals"], f=a["fundamentals"], fin=a["financials"]["annual"],
        peers=a["peers"], news=a["news"], fil=a["filings"], n=n, meta=report["meta"],
        charts=charts.all_charts(a), money=money, pct=pct, x=lambda v, nd=1: fmt_x(v, nd), num=num,
        generated_at=report["generated_at"][:16].replace("T", " ") + " UTC", generated_date=report["generated_at"][:10],
    )
    HTML(string=html, base_url=str(TEMPLATES)).write_pdf(out)


def index_entry(report: dict[str, Any]) -> dict[str, Any]:
    a, n = report["analysis"], report["narrative"]
    scores = [s["score"] for s in a["scorecard"]]
    return {
        "id": report["id"], "ticker": a["meta"]["ticker"], "name": a["meta"]["name"],
        "sector": a["meta"].get("sector"), "industry": a["meta"].get("industry"),
        "generated_at": report["generated_at"], "price": a["price"]["last"], "currency": a["meta"].get("currency"),
        "change_1d_pct": a["price"]["change_1d_pct"], "return_1y": a["price"]["returns"].get("1y"),
        "stance": n["summary"]["stance"], "confidence": n["summary"]["confidence"],
        "headline": n["summary"]["headline"], "technical_bias": a["technicals"]["bias"],
        "news_overall": a["news"]["overall"], "score_avg": round(sum(scores) / len(scores)) if scores else None,
        "model": report["meta"].get("model"), "pdf": f"reports/{report['id']}/report.pdf" if report.get("pdf") else None,
        "spark": [c for c in a["series"]["close"][-60:] if c is not None],
    }


def update_index(entry: dict[str, Any]) -> list[dict[str, Any]]:
    path = reports_dir() / "index.json"
    with _lock:
        try:
            items = json.loads(path.read_text("utf-8")).get("reports", [])
        except (FileNotFoundError, json.JSONDecodeError):
            items = []
        items = [i for i in items if i.get("id") != entry["id"]] + [entry]
        # drop index entries whose folder was deleted by the user
        items = [i for i in items if (reports_dir() / i["id"]).is_dir()]
        items.sort(key=lambda i: i.get("generated_at", ""), reverse=True)
        _atomic_write(path, json.dumps({"reports": items}, indent=1).encode())
    return items


def publish(analysis: dict[str, Any], llm: dict[str, Any] | None, meta: dict[str, Any] | None) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    rid = safe_id(analysis["meta"]["ticker"], now)
    folder = reports_dir() / rid
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o755)
    analysis = {k: v for k, v in analysis.items() if k != "llm_briefs"}
    report = {
        "id": rid, "schema": 1, "generated_at": now.isoformat(timespec="seconds"),
        "meta": {k: v for k, v in (meta or {}).items() if k in ("model", "execution_id", "trigger", "duration_s")},
        "analysis": analysis, "narrative": build_narrative(analysis, llm), "pdf": False,
    }
    pdf_error = None
    try:
        render_pdf(report, folder / "report.pdf")
        os.chmod(folder / "report.pdf", 0o644)
        report["pdf"] = True
    except Exception as e:  # noqa: BLE001 - the web report is still useful without a PDF
        pdf_error = str(e)
    _atomic_write(folder / "report.json", json.dumps(report, indent=1).encode())
    update_index(index_entry(report))
    site = os.getenv("SITE_BASE_URL", "http://localhost:8088").rstrip("/")
    return {
        "id": rid, "report_url": f"{site}/report.html?id={rid}",
        "pdf_url": f"{site}/reports/{rid}/report.pdf" if report["pdf"] else None,
        "stance": report["narrative"]["summary"]["stance"], "headline": report["narrative"]["summary"]["headline"],
        "llm_coverage": report["narrative"]["llm_coverage"], "pdf_error": pdf_error,
    }
