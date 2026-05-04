from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import (
    BenchmarkDiario,
    Dividendo,
    PrecoDiario,
    RelatorioMensal,
    Ticker,
    get_cnpj_by_ticker,
    get_ultimo_preco_date,
    volume_medio_21d,
)
from src.fii_analysis.features.indicators import get_pvp
from src.fii_analysis.features.valuation import get_dy_gap


def get_info_ticker(ticker: str, session: Session) -> dict | None:
    row = session.execute(
        select(Ticker).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "cnpj": row.cnpj,
        "ticker": row.ticker,
        "nome": row.nome,
        "segmento": row.segmento,
        "mandato": row.mandato,
        "tipo_gestao": row.tipo_gestao,
        "data_inicio": str(row.data_inicio) if row.data_inicio else None,
        "inativo_em": str(row.inativo_em) if row.inativo_em else None,
    }


def get_proximas_datas_com(ticker: str, session: Session, limite: int = 5) -> list[dict]:
    hoje = date.today()
    rows = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker, Dividendo.data_com >= hoje)
        .order_by(Dividendo.data_com.asc())
        .limit(limite)
    ).all()
    return [{"data_com": str(r[0]), "valor_cota": float(r[1]) if r[1] else None} for r in rows]


def get_historico_pl(ticker: str, session: Session, meses: int = 24) -> pd.DataFrame:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return pd.DataFrame()
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
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["data_ref", "patrimonio_liq", "vp_por_cota"])
    df = df.sort_values("data_ref").reset_index(drop=True)
    df["patrimonio_liq"] = df["patrimonio_liq"].astype(float)
    df["vp_por_cota"] = df["vp_por_cota"].astype(float)
    return df


def get_ultimo_preco(ticker: str, session: Session) -> dict | None:
    row = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento, PrecoDiario.volume, PrecoDiario.coletado_em)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {
        "data": str(row[0]),
        "fechamento": float(row[1]) if row[1] else None,
        "volume": int(row[2]) if row[2] else None,
        "coletado_em": str(row[3]) if row[3] else None,
    }


def get_serie_preco_volume(ticker: str, session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento, PrecoDiario.volume)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento.isnot(None))
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["data", "fechamento", "volume"])
    df["fechamento"] = df["fechamento"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df


def get_benchmark_ifix(session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(BenchmarkDiario.data, BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == "IFIX.SA")
        .order_by(BenchmarkDiario.data.asc())
    ).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["data", "fechamento"])


def get_ifix_ytd(session: Session) -> float | None:
    df = get_benchmark_ifix(session)
    if df.empty:
        return None
    hoje = date.today()
    ano_inicio = date(hoje.year, 1, 1)
    df_ytd = df[df["data"] >= ano_inicio]
    if len(df_ytd) < 2:
        return None
    primeiro = float(df_ytd.iloc[0]["fechamento"])
    ultimo = float(df_ytd.iloc[-1]["fechamento"])
    if primeiro > 0:
        return ultimo / primeiro - 1.0
    return None


def get_dividendos_historico(ticker: str, session: Session) -> pd.DataFrame:
    rows = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker, Dividendo.valor_cota.isnot(None))
        .order_by(Dividendo.data_com.asc())
    ).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["data_com", "valor_cota"])


def get_pvp_anterior(ticker: str, session) -> float | None:
    rows = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(2)
    ).scalars().all()
    if len(rows) < 2:
        return None
    return get_pvp(ticker, rows[1], session)


def get_dy_gap_anterior(ticker: str, session) -> float | None:
    rows = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(22)
    ).scalars().all()
    if len(rows) < 22:
        return None
    return get_dy_gap(ticker, rows[21], session)


def get_volume_medio_21d_ticker(ticker: str, session) -> float | None:
    ultimo = get_ultimo_preco_date(ticker, session)
    if ultimo is None:
        return None
    return volume_medio_21d(ticker, ultimo, session)


def get_dias_desatualizado(ticker: str, session) -> int | None:
    import pandas_market_calendars as mcal

    ultimo = get_ultimo_preco_date(ticker, session)
    if ultimo is None:
        return None
    hoje = date.today()
    if ultimo >= hoje:
        return 0
    b3 = mcal.get_calendar("B3")
    schedule = b3.schedule(start_date=pd.Timestamp(ultimo + timedelta(days=1)), end_date=pd.Timestamp(hoje))
    return len(schedule)


def resolve_periodo(periodo: str, ticker: str, session) -> date | None:
    if periodo == "Max":
        return None
    ultimo = get_ultimo_preco_date(ticker, session)
    if ultimo is None:
        return None
    ref = ultimo
    if periodo == "1m":
        return ref - relativedelta(months=1)
    if periodo == "6m":
        return ref - relativedelta(months=6)
    if periodo == "1a":
        return ref - relativedelta(years=1)
    if periodo == "YTD":
        return date(ref.year, 1, 1)
    if periodo == "2a":
        return ref - relativedelta(years=2)
    if periodo == "3a":
        return ref - relativedelta(years=3)
    return None
