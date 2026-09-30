#!/usr/bin/env python3
"""Clean an n8n workflow export before committing it.

Removes anything instance-specific or potentially sensitive:
  * credential references (ids + names)       * pinned test data (pinData)
  * instance ids, version ids, share/owner info * static data (can hold tokens)
and fails loudly if something that looks like a secret is still present.

Usage:
  python scripts/sanitize_workflow.py exported.json -o n8n/workflows/research-report.json
  python scripts/sanitize_workflow.py n8n/workflows/*.json --check     # CI / pre-commit: verify only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DROP_TOP = {"pinData", "staticData", "versionId", "activeVersionId", "shared", "homeProject", "sharedWithProjects",
            "usedCredentials", "createdAt", "updatedAt", "triggerCount", "isArchived", "parentFolder", "scopes",
            "checksum", "versionCounter", "activeVersion"}
DROP_META = {"instanceId"}
DROP_NODE = {"credentials"}

SECRET_PATTERNS = [
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "Groq API key"),
    (re.compile(r"sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"), "OpenAI/Anthropic-style API key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "Slack token"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "Google API key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"), "bearer token"),
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\"\s*:\s*\"[^\"={][^\"]{7,}\""), "hard-coded secret field"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@(?!example\.(?:com|org))[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "email address"),
    (re.compile(r"https?://(?!localhost|127\.0\.0\.1|host\.docker\.internal|analytics|n8n|ollama)"
                r"(?:\d{1,3}\.){3}\d{1,3}"), "hard-coded IP address"),
]


def sanitize(wf: dict) -> dict:
    wf = {k: v for k, v in wf.items() if k not in DROP_TOP}
    if isinstance(wf.get("meta"), dict):
        wf["meta"] = {k: v for k, v in wf["meta"].items() if k not in DROP_META}
    wf["active"] = False
    wf["pinData"] = {}
    for n in wf.get("nodes", []):
        for k in DROP_NODE:
            n.pop(k, None)
    return wf


def find_secrets(text: str) -> list[str]:
    hits = []
    for rx, label in SECRET_PATTERNS:
        for m in rx.finditer(text):
            hits.append(f"{label}: {m.group(0)[:12]}…")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="write the cleaned workflow here (single input only)")
    ap.add_argument("--check", action="store_true", help="only verify; exit 1 if anything needs cleaning")
    args = ap.parse_args()

    failed = False
    for path in args.files:
        raw = path.read_text(encoding="utf-8")
        wf = json.loads(raw)
        clean = sanitize(wf)
        out_text = json.dumps(clean, indent=2, ensure_ascii=False) + "\n"
        secrets = find_secrets(out_text)
        if secrets:
            failed = True
            print(f"✗ {path}: possible secrets found:\n  - " + "\n  - ".join(secrets), file=sys.stderr)
        if args.check:
            removed = sorted(set(wf) - set(clean)) + (["credentials"] if any("credentials" in n for n in wf.get("nodes", [])) else [])
            if removed or wf.get("pinData") or (wf.get("meta") or {}).get("instanceId"):
                failed = True
                print(f"✗ {path}: not sanitized (contains {', '.join(removed) or 'pinData/instanceId'}). "
                      f"Run: python scripts/sanitize_workflow.py {path} -o {path}", file=sys.stderr)
            elif not secrets:
                print(f"✓ {path}")
            continue
        target = args.output or path
        target.write_text(out_text, encoding="utf-8")
        print(f"✓ wrote sanitized workflow to {target}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
