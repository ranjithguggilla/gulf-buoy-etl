"""Tests for unit normalization and NetCDF writer."""

import tempfile
from pathlib import Path

import pandas as pd
import xarray as xr

from gbe.config import Station
from gbe.transform import (
    normalize_units,
    sha256_file,
    split_by_day,
    to_xarray,
    write_daily_netcdf,
)
from gbe.validation import validate_dataframe

STATION = Station(
    id="42002", name="Test Buoy", source="ndbc",
    latitude=26.0, longitude=-93.5,
)


class TestUnitNormalization:
    def test_no_op_if_already_si(self, sample_df):
        out = normalize_units(sample_df)
        # Wind speed already in m/s (5.5) → unchanged
        assert out["wind_speed"].iloc[0] == sample_df["wind_speed"].iloc[0]

    def test_converts_mph_to_ms(self, sample_df):
        df = sample_df.copy()
        df["wind_speed"] = 80.0  # clearly mph
        out = normalize_units(df)
        assert out["wind_speed"].iloc[0] < 40.0  # ~36 m/s


class TestXarrayConversion:
    def test_basic_dataset_construction(self, sample_df):
        ds = to_xarray(sample_df, STATION)
        assert isinstance(ds, xr.Dataset)
        assert "wind_speed" in ds.data_vars
        assert "time" in ds.coords

    def test_cf_global_attributes(self, sample_df):
        ds = to_xarray(sample_df, STATION)
        assert "CF-1.8" in ds.attrs["Conventions"]
        assert "ACDD-1.3" in ds.attrs["Conventions"]
        assert ds.attrs["geospatial_lat_min"] == STATION.latitude
        assert ds.attrs["platform"] == f"NDBC station {STATION.id}"

    def test_qc_flag_attributes(self, sample_df):
        df, _ = validate_dataframe(sample_df, station_id=STATION.id)
        ds = to_xarray(df, STATION)
        assert "wind_speed_qc" in ds.data_vars
        attrs = ds["wind_speed_qc"].attrs
        assert "flag_meanings" in attrs
        assert "flag_values" in attrs

    def test_empty_input_returns_empty(self):
        ds = to_xarray(pd.DataFrame(), STATION)
        assert not ds.data_vars


class TestDailySplitter:
    def test_splits_by_utc_date(self):
        idx = pd.to_datetime([
            "2026-05-13 23:00", "2026-05-14 00:00", "2026-05-14 12:00",
            "2026-05-15 00:00",
        ], utc=True)
        df = pd.DataFrame({"wind_speed": [1, 2, 3, 4]}, index=idx)
        groups = split_by_day(df)
        assert len(groups) == 3


class TestNetCDFWriter:
    def test_writes_one_file_per_day(self, sample_df):
        df, _ = validate_dataframe(sample_df, station_id=STATION.id)
        with tempfile.TemporaryDirectory() as tmp:
            files = write_daily_netcdf(df, STATION, Path(tmp))
            # All 24 hours fall on one UTC day → 1 file
            assert len(files) == 1
            path, digest = files[0]
            assert path.suffix == ".nc"
            assert len(digest) == 64
            # Sidecar exists
            assert (path.with_suffix(".nc.sha256")).is_file()

    def test_netcdf_loads_back(self, sample_df):
        df, _ = validate_dataframe(sample_df, station_id=STATION.id)
        with tempfile.TemporaryDirectory() as tmp:
            files = write_daily_netcdf(df, STATION, Path(tmp))
            ds = xr.open_dataset(files[0][0])
            assert "wind_speed" in ds.data_vars
            assert ds.attrs["platform"].startswith("NDBC")
            ds.close()

    def test_sha256_matches_file(self, sample_df, tmp_path):
        df, _ = validate_dataframe(sample_df, station_id=STATION.id)
        files = write_daily_netcdf(df, STATION, tmp_path)
        path, digest = files[0]
        assert sha256_file(path) == digest
