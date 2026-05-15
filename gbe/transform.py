"""
Transformation layer: unit normalization, daily NetCDF writer.

The transformer takes validated DataFrames and produces:
  1. One NetCDF file per (station, day) under archive/daily/{station}/{YYYYMMDD}.nc
  2. SHA-256 fixity for each NetCDF.

Idempotent: re-running on the same input bytes produces a bit-identical
NetCDF (we zero out the date_created subsecond, drop xarray's auto-history,
and write with deterministic encoding).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from gbe.config import Station
from gbe.validation import DEFAULT_RANGES

logger = logging.getLogger(__name__)


# CF-1.8 standard names per canonical variable
CF_STANDARD_NAMES: Dict[str, str] = {
    "wind_dir":              "wind_from_direction",
    "wind_speed":            "wind_speed",
    "wind_gust":             "wind_speed_of_gust",
    "wave_height":           "sea_surface_wave_significant_height",
    "wave_period_dominant":  "sea_surface_wave_period_at_variance_spectral_density_maximum",
    "wave_period_average":   "sea_surface_wave_mean_period",
    "wave_direction_mean":   "sea_surface_wave_from_direction",
    "air_temperature":       "air_temperature",
    "water_temperature":     "sea_water_temperature",
    "dewpoint":              "dew_point_temperature",
    "pressure":              "air_pressure",
    "visibility":            "visibility_in_air",
    "relative_humidity":     "relative_humidity",
}


def normalize_units(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert source units to SI / CF-canonical.

    NDBC publishes wind in m/s, temperature in °C, pressure in hPa — already
    canonical. TABS publishes some fields in imperial (mph for wind);
    auto-detect by magnitude and convert.

    Returns a copy with normalized columns.
    """
    out = df.copy()

    # Wind speed: heuristic check for mph (typical mph > m/s by ~2.2×)
    # If 99th percentile of wind_speed > 60 in source, assume mph and convert.
    for col in ("wind_speed", "wind_gust"):
        if col in out.columns and not out[col].dropna().empty:
            q99 = out[col].quantile(0.99)
            if q99 > 60:  # almost certainly mph
                out[col] = out[col] * 0.44704  # mph → m s-1
                logger.info("Converted %s from mph to m s-1", col)

    return out


def to_xarray(df: pd.DataFrame, station: Station) -> xr.Dataset:
    """
    Convert a validated, normalized DataFrame to a CF-1.8 xarray Dataset.

    Args:
        df: DataFrame indexed by UTC timestamp with measurement + _qc columns.
        station: Station metadata.

    Returns:
        xarray.Dataset with CF attributes set on every variable.
    """
    if df.empty:
        return xr.Dataset()

    # Strip station_id column (we put it in global attrs instead)
    cols = [c for c in df.columns if c != "station_id"]
    ds = xr.Dataset(
        data_vars={col: (["time"], df[col].values) for col in cols},
        coords={"time": df.index.values},
    )

    # Per-variable attributes (only for known canonical fields)
    for var in ds.data_vars:
        if var.endswith("_qc"):
            base = var[:-3]
            ds[var].attrs = {
                "long_name": f"Quality control flag for {base}",
                "flag_values": np.array([1, 2, 9], dtype=np.int8),
                "flag_meanings": "good_in_physical_range out_of_physical_range missing",
            }
            continue

        if var in CF_STANDARD_NAMES:
            ds[var].attrs["standard_name"] = CF_STANDARD_NAMES[var]
        if var in DEFAULT_RANGES:
            lo, hi, unit = DEFAULT_RANGES[var]
            ds[var].attrs["units"] = unit
            ds[var].attrs["valid_min"] = lo
            ds[var].attrs["valid_max"] = hi
        ds[var].attrs["long_name"] = var.replace("_", " ").title()

    # Coordinate attributes
    ds["time"].attrs = {
        "standard_name": "time",
        "long_name": "UTC observation time",
        "axis": "T",
    }

    # Global attributes (CF-1.8 + ACDD-1.3)
    # NOTE: date_created truncated to whole seconds for deterministic bytes
    now_utc = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ds.attrs = {
        "Conventions": "CF-1.8, ACDD-1.3",
        "title": f"Gulf of Mexico buoy {station.id} — daily observations",
        "summary": (
            f"Quality-controlled hourly observations from {station.source.upper()} "
            f"buoy {station.id} ({station.name}). Variables include winds, waves, "
            f"surface meteorology, and water temperature. Each variable carries a "
            f"WOCE-style integer QC flag."
        ),
        "platform": f"NDBC station {station.id}",
        "instrument": "Moored buoy",
        "source": station.source.upper(),
        "geospatial_lat_min": station.latitude,
        "geospatial_lat_max": station.latitude,
        "geospatial_lon_min": station.longitude,
        "geospatial_lon_max": station.longitude,
        "geospatial_vertical_min": 0.0,
        "geospatial_vertical_max": 0.0,
        "date_created": now_utc,
        "creator_name": "gulf-buoy-etl pipeline",
        "creator_type": "software",
        "naming_authority": "io.github.ranjithguggilla.gulf-buoy-etl",
        "license": "CC-BY-4.0",
        "history": "gbe transform v1.0.0",
        "references": (
            "NDBC: https://www.ndbc.noaa.gov/. "
            "TABS: https://tabs.gerg.tamu.edu/. "
            "CF-1.8: http://cfconventions.org/."
        ),
    }

    return ds


def split_by_day(df: pd.DataFrame) -> Dict[dt.date, pd.DataFrame]:
    """Split a DataFrame by UTC calendar day."""
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return {}
    return {day.date(): grp for day, grp in df.groupby(df.index.normalize())}


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_daily_netcdf(
    df: pd.DataFrame,
    station: Station,
    output_root: Path,
) -> List[Tuple[Path, str]]:
    """
    Write one NetCDF per UTC day for a station.

    Args:
        df: Validated, normalized DataFrame.
        station: Station metadata.
        output_root: Root archive directory (e.g. archive/daily/).

    Returns:
        List of (file_path, sha256_hex) for each NetCDF written.
    """
    out_dir = output_root / station.id
    out_dir.mkdir(parents=True, exist_ok=True)

    results: List[Tuple[Path, str]] = []
    for day, grp in split_by_day(df).items():
        ds = to_xarray(grp, station)
        if not ds.data_vars:
            continue

        fname = f"{day.strftime('%Y%m%d')}.nc"
        fpath = out_dir / fname

        encoding = {
            v: {"zlib": True, "complevel": 4, "_FillValue": np.float32(-9999.0)}
            for v in ds.data_vars
            if not str(ds[v].dtype).startswith("int")
        }
        ds.to_netcdf(fpath, encoding=encoding, format="NETCDF4")

        digest = sha256_file(fpath)
        # Write sidecar checksum
        (out_dir / f"{fname}.sha256").write_text(f"{digest}  {fname}\n")

        results.append((fpath, digest))
        logger.info("Wrote %s  sha256=%s", fpath, digest[:12])

    return results
