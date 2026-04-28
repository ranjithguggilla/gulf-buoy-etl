"""
Top-level Pipeline orchestrator.

Wires together: pull → validate → transform → write daily NetCDF → QC report.
Tracks metrics and produces a single ValidationReport per station per run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from gbe.archive import aggregate_month
from gbe.config import Station, load_stations
from gbe.metrics import MetricsRecorder
from gbe.qc import render_markdown_report, write_qc_report
from gbe.sources import fetch_ndbc, fetch_tabs, parse_ndbc_text, parse_tabs_csv
from gbe.transform import normalize_units, write_daily_netcdf
from gbe.validation import ValidationReport, validate_dataframe

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates one full ETL cycle.

    Usage:
        pipe = Pipeline(stations_yaml="etc/stations.yaml",
                        archive_root=Path("archive"))
        results = pipe.run()
        pipe.write_qc_report(results)
        pipe.metrics.write(Path("archive/metrics.prom"))
    """

    def __init__(
        self,
        stations_yaml: Path | None = None,
        archive_root: Path = Path("archive"),
        raw_root: Path = Path("data/raw"),
    ):
        self.stations: List[Station] = load_stations(stations_yaml) if stations_yaml else load_stations()
        self.archive_root = Path(archive_root)
        self.raw_root = Path(raw_root)
        self.metrics = MetricsRecorder()

    # ── Fetch ────────────────────────────────────────────────────────────────

    def pull_station(self, station: Station) -> str:
        """Fetch raw text for one station; persists to data/raw/{id}/{ts}.txt."""
        if station.source == "ndbc":
            raw = fetch_ndbc(station.id)
        elif station.source == "tabs":
            alias = station.tabs_alias or station.id
            raw = fetch_tabs(alias)
        else:
            raise ValueError(f"Unknown source '{station.source}' for {station.id}")

        self.metrics.record_pull(station.id, len(raw.encode("utf-8")))

        out_dir = self.raw_root / station.id
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out_path = out_dir / f"{ts}.txt"
        out_path.write_text(raw)
        logger.info("Pulled %s → %s (%d bytes)", station.id, out_path, len(raw))
        return raw

    def parse_raw(self, station: Station, raw_text: str) -> pd.DataFrame:
        """Parse raw text → canonical DataFrame."""
        if station.source == "ndbc":
            return parse_ndbc_text(raw_text, station_id=station.id)
        if station.source == "tabs":
            return parse_tabs_csv(raw_text, station_id=station.id)
        raise ValueError(f"Unknown source '{station.source}'")

    # ── End-to-end ───────────────────────────────────────────────────────────

    def process_station(
        self,
        station: Station,
        raw_text: str | None = None,
    ) -> Tuple[ValidationReport, list]:
        """
        Run full pipeline for a single station.

        Args:
            station: Station to process.
            raw_text: If provided, skip the HTTP fetch (used in tests).

        Returns:
            (ValidationReport, list of (Path, sha256) for daily NetCDFs)
        """
        if raw_text is None:
            raw_text = self.pull_station(station)

        df = self.parse_raw(station, raw_text)
        df = normalize_units(df)
        df, report = validate_dataframe(df, station.id)
        daily_files = write_daily_netcdf(df, station, self.archive_root / "daily")

        self.metrics.files_written += len(daily_files)
        self.metrics.mark_station_ok()
        return report, daily_files

    def run(self) -> List[Tuple[Station, ValidationReport, list]]:
        """Process every configured station; return per-station results."""
        results: List[Tuple[Station, ValidationReport, list]] = []
        for station in self.stations:
            try:
                report, files = self.process_station(station)
                results.append((station, report, files))
            except Exception as exc:
                logger.error("Station %s failed: %s", station.id, exc)
                self.metrics.mark_station_fail()
                results.append((
                    station,
                    ValidationReport(station_id=station.id, n_total=0),
                    [],
                ))
        self.metrics.finalize()
        return results

    # ── Reports ──────────────────────────────────────────────────────────────

    def write_qc_report(
        self,
        results: List[Tuple[Station, ValidationReport, list]],
        report_path: Path | None = None,
    ) -> Path:
        """Render and persist the Markdown QC report for this run."""
        metrics_dict = {
            "bytes_pulled": self.metrics.total_bytes,
            "files_written": self.metrics.files_written,
            "stations_ok": self.metrics.stations_ok,
            "stations_fail": self.metrics.stations_fail,
            "duration_s": self.metrics.duration_s,
        }
        md = render_markdown_report(results, metrics_dict)

        if report_path is None:
            stamp = pd.Timestamp.utcnow().strftime("%Y-%m")
            report_path = self.archive_root / "reports" / stamp / "qc-report.md"
        return write_qc_report(report_path, md)

    def aggregate_month(self, month: str) -> Path:
        """Build the monthly submission package for `month` (YYYY-MM)."""
        _, tarball = aggregate_month(
            month=month,
            daily_root=self.archive_root / "daily",
            output_root=self.archive_root / "monthly",
            station_ids=[s.id for s in self.stations],
            changelog_path=Path("CHANGELOG.md") if Path("CHANGELOG.md").is_file() else None,
        )
        return tarball
