"""Staging: raw CSV -> typed-safe Parquet, with a schema contract.

We load every column as VARCHAR (all_varchar) so messy/empty numeric cells never
break ingestion; typing happens later in the marts SQL via TRY_CAST. Before
loading we validate the header against the dataset's required columns; a file
missing required columns is moved to data/quarantine and skipped (fail loud,
don't silently corrupt the warehouse).
"""
from __future__ import annotations

import csv
import shutil

import duckdb

from . import config
from .sources import REGISTRY, DatasetSpec

log = config.get_logger("stage")


def _read_header(path, delimiter: str) -> list[str]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        return next(reader, [])


def _validate(spec: DatasetSpec, header: list[str]) -> list[str]:
    """Return the list of missing required columns (empty == valid)."""
    present = {h.strip() for h in header}
    return [c for c in spec.required_columns if c not in present]


def stage_source(source: str) -> dict:
    spec = REGISTRY[source]
    raw_dir = config.RAW / spec.name
    out_dir = config.STAGING / spec.name
    out_dir.mkdir(parents=True, exist_ok=True)

    tally = {"staged": 0, "quarantined": 0}
    if not raw_dir.exists():
        log.warning("no raw data for %s", source)
        return tally

    con = duckdb.connect()
    for csv_path in sorted(raw_dir.glob("*.csv")):
        period_key = csv_path.stem
        header = _read_header(csv_path, spec.delimiter)
        missing = _validate(spec, header)
        if missing:
            qdir = config.QUARANTINE / spec.name
            qdir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(csv_path, qdir / csv_path.name)
            log.error("QUARANTINE %s %s — missing columns: %s",
                      source, period_key, ", ".join(missing))
            tally["quarantined"] += 1
            continue

        out_path = out_dir / f"{period_key}.parquet"
        # Values are repo-controlled (our own paths + a fixed delimiter), so inline them:
        src = str(csv_path).replace("'", "''")
        dst = str(out_path).replace("'", "''")
        delim = spec.delimiter.replace("'", "''")
        con.execute(
            f"""
            COPY (
                SELECT * FROM read_csv('{src}', delim='{delim}', header=true,
                                       all_varchar=true, ignore_errors=true)
            ) TO '{dst}' (FORMAT parquet);
            """
        )
        n = con.execute(f"SELECT count(*) FROM read_parquet('{dst}')").fetchone()[0]
        log.info("staged  %s %s -> %s rows", source, period_key, f"{n:,}")
        tally["staged"] += 1

    con.close()
    log.info("done    stage %s -> %s", source, tally)
    return tally
