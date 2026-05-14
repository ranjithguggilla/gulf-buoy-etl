# Changelog

All notable changes to this project are documented here, in reverse
chronological order. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-05-15

### Added
- Initial production release: autonomous Gulf of Mexico buoy ETL.
- `gbe` CLI with `pull`, `validate`, `transform`, `qc-report`, `publish`.
- NDBC realtime2 + TABS source adapters.
- Daily NetCDF (CF-1.8) and monthly tar.gz aggregations with SHA-256 fixity.
- Markdown QC reports (gap, range-violation, uptime tables).
- Exponential-backoff retry on transient network errors.
- Prometheus text-format metrics endpoint.
- Zenodo DOI minting for monthly submission packages (stubbed for sandbox).
- systemd timer + crontab for unattended nightly runs.
- GitHub Pages status dashboard.

### Stations on first run
- 42002 (Central Gulf of Mexico)
- 42019 (Freeport, TX — TABS B)
- 42020 (Corpus Christi, TX — TABS V)
- 42035 (Galveston Bay entrance)
