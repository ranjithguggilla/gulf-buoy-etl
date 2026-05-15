"""
Zenodo DOI minting for monthly data packages.

In production:
  export ZENODO_TOKEN=<personal access token>
  gbe publish 2026-04

The publisher creates a Zenodo deposition, uploads the monthly tarball,
attaches a metadata block, and publishes — minting a permanent DOI.

For development / CI, ZENODO_SANDBOX=1 routes to https://sandbox.zenodo.org.
If no token is set, publish() prints what *would* happen and exits cleanly
(no failure) — this keeps `make all` working without secrets.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import requests

from gbe.retry import retry

logger = logging.getLogger(__name__)


def zenodo_base_url() -> str:
    """Sandbox vs production Zenodo URL."""
    if os.environ.get("ZENODO_SANDBOX", "0") == "1":
        return "https://sandbox.zenodo.org/api"
    return "https://zenodo.org/api"


def build_metadata(month: str, station_ids: list) -> dict:
    """Build the Zenodo deposition metadata block."""
    return {
        "metadata": {
            "title": f"Gulf of Mexico buoy observations — {month}",
            "upload_type": "dataset",
            "description": (
                f"Quality-controlled hourly buoy observations from NDBC and "
                f"TABS networks for {month}. Includes daily CF-1.8 NetCDFs "
                f"for stations {', '.join(station_ids)}, with SHA-256 fixity, "
                f"ISO 19115-2 sidecar metadata, and pipeline provenance."
            ),
            "creators": [
                {"name": "Guggilla, Ranjith"},
            ],
            "keywords": [
                "oceanography", "Gulf of Mexico", "buoy", "NDBC", "TABS",
                "time series", "FAIR", "NetCDF",
            ],
            "access_right": "open",
            "license": "cc-by-4.0",
            "communities": [],  # add e.g. {"identifier": "ocean-best-practices"} if a community is targeted
            "related_identifiers": [
                {
                    "identifier": "https://www.ndbc.noaa.gov/",
                    "relation": "isDerivedFrom",
                    "resource_type": "dataset",
                },
                {
                    "identifier": "https://tabs.gerg.tamu.edu/",
                    "relation": "isDerivedFrom",
                    "resource_type": "dataset",
                },
            ],
        }
    }


@retry(
    exceptions=(requests.RequestException,),
    max_attempts=4,
    base_delay=3.0,
)
def _http_post(url: str, headers: dict, **kwargs) -> requests.Response:
    return requests.post(url, headers=headers, timeout=60, **kwargs)


@retry(
    exceptions=(requests.RequestException,),
    max_attempts=4,
    base_delay=3.0,
)
def _http_put(url: str, headers: dict, **kwargs) -> requests.Response:
    return requests.put(url, headers=headers, timeout=120, **kwargs)


def publish_to_zenodo(
    tarball: Path,
    month: str,
    station_ids: list,
    token: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Mint a DOI for a monthly data package on Zenodo.

    Args:
        tarball: Path to gulf-buoy-{month}.tar.gz.
        month: "YYYY-MM".
        station_ids: List of station IDs included.
        token: Zenodo personal access token; defaults to ZENODO_TOKEN env var.
        dry_run: If True, log what would be uploaded but don't call API.

    Returns:
        Minted DOI (e.g. "10.5281/zenodo.1234567"), or None if no token /
        dry-run.
    """
    token = token or os.environ.get("ZENODO_TOKEN")
    if not token or dry_run:
        logger.info(
            "DRY RUN: would publish %s to Zenodo (month=%s, stations=%s)",
            tarball, month, station_ids,
        )
        return None

    base = zenodo_base_url()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create deposition
    resp = _http_post(f"{base}/deposit/depositions", headers=headers, json={})
    resp.raise_for_status()
    deposition = resp.json()
    bucket_url = deposition["links"]["bucket"]
    deposition_id = deposition["id"]
    logger.info("Created Zenodo deposition id=%d", deposition_id)

    # 2. Upload tarball into the bucket
    with open(tarball, "rb") as f:
        upload_url = f"{bucket_url}/{tarball.name}"
        resp = _http_put(upload_url, headers=headers, data=f)
        resp.raise_for_status()

    # 3. Attach metadata
    metadata = build_metadata(month, station_ids)
    resp = requests.put(
        f"{base}/deposit/depositions/{deposition_id}",
        headers={**headers, "Content-Type": "application/json"},
        json=metadata, timeout=60,
    )
    resp.raise_for_status()

    # 4. Publish
    resp = _http_post(
        f"{base}/deposit/depositions/{deposition_id}/actions/publish",
        headers=headers,
    )
    resp.raise_for_status()
    published = resp.json()
    doi = published.get("doi") or published.get("metadata", {}).get("doi")
    logger.info("Published! DOI = %s", doi)
    return doi
