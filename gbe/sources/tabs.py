"""
TABS (Texas Automated Buoy System, GERG/Texas A&M) data fetcher.

TABS publishes near-real-time CSV at:
    https://tabs.gerg.tamu.edu/Tglo/data/buoy{alias}_recent.csv

For the purposes of this pipeline, TABS data has the same canonical schema
as NDBC after parsing. The fetcher returns CSV text; the parser returns a
DataFrame indexed by UTC timestamp.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd
import requests

from gbe.retry import retry

logger = logging.getLogger(__name__)

TABS_URL = "https://tabs.gerg.tamu.edu/Tglo/data/buoy{alias}_recent.csv"
TABS_TIMEOUT = 30

# TABS CSV column standardization (raw → canonical)
TABS_COLUMN_MAP = {
    "Date": "_date_raw",
    "Time": "_time_raw",
    "WindDir": "wind_dir",
    "WindSpd": "wind_speed",
    "WindGust": "wind_gust",
    "AirTemp": "air_temperature",
    "BaroPres": "pressure",
    "RelHum": "relative_humidity",
    "WaterTemp": "water_temperature",
    "WaveHt": "wave_height",
    "DomWavePeriod": "wave_period_dominant",
}


@retry(
    exceptions=(requests.RequestException,),
    max_attempts=5,
    base_delay=2.0,
    max_delay=60.0,
)
def fetch_tabs(buoy_alias: str, timeout: int = TABS_TIMEOUT) -> str:
    """
    Fetch raw TABS CSV for a single TABS buoy.

    Args:
        buoy_alias: TABS buoy letter (e.g. "B", "V"). NOT the NDBC ID.
        timeout: HTTP read timeout (seconds).

    Returns:
        Raw CSV body (UTF-8).
    """
    url = TABS_URL.format(alias=buoy_alias)
    logger.info("GET %s", url)
    response = requests.get(url, timeout=timeout)

    if response.status_code == 429:
        raise requests.RequestException("HTTP 429 Too Many Requests")

    response.raise_for_status()
    return response.text


def parse_tabs_csv(raw_text: str, station_id: Optional[str] = None) -> pd.DataFrame:
    """
    Parse TABS CSV into a canonical DataFrame.

    Args:
        raw_text: Raw CSV text from fetch_tabs().
        station_id: Optional NDBC-style station ID for the output table.

    Returns:
        DataFrame indexed by UTC timestamp with canonical column names.
    """
    if not raw_text.strip():
        return pd.DataFrame()

    df = pd.read_csv(io.StringIO(raw_text), na_values=["", "NA", "-999"])

    # Strip whitespace from headers (TABS sometimes pads them)
    df.columns = [c.strip() for c in df.columns]

    # Rename to canonical
    df = df.rename(columns=TABS_COLUMN_MAP)

    # Combine date + time → UTC timestamp
    if "_date_raw" in df.columns and "_time_raw" in df.columns:
        df["timestamp"] = pd.to_datetime(
            df["_date_raw"].astype(str) + " " + df["_time_raw"].astype(str),
            errors="coerce",
            utc=True,
        )
        df = df.drop(columns=["_date_raw", "_time_raw"])
    elif "Date" in df.columns:
        df["timestamp"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df = df.drop(columns=["Date"])

    if station_id is not None:
        df["station_id"] = station_id
    df.attrs["source"] = "TABS"

    # Coerce all measurement columns to numeric
    for col in df.columns:
        if col not in ("timestamp", "station_id"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "timestamp" in df.columns:
        df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df
