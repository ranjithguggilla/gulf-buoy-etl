"""
NOAA NDBC realtime2 data fetcher and parser.

URL pattern (public, no auth):
    https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt

NDBC fixed-width format (lines starting with '#' are header).
Column order is fixed across stations:
    #YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE

Missing values: "MM" (string sentinel).
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd
import requests

from gbe.retry import retry

logger = logging.getLogger(__name__)

NDBC_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt"
NDBC_TIMEOUT = 30  # seconds
NDBC_MISSING_TOKEN = "MM"

# Column name standardization (raw → canonical)
NDBC_COLUMN_MAP = {
    "WDIR": "wind_dir",
    "WSPD": "wind_speed",
    "GST":  "wind_gust",
    "WVHT": "wave_height",
    "DPD":  "wave_period_dominant",
    "APD":  "wave_period_average",
    "MWD":  "wave_direction_mean",
    "PRES": "pressure",
    "ATMP": "air_temperature",
    "WTMP": "water_temperature",
    "DEWP": "dewpoint",
    "VIS":  "visibility",
    "PTDY": "pressure_tendency",
    "TIDE": "tide_level",
}


@retry(
    exceptions=(requests.RequestException,),
    max_attempts=5,
    base_delay=2.0,
    max_delay=60.0,
)
def fetch_ndbc(station_id: str, timeout: int = NDBC_TIMEOUT) -> str:
    """
    Fetch raw NDBC realtime2 text for a single station.

    Args:
        station_id: 5-character NDBC ID, e.g. "42019".
        timeout: HTTP read timeout (seconds).

    Returns:
        Raw text body (UTF-8).

    Raises:
        requests.HTTPError on permanent 4xx.
        requests.RequestException on persistent transient errors.
    """
    url = NDBC_URL.format(station_id=station_id)
    logger.info("GET %s", url)
    response = requests.get(url, timeout=timeout)

    # 429 is transient — let retry decorator handle it
    if response.status_code == 429:
        raise requests.RequestException("HTTP 429 Too Many Requests")

    response.raise_for_status()
    return response.text


def parse_ndbc_text(raw_text: str, station_id: Optional[str] = None) -> pd.DataFrame:
    """
    Parse NDBC realtime2 text into a typed pandas DataFrame.

    Args:
        raw_text: Raw text body from fetch_ndbc().
        station_id: Optional station ID; added as a column for joining.

    Returns:
        DataFrame indexed by UTC timestamp, columns renamed via NDBC_COLUMN_MAP.
        Missing values ("MM") replaced with NaN.
    """
    lines = raw_text.splitlines()
    if not lines:
        return pd.DataFrame()

    # Find header rows (start with #). NDBC has 2 header lines: column names + units.
    header_lines = [ln for ln in lines if ln.startswith("#")]
    data_lines = [ln for ln in lines if not ln.startswith("#") and ln.strip()]
    if not header_lines or not data_lines:
        return pd.DataFrame()

    # First header line: column names (strip leading '#')
    header_cols = header_lines[0].lstrip("#").split()
    units = header_lines[1].lstrip("#").split() if len(header_lines) > 1 else []

    # Reconstruct a clean text and read as fixed-whitespace
    csv_text = " ".join(header_cols) + "\n" + "\n".join(data_lines)
    df = pd.read_csv(
        io.StringIO(csv_text),
        sep=r"\s+",
        engine="python",
        na_values=[NDBC_MISSING_TOKEN, "999", "99.0", "999.0"],
    )

    # Build a UTC timestamp from YY MM DD hh mm.
    # NDBC publishes either 2-digit (#YY) or 4-digit (#yr) year columns.
    # Auto-expand 2-digit years to 21st century equivalents.
    time_cols = ["YY", "MM", "DD", "hh", "mm"]
    if all(c in df.columns for c in time_cols):
        yy = df["YY"].astype(int)
        yy = yy.where(yy >= 100, yy + 2000)  # 26 -> 2026; 2026 stays 2026
        df["timestamp"] = pd.to_datetime(
            dict(
                year=yy,
                month=df["MM"].astype(int),
                day=df["DD"].astype(int),
                hour=df["hh"].astype(int),
                minute=df["mm"].astype(int),
            ),
            utc=True,
        )
        df = df.drop(columns=time_cols)

    # Rename measurement columns to canonical names
    df = df.rename(columns=NDBC_COLUMN_MAP)

    # Attach station id and units metadata
    if station_id is not None:
        df["station_id"] = station_id
    if units:
        df.attrs["units"] = dict(zip(header_cols, units))
    df.attrs["source"] = "NDBC"

    # Coerce measurement columns to numeric
    for col in df.columns:
        if col not in ("timestamp", "station_id"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.set_index("timestamp").sort_index()
    return df
