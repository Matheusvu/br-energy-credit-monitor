# ⚡ Brazil Power-Sector Credit-Risk Monitor

A **DuckDB + Parquet data warehouse** of Brazilian power-sector open data (ONS, and —
on the roadmap — ANEEL/CCEE/CVM), built for a **private-credit team** to monitor the
sector and drill down to borrower/asset level. The core deliverable is a tidy,
documented, continuously-updated dataset you query with **Claude Code**; a static
dashboard is one view on top.

> Full design & source inventory: [`docs/PLATFORM_SPEC.md`](docs/PLATFORM_SPEC.md).
> Analyst's map (data model, conventions, example queries): [`CLAUDE.md`](CLAUDE.md).

## Quick start

```bash
# 1. Install uv (once):  curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                                            # create env + install deps
uv run python -m bpcm.cli refresh --months 12 --end 2026-03
open dashboard/index.html                          # view the dashboard
```

`refresh` runs the whole pipeline: **ingest → stage → marts → quality → export**.

## What you get

- `data/marts/mart_plant_monthly.parquet` — per plant × source × month: curtailed energy,
  generation, and **curtailment rate %**. Query it directly:
  ```bash
  duckdb -c ".read queries/top_curtailed_plants.sql"
  ```
- `dashboard/` — the static dashboard, now fed from the warehouse.
- `data/manifest.jsonl` — provenance for every downloaded file (URL, hash, rows, timestamp).

## Pipeline (robust by design)

| Stage | Module | Robustness |
|---|---|---|
| ingest | `bpcm/ingest.py` | retries+backoff, atomic writes, sha256, idempotent, 404-tolerant |
| stage | `bpcm/stage.py` | schema-contract validation; bad files → `data/quarantine/` |
| marts | `bpcm/marts.py` | DuckDB SQL; shared tested formula (`bpcm/transforms.py`) |
| quality | `bpcm/quality.py` | range/null/referential assertions; fails loud |
| export | `bpcm/export_dashboard.py` | marts → `dashboard/data.js` |

```bash
uv run pytest          # transform + plumbing unit tests
uv run python -m bpcm.cli manifest   # provenance summary
```

## Adding a source

Add one `DatasetSpec` to `bpcm/sources.py` (S3 path, period type, required columns).
The ingest/stage machinery is generic.

## Automation

`.github/workflows/refresh.yml` re-runs the pipeline monthly, commits updated marts +
dashboard data, and deploys the dashboard to GitHub Pages. (Enable Pages: Settings → Pages → GitHub Actions.)

## Roadmap

Prices/revenue (CMO/PLD) → entity resolution (ANEEL SIGA + *Agentes de Geração*: `ceg → CNPJ`)
→ credit layer (CVM debentures + financials) → company-level marts → drill-down views.
Details in [`docs/PLATFORM_SPEC.md`](docs/PLATFORM_SPEC.md).
