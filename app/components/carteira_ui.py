"""
Utilitários de UI para carteira — carregamento e persistência com cache Streamlit.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import Carteira, get_session_ctx


@st.cache_data(ttl=300)
def load_tickers_ativos() -> list[str]:
    with get_session_ctx() as session:
        return tickers_ativos(session)


@st.cache_data(ttl=300, show_spinner=False)
def load_carteira_db() -> list[dict]:
    from sqlalchemy import select
    with get_session_ctx() as session:
        rows = session.execute(
            select(Carteira).order_by(Carteira.ticker)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "ticker": r.ticker,
                "quantidade": r.quantidade,
                "preco_medio": float(r.preco_medio),
                "data_compra": str(r.data_compra),
            }
            for r in rows
        ]


def save_carteira_posicao(ticker: str, quantidade: int, preco_medio: float, data_compra: date):
    with get_session_ctx() as session:
        pos = Carteira(
            ticker=ticker,
            quantidade=quantidade,
            preco_medio=preco_medio,
            data_compra=data_compra,
        )
        session.add(pos)
        session.commit()


def delete_carteira_posicao(pos_id: int):
    with get_session_ctx() as session:
        pos = session.get(Carteira, pos_id)
        if pos:
            session.delete(pos)
            session.commit()


def _parse_br_number(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("valor vazio")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    text = text.replace("R$", "").replace("%", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    if not text:
        raise ValueError("valor vazio")
    return float(text)


def normalize_carteira_csv(df_csv: pd.DataFrame, default_date: date | None = None) -> tuple[list[dict], str]:
    """Aceita CSV canônico ou export consolidado de corretora."""
    default_date = default_date or date.today()

    canonical = {"ticker", "quantidade", "preco_medio", "data_compra"}
    if canonical.issubset(set(df_csv.columns)):
        records = []
        for _, row in df_csv.iterrows():
            records.append({
                "ticker": str(row["ticker"]).upper().strip(),
                "quantidade": int(row["quantidade"]),
                "preco_medio": float(row["preco_medio"]),
                "data_compra": pd.to_datetime(row["data_compra"]).date(),
            })
        return records, "canonical"

    broker_export = {"Ativo", "Qtd", "Preço médio"}
    if broker_export.issubset(set(df_csv.columns)):
        records = []
        for _, row in df_csv.iterrows():
            ticker = str(row["Ativo"]).upper().strip()
            if not ticker or "ATIVOS" in ticker:
                continue
            records.append({
                "ticker": ticker,
                "quantidade": int(_parse_br_number(row["Qtd"])),
                "preco_medio": _parse_br_number(row["Preço médio"]),
                "data_compra": default_date,
            })
        return records, "broker_export"

    available = ", ".join(map(str, df_csv.columns))
    raise ValueError(
        "CSV em formato nao suportado. "
        "Use `ticker,quantidade,preco_medio,data_compra` ou `Ativo,Qtd,Preço médio`. "
        f"Colunas encontradas: {available}"
    )
