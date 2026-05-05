"""End-to-end tests using the bundled offline fixtures."""

from pathlib import Path

from gbe.config import DEFAULT_STATIONS
from gbe.pipeline import Pipeline

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "data" / "sample"


class TestPipelineEndToEnd:
    def test_process_station_with_sample_data(self, tmp_path):
        pipe = Pipeline(archive_root=tmp_path, raw_root=tmp_path / "raw")

        # Use 42002 (NDBC). Skip if sample file not generated yet.
        sample_file = SAMPLE / "42002.txt"
        if not sample_file.is_file():
            import pytest
            pytest.skip(f"Sample fixture missing: {sample_file}")

        station = next(s for s in DEFAULT_STATIONS if s.id == "42002")
        raw = sample_file.read_text()
        report, files = pipe.process_station(station, raw_text=raw)

        assert report.n_total > 0
        assert len(files) >= 1
        for path, digest in files:
            assert path.is_file()
            assert len(digest) == 64

    def test_qc_report_renders(self, tmp_path):
        pipe = Pipeline(archive_root=tmp_path)
        results = []
        # Synth a minimal report
        from gbe.validation import ValidationReport
        for s in DEFAULT_STATIONS[:1]:
            results.append((s, ValidationReport(station_id=s.id, n_total=10), []))
        pipe.metrics.finalize()
        path = pipe.write_qc_report(results)
        assert path.is_file()
        text = path.read_text()
        assert "Gulf Buoy ETL" in text
