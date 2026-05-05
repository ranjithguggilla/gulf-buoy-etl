"""Parser tests for NDBC + TABS data sources."""

import pandas as pd

from gbe.sources.ndbc import parse_ndbc_text
from gbe.sources.tabs import parse_tabs_csv


class TestNdbcParser:
    def test_parses_header_and_data(self, ndbc_text):
        df = parse_ndbc_text(ndbc_text, station_id="42002")
        assert not df.empty
        assert len(df) == 4
        # canonical column names applied
        assert "wind_speed" in df.columns
        assert "water_temperature" in df.columns
        # timestamp is a DatetimeIndex
        assert isinstance(df.index, pd.DatetimeIndex)
        # values are numeric
        assert df["wind_speed"].dtype.kind == "f"

    def test_records_station_id(self, ndbc_text):
        df = parse_ndbc_text(ndbc_text, station_id="42002")
        assert (df["station_id"] == "42002").all()

    def test_attaches_units_metadata(self, ndbc_text):
        df = parse_ndbc_text(ndbc_text, station_id="42002")
        assert df.attrs.get("source") == "NDBC"
        assert "units" in df.attrs

    def test_returns_empty_on_empty_input(self):
        df = parse_ndbc_text("", station_id="42002")
        assert df.empty

    def test_monotonic_sorted_index(self, ndbc_text):
        df = parse_ndbc_text(ndbc_text, station_id="42002")
        assert df.index.is_monotonic_increasing


class TestTabsParser:
    def test_parses_csv(self, tabs_csv):
        df = parse_tabs_csv(tabs_csv, station_id="42019")
        assert not df.empty
        assert "wind_speed" in df.columns
        assert "water_temperature" in df.columns
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_returns_empty_on_empty_input(self):
        df = parse_tabs_csv("", station_id="42019")
        assert df.empty

    def test_marks_source(self, tabs_csv):
        df = parse_tabs_csv(tabs_csv, station_id="42019")
        assert df.attrs.get("source") == "TABS"
