#!/usr/bin/env python3
"""
Generate offline sample fixtures: realistic synthetic NDBC realtime2 + TABS
CSV files, plus an injected gap and one out-of-range spike per station, so
the entire pipeline can be exercised in CI without network.

Fixtures go to data/sample/{station_id}.txt and data/sample/{tabs_alias}.csv.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 7 days of hourly samples
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
HOURS = 24 * 7


def synth_ndbc(station_id: str, lat: float, lon: float) -> str:
    """Generate a realistic NDBC realtime2-format text file."""
    header = (
        "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"
        "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT    hPa  degC  degC  degC  nmi hPa     ft\n"
    )
    rows = []

    for i in range(HOURS):
        t = NOW - timedelta(hours=i)

        # Inject a 4-hour gap on day 3
        if 70 <= i < 74:
            continue

        # Realistic Gulf of Mexico values
        wind_dir = (180 + 30 * random.gauss(0, 1)) % 360
        wind_speed = max(0, 5.5 + 2.0 * random.gauss(0, 1))
        wind_gust = wind_speed * (1.0 + 0.15 * abs(random.gauss(0, 1)))
        wave_height = max(0, 1.2 + 0.4 * random.gauss(0, 1))
        wave_period_dom = max(2.0, 7.0 + 1.0 * random.gauss(0, 1))
        wave_period_avg = wave_period_dom * 0.85
        wave_dir = (170 + 25 * random.gauss(0, 1)) % 360
        pressure = 1015.0 + 4.0 * random.gauss(0, 1)
        air_temp = 26.0 - 0.05 * i + 1.5 * random.gauss(0, 1)
        water_temp = 27.0 + 0.5 * random.gauss(0, 1)
        dewpoint = air_temp - 3.0 - abs(random.gauss(0, 1))
        visibility = 99.0  # MM-equivalent for most NDBC stations
        ptdy = random.gauss(0, 0.5)
        tide = "MM"

        # Inject one out-of-range temperature spike at hour 24
        if i == 24:
            air_temp = 99.9  # clearly nonsense

        rows.append(
            f"{t.year % 100:02d} {t.month:02d} {t.day:02d} {t.hour:02d} {t.minute:02d} "
            f"{int(wind_dir):3d} {wind_speed:4.1f} {wind_gust:4.1f} "
            f"{wave_height:5.2f} {wave_period_dom:5.1f} {wave_period_avg:5.1f} "
            f"{int(wave_dir):3d} {pressure:6.1f} {air_temp:5.1f} {water_temp:5.1f} "
            f"{dewpoint:5.1f} {visibility:4.1f} {ptdy:+5.2f}    {tide}"
        )

    return header + "\n".join(rows) + "\n"


def synth_tabs(alias: str) -> str:
    """Generate a TABS-format CSV (different schema than NDBC)."""
    header = "Date,Time,WindDir,WindSpd,WindGust,AirTemp,BaroPres,RelHum,WaterTemp,WaveHt,DomWavePeriod\n"
    rows = []
    for i in range(HOURS):
        t = NOW - timedelta(hours=i)
        # TABS publishes wind speed in mph (so the normalize_units heuristic kicks in)
        wind_speed_mph = max(0, 12.0 + 4.0 * random.gauss(0, 1))
        wind_gust_mph = wind_speed_mph * 1.2
        rows.append(
            f"{t.strftime('%Y-%m-%d')},{t.strftime('%H:%M:%S')},"
            f"{(180 + 30*random.gauss(0,1))%360:5.1f},"
            f"{wind_speed_mph:5.1f},{wind_gust_mph:5.1f},"
            f"{26.0 + 1.5*random.gauss(0,1):5.1f},"
            f"{1015.0 + 4.0*random.gauss(0,1):6.1f},"
            f"{75.0 + 10*random.gauss(0,1):5.1f},"
            f"{27.0 + 0.5*random.gauss(0,1):5.1f},"
            f"{1.2 + 0.4*random.gauss(0,1):4.2f},"
            f"{7.0 + 1.0*random.gauss(0,1):4.1f}"
        )
    return header + "\n".join(rows) + "\n"


STATIONS = [
    ("42002", 26.055, -93.646, "ndbc", None),
    ("42019", 27.910, -95.345, "tabs", "B"),
    ("42020", 26.967, -96.694, "tabs", "V"),
    ("42035", 29.232, -94.413, "ndbc", None),
]


def main():
    for sid, lat, lon, src, alias in STATIONS:
        if src == "ndbc":
            content = synth_ndbc(sid, lat, lon)
            (OUT_DIR / f"{sid}.txt").write_text(content)
            print(f"  wrote sample/{sid}.txt  ({len(content)} bytes)")
        else:
            content = synth_tabs(alias or sid)
            (OUT_DIR / f"{sid}.csv").write_text(content)
            print(f"  wrote sample/{sid}.csv  ({len(content)} bytes)")
    print(f"\nSample fixtures generated in {OUT_DIR}/")


if __name__ == "__main__":
    main()
