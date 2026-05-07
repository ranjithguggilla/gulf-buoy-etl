#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — Developer one-shot runner.
#
# Usage:
#   ./run.sh                # full pipeline using sample data (no network)
#   ./run.sh --live         # pull from real NDBC + TABS APIs
#   ./run.sh --publish      # also build the monthly package
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODE="${1:-sample}"

if ! command -v gbe &>/dev/null; then
    echo "[ERROR] gbe command not found."
    echo "        Run: pip install -e '.[dev]'"
    exit 1
fi

echo "═══════════════════════════════════════════════════════"
echo " gulf-buoy-etl — developer runner ($MODE)"
echo "═══════════════════════════════════════════════════════"

case "${MODE}" in
    --live)
        gbe run --archive-root archive
        ;;
    --publish)
        gbe run --archive-root archive
        gbe publish "$(date -u +%Y-%m)" --dry-run
        ;;
    sample|*)
        echo "[INFO] Running with bundled sample data (no network calls)..."
        python -m scripts.demo_from_sample
        ;;
esac

echo ""
echo "Pipeline complete. Archive root: $(pwd)/archive/"
