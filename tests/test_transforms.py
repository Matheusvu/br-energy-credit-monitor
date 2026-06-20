"""Unit tests for the core transforms and source plumbing (no network)."""
from datetime import date

import duckdb
import pytest

from bpcm.sources import REGISTRY, months_back
from bpcm.transforms import curtailment_mwh_expr


def test_months_back_wraps_year():
    got = months_back(date(2026, 2, 1), 4)
    assert got == [(2026, 2), (2026, 1), (2025, 12), (2025, 11)]


def test_url_and_period_keys():
    wind = REGISTRY["ons.curtailment_wind"]
    assert wind.url(2026, 3).endswith("RESTRICAO_COFF_EOLICA_2026_03.csv")
    assert wind.period_key(2026, 3) == "2026-03"
    gen = REGISTRY["ons.generation"]
    assert gen.url(2025, 12).endswith("GERACAO_USINA-2_2025_12.csv")


def test_curtailment_formula():
    """Flagged-only, negative-clamped, half-hourly energy."""
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE t (val_geracao VARCHAR, val_geracaoreferencia VARCHAR,
                        val_geracaoreferenciafinal VARCHAR, cod_razaorestricao VARCHAR)
    """)
    con.execute("""
        INSERT INTO t VALUES
        ('10', '30', '',   'ENE'),   -- flagged: (30-10)*0.5 = 10.0  (uses reference)
        ('10', '30', '50', 'CNF'),   -- flagged: (50-10)*0.5 = 20.0  (final wins over reference)
        ('40', '30', '',   'ENE'),   -- flagged but gen>ref -> clamp 0
        ('10', '30', '',   ''),      -- NOT flagged -> 0
        ('10', '30', '',   NULL)     -- NOT flagged -> 0
    """)
    expr = curtailment_mwh_expr(0.5)
    total = con.execute(f"SELECT SUM({expr}) FROM t").fetchone()[0]
    con.close()
    assert total == pytest.approx(30.0)


def test_curtailment_rate_consistency():
    """rate = curtailed / (gen_observed + curtailed) stays in [0,1]."""
    con = duckdb.connect()
    con.execute("CREATE TABLE t (val_geracao VARCHAR, val_geracaoreferencia VARCHAR, "
                "val_geracaoreferenciafinal VARCHAR, cod_razaorestricao VARCHAR)")
    con.execute("INSERT INTO t VALUES ('20','60','','ENE')")  # curtailed=(60-20)*.5=20; gen=20*.5=10
    expr = curtailment_mwh_expr(0.5)
    curtailed, gen = con.execute(
        f"SELECT SUM({expr}), SUM(TRY_CAST(val_geracao AS DOUBLE))*0.5 FROM t").fetchone()
    con.close()
    rate = curtailed / (gen + curtailed)
    assert curtailed == pytest.approx(20.0)
    assert 0.0 <= rate <= 1.0
    assert rate == pytest.approx(20.0 / 30.0)
