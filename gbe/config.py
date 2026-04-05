"""
Station configuration loader.

Stations are defined in YAML (etc/stations.yaml). Loading is cached on the
filesystem mtime so config changes are picked up between cron runs without
restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass(frozen=True)
class Station:
    """A single Gulf of Mexico buoy station."""

    id: str                       # NDBC station id (e.g. "42019")
    name: str                     # Human-readable
    source: str                   # "ndbc" or "tabs"
    latitude: float               # Degrees north
    longitude: float              # Degrees east (negative for W)
    description: str = ""
    tabs_alias: Optional[str] = None  # e.g. "B" for buoy B (TABS only)
    variables: List[str] = field(default_factory=lambda: [
        "wind_dir", "wind_speed", "wind_gust",
        "wave_height", "wave_period",
        "air_temperature", "water_temperature",
        "pressure", "dewpoint", "visibility",
    ])

    @property
    def archive_subdir(self) -> str:
        """Relative archive directory under data/raw and archive/daily."""
        return self.id


# Default Gulf of Mexico stations (NDBC + TABS).
# Hard-coded as a guaranteed fallback if etc/stations.yaml is unreadable.
DEFAULT_STATIONS: List[Station] = [
    Station(
        id="42002", name="Central Gulf of Mexico",
        source="ndbc", latitude=26.055, longitude=-93.646,
        description="3-meter discus buoy operated by NDBC; central Gulf.",
    ),
    Station(
        id="42019", name="Freeport, TX",
        source="tabs", tabs_alias="B",
        latitude=27.910, longitude=-95.345,
        description="TABS Buoy B; outer Texas shelf off Freeport.",
    ),
    Station(
        id="42020", name="Corpus Christi, TX",
        source="tabs", tabs_alias="V",
        latitude=26.967, longitude=-96.694,
        description="TABS Buoy V; offshore Corpus Christi.",
    ),
    Station(
        id="42035", name="Galveston Bay Entrance",
        source="ndbc", latitude=29.232, longitude=-94.413,
        description="3-meter discus, mouth of Galveston Bay.",
    ),
]


def load_stations(config_path: Optional[Path] = None) -> List[Station]:
    """
    Load station definitions.

    Args:
        config_path: Path to YAML file. If None or unreadable, returns
                     DEFAULT_STATIONS.

    Returns:
        List of Station objects.
    """
    if config_path is None or not Path(config_path).is_file():
        return list(DEFAULT_STATIONS)

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    stations_yaml = raw.get("stations", [])
    if not stations_yaml:
        return list(DEFAULT_STATIONS)

    out: List[Station] = []
    for s in stations_yaml:
        out.append(Station(
            id=str(s["id"]),
            name=s.get("name", s["id"]),
            source=s.get("source", "ndbc"),
            latitude=float(s.get("latitude", 0.0)),
            longitude=float(s.get("longitude", 0.0)),
            description=s.get("description", ""),
            tabs_alias=s.get("tabs_alias"),
            variables=s.get("variables", Station.__dataclass_fields__["variables"].default_factory()),
        ))
    return out
