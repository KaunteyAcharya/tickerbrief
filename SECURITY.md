# Security

This project is designed to run **locally** and to be published to GitHub without leaking anything private.

## What stays on your machine

| Item | Where it lives | Committed? |
|---|---|---|
| `N8N_ENCRYPTION_KEY`, SEC contact email, any API keys | `.env` | **No** (git-ignored; `.env.example` holds placeholders) |
| n8n database, credentials, execution logs | Docker volume `n8n_data` | **No** |
| Generated reports (JSON + PDF) | `site/reports/` | **No** (git-ignored; only `site/samples/` is committed) |
| Ollama models | Ollama on the host / `ollama_data` volume | **No** |

## Guard rails in this repo

- **Localhost only.** Every published port is bound to `127.0.0.1`, so n8n, the analytics API and the site can't be reached from your network.
- **No credentials in the workflow.** The workflow uses only key-less sources (yfinance, SEC EDGAR, RSS) and a local LLM. Configuration comes from environment variables that n8n reads via `$env`.
- **Sanitized exports.** `scripts/sanitize_workflow.py` strips credential references, pinned data, instance IDs and sharing metadata, and refuses to write a file that still looks like it holds a secret.
- **Secret scanning.** gitleaks runs as a pre-commit hook (`pre-commit install`) and in CI across the full git history.
- **Safe rendering.** The site inserts all report text with `textContent`, only follows `http(s)` links, and is served with a strict Content-Security-Policy (no third-party scripts; ECharts is vendored).
- **Least privilege.** The analytics container runs as an unprivileged user; nginx serves the site read-only.

## Before you push

```bash
git status --ignored            # .env, site/reports/*, n8n data must show as ignored
python scripts/sanitize_workflow.py n8n/workflows/*.json --check
gitleaks git --redact .          # or: pre-commit run --all-files
```

If you edit the workflow in n8n, export it (⋯ → Download) and run it through the sanitizer before committing:

```bash
python scripts/sanitize_workflow.py ~/Downloads/workflow.json -o n8n/workflows/research-report.json
```

## Exposing the stack beyond localhost

Don't, unless you add authentication: put the webhook behind n8n Header Auth, enable n8n user management with a strong password, and serve everything over HTTPS behind a reverse proxy.

## Reporting a vulnerability

Please open a private security advisory on the repository instead of a public issue.
