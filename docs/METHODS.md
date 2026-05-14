# Technical Methods — gulf-buoy-etl

## 1. Data Sources

### 1.1 NOAA National Data Buoy Center (NDBC)

NDBC's `realtime2` endpoint publishes ~24 hours of recent observations per
station as fixed-width ASCII at the URL

    https://www.ndbc.noaa.gov/data/realtime2/{station_id}.txt

The format consists of two header lines (column names, units) followed by
hourly records. Missing values use the sentinel string `MM`. Variables
include wind direction/speed/gust, significant wave height, dominant and
average wave period, mean wave direction, sea-level pressure, air and water
temperature, dewpoint, visibility, pressure tendency, and tide.

### 1.2 TABS (Texas Automated Buoy System)

The TABS network is operated by the Geochemical and Environmental Research
Group (GERG) at Texas A&M. TABS buoys are labelled by letter (A, B, …, V)
and publish near-real-time CSV at

    https://tabs.gerg.tamu.edu/Tglo/data/buoy{alias}_recent.csv

TABS schema differs from NDBC. The pipeline maps both to a single canonical
schema (`gbe.sources.NDBC_COLUMN_MAP`, `gbe.sources.TABS_COLUMN_MAP`).

## 2. Quality Control

### 2.1 Range gates

Each canonical variable carries a `(min, max, unit)` triple in
`gbe.validation.DEFAULT_RANGES`. Limits follow WMO operational guidance
and NDBC's published valid ranges:

| Variable                  | Min   | Max    | Unit             |
|---------------------------|-------|--------|------------------|
| `wind_dir`                | 0     | 360    | degT             |
| `wind_speed`              | 0     | 100    | m s⁻¹            |
| `wind_gust`               | 0     | 120    | m s⁻¹            |
| `wave_height`             | 0     | 30     | m                |
| `wave_period_*`           | 0     | 30     | s                |
| `wave_direction_mean`     | 0     | 360    | degT             |
| `air_temperature`         | −20   | 50     | °C               |
| `water_temperature`       | −2    | 40     | °C               |
| `dewpoint`                | −30   | 40     | °C               |
| `pressure`                | 900   | 1100   | hPa              |
| `visibility`              | 0     | 50     | km               |
| `relative_humidity`       | 0     | 100    | %                |

Values outside the range receive QC flag 2 (suspect). NaN values receive
QC flag 9 (missing). In-range values receive QC flag 1 (good).

### 2.2 Timestamp checks

- **Monotonicity**: `df.index.is_monotonic_increasing`. Violations are
  documented (the data is still archived; the consumer is informed).
- **Duplicates**: `df.index.duplicated().sum()`. Duplicates are preserved
  in the output (consumer decides whether to aggregate).
- **Gaps**: differences between consecutive timestamps that exceed
  1.5 hours are recorded in `report.gaps_hours`.

### 2.3 Unit normalization

Wind speed normalization uses a magnitude-based heuristic. If the 99th
percentile of `wind_speed` exceeds 60, the values are assumed to be in
miles per hour (which TABS sometimes publishes) and multiplied by
`0.44704` to convert to m s⁻¹. The heuristic is logged.

## 3. Output Format

### 3.1 Daily NetCDF

One file per station per UTC day. CF-1.8 + ACDD-1.3 compliant.

| Attribute            | Source |
|----------------------|--------|
| `Conventions`        | hard-coded `"CF-1.8, ACDD-1.3"` |
| `title`              | f-string with cast id |
| `summary`            | f-string with station + source |
| `platform`           | `NDBC station {id}` |
| `instrument`         | `Moored buoy` |
| `source`             | `NDBC` or `TABS` |
| `geospatial_lat_*`   | from `Station.latitude` |
| `geospatial_lon_*`   | from `Station.longitude` |
| `date_created`       | UTC now, second-precision |
| `creator_name`       | `gulf-buoy-etl pipeline` |
| `license`            | `CC-BY-4.0` |
| `history`            | `gbe transform v1.0.0` |
| `references`         | URLs of NDBC, TABS, CF |

Per-variable attributes: `standard_name` from a lookup table,
`units`, `valid_min`, `valid_max`, `long_name`.

Each `_qc` companion carries:
- `long_name`: "Quality control flag for {var}"
- `flag_values`: `int8 [1, 2, 9]`
- `flag_meanings`: `"good_in_physical_range out_of_physical_range missing"`

### 3.2 Idempotency

Re-running the pipeline on the same parsed DataFrame produces NetCDF files
with identical SHA-256. Achieved by:
- Truncating `date_created` to whole seconds.
- Explicit `encoding` dict in `to_netcdf` (no library-default drift).
- Fixed `history` string, not auto-extended.

### 3.3 Fixity

Each NetCDF gets a sidecar `{name}.nc.sha256` in the format

    {hex_digest}  {filename}

compatible with `sha256sum -c`. The monthly aggregator also produces a
`MANIFEST.sha256` covering all files in the package.

## 4. Monthly Submission Package

Layout of `archive/monthly/gulf-buoy-{YYYY-MM}.tar.gz`:

    gulf-buoy-{YYYY-MM}/
    ├── {station_id}/
    │   ├── {YYYYMMDD}.nc
    │   └── {YYYYMMDD}.nc.sha256
    ├── README.txt           # plain-text description
    ├── MANIFEST.sha256      # aggregated fixity, sha256sum -c compatible
    ├── metadata.xml         # ISO 19115-2 sidecar (stub)
    └── CHANGELOG.md         # copy of repo CHANGELOG

## 5. DOI Minting

Monthly packages are deposited to Zenodo via the REST API
(`POST /api/deposit/depositions`, `PUT /api/files/{bucket}/{filename}`,
`POST /api/deposit/depositions/{id}/actions/publish`). The metadata block
specifies:

- `upload_type`: `dataset`
- `creators`: `[{"name": "Guggilla, Ranjith"}]`
- `license`: `cc-by-4.0`
- `related_identifiers`: NDBC and TABS URLs marked `isDerivedFrom`

Failed deposition attempts are retried with the same exponential-backoff
decorator (`base=3 s`, 4 attempts). When `ZENODO_TOKEN` is unset, the
publisher logs what it would do and exits 0 — allowing CI runs without
secrets.

## 6. Telemetry

`gbe.metrics.MetricsRecorder` emits Prometheus text format suitable for
the `node_exporter` textfile collector. Exposed metrics:

| Metric                                | Type    | Labels      |
|---------------------------------------|---------|-------------|
| `gbe_run_duration_seconds`            | gauge   | —           |
| `gbe_last_run_unixtime`               | gauge   | —           |
| `gbe_files_written_total`             | counter | —           |
| `gbe_stations_succeeded_total`        | counter | —           |
| `gbe_stations_failed_total`           | counter | —           |
| `gbe_bytes_pulled_total`              | counter | `station`   |

## 7. References

- WMO (2019). *Manual on the Observation of Clouds and Other Meteors*.
- NOAA NDBC (2024). *NDBC Technical Document 09-02, Handbook of
  Automated Data Quality Control Checks and Procedures*.
- Guo, Schwehr & Smith (2017). TABS Buoy Network — Texas Coastal Ocean
  Observing.
- CF Metadata Conventions v1.8 (2020). http://cfconventions.org/
- Attribute Convention for Data Discovery 1.3 (2015).
  https://wiki.esipfed.org/ACDD_1.3
- ISO 19115-2:2019 — Geographic information — Metadata.
- FAIR Data Principles (Wilkinson et al., 2016). doi:10.1038/sdata.2016.18
