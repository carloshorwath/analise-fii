from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import Dividendo, PrecoDiario


def get_dividend_windows(ticker: str, session: Session) -> pd.DataFrame:
    """
    Retorna janela ±10 pregões ao redor de cada data-com.

    Usa fechamento_aj (preço ajustado por dividendos) para calcular retornos.
    Com preços ajustados, o efeito mecânico do ex-dividend já está removido:
    a série reflete retorno total (preço + dividendo) sem queda artificial no dia +1.
    """
    dividendos = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker)
        .order_by(Dividendo.data_com.asc())
    ).all()
    if not dividendos:
        return pd.DataFrame(
            columns=["ticker", "data_com", "valor_cota", "dia_relativo", "data", "fechamento", "retorno"]
        )

    pregoes = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not pregoes:
        return pd.DataFrame(
            columns=["ticker", "data_com", "valor_cota", "dia_relativo", "data", "fechamento", "retorno"]
        )

    datas_pregoes = [p.data for p in pregoes]
    fechamentos = {p.data: float(p.fechamento_aj) for p in pregoes if p.fechamento_aj is not None}
    datas_set = set(datas_pregoes)

    rows = []
    for data_com, valor_cota in dividendos:
        if data_com in datas_set:
            idx_dia0 = datas_pregoes.index(data_com)
        else:
            idx_dia0 = None
            for i, d in enumerate(datas_pregoes):
                if d > data_com:
                    break
                idx_dia0 = i
            if idx_dia0 is None:
                continue

        idx_start = max(0, idx_dia0 - 10)
        idx_end = min(len(datas_pregoes) - 1, idx_dia0 + 10)
        janela = datas_pregoes[idx_start : idx_end + 1]

        for i, d in enumerate(janela):
            dia_relativo = (idx_start + i) - idx_dia0
            if dia_relativo < -10 or dia_relativo > 10:
                continue

            fech = fechamentos.get(d)
            if fech is None:
                continue

            if i == 0:
                retorno = None
            else:
                fech_ant = fechamentos.get(janela[i - 1])
                if fech_ant is None or fech_ant == 0:
                    retorno = None
                else:
                    retorno = (fech / fech_ant) - 1.0

            rows.append(
                {
                    "ticker": ticker,
                    "data_com": data_com,
                    "valor_cota": float(valor_cota) if valor_cota is not None else None,
                    "dia_relativo": dia_relativo,
                    "data": d,
                    "fechamento": fech,
                    "retorno": retorno,
                }
            )

    return pd.DataFrame(rows)


def get_abnormal_returns(ticker: str, benchmark_returns: pd.Series, session: Session) -> pd.DataFrame:
    windows = get_dividend_windows(ticker, session)
    if windows.empty:
        return pd.DataFrame(
            columns=[
                "ticker", "data_com", "valor_cota", "dia_relativo",
                "data", "fechamento", "retorno", "retorno_benchmark", "retorno_anormal",
            ]
        )

    ret_bench = []
    ret_abn = []
    for _, row in windows.iterrows():
        d = row["data"]
        rb = benchmark_returns.get(d) if d in benchmark_returns.index else None
        ret_bench.append(rb)
        if row["retorno"] is not None and rb is not None:
            ret_abn.append(row["retorno"] - rb)
        else:
            ret_abn.append(None)

    windows = windows.copy()
    windows["retorno_benchmark"] = ret_bench
    windows["retorno_anormal"] = ret_abn
    return windows
