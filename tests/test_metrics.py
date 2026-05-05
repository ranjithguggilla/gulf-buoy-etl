"""Tests for the Prometheus metrics recorder."""

from gbe.metrics import MetricsRecorder


class TestMetricsRecorder:
    def test_records_per_station_bytes(self):
        m = MetricsRecorder()
        m.record_pull("42002", 1000)
        m.record_pull("42019", 500)
        m.record_pull("42002", 200)
        assert m.bytes_pulled == {"42002": 1200, "42019": 500}
        assert m.total_bytes == 1700

    def test_counts_station_outcomes(self):
        m = MetricsRecorder()
        m.mark_station_ok()
        m.mark_station_ok()
        m.mark_station_fail()
        assert m.stations_ok == 2
        assert m.stations_fail == 1

    def test_prometheus_format(self):
        m = MetricsRecorder()
        m.record_pull("42002", 1000)
        m.files_written = 3
        m.mark_station_ok()
        m.finalize()
        text = m.to_prometheus()

        assert "# HELP gbe_bytes_pulled_total" in text
        assert "# TYPE gbe_bytes_pulled_total counter" in text
        assert 'gbe_bytes_pulled_total{station="42002"} 1000' in text
        assert "gbe_files_written_total 3" in text
        assert "gbe_stations_succeeded_total 1" in text

    def test_write_creates_parent_dirs(self, tmp_path):
        m = MetricsRecorder()
        m.finalize()
        path = tmp_path / "nested" / "metrics.prom"
        m.write(path)
        assert path.is_file()
        assert "gbe_run_duration_seconds" in path.read_text()
