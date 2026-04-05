"""
gulf-buoy-etl — Autonomous ETL for Texas/Gulf of Mexico buoy data.

Public API:
- Station: dataclass describing a single buoy station
- Pipeline: orchestrator for pull → validate → transform → qc-report → publish
- MetricsRecorder: Prometheus text-format metrics emitter
"""

__version__ = "1.0.0"
__author__ = "Ranjith Guggilla"

from gbe.config import Station, load_stations
from gbe.metrics import MetricsRecorder
from gbe.pipeline import Pipeline

__all__ = ["Station", "load_stations", "MetricsRecorder", "Pipeline"]
