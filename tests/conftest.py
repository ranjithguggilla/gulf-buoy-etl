"""Shared fixtures for gulf-buoy-etl tests."""

import pandas as pd
import pytest

NDBC_SAMPLE_TEXT = """#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT    hPa  degC  degC  degC  nmi hPa     ft
26 05 14 12 00 180  5.5  7.0  1.20   7.0   6.2 170 1015.2  26.5  27.0  23.1 99.0 +0.20    MM
26 05 14 11 00 175  5.2  6.5  1.10   7.1   6.0 168 1015.5  26.8  27.0  23.3 99.0 +0.15    MM
26 05 14 10 00 178  5.8  7.2  1.30   6.9   6.3 172 1015.1  27.0  27.0  23.5 99.0 +0.10    MM
26 05 14 09 00 182  5.1  6.3  1.15   7.0   6.1 175 1014.9  27.2  26.9  23.4 99.0 +0.05    MM
"""

TABS_SAMPLE_CSV = """Date,Time,WindDir,WindSpd,WindGust,AirTemp,BaroPres,RelHum,WaterTemp,WaveHt,DomWavePeriod
2026-05-14,12:00:00,180.0,12.0,15.0,26.5,1015.2,75.0,27.0,1.20,7.0
2026-05-14,11:00:00,175.0,11.5,14.5,26.8,1015.5,76.0,27.0,1.10,7.1
2026-05-14,10:00:00,178.0,13.0,16.0,27.0,1015.1,74.0,27.0,1.30,6.9
"""


@pytest.fixture
def ndbc_text() -> str:
    return NDBC_SAMPLE_TEXT


@pytest.fixture
def tabs_csv() -> str:
    return TABS_SAMPLE_CSV


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """A small valid hourly buoy DataFrame in canonical schema."""
    idx = pd.date_range("2026-05-14 00:00", periods=24, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "wind_dir":         [180.0] * 24,
            "wind_speed":       [5.5] * 24,
            "wind_gust":        [7.0] * 24,
            "wave_height":      [1.2] * 24,
            "wave_period_dominant": [7.0] * 24,
            "air_temperature":  [26.5] * 24,
            "water_temperature": [27.0] * 24,
            "pressure":         [1015.0] * 24,
        },
        index=idx,
    )
