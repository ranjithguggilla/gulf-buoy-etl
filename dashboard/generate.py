#!/usr/bin/env python3
"""
Generate the GitHub Pages status dashboard.

Reads:
  archive/metrics.prom        (Prometheus text format)
  archive/daily/{id}/*.nc     (count + timestamps)
  archive/reports/*/qc-report.md  (most recent)

Writes:
  dashboard/status.json
  dashboard/index.html        (rendered from index.template.html)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "archive"
OUT_DIR = REPO / "dashboard"

PROM_LINE = re.compile(r"^([a-zA-Z_:][\w:]*)(\{[^}]*\})?\s+([-\d.]+)")


def parse_prometheus(text: str) -> dict:
    """Parse a Prometheus text-format file into a dict-of-dicts."""
    out: dict = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = PROM_LINE.match(line)
        if not m:
            continue
        name, labels, value = m.group(1), m.group(2) or "", m.group(3)
        try:
            value = float(value)
        except ValueError:
            continue
        if labels:
            out.setdefault(name, {})[labels] = value
        else:
            out[name] = value
    return out


def build_status() -> dict:
    """Build the structured status payload for the dashboard."""
    metrics_path = ARCHIVE / "metrics.prom"
    metrics = parse_prometheus(metrics_path.read_text()) if metrics_path.is_file() else {}

    daily_root = ARCHIVE / "daily"
    stations = []
    if daily_root.is_dir():
        for station_dir in sorted(daily_root.iterdir()):
            if not station_dir.is_dir():
                continue
            files = sorted(station_dir.glob("*.nc"))
            stations.append({
                "id": station_dir.name,
                "n_files": len(files),
                "latest": files[-1].stem if files else None,
                "latest_size": files[-1].stat().st_size if files else 0,
            })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "stations": stations,
        "pipeline_version": "1.0.0",
    }


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>gulf-buoy-etl status</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  body  {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue",
          Helvetica, Arial, sans-serif; margin: 0; padding: 0;
          background: #0f1419; color: #e6edf3; }}
  header {{ background: #161b22; padding: 1.5rem 2rem; border-bottom: 1px solid #30363d; }}
  h1    {{ margin: 0; font-size: 1.5rem; }}
  .sub  {{ color: #8b949e; margin-top: .25rem; font-size: .9rem; }}
  .container {{ max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 1rem; }}
  .card .label {{ color: #8b949e; font-size: .85rem; text-transform: uppercase;
                  letter-spacing: .05em; }}
  .card .value {{ font-size: 1.6rem; font-weight: 600; margin-top: .25rem; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22;
          border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: .65rem 1rem; text-align: left; border-bottom: 1px solid #30363d; }}
  th    {{ background: #1f2937; font-weight: 600; color: #8b949e;
          text-transform: uppercase; font-size: .8rem; }}
  td.ok {{ color: #3fb950; font-weight: 600; }}
  td.warn {{ color: #d29922; }}
  td.fail {{ color: #f85149; font-weight: 600; }}
  footer {{ text-align: center; color: #6e7681; padding: 2rem; font-size: .85rem; }}
  a {{ color: #58a6ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  pre {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
        padding: 1rem; overflow-x: auto; font-size: .85rem; }}
</style>
</head>
<body>
  <header>
    <h1>🌊 gulf-buoy-etl status</h1>
    <div class="sub">Autonomous ETL for Gulf of Mexico buoy data — generated {generated_at}</div>
  </header>

  <div class="container">
    <div class="cards">
      <div class="card">
        <div class="label">Stations succeeded</div>
        <div class="value">{stations_ok} / {stations_total}</div>
      </div>
      <div class="card">
        <div class="label">NetCDF files</div>
        <div class="value">{files_written}</div>
      </div>
      <div class="card">
        <div class="label">Bytes pulled</div>
        <div class="value">{bytes_pulled}</div>
      </div>
      <div class="card">
        <div class="label">Last run duration</div>
        <div class="value">{duration_s} s</div>
      </div>
    </div>

    <h2 style="font-size: 1.15rem; margin-top: 0;">Per-station archive</h2>
    <table>
      <thead>
        <tr><th>Station ID</th><th>NetCDFs</th><th>Latest day</th><th>Latest size</th></tr>
      </thead>
      <tbody>
        {station_rows}
      </tbody>
    </table>

    <p style="margin-top: 2rem;">
      <a href="../archive/reports/">Browse QC reports →</a>
      &nbsp;·&nbsp;
      <a href="status.json">Raw JSON status</a>
      &nbsp;·&nbsp;
      <a href="https://github.com/ranjithguggilla/gulf-buoy-etl">Source code on GitHub</a>
    </p>
  </div>

  <footer>
    gulf-buoy-etl v{version} · <a href="https://github.com/ranjithguggilla/gulf-buoy-etl">github.com/ranjithguggilla/gulf-buoy-etl</a>
  </footer>
</body>
</html>
"""


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def render_html(status: dict) -> str:
    metrics = status["metrics"]
    rows = []
    for s in status["stations"]:
        size = fmt_bytes(s["latest_size"])
        rows.append(
            f"<tr><td><strong>{s['id']}</strong></td>"
            f"<td>{s['n_files']}</td>"
            f"<td>{s['latest'] or '—'}</td>"
            f"<td>{size}</td></tr>"
        )
    return HTML.format(
        generated_at=status["generated_at"],
        version=status["pipeline_version"],
        stations_ok=int(metrics.get("gbe_stations_succeeded_total", 0)),
        stations_total=len(status["stations"]),
        files_written=int(metrics.get("gbe_files_written_total", 0)),
        bytes_pulled=fmt_bytes(int(sum(
            v for v in metrics.get("gbe_bytes_pulled_total", {}).values()
        ))) if isinstance(metrics.get("gbe_bytes_pulled_total"), dict)
            else fmt_bytes(int(metrics.get("gbe_bytes_pulled_total", 0))),
        duration_s=f"{metrics.get('gbe_run_duration_seconds', 0):.2f}",
        station_rows="\n        ".join(rows) or "<tr><td colspan=4>No data yet</td></tr>",
    )


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    status = build_status()
    (OUT_DIR / "status.json").write_text(json.dumps(status, indent=2))
    (OUT_DIR / "index.html").write_text(render_html(status))
    print(f"  → {OUT_DIR / 'status.json'}")
    print(f"  → {OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
