"""
Prometheus text-format metrics recorder.

Each pipeline run emits a metrics.prom file in the archive root:

    # HELP gbe_run_duration_seconds Duration of the most recent pipeline run.
    # TYPE gbe_run_duration_seconds gauge
    gbe_run_duration_seconds 41.85

    # HELP gbe_bytes_pulled_total Cumulative bytes pulled across stations.
    # TYPE gbe_bytes_pulled_total counter
    gbe_bytes_pulled_total{station="42002"} 12348
    gbe_bytes_pulled_total{station="42019"} 11203
    ...

Scrapeable by a sidecar Prometheus node-exporter textfile collector. No
external dependencies — plain ASCII output.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class MetricsRecorder:
    """In-memory metrics for a single pipeline run."""

    start_ts: float = field(default_factory=time.time)
    bytes_pulled: Dict[str, int] = field(default_factory=dict)
    files_written: int = 0
    stations_ok: int = 0
    stations_fail: int = 0
    last_run_unixtime: float = 0.0

    def record_pull(self, station_id: str, n_bytes: int) -> None:
        self.bytes_pulled[station_id] = self.bytes_pulled.get(station_id, 0) + n_bytes

    def mark_station_ok(self) -> None:
        self.stations_ok += 1

    def mark_station_fail(self) -> None:
        self.stations_fail += 1

    def finalize(self) -> None:
        self.last_run_unixtime = time.time()

    @property
    def duration_s(self) -> float:
        return time.time() - self.start_ts

    @property
    def total_bytes(self) -> int:
        return sum(self.bytes_pulled.values())

    def to_prometheus(self) -> str:
        """Render as Prometheus text format."""
        lines = []

        lines += [
            "# HELP gbe_run_duration_seconds Duration of the most recent pipeline run.",
            "# TYPE gbe_run_duration_seconds gauge",
            f"gbe_run_duration_seconds {self.duration_s:.4f}",
            "",
            "# HELP gbe_last_run_unixtime UTC unix timestamp of the most recent run.",
            "# TYPE gbe_last_run_unixtime gauge",
            f"gbe_last_run_unixtime {self.last_run_unixtime:.0f}",
            "",
            "# HELP gbe_files_written_total NetCDF files produced this run.",
            "# TYPE gbe_files_written_total counter",
            f"gbe_files_written_total {self.files_written}",
            "",
            "# HELP gbe_stations_succeeded_total Stations completing successfully.",
            "# TYPE gbe_stations_succeeded_total counter",
            f"gbe_stations_succeeded_total {self.stations_ok}",
            "",
            "# HELP gbe_stations_failed_total Stations failing after all retries.",
            "# TYPE gbe_stations_failed_total counter",
            f"gbe_stations_failed_total {self.stations_fail}",
            "",
            "# HELP gbe_bytes_pulled_total Raw bytes pulled from each station.",
            "# TYPE gbe_bytes_pulled_total counter",
        ]
        for station, n in sorted(self.bytes_pulled.items()):
            lines.append(f'gbe_bytes_pulled_total{{station="{station}"}} {n}')
        lines.append("")
        return "\n".join(lines)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_prometheus())
