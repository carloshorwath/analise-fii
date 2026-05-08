from datetime import date, timedelta

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from loguru import logger
from sqlalchemy import func, select

from src.fii_analysis.data.database import (
    BenchmarkDiario, Dividendo, PrecoDiario, RelatorioMensal, Ticker,
    get_cnpj_by_ticker, volume_medio_21d,
)
from src.fii_analysis.features.indicators import get_pvp, get_dy_trailing
from src.fii_analysis.features.valuation import get_dy_n_meses


def _get_segmento(ticker: str, session) -> str | None:
    return session.execute(
        select(Ticker.segmento).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()


def _cvm_defasada(ticker: str, t: date, session) -> bool:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return True
    ultima_entrega = session.execute(
        select(RelatorioMensal.data_entrega)
        .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega.isnot(None))
        .order_by(RelatorioMensal.data_entrega.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultima_entrega is None:
        return True
    return (t - ultima_entrega).days > 45


def _get_return_n_months(ticker: str, fim: date, n_meses: int, session) -> float | None:
    inicio_ref = fim - relativedelta(months=n_meses)

    preco_inicio = session.execute(
        select(PrecoDiario.fechamento_aj)
        .where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data >= inicio_ref,
            PrecoDiario.fechamento_aj.isnot(None),
        )
        .order_by(PrecoDiario.data.asc())
        .limit(1)
    ).scalar_one_or_none()

    preco_fim = session.execute(
        select(PrecoDiario.fechamento_aj)
        .where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data <= fim,
            PrecoDiario.fechamento_aj.isnot(None),
        )
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    if preco_inicio is None or preco_fim is None:
        return None

    preco_inicio = float(preco_inicio)
    preco_fim = float(preco_fim)
    if preco_inicio <= 0:
        return None

    return preco_fim / preco_inicio - 1.0


def carteira_panorama(tickers: list[str], session) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        ultimo = session.execute(
            select(PrecoDiario.data, PrecoDiario.fechamento)
            .where(PrecoDiario.ticker == ticker)
            .order_by(PrecoDiario.data.desc())
            .limit(1)
        ).first()

        if ultimo is None:
            rows.append({"ticker": ticker, "preco": None, "vp": None, "pvp": None,
                         "dy_12m": None, "dy_24m": None, "dy_mes": None,
                         "rent_12m": None, "rent_24m": None,
                         "segmento": None, "cvm_defasada": True,
                         "volume_medio_21d": None})
            continue

        data_ultimo = ultimo[0]
        fech_ultimo = float(ultimo[1]) if ultimo[1] else None

        cnpj = get_cnpj_by_ticker(ticker, session)
        vp_row = None
        if cnpj:
            vp_row = session.execute(
                select(RelatorioMensal.vp_por_cota)
                .where(
                    RelatorioMensal.cnpj == cnpj,
                    RelatorioMensal.data_entrega <= data_ultimo,
                    RelatorioMensal.vp_por_cota.isnot(None),
                )
                .order_by(RelatorioMensal.data_referencia.desc())
                .limit(1)
            ).scalar_one_or_none()

        vp = float(vp_row) if vp_row else None
        pvp = (fech_ultimo / vp) if (fech_ultimo and vp and vp > 0) else None

        dy_12m = get_dy_n_meses(ticker, data_ultimo, 12, session)
        dy_24m = get_dy_n_meses(ticker, data_ultimo, 24, session)

        dy_mes_row = None
        if cnpj:
            dy_mes_row = session.execute(
                select(RelatorioMensal.dy_mes_pct)
                .where(
                    RelatorioMensal.cnpj == cnpj,
                    RelatorioMensal.data_entrega <= data_ultimo,
                )
                .order_by(RelatorioMensal.data_referencia.desc())
                .limit(1)
            ).scalar_one_or_none()
        dy_mes = float(dy_mes_row) / 100.0 if dy_mes_row is not None else None

        rent_12m = _get_return_n_months(ticker, data_ultimo, 12, session)
        rent_24m = _get_return_n_months(ticker, data_ultimo, 24, session)

        segmento = _get_segmento(ticker, session)
        cvm_def = _cvm_defasada(ticker, data_ultimo, session)
        vol_medio = volume_medio_21d(ticker, data_ultimo, session)

        rows.append({
            "ticker": ticker, "preco": fech_ultimo, "vp": vp, "pvp": pvp,
            "dy_12m": dy_12m, "dy_24m": dy_24m, "dy_mes": dy_mes,
            "rent_12m": rent_12m, "rent_24m": rent_24m, "segmento": segmento,
            "cvm_defasada": cvm_def, "volume_medio_21d": vol_medio,
        })

    return pd.DataFrame(rows)


def alocacao_segmento(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "preco" not in df.columns:
        return pd.DataFrame(columns=["segmento", "count", "pct"])
    total = df["preco"].dropna().sum()
    if total == 0:
        return pd.DataFrame(columns=["segmento", "count", "pct"])
    grp = df.groupby("segmento")["preco"].sum().reset_index()
    grp.columns = ["segmento", "total_preco"]
    grp["count"] = df.groupby("segmento")["ticker"].count().values
    grp["pct"] = grp["total_preco"] / total
    return grp[["segmento", "count", "pct"]]


_IFIX_TICKER = "XFIX11"


def retorno_vs_ifix(ticker: str, inicio: date, fim: date, session) -> dict:
    """Retorno do FII vs IFIX no período [inicio, fim].

    XFIX11 é buscado da tabela benchmark_diario (populada via load_benchmark_yfinance).
    Se não houver dados do IFIX, retorna None com warning — NÃO retorna zero.
    """
    preco_ini = session.execute(
        select(PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data >= inicio)
        .order_by(PrecoDiario.data.asc()).limit(1)
    ).scalar_one_or_none()
    preco_fim = session.execute(
        select(PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= fim)
        .order_by(PrecoDiario.data.desc()).limit(1)
    ).scalar_one_or_none()

    if preco_ini is None or preco_fim is None or float(preco_ini) == 0:
        return {"ticker": ticker, "retorno": None, "ifix_retorno": None, "diferenca": None}

    ret_fii = float(preco_fim) / float(preco_ini) - 1.0

    ifix_ini = session.execute(
        select(BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == _IFIX_TICKER, BenchmarkDiario.data >= inicio)
        .order_by(BenchmarkDiario.data.asc()).limit(1)
    ).scalar_one_or_none()
    ifix_fim = session.execute(
        select(BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == _IFIX_TICKER, BenchmarkDiario.data <= fim)
        .order_by(BenchmarkDiario.data.desc()).limit(1)
    ).scalar_one_or_none()

    ifix_retorno = None
    diferenca = None
    if ifix_ini is None or ifix_fim is None or float(ifix_ini) == 0:
        logger.warning(
            "retorno_vs_ifix: sem dados de IFIX.SA em benchmark_diario para o periodo {}-{}. "
            "Execute load_benchmark_yfinance('XFIX11', session) para popular.",
            inicio, fim,
        )
    else:
        ifix_retorno = float(ifix_fim) / float(ifix_ini) - 1.0
        diferenca = ret_fii - ifix_retorno

    return {"ticker": ticker, "retorno": ret_fii, "ifix_retorno": ifix_retorno, "diferenca": diferenca}


def herfindahl(pesos: list[float]) -> dict:
    if not pesos:
        return {"hh": None, "maior_peso": None}
    pesos_arr = np.array(pesos)
    pesos_arr = pesos_arr / pesos_arr.sum()
    return {"hh": float(np.sum(pesos_arr ** 2)), "maior_peso": float(np.max(pesos_arr))}
