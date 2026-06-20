"""Build analytical marts from staging Parquet using DuckDB.

mart_plant_monthly — one row per (plant, source, month):
    curtailed_mwh      constrained-off energy (flagged intervals only)
    gen_observed_mwh   the plant's own generation from the curtailment file
    generation_mwh     generation from the ONS generation dataset (independent cross-check)
    curtailment_rate   curtailed / (gen_observed + curtailed)   [0..1]

The rate uses the curtailment file's own generation column so curtailed and
generated energy share identical half-hourly units — robust to the generation
dataset's sampling cadence.
"""
from __future__ import annotations

import duckdb

from . import config
from .sources import REGISTRY
from .transforms import curtailment_mwh_expr

log = config.get_logger("marts")


def _glob(source: str) -> str | None:
    d = config.STAGING / source
    return f"{d}/*.parquet" if d.exists() and any(d.glob("*.parquet")) else None


def build_plant_monthly() -> int:
    wind = _glob("ons.curtailment_wind")
    solar = _glob("ons.curtailment_solar")
    gen = _glob("ons.generation")

    arms = []
    if wind:
        arms.append(f"SELECT 'wind'  AS source, * FROM read_parquet('{wind}', union_by_name=true)")
    if solar:
        arms.append(f"SELECT 'solar' AS source, * FROM read_parquet('{solar}', union_by_name=true)")
    if not arms:
        raise RuntimeError("no curtailment staging data found — run ingest+stage first")
    curt_union = "\nUNION ALL BY NAME\n".join(arms)

    curt_h = REGISTRY["ons.curtailment_wind"].interval_hours  # 0.5
    gen_h = REGISTRY["ons.generation"].interval_hours          # 1.0

    gen_cte = (
        f"""gen AS (
            SELECT id_ons,
                   strftime(CAST(din_instante AS TIMESTAMP), '%Y-%m') AS month,
                   SUM(COALESCE(TRY_CAST(val_geracao AS DOUBLE), 0)) * {gen_h} AS generation_mwh
            FROM read_parquet('{gen}', union_by_name=true)
            GROUP BY id_ons, month
        ),"""
        if gen else 'gen AS (SELECT NULL::VARCHAR AS id_ons, NULL::VARCHAR AS "month", NULL::DOUBLE AS generation_mwh),'
    )

    sql = f"""
    COPY (
      WITH curt_raw AS (
        {curt_union}
      ),
      curt AS (
        SELECT
          id_ons,
          source,
          strftime(CAST(din_instante AS TIMESTAMP), '%Y-%m') AS month,
          any_value(nom_usina)      AS plant_name,
          any_value(id_subsistema)  AS subsystem,
          any_value(nom_subsistema) AS subsystem_name,
          any_value(id_estado)      AS uf,
          any_value(nom_estado)     AS uf_name,
          max(ceg)                  AS ceg,
          SUM({curtailment_mwh_expr(curt_h)}) AS curtailed_mwh,
          SUM(COALESCE(TRY_CAST(val_geracao AS DOUBLE), 0)) * {curt_h} AS gen_observed_mwh
        FROM curt_raw
        WHERE id_ons IS NOT NULL AND id_ons <> ''
        GROUP BY id_ons, source, month
      ),
      {gen_cte}
      final AS (
        SELECT
          c.id_ons, c.ceg, c.plant_name, c.source,
          c.subsystem, c.subsystem_name, c.uf, c.uf_name, c.month,
          ROUND(c.curtailed_mwh, 3)               AS curtailed_mwh,
          ROUND(c.gen_observed_mwh, 3)            AS gen_observed_mwh,
          ROUND(g.generation_mwh, 3)              AS generation_mwh,
          CASE WHEN (c.gen_observed_mwh + c.curtailed_mwh) > 0
               THEN ROUND(c.curtailed_mwh / (c.gen_observed_mwh + c.curtailed_mwh), 4)
               ELSE NULL END                      AS curtailment_rate
        FROM curt c
        LEFT JOIN gen g ON g.id_ons = c.id_ons AND g.month = c.month
      )
      SELECT * FROM final ORDER BY curtailed_mwh DESC
    ) TO '{config.MARTS / 'mart_plant_monthly.parquet'}' (FORMAT parquet);
    """

    con = duckdb.connect()
    con.execute(sql)
    n = con.execute(
        f"SELECT count(*) FROM read_parquet('{config.MARTS / 'mart_plant_monthly.parquet'}')"
    ).fetchone()[0]
    con.close()
    log.info("built   mart_plant_monthly -> %s rows", f"{n:,}")
    return n
