"""
Range and timestamp validators for buoy time-series data.

Every variable carries a physical limit. Values outside the limits are
flagged in a separate _qc column, NOT removed — the validator's job is to
document, not to silently drop data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Physical limits — derived from NDBC operational limits + WMO standards.
# Format: (min, max, unit).
DEFAULT_RANGES: Dict[str, Tuple[float, float, str]] = {
    "wind_dir":              (0.0,    360.0,  "degT"),
    "wind_speed":            (0.0,    100.0,  "m s-1"),
    "wind_gust":             (0.0,    120.0,  "m s-1"),
    "wave_height":           (0.0,     30.0,  "m"),
    "wave_period_dominant":  (0.0,     30.0,  "s"),
    "wave_period_average":   (0.0,     30.0,  "s"),
    "wave_direction_mean":   (0.0,    360.0,  "degT"),
    "air_temperature":       (-20.0,   50.0,  "degree_Celsius"),
    "water_temperature":     (-2.0,    40.0,  "degree_Celsius"),
    "dewpoint":              (-30.0,   40.0,  "degree_Celsius"),
    "pressure":              (900.0,  1100.0, "hPa"),
    "visibility":            (0.0,     50.0,  "km"),
    "relative_humidity":     (0.0,    100.0,  "percent"),
    "pressure_tendency":     (-50.0,   50.0,  "hPa"),
    "tide_level":            (-5.0,     5.0,  "m"),
}


@dataclass
class ValidationReport:
    """Per-variable validation outcome for one fetch cycle."""

    station_id: str
    n_total: int
    n_in_range: Dict[str, int] = field(default_factory=dict)
    n_out_of_range: Dict[str, int] = field(default_factory=dict)
    n_missing: Dict[str, int] = field(default_factory=dict)
    monotonic_timestamps: bool = True
    duplicate_timestamps: int = 0
    gaps_hours: List[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "station_id": self.station_id,
            "n_total": self.n_total,
            "n_in_range": self.n_in_range,
            "n_out_of_range": self.n_out_of_range,
            "n_missing": self.n_missing,
            "monotonic_timestamps": self.monotonic_timestamps,
            "duplicate_timestamps": self.duplicate_timestamps,
            "gaps_hours_count": len(self.gaps_hours),
            "max_gap_hours": float(max(self.gaps_hours)) if self.gaps_hours else 0.0,
        }


def validate_dataframe(
    df: pd.DataFrame,
    station_id: str,
    ranges: Dict[str, Tuple[float, float, str]] = None,
    gap_threshold_hours: float = 1.5,
) -> Tuple[pd.DataFrame, ValidationReport]:
    """
    Run all validators on a buoy DataFrame.

    Args:
        df: Input DataFrame, timestamp-indexed.
        station_id: Station identifier.
        ranges: Per-variable (min, max, unit) limits. Defaults to DEFAULT_RANGES.
        gap_threshold_hours: Minimum gap to record in the report.

    Returns:
        (df_with_qc_columns, ValidationReport)
        df_with_qc_columns has additional {var}_qc int columns:
            1 = good (in range)
            2 = suspect (out of physical range)
            9 = missing
    """
    ranges = ranges or DEFAULT_RANGES
    report = ValidationReport(station_id=station_id, n_total=len(df))

    if df.empty:
        return df, report

    out = df.copy()

    # Timestamp checks
    if isinstance(out.index, pd.DatetimeIndex):
        report.monotonic_timestamps = bool(out.index.is_monotonic_increasing)
        report.duplicate_timestamps = int(out.index.duplicated().sum())
        if len(out.index) > 1:
            diffs = out.index.to_series().diff().dt.total_seconds() / 3600.0
            gaps = diffs[diffs > gap_threshold_hours]
            report.gaps_hours = [float(g) for g in gaps.dropna().tolist()]

    # Range checks per variable
    for var, (lo, hi, _unit) in ranges.items():
        if var not in out.columns:
            continue

        values = out[var]
        missing_mask = values.isna()
        out_of_range_mask = (~missing_mask) & ((values < lo) | (values > hi))
        in_range_mask = (~missing_mask) & (~out_of_range_mask)

        qc = np.full(len(values), 9, dtype=np.int8)  # default missing
        qc[in_range_mask.values] = 1
        qc[out_of_range_mask.values] = 2
        out[f"{var}_qc"] = qc

        report.n_in_range[var] = int(in_range_mask.sum())
        report.n_out_of_range[var] = int(out_of_range_mask.sum())
        report.n_missing[var] = int(missing_mask.sum())

    return out, report
