"""Command-line entrypoint for the pipeline.

Examples:
    uv run python -m bpcm.cli refresh --months 3 --end 2026-03
    uv run python -m bpcm.cli ingest --source ons.curtailment_wind --months 12
    uv run python -m bpcm.cli marts && uv run python -m bpcm.cli export
"""
from __future__ import annotations

import argparse
from datetime import date

from . import config, manifest, marts, quality, stage
from .export_dashboard import export
from .ingest import ingest
from .sources import REGISTRY, months_back

log = config.get_logger("cli")

DEFAULT_SOURCES = ["ons.curtailment_wind", "ons.curtailment_solar", "ons.generation"]


def _periods(months: int, end: str | None):
    if end:
        y, m = (int(x) for x in end.split("-"))
        end_date = date(y, m, 1)
    else:
        end_date = date.today().replace(day=1)
    return [(y, m) for (y, m) in months_back(end_date, months)]


def _do_ingest(sources, months, end, force):
    periods = _periods(months, end)
    for s in sources:
        ingest(s, [(y, m) for (y, m) in periods], force=force)


def _do_stage(sources):
    for s in sources:
        stage.stage_source(s)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bpcm", description="Brazil power-sector credit-risk pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--source", action="append", dest="sources",
                        help="source id (repeatable); default: all ONS sources")
        sp.add_argument("--months", type=int, default=3, help="months back to include")
        sp.add_argument("--end", help="last month YYYY-MM (default: current month)")

    sp = sub.add_parser("ingest", help="download + validate + land raw")
    add_common(sp); sp.add_argument("--force", action="store_true")
    sub.add_parser("stage", help="raw CSV -> staging Parquet").add_argument(
        "--source", action="append", dest="sources")
    sub.add_parser("marts", help="staging -> mart_plant_monthly")
    sub.add_parser("quality", help="run data-quality checks")
    sub.add_parser("export", help="mart -> dashboard/data.js")
    sub.add_parser("manifest", help="print provenance summary")

    sp = sub.add_parser("refresh", help="run the full pipeline end-to-end")
    add_common(sp); sp.add_argument("--force", action="store_true")

    args = p.parse_args(argv)
    sources = getattr(args, "sources", None) or DEFAULT_SOURCES
    for s in sources:
        if s not in REGISTRY:
            p.error(f"unknown source '{s}'. Known: {', '.join(REGISTRY)}")

    if args.cmd == "ingest":
        _do_ingest(sources, args.months, args.end, args.force)
    elif args.cmd == "stage":
        _do_stage(sources)
    elif args.cmd == "marts":
        marts.build_plant_monthly()
    elif args.cmd == "quality":
        quality.check_plant_monthly()
    elif args.cmd == "export":
        export()
    elif args.cmd == "manifest":
        for r in manifest.summary():
            print(f"{r['source']:<26} {r['period']:<8} {r['rows']:>9} rows  {r['bytes']/1e6:6.1f} MB  {r['fetched_at']}")
    elif args.cmd == "refresh":
        _do_ingest(sources, args.months, args.end, args.force)
        _do_stage(sources)
        marts.build_plant_monthly()
        quality.check_plant_monthly()
        export()
        log.info("refresh complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
