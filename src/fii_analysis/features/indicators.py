from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select

from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal, Ticker


def _get_cnpj(ticker: str, session) -> str | None:
    return session.execute(
        select(Ticker.cnpj).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()


def get_pvp(ticker: str, data: date, session) -> float | None:
    preco_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data == data,
        )
    ).scalar_one_or_none()
    if preco_row is None:
        return None

    cnpj = _get_cnpj(ticker, session)
    if cnpj is None:
        return None

    vp = session.execute(
        select(RelatorioMensal.vp_por_cota)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.data_entrega <= data,
            RelatorioMensal.vp_por_cota.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(1)
    ).scalar_one_or_none()
    if vp is None:
        return None

    return float(preco_row) / float(vp)


def get_dy_trailing(ticker: str, data: date, session, janela_dias: int = 365) -> float | None:
    preco_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data == data,
        )
    ).scalar_one_or_none()
    if preco_row is None:
        return None

    inicio = data - timedelta(days=janela_dias)
    soma = session.execute(
        select(func.coalesce(func.sum(Dividendo.valor_cota), 0)).where(
            Dividendo.ticker == ticker,
            Dividendo.data_com > inicio,
            Dividendo.data_com <= data,
        )
    ).scalar_one()
    if soma == 0:
        return None

    return float(soma) / float(preco_row)


def get_pvp_serie(ticker: str, session) -> pd.DataFrame:
    cnpj = _get_cnpj(ticker, session)
    if cnpj is None:
        return pd.DataFrame(columns=["data", "fechamento", "vp_por_cota", "pvp"])

    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not precos:
        return pd.DataFrame(columns=["data", "fechamento", "vp_por_cota", "pvp"])

    relatorios = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.data_entrega,
            RelatorioMensal.vp_por_cota,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.vp_por_cota.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_entrega.asc())
    ).all()

    vp_por_entrega = [(r.data_entrega, float(r.vp_por_cota)) for r in relatorios]

    rows = []
    for d, fech in precos:
        fech_f = float(fech) if fech is not None else None
        vp_vigente = None
        for entrega, vp_val in reversed(vp_por_entrega):
            if entrega <= d:
                vp_vigente = vp_val
                break
        pvp = fech_f / vp_vigente if (fech_f is not None and vp_vigente is not None) else None
        rows.append({"data": d, "fechamento": fech_f, "vp_por_cota": vp_vigente, "pvp": pvp})

    return pd.DataFrame(rows)


def get_dy_serie(ticker: str, session, janela_dias: int = 365) -> pd.DataFrame:
    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not precos:
        return pd.DataFrame(columns=["data", "fechamento", "dividendos_12m", "dy"])

    dividendos = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker)
        .order_by(Dividendo.data_com.asc())
    ).all()

    div_dates = [d.data_com for d in dividendos]
    div_vals = [float(d.valor_cota) if d.valor_cota is not None else 0.0 for d in dividendos]

    rows = []
    for d, fech in precos:
        fech_f = float(fech) if fech is not None else None
        inicio = d - timedelta(days=janela_dias)
        soma = 0.0
        for i, dd in enumerate(div_dates):
            if inicio < dd <= d:
                soma += div_vals[i]
        dy = soma / fech_f if (fech_f is not None and fech_f > 0 and soma > 0) else None
        rows.append({"data": d, "fechamento": fech_f, "dividendos_12m": soma if soma > 0 else None, "dy": dy})

    return pd.DataFrame(rows)
