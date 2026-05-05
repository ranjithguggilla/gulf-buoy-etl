"""Tests for the station-config loader."""


from gbe.config import DEFAULT_STATIONS, load_stations


class TestDefaultStations:
    def test_four_stations(self):
        assert len(DEFAULT_STATIONS) == 4

    def test_all_have_required_fields(self):
        for s in DEFAULT_STATIONS:
            assert isinstance(s.id, str) and len(s.id) >= 4
            assert s.name
            assert s.source in ("ndbc", "tabs")
            assert -90 <= s.latitude <= 90
            assert -180 <= s.longitude <= 180

    def test_archive_subdir_matches_id(self):
        for s in DEFAULT_STATIONS:
            assert s.archive_subdir == s.id


class TestYamlLoader:
    def test_missing_file_returns_defaults(self, tmp_path):
        stations = load_stations(tmp_path / "does-not-exist.yaml")
        assert stations == DEFAULT_STATIONS

    def test_loads_from_yaml(self, tmp_path):
        yaml_text = """
stations:
  - id: "99999"
    name: "Synthetic station"
    source: "ndbc"
    latitude: 25.0
    longitude: -95.0
"""
        path = tmp_path / "stations.yaml"
        path.write_text(yaml_text)

        stations = load_stations(path)
        assert len(stations) == 1
        assert stations[0].id == "99999"
        assert stations[0].latitude == 25.0
