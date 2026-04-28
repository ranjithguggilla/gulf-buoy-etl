"""
Click CLI: gbe pull / validate / transform / qc-report / publish.

Each subcommand is independently invocable for ops debugging. The combined
nightly flow is `gbe run` (alias for pull + validate + transform + qc-report).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from gbe import __version__
from gbe.pipeline import Pipeline
from gbe.publish import publish_to_zenodo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("gbe")


@click.group()
@click.version_option(version=__version__, prog_name="gbe")
def main():
    """gulf-buoy-etl — autonomous Gulf of Mexico buoy ETL pipeline."""


# ─── pull ────────────────────────────────────────────────────────────────────

@main.command()
@click.option("--stations", type=click.Path(exists=True),
              help="Path to stations.yaml (default: built-in 4-station list).")
@click.option("--raw-root", type=click.Path(), default="data/raw",
              show_default=True, help="Where to drop raw text files.")
def pull(stations: str | None, raw_root: str):
    """Fetch raw realtime2 / TABS text for every configured station."""
    pipe = Pipeline(stations_yaml=Path(stations) if stations else None,
                    raw_root=Path(raw_root))
    for station in pipe.stations:
        try:
            pipe.pull_station(station)
        except Exception as exc:
            logger.error("Pull failed for %s: %s", station.id, exc)
            pipe.metrics.mark_station_fail()
    pipe.metrics.finalize()
    click.echo(f"Pulled {pipe.metrics.stations_ok or len(pipe.stations)} stations "
               f"({pipe.metrics.total_bytes} bytes).")


# ─── validate ────────────────────────────────────────────────────────────────

@main.command()
@click.option("--raw-dir", type=click.Path(exists=True), required=True,
              help="Directory containing a single raw text file to validate.")
@click.option("--station-id", required=True, help="NDBC station id.")
@click.option("--source", type=click.Choice(["ndbc", "tabs"]), default="ndbc",
              show_default=True)
def validate(raw_dir: str, station_id: str, source: str):
    """Run range/timestamp/gap validation on the latest raw file."""
    from gbe.sources import parse_ndbc_text, parse_tabs_csv
    from gbe.transform import normalize_units
    from gbe.validation import validate_dataframe

    raw_files = sorted(Path(raw_dir).glob("*.txt"))
    if not raw_files:
        click.echo(f"No .txt files in {raw_dir}", err=True)
        sys.exit(2)

    text = raw_files[-1].read_text()
    df = parse_ndbc_text(text, station_id) if source == "ndbc" else parse_tabs_csv(text, station_id)
    df = normalize_units(df)
    _, report = validate_dataframe(df, station_id)
    click.echo(json.dumps(report.to_dict(), indent=2, default=str))


# ─── transform ───────────────────────────────────────────────────────────────

@main.command()
@click.option("--stations", type=click.Path(exists=True),
              help="Path to stations.yaml.")
@click.option("--archive-root", type=click.Path(), default="archive",
              show_default=True)
def transform(stations: str | None, archive_root: str):
    """Pull, parse, validate, normalize and write daily NetCDFs."""
    pipe = Pipeline(
        stations_yaml=Path(stations) if stations else None,
        archive_root=Path(archive_root),
    )
    results = pipe.run()
    click.echo(f"Wrote {pipe.metrics.files_written} NetCDF files "
               f"({pipe.metrics.stations_ok}/{len(results)} stations succeeded).")


# ─── qc-report ───────────────────────────────────────────────────────────────

@main.command(name="qc-report")
@click.option("--stations", type=click.Path(exists=True),
              help="Path to stations.yaml.")
@click.option("--archive-root", type=click.Path(), default="archive",
              show_default=True)
@click.option("--output", type=click.Path(), default=None,
              help="Where to write the Markdown report.")
def qc_report(stations: str | None, archive_root: str, output: str | None):
    """Run the full pipeline and emit a Markdown QC report."""
    pipe = Pipeline(
        stations_yaml=Path(stations) if stations else None,
        archive_root=Path(archive_root),
    )
    results = pipe.run()
    path = pipe.write_qc_report(results, report_path=Path(output) if output else None)
    pipe.metrics.write(Path(archive_root) / "metrics.prom")
    click.echo(f"QC report: {path}")
    click.echo(f"Metrics  : {Path(archive_root) / 'metrics.prom'}")


# ─── publish ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("month")  # YYYY-MM
@click.option("--archive-root", type=click.Path(), default="archive",
              show_default=True)
@click.option("--dry-run", is_flag=True, help="Log without calling Zenodo.")
def publish(month: str, archive_root: str, dry_run: bool):
    """Aggregate MONTH (YYYY-MM) and mint a Zenodo DOI."""
    pipe = Pipeline(archive_root=Path(archive_root))
    tarball = pipe.aggregate_month(month)
    doi = publish_to_zenodo(
        tarball=tarball,
        month=month,
        station_ids=[s.id for s in pipe.stations],
        dry_run=dry_run,
    )
    if doi:
        click.echo(f"DOI minted: {doi}")
    else:
        click.echo(f"Tarball ready (no DOI minted): {tarball}")


# ─── run (alias) ─────────────────────────────────────────────────────────────

@main.command()
@click.option("--stations", type=click.Path(exists=True))
@click.option("--archive-root", type=click.Path(), default="archive",
              show_default=True)
def run(stations: str | None, archive_root: str):
    """Full nightly cycle: pull → transform → qc-report → metrics."""
    pipe = Pipeline(
        stations_yaml=Path(stations) if stations else None,
        archive_root=Path(archive_root),
    )
    results = pipe.run()
    pipe.write_qc_report(results)
    pipe.metrics.write(Path(archive_root) / "metrics.prom")
    click.echo(
        f"OK  stations={pipe.metrics.stations_ok}/{len(results)}  "
        f"files={pipe.metrics.files_written}  "
        f"bytes={pipe.metrics.total_bytes}  "
        f"duration={pipe.metrics.duration_s:.1f}s"
    )


if __name__ == "__main__":
    main()
