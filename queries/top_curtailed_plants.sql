-- Top curtailed plants in the latest month, with curtailment rate.
-- Run: duckdb -c ".read queries/top_curtailed_plants.sql"
SELECT
    plant_name,
    source,
    subsystem_name,
    uf,
    month,
    ROUND(curtailed_mwh / 1000, 1)        AS curtailed_gwh,
    ROUND(curtailment_rate * 100, 1)      AS curtailment_pct
FROM 'data/marts/mart_plant_monthly.parquet'
WHERE month = (SELECT max(month) FROM 'data/marts/mart_plant_monthly.parquet')
ORDER BY curtailed_mwh DESC
LIMIT 20;
