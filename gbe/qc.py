"""
QC report generation (Markdown).

A QC report for a fetch cycle covers, per station:
- Total observations pulled
- Time span (first / last UTC timestamp)
- Operational uptime (% of expected hourly samples present)
- Variables with out-of-range values
- Detected data gaps (start → end → duration hours)
- SHA-256 fixity of every produced NetCDF
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from jinja2 import Template

from gbe.validation import ValidationReport

logger = logging.getLogger(__name__)


QC_TEMPLATE = """# Gulf Buoy ETL — QC Report

**Generated:** {{ generated_at }}
**Pipeline version:** {{ version }}
**Stations processed:** {{ n_stations }}

---

## Summary

| Station | Source | Observations | First Sample (UTC) | Last Sample (UTC) | Uptime % | Max Gap (h) |
|---------|--------|--------------|--------------------|-------------------|----------|-------------|
{% for row in summary_rows -%}
| {{ row.id }} | {{ row.source }} | {{ row.n_total }} | {{ row.first }} | {{ row.last }} | {{ "%.1f"|format(row.uptime_pct) }} | {{ "%.1f"|format(row.max_gap_h) }} |
{% endfor %}

---

## Per-Station Detail

{% for s in stations %}
### Station {{ s.id }} — {{ s.name }}

**Source:** `{{ s.source }}`
**Position:** {{ "%.3f"|format(s.latitude) }}°N, {{ "%.3f"|format(s.longitude) }}°E
**Observations pulled:** {{ s.n_total }}
**Monotonic timestamps:** {{ "✓" if s.monotonic else "✗" }}
**Duplicate timestamps:** {{ s.duplicates }}

#### Range-check summary

| Variable | In range | Out of range | Missing |
|----------|----------|--------------|---------|
{% for v in s.variables -%}
| `{{ v.name }}` | {{ v.in_range }} | {{ v.out_of_range }} | {{ v.missing }} |
{% endfor %}

{% if s.gaps -%}
#### Detected gaps (≥ 1.5 h)

{% for g in s.gaps -%}
- {{ "%.1f"|format(g) }} h
{% endfor %}
{% else -%}
*No gaps ≥ 1.5 h detected.*
{% endif %}

#### Archive files written

{% for f in s.files -%}
- `{{ f.path }}`  SHA-256 `{{ f.sha256[:16] }}...`
{% endfor %}

---
{% endfor %}

## Pipeline metrics

| Metric | Value |
|--------|-------|
| Total bytes pulled | {{ metrics.bytes_pulled }} |
| Total NetCDFs written | {{ metrics.files_written }} |
| Stations succeeded | {{ metrics.stations_ok }} |
| Stations failed | {{ metrics.stations_fail }} |
| Run duration (s) | {{ "%.2f"|format(metrics.duration_s) }} |

*This report was produced by `gbe qc-report`.*
"""


@dataclass
class StationDetail:
    """Per-station detail block for the Markdown template."""

    id: str
    name: str
    source: str
    latitude: float
    longitude: float
    n_total: int
    monotonic: bool
    duplicates: int
    first: str
    last: str
    uptime_pct: float
    max_gap_h: float
    variables: List[Dict] = field(default_factory=list)
    gaps: List[float] = field(default_factory=list)
    files: List[Dict] = field(default_factory=list)


def compute_uptime_pct(
    report: ValidationReport,
    expected_hours: int = 168,  # 7 days
) -> float:
    """
    Operational uptime: fraction of expected hourly samples that arrived.

    Capped at 100% (some stations report sub-hourly).
    """
    if expected_hours == 0:
        return 0.0
    return min(100.0, 100.0 * report.n_total / expected_hours)


def render_markdown_report(
    reports: List[Tuple],   # List of (Station, ValidationReport, [files])
    metrics: Dict,
    version: str = "1.0.0",
) -> str:
    """
    Render the Markdown QC report.

    Args:
        reports: List of (Station, ValidationReport, files) tuples.
                 files is a list of (Path, sha256_hex).
        metrics: Dict with bytes_pulled, files_written, stations_ok,
                 stations_fail, duration_s.
        version: Pipeline version.

    Returns:
        Rendered Markdown string.
    """
    summary_rows = []
    stations = []

    for station, report, files in reports:
        uptime = compute_uptime_pct(report)
        max_gap = max(report.gaps_hours) if report.gaps_hours else 0.0
        first = "—"
        last = "—"

        summary_rows.append({
            "id": station.id,
            "source": station.source.upper(),
            "n_total": report.n_total,
            "first": first,
            "last": last,
            "uptime_pct": uptime,
            "max_gap_h": max_gap,
        })

        variables = []
        for v_name in sorted(set(report.n_in_range.keys()) |
                              set(report.n_out_of_range.keys()) |
                              set(report.n_missing.keys())):
            variables.append({
                "name": v_name,
                "in_range": report.n_in_range.get(v_name, 0),
                "out_of_range": report.n_out_of_range.get(v_name, 0),
                "missing": report.n_missing.get(v_name, 0),
            })

        stations.append(StationDetail(
            id=station.id,
            name=station.name,
            source=station.source.upper(),
            latitude=station.latitude,
            longitude=station.longitude,
            n_total=report.n_total,
            monotonic=report.monotonic_timestamps,
            duplicates=report.duplicate_timestamps,
            first=first,
            last=last,
            uptime_pct=uptime,
            max_gap_h=max_gap,
            variables=variables,
            gaps=report.gaps_hours,
            files=[{"path": str(p), "sha256": h} for p, h in files],
        ))

    template = Template(QC_TEMPLATE, trim_blocks=True, lstrip_blocks=True)
    return template.render(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        version=version,
        n_stations=len(reports),
        summary_rows=summary_rows,
        stations=stations,
        metrics=metrics,
    )


def write_qc_report(
    path: Path,
    content: str,
) -> Path:
    """Write the QC Markdown report to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    logger.info("QC report written to %s", path)
    return path
