#!/usr/bin/env python3
"""
Run the full pipeline against bundled offline fixtures (no network).

Used by `make demo` and `./run.sh`. Exercises:
- parse_ndbc_text / parse_tabs_csv
- normalize_units
- validate_dataframe
- write_daily_netcdf  (writes archive/daily/{station}/*.nc)
- render_markdown_report  (writes archive/reports/{YYYY-MM}/qc-report.md)
- MetricsRecorder.write  (writes archive/metrics.prom)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gbe.config import DEFAULT_STATIONS
from gbe.metrics import MetricsRecorder
from gbe.pipeline import Pipeline
from gbe.qc import render_markdown_report, write_qc_report

REPO = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO / "data" / "sample"


def main():
    pipe = Pipeline(archive_root=REPO / "archive", raw_root=REPO / "data" / "raw")
    pipe.metrics = MetricsRecorder()

    results = []
    for station in DEFAULT_STATIONS:
        if station.source == "ndbc":
            sample_file = SAMPLE_DIR / f"{station.id}.txt"
        else:
            sample_file = SAMPLE_DIR / f"{station.id}.csv"

        if not sample_file.is_file():
            print(f"  SKIP {station.id}: no sample fixture at {sample_file}")
            continue

        raw_text = sample_file.read_text()
        pipe.metrics.record_pull(station.id, len(raw_text.encode("utf-8")))

        report, files = pipe.process_station(station, raw_text=raw_text)
        results.append((station, report, files))
        print(f"  {station.id} ({station.source.upper()})  obs={report.n_total}  files={len(files)}")

    pipe.metrics.finalize()
    metrics_dict = {
        "bytes_pulled": pipe.metrics.total_bytes,
        "files_written": pipe.metrics.files_written,
        "stations_ok": pipe.metrics.stations_ok,
        "stations_fail": pipe.metrics.stations_fail,
        "duration_s": pipe.metrics.duration_s,
    }

    md = render_markdown_report(results, metrics_dict)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m")
    report_path = REPO / "archive" / "reports" / stamp / "qc-report.md"
    write_qc_report(report_path, md)
    print(f"\n  → QC report : {report_path}")

    metrics_path = REPO / "archive" / "metrics.prom"
    pipe.metrics.write(metrics_path)
    print(f"  → Metrics   : {metrics_path}")
    print(f"  → Archive   : {REPO / 'archive' / 'daily'}")


if __name__ == "__main__":
    main()
