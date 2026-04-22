"""
Monthly aggregation + GRIIDC-style submission package.

A submission package for month YYYY-MM contains:
    {station}/{day}.nc        — daily NetCDFs
    {station}/{day}.nc.sha256 — fixity sidecar
    README.txt                — what's in this package
    MANIFEST.sha256           — aggregated checksum manifest
    metadata.xml              — ISO 19115-2 sidecar (stub)
    CHANGELOG.md              — copy of repo CHANGELOG
"""

from __future__ import annotations

import logging
import shutil
import tarfile
from pathlib import Path
from typing import List, Tuple

from gbe.transform import sha256_file

logger = logging.getLogger(__name__)


README_TEMPLATE = """GULF BUOY ETL — MONTHLY SUBMISSION PACKAGE
============================================

Month: {month}
Producer: gulf-buoy-etl v{version}
Generated: {generated_at}
Package format: GRIIDC-style submission directory

CONTENTS
--------

  {station_count} station directories, each with one NetCDF per UTC day:
      {{station_id}}/{{YYYYMMDD}}.nc
      {{station_id}}/{{YYYYMMDD}}.nc.sha256

  MANIFEST.sha256   Aggregate SHA-256 of every payload file
  metadata.xml      ISO 19115-2 metadata sidecar (stub)
  CHANGELOG.md      Pipeline version history

VERIFICATION
------------

Verify byte-level fixity:

    sha256sum -c MANIFEST.sha256

CITATION
--------

If you use these data, please cite the producing institution (NDBC and/or
GERG/TABS) AND the originating buoy DOIs. The DOI for this monthly archive
package, when minted to Zenodo, will be inserted in CHANGELOG.md.

LICENSE
-------

CC-BY-4.0  (https://creativecommons.org/licenses/by/4.0/)
"""


def build_manifest(payload_dir: Path) -> str:
    """
    Build a SHA-256 manifest of all .nc and .sha256 files under payload_dir.

    Output format is compatible with `sha256sum -c MANIFEST.sha256`.
    """
    lines: List[str] = []
    for p in sorted(payload_dir.rglob("*.nc")):
        rel = p.relative_to(payload_dir)
        digest = sha256_file(p)
        lines.append(f"{digest}  {rel}")
    return "\n".join(lines) + "\n"


def build_iso19115_xml(
    month: str,
    station_ids: List[str],
    creator: str = "gulf-buoy-etl pipeline",
) -> str:
    """
    Build a minimal ISO 19115-2 sidecar XML.

    This is a stub — production deployments should use a templating library
    like xmltodict or pygeometa. Suitable as a placeholder for GRIIDC
    submission while still being syntactically valid XML.
    """
    stations_xml = "\n".join(
        f"    <gmd:platform>{sid}</gmd:platform>" for sid in station_ids
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier>
    <gco:CharacterString>gulf-buoy-etl-{month}</gco:CharacterString>
  </gmd:fileIdentifier>
  <gmd:language>
    <gco:CharacterString>eng</gco:CharacterString>
  </gmd:language>
  <gmd:contact>
    <gco:CharacterString>{creator}</gco:CharacterString>
  </gmd:contact>
  <gmd:identificationInfo>
    <gmd:title>Gulf of Mexico buoy observations — {month}</gmd:title>
    <gmd:abstract>Quality-controlled hourly buoy observations from NDBC and TABS networks for {month}.</gmd:abstract>
{stations_xml}
  </gmd:identificationInfo>
</gmd:MD_Metadata>
"""


def aggregate_month(
    month: str,             # "YYYY-MM"
    daily_root: Path,
    output_root: Path,
    station_ids: List[str],
    version: str = "1.0.0",
    changelog_path: Path | None = None,
) -> Tuple[Path, Path]:
    """
    Build a monthly submission package.

    Args:
        month: Target month "YYYY-MM".
        daily_root: archive/daily/ root.
        output_root: archive/monthly/ root.
        station_ids: List of station IDs to include.
        version: Pipeline version.
        changelog_path: Path to repo CHANGELOG.md (copied into package).

    Returns:
        (package_dir, tarball_path)
    """
    year, mon = month.split("-")
    package_dir = output_root / f"gulf-buoy-{month}"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy daily files for each station, filtered to this month
    n_files = 0
    for sid in station_ids:
        src_dir = daily_root / sid
        if not src_dir.is_dir():
            continue
        dst_dir = package_dir / sid
        dst_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"{year}{mon}"
        for f in src_dir.glob(f"{prefix}*.nc"):
            shutil.copy2(f, dst_dir / f.name)
            sidecar = src_dir / f"{f.name}.sha256"
            if sidecar.is_file():
                shutil.copy2(sidecar, dst_dir / sidecar.name)
            n_files += 1

    # README
    from datetime import datetime, timezone
    readme_text = README_TEMPLATE.format(
        month=month,
        version=version,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        station_count=len(station_ids),
    )
    (package_dir / "README.txt").write_text(readme_text)

    # Manifest
    manifest = build_manifest(package_dir)
    (package_dir / "MANIFEST.sha256").write_text(manifest)

    # ISO 19115-2 sidecar
    xml = build_iso19115_xml(month, station_ids)
    (package_dir / "metadata.xml").write_text(xml)

    # Copy CHANGELOG
    if changelog_path and changelog_path.is_file():
        shutil.copy2(changelog_path, package_dir / "CHANGELOG.md")

    # Tarball
    tarball = output_root / f"gulf-buoy-{month}.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(package_dir, arcname=package_dir.name)

    logger.info("Built monthly package: %s (%d files, %d bytes)",
                tarball, n_files, tarball.stat().st_size)
    return package_dir, tarball
