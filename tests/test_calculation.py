import pytest
from datetime import date, timedelta
from src.fii_analysis.features.valuation import get_pvp_percentil, get_dy_gap, get_dy_gap_percentil, get_pvp_zscore
from src.fii_analysis.data.database import PrecoDiario

def test_pvp_percentil_insufficient_data(db_session):
    # Test MOCK11 with very early date (only a few days of data available)
    # The start_date is 2024-01-01.
    # Query on 2024-01-10 (only ~7 trading days)
    pct, n = get_pvp_percentil("MOCK11", date(2024, 1, 10), session=db_session)
    assert pct is None
    assert n == 0

def test_pvp_percentil_sufficient_data(db_session):
    # Query after a long period (e.g. 300 business days later, which is approx mid 2025)
    # 300 business days is approx 420 calendar days from 2024-01-01 => ~ March 2025
    pct, n = get_pvp_percentil("MOCK11", date(2025, 4, 1), session=db_session)
    assert pct is not None
    assert n > 63
    assert 0 <= pct <= 100

def test_dy_gap(db_session):
    # MOCK11 has 1.0 dividend monthly, price is 100 => DY 12m approx 12% = 0.12
    # CDI accumulated 12m is approx (1 + 0.0004)^252 - 1 = 0.106
    # Expected DY Gap: 0.12 - 0.106 = 0.014 (1.4%)
    gap = get_dy_gap("MOCK11", date(2025, 4, 1), session=db_session)
    assert gap is not None
    assert abs(gap - 0.014) < 0.02

def test_dy_gap_percentil(db_session):
    # Query with enough data (>252 days)
    pct = get_dy_gap_percentil("MOCK11", date(2025, 4, 1), session=db_session)
    assert pct is not None
    assert 0 <= pct <= 100

    # Query with insufficient data (<252 days)
    pct_early = get_dy_gap_percentil("MOCK11", date(2024, 6, 1), session=db_session)
    assert pct_early is None

def test_pvp_zscore(db_session):
    # Query with enough data (>252 days)
    z = get_pvp_zscore("MOCK11", date(2025, 4, 1), session=db_session)
    assert z is not None
    
    # Since prices and VP are constant at 100.0, the standard deviation is 0.0
    # The code returns 0.0 when std == 0
    assert z == 0.0

    # Query with insufficient data (<252 days)
    z_early = get_pvp_zscore("MOCK11", date(2024, 6, 1), session=db_session)
    assert z_early is None
