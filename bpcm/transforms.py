"""Shared SQL expression fragments, so the core logic is defined once and tested.

Curtailment (constrained-off) energy for one half-hourly row:
    counted only when a restriction reason is recorded;
    MWmed = max(0, reference_final [or reference] - generation);
    energy MWh = MWmed * interval_hours.
"""
from __future__ import annotations


def curtailment_mwh_expr(
    interval_hours: float,
    ref_final: str = "val_geracaoreferenciafinal",
    ref: str = "val_geracaoreferencia",
    gen: str = "val_geracao",
    reason: str = "cod_razaorestricao",
) -> str:
    return (
        f"CASE WHEN {reason} IS NOT NULL AND {reason} <> '' "
        f"THEN GREATEST(0, "
        f"COALESCE(TRY_CAST({ref_final} AS DOUBLE), TRY_CAST({ref} AS DOUBLE), 0) "
        f"- COALESCE(TRY_CAST({gen} AS DOUBLE), 0)) * {interval_hours} "
        f"ELSE 0 END"
    )
