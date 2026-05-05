"""Tests for range / timestamp / gap validation."""

import numpy as np
import pandas as pd

from gbe.validation import DEFAULT_RANGES, validate_dataframe


class TestRangeChecks:
    def test_in_range_values_flagged_good(self, sample_df):
        df, report = validate_dataframe(sample_df, station_id="42002")
        # All values are physically valid → all qc flags == 1
        for col in ["wind_speed", "water_temperature", "pressure"]:
            qc_col = f"{col}_qc"
            assert qc_col in df.columns
            assert (df[qc_col] == 1).all()

    def test_out_of_range_value_flagged_2(self, sample_df):
        df = sample_df.copy()
        df.loc[df.index[0], "air_temperature"] = 99.9  # nonsense
        out, report = validate_dataframe(df, station_id="42002")
        assert out["air_temperature_qc"].iloc[0] == 2
        assert report.n_out_of_range["air_temperature"] == 1

    def test_nan_flagged_missing(self, sample_df):
        df = sample_df.copy()
        df.loc[df.index[0], "wave_height"] = np.nan
        out, report = validate_dataframe(df, station_id="42002")
        assert out["wave_height_qc"].iloc[0] == 9
        assert report.n_missing["wave_height"] == 1

    def test_unknown_column_not_flagged(self, sample_df):
        df = sample_df.copy()
        df["custom_field"] = 42.0
        out, _ = validate_dataframe(df, station_id="42002")
        # No QC column added for unknown variables
        assert "custom_field_qc" not in out.columns


class TestTimestampChecks:
    def test_monotonic_true_for_sorted(self, sample_df):
        _, report = validate_dataframe(sample_df, station_id="42002")
        assert report.monotonic_timestamps

    def test_duplicates_counted(self, sample_df):
        df = pd.concat([sample_df, sample_df.iloc[[0]]])
        _, report = validate_dataframe(df, station_id="42002")
        assert report.duplicate_timestamps >= 1


class TestGapDetection:
    def test_detects_gap(self, sample_df):
        # Drop hours 5-9 to create a 5-hour gap
        df = sample_df.drop(sample_df.index[5:10])
        _, report = validate_dataframe(df, station_id="42002")
        assert len(report.gaps_hours) >= 1
        assert max(report.gaps_hours) >= 4.0

    def test_no_gap_for_continuous(self, sample_df):
        _, report = validate_dataframe(sample_df, station_id="42002")
        assert report.gaps_hours == []


class TestReportSerialization:
    def test_to_dict_has_expected_keys(self, sample_df):
        _, report = validate_dataframe(sample_df, station_id="42002")
        d = report.to_dict()
        for k in ("station_id", "n_total", "n_in_range", "n_out_of_range",
                  "monotonic_timestamps", "max_gap_hours"):
            assert k in d


class TestDefaultRanges:
    def test_all_canonical_variables_have_units(self):
        for var, (lo, hi, unit) in DEFAULT_RANGES.items():
            assert isinstance(lo, (int, float))
            assert isinstance(hi, (int, float))
            assert hi > lo
            assert isinstance(unit, str) and unit
