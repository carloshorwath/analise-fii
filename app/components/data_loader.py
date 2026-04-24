import sys
from datetime import date
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import Carteira, get_session


@st.cache_data(ttl=300)
def load_tickers_ativos() -> list[str]:
    session = get_session()
    result = tickers_ativos(session)
    session.close()
    return result


def load_carteira_db() -> list[dict]:
    from sqlalchemy import select
    session = get_session()
    rows = session.execute(
        select(Carteira).order_by(Carteira.ticker)
    ).scalars().all()
    result = [
        {
            "id": r.id,
            "ticker": r.ticker,
            "quantidade": r.quantidade,
            "preco_medio": float(r.preco_medio),
            "data_compra": str(r.data_compra),
        }
        for r in rows
    ]
    session.close()
    return result


def save_carteira_posicao(ticker: str, quantidade: int, preco_medio: float, data_compra: date):
    session = get_session()
    pos = Carteira(
        ticker=ticker,
        quantidade=quantidade,
        preco_medio=preco_medio,
        data_compra=data_compra,
    )
    session.add(pos)
    session.commit()
    session.close()


def delete_carteira_posicao(pos_id: int):
    session = get_session()
    pos = session.get(Carteira, pos_id)
    if pos:
        session.delete(pos)
        session.commit()
    session.close()
