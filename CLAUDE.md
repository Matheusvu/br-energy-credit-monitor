# CLAUDE.md — analyst's map for the Brazil power-sector credit monitor

This repo is a **DuckDB + Parquet data warehouse** of Brazilian power-sector open data,
built for **credit-risk monitoring** and designed to be queried with Claude Code.

## How the pipeline works

```
uv run python -m bpcm.cli refresh --months 12 --end 2026-03
```

Stages (each also runnable on its own): `ingest → stage → marts → quality → export`.

- **ingest** — downloads source CSVs to `data/raw/<source>/<period>.csv` (retried, hashed,
  idempotent, logged to `data/manifest.jsonl`).
- **stage** — validates the header against a schema contract, then writes typed-safe Parquet
  to `data/staging/<source>/`. Files missing required columns go to `data/quarantine/`.
- **marts** — DuckDB SQL builds `data/marts/mart_plant_monthly.parquet`.
- **quality** — assertions (rate ∈ [0,1], non-negative, ids present, …). Fails loud.
- **export** — writes `dashboard/data.js` for the static dashboard.

Add a new ONS monthly dataset by adding one `DatasetSpec` to `bpcm/sources.py` — the rest is generic.

## Querying with DuckDB (what you'll usually do)

```bash
duckdb -c "SELECT * FROM 'data/marts/mart_plant_monthly.parquet' ORDER BY curtailed_mwh DESC LIMIT 20"
```
Or in Python: `import duckdb; duckdb.sql("SELECT ... FROM 'data/marts/*.parquet'")`.
You can also query staging Parquet directly for granular (per-interval) analysis.

## Data model

### `mart_plant_monthly` (one row per plant × source × month)
| column | meaning |
|---|---|
| `id_ons` | ONS plant id (master join key) |
| `ceg` | ANEEL CEG code (join to asset registry → owner; blank for plant-sets) |
| `plant_name`, `source` (`wind`/`solar`) | |
| `subsystem` (N/NE/SE/S), `subsystem_name`, `uf`, `uf_name` | location |
| `month` | `YYYY-MM` |
| `curtailed_mwh` | constrained-off energy (flagged intervals only) |
| `gen_observed_mwh` | plant generation from the curtailment file (same ½-h units) |
| `generation_mwh` | generation from the ONS generation dataset (cross-check) |
| `curtailment_rate` | `curtailed / (gen_observed + curtailed)` ∈ [0,1] |

## Unit & method conventions (important)
- ONS values are **MWmed** (average MW over the sample). Energy: `MWh = MWmed × interval_hours`.
  Curtailment data is **half-hourly** (×0.5); generation is **hourly** (×1.0).
- **Curtailment counted only when `cod_razaorestricao` is set** — otherwise it's forecast error,
  not constrained-off. Reason codes: `ENE` oversupply, `CNF` reliability, `REL` external grid, `PAR` contract.
- Curtailment per interval = `max(0, val_geracaoreferenciafinal [or val_geracaoreferencia] − val_geracao)`.

## Source datasets (see `bpcm/sources.py`, full inventory in `docs/PLATFORM_SPEC.md`)
- `ons.curtailment_wind`, `ons.curtailment_solar` — constrained-off, ½-hourly, per plant.
- `ons.generation` — `geracao-usina-2`, hourly, per plant (all technologies).

## Roadmap (next phases — see `docs/PLATFORM_SPEC.md`)
Prices/revenue (CMO/PLD) → entity resolution (SIGA + Agentes: `ceg → CNPJ`) → credit layer
(CVM debentures + financials) → company-level marts → automation + drill-down views.

## Example questions to ask Claude here
- "Top 15 plants by curtailment in 2026-03, with their curtailment rate."
- "Monthly wind vs solar curtailment GWh for the Nordeste."
- "Which plants have curtailment_rate > 30%? Group by state."
- "Once entity resolution lands: roll curtailed_mwh up to company (CNPJ) via the owner bridge."

See `queries/` for ready-to-run examples.
