#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# verify_archive.sh — Verify SHA-256 fixity of the entire daily archive.
#
# Walks every {station}/{YYYYMMDD}.nc.sha256 sidecar under archive/daily
# and runs sha256sum -c against it. Prints a one-line PASS/FAIL summary
# at the end and exits non-zero if any file failed.
#
# Used by:
#   - The publish step before tarring up a monthly package
#   - Manual operator sanity-check after disk migration
#   - CI on a fixed sample archive
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ARCHIVE_ROOT="${1:-archive/daily}"

if [ ! -d "${ARCHIVE_ROOT}" ]; then
    echo "ERROR: ${ARCHIVE_ROOT} does not exist" >&2
    exit 2
fi

TOTAL=0
OK=0
FAIL=0

while IFS= read -r -d '' sha; do
    TOTAL=$((TOTAL + 1))
    dir="$(dirname "${sha}")"
    # sha256sum expects to be run from the directory of the sidecar
    if (cd "${dir}" && sha256sum -c "$(basename "${sha}")" >/dev/null 2>&1); then
        OK=$((OK + 1))
    else
        FAIL=$((FAIL + 1))
        echo "FAIL ${sha}" >&2
    fi
done < <(find "${ARCHIVE_ROOT}" -name "*.sha256" -print0)

echo "Checksum verification: ${OK}/${TOTAL} OK, ${FAIL} failed"
if [ "${FAIL}" -gt 0 ]; then
    exit 1
fi
