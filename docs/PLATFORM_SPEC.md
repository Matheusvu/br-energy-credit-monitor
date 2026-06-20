# Brazil Power-Sector Credit-Risk Monitoring Platform — Build Spec

> This document is both the implementation plan **and** the seed brief for an `/ultraplan`
> cloud build. It is intentionally concrete (real dataset IDs / URL patterns / join keys)
> so the remote planner starts grounded.

## Context

A **private-credit team in Brazil** lends to power-sector companies (largely via *debêntures
incentivadas* / Lei 12.431 and bank debt). They need to monitor the whole energy sector and
**drill down to borrower/asset level** to track signals — curtailment, generation, capacity
factor, availability, prices/revenue, hydrology, and the company's debt & financials — that
affect a borrower's ability to repay.

The deliverable is **not just a dashboard**. The core asset is a **continuously-updated,
well-documented local data warehouse** that the team queries with **Claude Code** to generate
analyses on demand. The dashboard is one view on top. The platform must be **robust**
(schema validation, idempotent incremental ingestion, retries, data-quality tests, provenance).

### Decisions locked with the user
- **Scope:** sector-wide ingestion now; borrower→asset mapping is a defined later layer (the
  team will supply their book; the CEG→CNPJ bridge is built regardless).
- **Sources:** all four families — ONS operational, prices/revenue (CMO/PLD/CCEE), ANEEL SIGA
  asset registry, market/credit (CVM debentures & financials).
- **Coverage:** whole sector (all generation technologies; transmission/auctions as context).
- **Stack (our recommendation):** **DuckDB + Parquet** analytical warehouse, **Python** ingestion
  managed by **`uv`**, medallion layout (raw → staging → marts). Rationale below.

## Recommended architecture

```
br-energy-credit-monitor/
├── pyproject.toml / uv.lock         # uv-managed env (httpx, polars, duckdb, pandera, tenacity, pytest)
├── CLAUDE.md                        # data model + dictionary + example questions/SQL (the analyst's map)
├── platform/
│   ├── sources/                     # one module per dataset: url builder, schema contract, parser
│   ├── ingest.py                    # CLI: download → validate → land raw (idempotent, retried)
│   ├── stage.py                     # raw CSV → typed/cleaned Parquet (staging)
│   ├── build_marts.py               # staging → analytical marts (star schema) via SQL
│   ├── quality.py                   # data-quality assertions (row counts, ranges, referential)
│   └── manifest.py                  # provenance log (source URL, fetch ts, hash, rows)
├── sql/                             # staging + mart transformation SQL (DuckDB)
├── queries/                         # example analyses the team can run/extend with Claude
├── data/
│   ├── raw/<source>/<period>.csv    # cached downloads (gitignored; re-fetchable)
│   ├── staging/*.parquet            # typed/clean (gitignored)
│   └── marts/*.parquet              # aggregated analytical tables (committed — small)
├── warehouse.duckdb                 # attaches marts/staging for SQL (or build on the fly)
├── dashboard/                       # the existing static dashboard, now fed from marts JSON
└── .github/workflows/refresh.yml    # scheduled ingest → rebuild marts → deploy Pages
```

**Why DuckDB + Parquet + Python/uv:** millions of half-hourly rows across many sources need a
real columnar engine; DuckDB is a single binary (no server), reads/writes Parquet, and lets
Claude Code answer ad-hoc questions in SQL. `uv` gives a fast, reproducible env without polluting
the system Python. This is the most effective setup for LLM-driven granular analysis.

## Data model (star schema)

**Dimensions**
- `dim_plant` — `id_ons, ceg, name, type, fuel, capacity_mw, uf, subsystem, lat, lon, status,
  commercial_op_date` ← ONS `usina_conjunto` + ANEEL **SIGA**.
- `dim_company` — `cnpj, razao_social, sector, cvm_code` ← ANEEL **Agentes de Geração** + CVM `cad_cia_aberta`.
- `bridge_plant_owner` — `ceg, cnpj, ownership_pct` ← ANEEL **Agentes de Geração** (1:N owners).
- `dim_debenture` — `isin, cnpj, series, volume, maturity, guarantees, lei12431_flag` ← CVM `oferta-distrib` (+ MME portarias, best-effort).
- `dim_subsystem`, `dim_date`.

**Facts**
- `fact_curtailment_hh` (per plant, ½-hourly) — constrained-off MWmed + reason/origin codes.
- `fact_generation_h` (per plant, hourly) — `val_geracao` (denominator for curtailment %).
- `fact_capacityfactor_d`, `fact_availability_h`, `fact_cmo_hh`, `fact_pld`,
  `fact_balance_h`, `fact_load_d`, `fact_ear_d`, `fact_ena_d`, `fact_interchange_h`.
- `fact_financials` (CNPJ, period) ← CVM DFP/ITR; `fact_material_facts` ← CVM IPE.

**Derived marts**
- `mart_plant_monthly` — generation, curtailment GWh & **rate %**, capacity factor, availability,
  est. revenue (`gen × CMO`) and **lost revenue** (`curtailed × CMO`).
- `mart_company_monthly` — plant KPIs rolled to company via `bridge_plant_owner` (ownership-weighted).
- `mart_company_credit` — operational KPIs + debt schedule + financial ratios (Debt/EBITDA, coverage)
  + material-fact flags → the credit-monitoring view.

## Verified source inventory (real IDs / URL patterns)

All ONS files: semicolon-delimited, UTF-8. S3 base: `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/...`

| Source | Dataset id / access | Grain | Join key | Notes |
|---|---|---|---|---|
| ONS curtailment wind | `restricao_coff_eolica_tm/RESTRICAO_COFF_EOLICA_YYYY_MM.csv` | plant, ½-h | id_ons, ceg | reason codes ENE/CNF/REL/PAR |
| ONS curtailment solar | `restricao_coff_fotovoltaica_tm/RESTRICAO_COFF_FOTOVOLTAICA_YYYY_MM.csv` | plant, ½-h | id_ons, ceg | identical schema |
| ONS generation hourly | `geracao_usina_2_ho/GERACAO_USINA-2_YYYY_MM.csv` (`geracao-usina-2`) | plant, h | id_ons, ceg | curtailment-% denominator |
| ONS capacity factor | `fator_capacidade_2_di/FATOR_CAPACIDADE_YYYY.csv` (`fator-capacidade-2`) | plant, daily | id_ons, ceg | incl. installed capacity, coords |
| ONS availability | `disponibilidade_usina_ho/DISPONIBILIDADE_USINA_YYYY_MM.csv` | plant, h | id_ons, ceg | operational/synchronized MW |
| ONS energy balance | `balanco_energia_subsistema_ho/...YYYY.csv` (`balanco-energia-subsistema`) | subsystem, h | id_subsistema | gen mix + interchange |
| ONS load | `carga_energia_di/CARGA_ENERGIA_YYYY.csv` (`carga-energia`) | subsystem, daily | id_subsistema | demand |
| ONS CMO | `cmo_tm/CMO_SEMIHORARIO_YYYY.csv` (`cmo-semi-horario`) | subsystem, ½-h | id_subsistema | R$/MWh price |
| ONS EAR / ENA | `ear_subsistema_di` / `ena_subsistema_di` | subsystem, daily | id_subsistema | hydro stored / inflow |
| ONS interchange | `intercambio_nacional_ho` (`intercambio-nacional`) | subsys-pair, h | id_subsistema | congestion driver |
| ONS plant registry | `usina_conjunto/RELACIONAMENTO_USINA_CONJUNTO.csv` | plant | id_ons | plant↔conjunto map |
| ANEEL SIGA | dadosabertos.aneel.gov.br `siga-empreendimentos-geracao.csv` | plant | **CEG** | master registry, no CNPJ |
| ANEEL Agentes de Geração | dadosabertos.aneel.gov.br `agentes-geracao-energia-eletrica.csv` | plant×owner | **CEG → CNPJ** | **entity-resolution backbone**, ownership_pct |
| ANEEL auctions | dadosabertos.aneel.gov.br `resultado-leiloes-geracao.csv` | project | CNPJ/name | contracted R$/MWh, term |
| CCEE PLD | dadosabertos.ccee.org.br `pld_horario` / `pld_media_diaria` | submarket, h/d | submarket+date | open since 2025 |
| CVM company master | dados.cvm.gov.br `cad_cia_aberta.csv` (`cia_aberta-cad`) | company | **CNPJ** | daily |
| CVM debenture offerings | dados.cvm.gov.br `oferta-distrib` (`oferta_distribuicao.csv`) | issuance | CNPJ + ISIN | filter power-sector issuers |
| CVM financials | dados.cvm.gov.br `cia_aberta-doc-dfp` / `-itr` (ZIP) | company, A/Q | CNPJ | balance/income/cashflow |
| CVM material facts | dados.cvm.gov.br `cia_aberta-doc-ipe` (ZIP) | company | CNPJ | indentures, avisos a debenturistas |

**Honest gaps (document, don't hide):** ONS↔CEG coverage is partial (use name fallback);
multi-owner CEGs are 1:N; Lei 12.431 tagging needs MME *portarias* (manual/semi-automated);
ANBIMA secondary spreads, B3 trading, and credit ratings are **paywalled** → out of open-data MVP.

## Robustness requirements (first-class)
- **Schema contracts** per dataset (expected columns/types) validated on ingest; mismatch → fail loud + quarantine file.
- **Idempotent incremental** loads keyed by (source, period); re-fetch when CKAN `metadata_modified` changes (ONS revises data retroactively).
- **Retries w/ backoff** on network; validate size/hash; guard against partial downloads.
- **Data-quality tests:** row-count floors, null thresholds, value ranges (e.g. capacity factor ∈ [0,1]),
  referential integrity (every fact plant resolves in `dim_plant`).
- **Provenance manifest:** source URL, fetch timestamp, file hash, row counts per load (auditable).
- **Structured logging** + per-run summary; **pytest** unit tests on transforms.

## Claude-Code-native ergonomics
- `CLAUDE.md`: full table/column dictionary, join keys, **unit conventions** (MWmed vs MWh → ×0.5 for ½-hourly),
  curtailment formula, caveats, and 8–10 worked example questions with SQL.
- `queries/`: ready-made analyses (curtailment-at-risk by borrower, revenue-at-risk, covenant headroom).
- Optional advanced: a small **MCP server** exposing DuckDB so Claude queries the warehouse directly.

## Phased roadmap (each phase independently shippable)
0. **Foundation** — repo restructure, uv+DuckDB env, ingestion framework w/ schema validation,
   manifest, quality harness, tests. One source end-to-end (ONS curtailment) as the template.
1. **Operational core** — all ONS operational datasets → staging → `mart_plant_monthly`
   (generation, curtailment %, capacity factor, availability). Re-point the existing dashboard at marts.
2. **Prices & revenue** — CMO + CCEE PLD → revenue & lost-revenue marts.
3. **Entity resolution** — SIGA + Agentes → `dim_plant`/`dim_company`/`bridge_plant_owner`;
   roll operational KPIs to company level (`mart_company_monthly`).
4. **Credit layer** — CVM cad/oferta/DFP/ITR/IPE → `dim_debenture`, `fact_financials`,
   `mart_company_credit`; best-effort Lei 12.431 tagging.
5. **Automation + views** — GitHub Actions scheduling (daily fast sources, monthly slow),
   Pages deploy, drill-down dashboard views (sector → plant → company credit card),
   `CLAUDE.md` analysis library, optional alerts.

## Existing assets to reuse
- Current repo `curtailment-brazil` (GitHub, Matheusvu) — its `scripts/build_data.sh` curtailment
  logic and the static dashboard (`index.html/app.js/styles.css`, vendored Chart.js) become the
  **Phase-1 view** fed from marts. Recommend renaming the repo to `br-energy-credit-monitor`.

## Execution via ultraplan
1. Commit this spec to the repo as `docs/PLATFORM_SPEC.md` and push (so the cloud session has full context).
2. Launch `/ultraplan` with a prompt like: *"Build the platform described in docs/PLATFORM_SPEC.md,
   starting with Phase 0 + Phase 1. Use DuckDB+Parquet+uv. Enforce the robustness requirements."*
3. Review the cloud plan, then execute remotely or pull back here.

## Verification
- `uv run python -m platform.ingest --source ons.curtailment_wind --since 2024-04` lands raw + manifest rows.
- `uv run python -m platform.stage && uv run python -m platform.build_marts` produces Parquet marts.
- `uv run pytest` passes (transform unit tests + quality assertions).
- `duckdb warehouse.duckdb "select * from mart_plant_monthly limit 20"` returns sane numbers
  (curtailment % in [0,1], totals match the current dashboard's Q1-2026 ≈ 5.65 TWh).
- Open the dashboard; KPIs render from marts. Entity check: a known NE wind plant resolves to a CNPJ.
