#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# nightly.sh — Production cron / systemd entrypoint.
#
# This is the *only* script invoked by the operating system scheduler. It
# must be deterministic, idempotent, and log everything.
#
# Lifecycle:
#   1. Activate the project virtualenv (or rely on system Python with gbe
#      installed in /usr/local).
#   2. cd to the repo root so relative paths in config resolve.
#   3. Run `gbe run` with a lockfile to prevent overlapping cron triggers.
#   4. Tee everything into logs/{YYYY-MM-DD}.log AND rotate old logs.
#   5. Exit with the inner exit code so systemd / cron sees real failures.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="${GBE_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LOG_DIR="${REPO_ROOT}/logs"
LOG_FILE="${LOG_DIR}/$(date -u +%Y-%m-%d).log"
LOCKFILE="${REPO_ROOT}/.nightly.lock"

mkdir -p "${LOG_DIR}"

# Acquire exclusive lock; bail (success) if another instance holds it.
exec 9>"${LOCKFILE}"
if ! flock -n 9; then
    echo "[$(date -u +%FT%TZ)] another instance running — exiting" \
        | tee -a "${LOG_FILE}" >&2
    exit 0
fi

cd "${REPO_ROOT}"

# Optional virtualenv (if .venv/ exists)
if [ -d "${REPO_ROOT}/.venv" ]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.venv/bin/activate"
fi

{
    echo "═════════════════════════════════════════════════════"
    echo " gulf-buoy-etl nightly run"
    echo " UTC : $(date -u +%FT%TZ)"
    echo " host: $(hostname)"
    echo " user: $(id -un)"
    echo " repo: ${REPO_ROOT}"
    echo "═════════════════════════════════════════════════════"
} | tee -a "${LOG_FILE}"

# Run the actual pipeline; tee output for ops review
if gbe run 2>&1 | tee -a "${LOG_FILE}"; then
    RC=0
    echo "[$(date -u +%FT%TZ)] OK" | tee -a "${LOG_FILE}"
else
    RC=$?
    echo "[$(date -u +%FT%TZ)] FAIL rc=${RC}" | tee -a "${LOG_FILE}" >&2
fi

# Rotate logs older than 60 days
find "${LOG_DIR}" -name "*.log" -mtime +60 -delete 2>/dev/null || true

exit "${RC}"
