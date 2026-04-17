import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import (
    Carteira,
    Dividendo,
    PrecoDiario,
    RelatorioMensal,
    Ticker,
    create_tables,
    get_engine,
    get_session,
)
from src.fii_analysis.features.composicao import classificar_fii, composicao_ativo
from src.fii_analysis.features.indicators import get_dy_serie, get_dy_trailing, get_pvp, get_pvp_serie
from src.fii_analysis.features.portfolio import carteira_panorama, herfindahl
from src.fii_analysis.features.radar import radar_matriz
from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital, tendencia_pl
from src.fii_analysis.features.valuation import (
    get_dy_gap,
    get_dy_gap_percentil,
    get_dy_n_meses,
    get_pvp_percentil,
    get_pvp_serie_cached,
)


@st.cache_data(ttl=300)
def load_tickers_ativos() -> list[str]:
    session = get_session()
    result = tickers_ativos(session)
    session.close()
    return result


@st.cache_data(ttl=300)
def load_ticker_info(ticker: str) -> dict | None:
    from sqlalchemy import select
    session = get_session()
    row = session.execute(
        select(Ticker).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()
    if row is None:
        session.close()
        return None
    info = {
        "cnpj": row.cnpj,
        "ticker": row.ticker,
        "nome": row.nome,
        "segmento": row.segmento,
        "mandato": row.mandato,
        "tipo_gestao": row.tipo_gestao,
        "data_inicio": str(row.data_inicio) if row.data_inicio else None,
        "inativo_em": str(row.inativo_em) if row.inativo_em else None,
    }
    session.close()
    return info


@st.cache_data(ttl=300)
def load_panorama() -> pd.DataFrame:
    session = get_session()
    tickers = tickers_ativos(session)
    df = carteira_panorama(tickers, session)
    session.close()
    return df


@st.cache_data(ttl=300)
def load_radar() -> pd.DataFrame:
    session = get_session()
    df = radar_matriz(session=session)
    session.close()
    return df


@st.cache_data(ttl=300)
def load_pvp_serie(ticker: str) -> pd.DataFrame:
    session = get_session()
    df = get_pvp_serie(ticker, session)
    session.close()
    return df


@st.cache_data(ttl=300)
def load_dy_serie(ticker: str) -> pd.DataFrame:
    session = get_session()
    df = get_dy_serie(ticker, session)
    session.close()
    return df


@st.cache_data(ttl=300)
def load_pvp_historico(ticker: str) -> list[tuple]:
    session = get_session()
    result = get_pvp_serie_cached(ticker, session)
    session.close()
    return result


@st.cache_data(ttl=300)
def load_pvp_atual(ticker: str) -> float | None:
    session = get_session()
    ultimo = session.execute(
        __import__("sqlalchemy").select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimo is None:
        session.close()
        return None
    pvp = get_pvp(ticker, ultimo, session)
    session.close()
    return pvp


@st.cache_data(ttl=300)
def load_pvp_percentil(ticker: str) -> float | None:
    session = get_session()
    ultimo = session.execute(
        __import__("sqlalchemy").select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimo is None:
        session.close()
        return None
    pct = get_pvp_percentil(ticker, ultimo, 504, session)
    session.close()
    return pct


@st.cache_data(ttl=300)
def load_dy_atual(ticker: str) -> float | None:
    session = get_session()
    ultimo = session.execute(
        __import__("sqlalchemy").select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimo is None:
        session.close()
        return None
    dy = get_dy_trailing(ticker, ultimo, session)
    session.close()
    return dy


@st.cache_data(ttl=300)
def load_dy_n_meses(ticker: str, n_meses: int) -> float | None:
    session = get_session()
    ultimo = session.execute(
        __import__("sqlalchemy").select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimo is None:
        session.close()
        return None
    dy = get_dy_n_meses(ticker, ultimo, n_meses, session)
    session.close()
    return dy


@st.cache_data(ttl=300)
def load_dy_gap(ticker: str) -> float | None:
    session = get_session()
    ultimo = session.execute(
        __import__("sqlalchemy").select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimo is None:
        session.close()
        return None
    gap = get_dy_gap(ticker, ultimo, session)
    session.close()
    return gap


@st.cache_data(ttl=300)
def load_dy_gap_percentil(ticker: str) -> float | None:
    session = get_session()
    ultimo = session.execute(
        __import__("sqlalchemy").select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimo is None:
        session.close()
        return None
    pct = get_dy_gap_percentil(ticker, ultimo, 504, session)
    session.close()
    return pct


@st.cache_data(ttl=300)
def load_saude(ticker: str) -> dict:
    session = get_session()
    tend = tendencia_pl(ticker, session=session)
    destruicao = flag_destruicao_capital(ticker, session)
    emissoes = emissoes_recentes(ticker, session=session)
    session.close()
    return {"tendencia_pl": tend, "destruicao": destruicao, "emissoes": emissoes}


@st.cache_data(ttl=300)
def load_composicao(ticker: str) -> dict:
    session = get_session()
    comp = composicao_ativo(ticker, session)
    tipo = classificar_fii(ticker, session)
    session.close()
    return {**comp, "tipo": tipo}


def load_proximas_datas_com(ticker: str, limite: int = 5) -> list[dict]:
    from sqlalchemy import select
    session = get_session()
    hoje = date.today()
    rows = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker, Dividendo.data_com >= hoje)
        .order_by(Dividendo.data_com.asc())
        .limit(limite)
    ).all()
    result = [{"data_com": str(r[0]), "valor_cota": float(r[1]) if r[1] else None} for r in rows]
    session.close()
    return result


@st.cache_data(ttl=300)
def load_pl_historico(ticker: str, meses: int = 24) -> pd.DataFrame:
    from sqlalchemy import select
    session = get_session()
    info = load_ticker_info(ticker)
    if info is None:
        session.close()
        return pd.DataFrame()
    cnpj = info["cnpj"]
    rows = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.patrimonio_liq,
            RelatorioMensal.vp_por_cota,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.patrimonio_liq.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(meses)
    ).all()
    session.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["data_ref", "patrimonio_liq", "vp_por_cota"])
    df = df.sort_values("data_ref").reset_index(drop=True)
    df["patrimonio_liq"] = df["patrimonio_liq"].astype(float)
    df["vp_por_cota"] = df["vp_por_cota"].astype(float)
    return df


@st.cache_data(ttl=300)
def load_ultimo_preco(ticker: str) -> dict | None:
    from sqlalchemy import select
    session = get_session()
    row = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento, PrecoDiario.volume, PrecoDiario.coletado_em)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).first()
    session.close()
    if row is None:
        return None
    return {
        "data": str(row[0]),
        "fechamento": float(row[1]) if row[1] else None,
        "volume": int(row[2]) if row[2] else None,
        "coletado_em": str(row[3]) if row[3] else None,
    }


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


@st.cache_data(ttl=300)
def load_benchmark_ifix() -> pd.DataFrame:
    from sqlalchemy import select
    from src.fii_analysis.data.database import BenchmarkDiario
    session = get_session()
    rows = session.execute(
        select(BenchmarkDiario.data, BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == "IFIX.SA")
        .order_by(BenchmarkDiario.data.asc())
    ).all()
    session.close()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["data", "fechamento"])
