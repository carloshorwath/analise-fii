from datetime import date
import pytest
import pandas as pd
from src.fii_analysis.features.indicators import get_pvp, get_dy_trailing, get_pvp_serie, get_dy_serie

def test_get_pvp_point_in_time(db_session):
    # For MOCK11:
    # First report reference date: 2024-01-31
    # First report delivery date: 2024-02-10
    # VP = 100.0
    
    # 1. Before delivery (2024-02-09): should return None because no reports are delivered yet
    pvp_before = get_pvp("MOCK11", date(2024, 2, 9), db_session)
    assert pvp_before is None

    # 2. On delivery date (2024-02-10): should return 100 / 100 = 1.0
    pvp_on = get_pvp("MOCK11", date(2024, 2, 10), db_session)
    assert pvp_on is not None
    assert abs(pvp_on - 1.0) < 1e-6

    # 3. After delivery (2024-02-11): should return 100 / 100 = 1.0
    pvp_after = get_pvp("MOCK11", date(2024, 2, 11), db_session)
    assert pvp_after is not None
    assert abs(pvp_after - 1.0) < 1e-6

def test_get_dy_trailing(db_session):
    # Test dy trailing returns correct values
    dy = get_dy_trailing("MOCK11", date(2025, 2, 15), db_session)
    assert dy is not None
    assert abs(dy - 0.12) < 0.02

def test_get_pvp_serie(db_session):
    # 1. Healthy ticker
    df = get_pvp_serie("MOCK11", db_session)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "pvp" in df.columns
    assert "vp_por_cota" in df.columns

    # 2. Non-existent ticker
    df_none = get_pvp_serie("NOT_EXIST", db_session)
    assert df_none.empty

    # 3. Ticker with no prices (insert mock ticker with cnpj but no prices)
    from src.fii_analysis.data.database import Ticker
    db_session.add(Ticker(cnpj="99.999.999/0001-99", ticker="NOPRICE11"))
    db_session.commit()
    df_noprice = get_pvp_serie("NOPRICE11", db_session)
    assert df_noprice.empty

def test_get_dy_serie(db_session):
    # 1. Healthy ticker
    df = get_dy_serie("MOCK11", db_session)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "dy" in df.columns

    # 2. Non-existent ticker or ticker with no prices
    df_none = get_dy_serie("NOT_EXIST", db_session)
    assert df_none.empty
