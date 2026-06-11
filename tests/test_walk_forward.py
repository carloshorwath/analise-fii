import pytest
import pandas as pd
from datetime import date, timedelta
from src.fii_analysis.models.walk_forward import make_splits, validate_no_leakage, print_splits_summary
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.data.database import Dividendo

def test_make_splits():
    # Create synthetic events
    events = pd.DataFrame({
        "data_com": [date(2024, 1, 1) + timedelta(days=i*30) for i in range(15)],
        "val": range(15)
    })
    
    # Run make_splits
    splits = make_splits(events, train_frac=0.6, val_frac=0.2, gap_days=10)
    
    assert splits["n_train"] > 0
    assert splits["n_val"] > 0
    assert splits["n_test"] > 0
    assert splits["n_train"] + splits["n_val"] + splits["n_test"] <= len(events)
    
    # Check gap constraint
    if splits["train_end"] and splits["val_start"]:
        assert (splits["val_start"] - splits["train_end"]).days >= 10
    if splits["val_end"] and splits["test_start"]:
        assert (splits["test_start"] - splits["val_end"]).days >= 10

def test_make_splits_errors_and_edge_cases():
    # 1. ValueError when both gap_days and forward_days are None
    events = pd.DataFrame({"data_com": [date(2024, 1, 1)]})
    with pytest.raises(ValueError, match="make_splits\\(\\) requer gap_days ou forward_days"):
        make_splits(events, gap_days=None, forward_days=None)

    # 2. Empty events dataframe
    empty_events = pd.DataFrame(columns=["data_com"])
    splits_empty = make_splits(empty_events, gap_days=10)
    assert splits_empty["n_train"] == 0
    assert splits_empty["n_val"] == 0
    assert splits_empty["n_test"] == 0
    assert splits_empty["train_end"] is None

def test_print_splits_summary():
    # Call print_splits_summary and check it runs without exceptions
    events = pd.DataFrame({
        "data_com": [date(2024, 1, 1) + timedelta(days=i*30) for i in range(15)]
    })
    splits = make_splits(events, train_frac=0.6, val_frac=0.2, gap_days=10)
    
    # Run summary print
    print_splits_summary(splits)

    # Summary print with empty splits
    empty_splits = {
        "train": pd.DataFrame(columns=["data_com"]),
        "val": pd.DataFrame(columns=["data_com"]),
        "test": pd.DataFrame(columns=["data_com"]),
        "train_end": None,
        "val_start": None,
        "val_end": None,
        "test_start": None,
        "n_train": 0,
        "n_val": 0,
        "n_test": 0,
    }
    print_splits_summary(empty_splits)

def test_validate_no_leakage():
    # Prepare all_windows containing dates mapped to event data_coms
    all_windows = pd.DataFrame([
        {"ticker": "MOCK11", "data_com": date(2024, 1, 31), "data": date(2024, 1, 25)},
        {"ticker": "MOCK11", "data_com": date(2024, 1, 31), "data": date(2024, 1, 31)},
        {"ticker": "MOCK11", "data_com": date(2024, 2, 29), "data": date(2024, 2, 20)},
        {"ticker": "MOCK11", "data_com": date(2024, 2, 29), "data": date(2024, 2, 29)},
        {"ticker": "MOCK11", "data_com": date(2024, 3, 31), "data": date(2024, 3, 25)},
        {"ticker": "MOCK11", "data_com": date(2024, 3, 31), "data": date(2024, 3, 31)},
    ])
    
    # 1. Clean splits (no date overlap)
    splits = {
        "train": pd.DataFrame([{"ticker": "MOCK11", "data_com": date(2024, 1, 31)}]),
        "val": pd.DataFrame([{"ticker": "MOCK11", "data_com": date(2024, 2, 29)}]),
        "test": pd.DataFrame([{"ticker": "MOCK11", "data_com": date(2024, 3, 31)}]),
    }
    
    errors = validate_no_leakage(splits, all_windows)
    assert len(errors) == 0

    # 2. Leakage (overlapping date between train and val)
    bad_windows = all_windows.copy()
    bad_windows = pd.concat([bad_windows, pd.DataFrame([
        {"ticker": "MOCK11", "data_com": date(2024, 1, 31), "data": date(2024, 2, 20)}
    ])], ignore_index=True)
    
    errors = validate_no_leakage(splits, bad_windows)
    assert len(errors) > 0
    assert any("treino/validação" in err for err in errors)

def test_get_dividend_windows_thinning(db_session):
    # Retrieve base windows from the database
    windows = get_dividend_windows("MOCK11", db_session)
    assert not windows.empty
    
    db_session.execute(Dividendo.__table__.delete().where(Dividendo.ticker == "MOCK11"))
    db_session.commit()
    
    from src.fii_analysis.data.database import PrecoDiario
    pregoes = db_session.execute(
        PrecoDiario.__table__.select().where(PrecoDiario.ticker == "MOCK11").order_by(PrecoDiario.data.asc())
    ).all()
    
    d1 = pregoes[100].data
    d2 = pregoes[110].data
    d3 = pregoes[130].data
    
    db_session.add(Dividendo(ticker="MOCK11", data_com=d1, valor_cota=1.0, fonte="test"))
    db_session.add(Dividendo(ticker="MOCK11", data_com=d2, valor_cota=1.0, fonte="test"))
    db_session.add(Dividendo(ticker="MOCK11", data_com=d3, valor_cota=1.0, fonte="test"))
    db_session.commit()
    
    res = get_dividend_windows("MOCK11", db_session)
    unique_coms = res["data_com"].unique()
    assert d1 in unique_coms
    assert d2 not in unique_coms
    assert d3 in unique_coms
