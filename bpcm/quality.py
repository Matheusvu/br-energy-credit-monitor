"""Data-quality assertions on the marts. Fail loud on violations."""
from __future__ import annotations

import duckdb

from . import config

log = config.get_logger("quality")

MART = config.MARTS / "mart_plant_monthly.parquet"


class DataQualityError(AssertionError):
    pass


def _scalar(con, q: str):
    return con.execute(q).fetchone()[0]


def check_plant_monthly() -> list[tuple[str, bool, str]]:
    if not MART.exists():
        raise DataQualityError("mart_plant_monthly.parquet missing — build marts first")

    con = duckdb.connect()
    t = f"read_parquet('{MART}')"
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = ""):
        results.append((name, ok, detail))

    n = _scalar(con, f"SELECT count(*) FROM {t}")
    check("non_empty", n > 0, f"{n} rows")

    bad_rate = _scalar(
        con, f"SELECT count(*) FROM {t} WHERE curtailment_rate IS NOT NULL "
             f"AND (curtailment_rate < 0 OR curtailment_rate > 1)")
    check("rate_in_0_1", bad_rate == 0, f"{bad_rate} rows out of range")

    neg = _scalar(con, f"SELECT count(*) FROM {t} WHERE curtailed_mwh < 0")
    check("curtailed_non_negative", neg == 0, f"{neg} negative rows")

    null_id = _scalar(con, f"SELECT count(*) FROM {t} WHERE id_ons IS NULL OR id_ons = ''")
    check("id_ons_present", null_id == 0, f"{null_id} null ids")

    bad_month = _scalar(
        con, f"SELECT count(*) FROM {t} WHERE month NOT SIMILAR TO '[0-9]{{4}}-[0-9]{{2}}'")
    check("month_format", bad_month == 0, f"{bad_month} malformed months")

    bad_source = _scalar(con, f"SELECT count(*) FROM {t} WHERE source NOT IN ('wind','solar')")
    check("source_valid", bad_source == 0, f"{bad_source} invalid sources")

    con.close()

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        log.info("%-24s %s %s", name, "PASS" if ok else "FAIL", detail)
    if failed:
        raise DataQualityError(f"{len(failed)} quality check(s) failed: "
                               + ", ".join(r[0] for r in failed))
    return results
