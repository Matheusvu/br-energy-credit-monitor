"""Registry of source datasets: how to build their URLs and what schema to expect.

Adding a new ONS monthly dataset is a one-liner here; the ingest/stage/marts
machinery is generic. Schema contracts list the columns we actually depend on
(a subset check) so ONS adding/reordering columns does not break ingestion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ONS_S3 = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset"


@dataclass(frozen=True)
class DatasetSpec:
    name: str                       # logical id, e.g. "ons.curtailment_wind"
    s3_subdir: str                  # S3 folder under ONS_S3
    file_prefix: str                # file name prefix before the period
    period: str                     # "monthly" | "annual"
    required_columns: tuple[str, ...]
    delimiter: str = ";"
    source_label: str | None = None  # e.g. "wind"/"solar" for curtailment datasets
    interval_hours: float = 0.5      # MWmed sample length -> energy MWh = MWmed * interval_hours
    extra: dict = field(default_factory=dict)

    def url(self, year: int, month: int | None = None) -> str:
        if self.period == "monthly":
            assert month is not None
            stem = f"{self.file_prefix}_{year:04d}_{month:02d}.csv"
        else:
            stem = f"{self.file_prefix}_{year:04d}.csv"
        return f"{ONS_S3}/{self.s3_subdir}/{stem}"

    def period_key(self, year: int, month: int | None = None) -> str:
        return f"{year:04d}-{month:02d}" if self.period == "monthly" else f"{year:04d}"


# Columns we depend on downstream (subset of the real header).
_CURTAILMENT_COLS = (
    "id_subsistema", "nom_subsistema", "id_estado", "nom_estado",
    "nom_usina", "id_ons", "ceg", "din_instante",
    "val_geracao", "val_geracaoreferencia", "val_geracaoreferenciafinal",
    "cod_razaorestricao",
)

REGISTRY: dict[str, DatasetSpec] = {
    "ons.curtailment_wind": DatasetSpec(
        name="ons.curtailment_wind",
        s3_subdir="restricao_coff_eolica_tm",
        file_prefix="RESTRICAO_COFF_EOLICA",
        period="monthly",
        required_columns=_CURTAILMENT_COLS,
        source_label="wind",
        interval_hours=0.5,
    ),
    "ons.curtailment_solar": DatasetSpec(
        name="ons.curtailment_solar",
        s3_subdir="restricao_coff_fotovoltaica_tm",
        file_prefix="RESTRICAO_COFF_FOTOVOLTAICA",
        period="monthly",
        required_columns=_CURTAILMENT_COLS,
        source_label="solar",
        interval_hours=0.5,
    ),
    "ons.generation": DatasetSpec(
        name="ons.generation",
        s3_subdir="geracao_usina_2_ho",
        file_prefix="GERACAO_USINA-2",
        period="monthly",
        # verified live before staging; we depend on these:
        required_columns=("din_instante", "id_ons", "nom_usina", "val_geracao"),
        interval_hours=1.0,  # hourly base; confirmed empirically in wiring step
    ),
}


def months_back(end: date, n: int) -> list[tuple[int, int]]:
    """Return [(year, month), ...] for the n months ending at `end` (newest first)."""
    out: list[tuple[int, int]] = []
    y, m = end.year, end.month
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out
