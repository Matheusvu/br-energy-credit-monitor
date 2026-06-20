"""Brazil power-sector credit-risk monitoring platform (bpcm).

A small, robust ETL + analytics platform that aggregates open data from ONS,
ANEEL, CCEE and CVM into a DuckDB/Parquet warehouse for credit-risk monitoring.

Pipeline stages (run via `python -m bpcm.cli`):
    ingest  -> download + validate + land raw CSVs (idempotent, retried, logged)
    stage   -> raw CSV -> typed/clean Parquet (schema-validated)
    marts   -> staging Parquet -> analytical marts (star schema)
    quality -> data-quality assertions on the marts
    export  -> marts -> dashboard/data.js for the static dashboard
"""

__version__ = "0.1.0"
