#!/bin/sh
# Imports (and publishes) the bundled workflow into n8n the first time the stack starts.
# To re-import later (overwrites your edits to this workflow):
#   docker compose run --rm -e FORCE_IMPORT=1 n8n-import
set -e
MARKER=/home/node/.n8n/.rrg_workflow_imported
WORKFLOW_IDS="rrgResearchRpt01 rrgReportForm001"

if [ -f "$MARKER" ] && [ "${FORCE_IMPORT:-0}" != "1" ]; then
  echo "[n8n-import] Workflow already imported - skipping (set FORCE_IMPORT=1 to re-import)."
  exit 0
fi

echo "[n8n-import] Importing workflows from /workflows ..."
n8n import:workflow --separate --input=/workflows
# Publish so the form and webhook are live as soon as n8n starts
for id in $WORKFLOW_IDS; do
  n8n publish:workflow --id="$id" || echo "[n8n-import] Could not publish $id automatically - open it in n8n and click Publish."
done
touch "$MARKER"
echo "[n8n-import] Done."
