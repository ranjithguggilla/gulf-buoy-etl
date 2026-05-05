"""Tests for QC report rendering."""


from gbe.config import Station
from gbe.qc import compute_uptime_pct, render_markdown_report, write_qc_report
from gbe.validation import ValidationReport

STATION = Station(
    id="42002", name="Test Buoy", source="ndbc",
    latitude=26.0, longitude=-93.5,
)


class TestUptimeCalc:
    def test_full_uptime(self):
        rep = ValidationReport(station_id="42002", n_total=168)
        assert compute_uptime_pct(rep, expected_hours=168) == 100.0

    def test_half_uptime(self):
        rep = ValidationReport(station_id="42002", n_total=84)
        assert compute_uptime_pct(rep, expected_hours=168) == 50.0

    def test_capped_at_100(self):
        rep = ValidationReport(station_id="42002", n_total=999)
        assert compute_uptime_pct(rep, expected_hours=168) == 100.0

    def test_zero_expected(self):
        rep = ValidationReport(station_id="42002", n_total=10)
        assert compute_uptime_pct(rep, expected_hours=0) == 0.0


class TestMarkdownReport:
    def test_renders_summary_table(self):
        rep = ValidationReport(
            station_id="42002", n_total=168,
            n_in_range={"wind_speed": 168},
            n_out_of_range={"wind_speed": 0},
            n_missing={"wind_speed": 0},
        )
        md = render_markdown_report(
            [(STATION, rep, [])],
            metrics={
                "bytes_pulled": 1024, "files_written": 1,
                "stations_ok": 1, "stations_fail": 0, "duration_s": 1.5,
            },
        )
        assert "# Gulf Buoy ETL — QC Report" in md
        assert "42002" in md
        assert "Test Buoy" in md
        assert "wind_speed" in md

    def test_writes_to_disk(self, tmp_path):
        path = tmp_path / "sub" / "report.md"
        write_qc_report(path, "# hi")
        assert path.read_text() == "# hi"
