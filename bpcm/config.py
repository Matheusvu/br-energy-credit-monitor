"""Central paths and constants for the pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

# ---- Paths (repo-root relative) -------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
STAGING = DATA / "staging"
MARTS = DATA / "marts"
QUARANTINE = DATA / "quarantine"
MANIFEST = DATA / "manifest.jsonl"
SQL_DIR = ROOT / "sql"
DASHBOARD = ROOT / "dashboard"

for _d in (RAW, STAGING, MARTS, QUARANTINE):
    _d.mkdir(parents=True, exist_ok=True)

# ---- Domain constants ------------------------------------------------------
# ONS subsystem codes
SUBSYSTEMS = {
    "N": "Norte",
    "NE": "Nordeste",
    "SE": "Sudeste/Centro-Oeste",
    "S": "Sul",
}

# Curtailment (constrained-off) restriction-reason codes
REASON_LABELS = {
    "ENE": "Energetico (sobreoferta)",
    "CNF": "Confiabilidade",
    "REL": "Indisp. externa (rede)",
    "PAR": "Contrato de conexao",
}

# Half-hourly samples -> energy in MWh = MWmed * 0.5h
HALF_HOUR_H = 0.5
# Hourly samples -> energy in MWh = MWmed * 1.0h
HOUR_H = 1.0


def get_logger(name: str) -> logging.Logger:
    """Structured-ish console logger shared across the pipeline."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
