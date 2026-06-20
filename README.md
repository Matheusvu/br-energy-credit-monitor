# ⚡ Curtailment Brasil

A dashboard for **wind and solar curtailment** (*constrained-off*) in Brazil's
national grid (SIN), built from official **ONS Open Data**.

Curtailment is renewable energy that *could* have been generated but was cut by
the operator due to grid limits, oversupply, or reliability constraints — a fast-growing
problem in Brazil's Northeast.

![dashboard](docs/screenshot.png)

## Quick start

No installs needed — everything runs with tools already on macOS (`curl`, `awk`).

```bash
# 1. Build the dataset (downloads ONS CSVs, aggregates them into data.js)
bash scripts/build_data.sh

# 2. Open the dashboard
open index.html
```

That's it. The page loads `data.js` and `vendor/chart.umd.min.js` via plain
`<script>` tags, so it works by **double-clicking `index.html`** — no web server.

## Configuring the build

```bash
MONTHS=12 END=2026-03 bash scripts/build_data.sh
```

- `MONTHS` — how many months back to include (default `12`).
- `END` — last month to include, `YYYY-MM` (default `2026-03`, the latest published wind month).

Months that aren't published yet are skipped automatically.

## How curtailment is computed

For each half-hourly record per plant:

```
curtailed_MWmed = max(0, val_geracaoreferenciafinal − val_geracao)   # falls back to val_geracaoreferencia
curtailed_MWh   = curtailed_MWmed × 0.5                                # 30-min samples
```

Only intervals that carry a **restriction reason** (`cod_razaorestricao`) are
counted, so normal forecast error is not mistaken for curtailment.

Reason codes:

| Code | Meaning |
|------|---------|
| `ENE` | Energético — oversupply / transmission limits |
| `CNF` | Reliability requirement |
| `REL` | External (grid) unavailability |
| `PAR` | Connection-agreement limit |

## Data source

[ONS — Dados Abertos](https://dados.ons.org.br/):

- `Restrição de Operação por Constrained-off de Usinas Eólicas`
- `Restrição de Operação por Constrained-off de Usinas Fotovoltaicas`

## Project layout

```
curtailment-brazil/
├── index.html              # dashboard markup
├── styles.css              # dark theme
├── app.js                  # renders charts from window.ONS_DATA
├── data.js                 # generated — aggregated dataset
├── scripts/build_data.sh   # downloads + aggregates ONS data
└── vendor/chart.umd.min.js # Chart.js (vendored, offline)
```
