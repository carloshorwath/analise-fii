from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal
from src.fii_analysis.features.indicators import get_pvp, get_pvp_serie
from src.fii_analysis.features.valuation import get_dy_n_meses


def get_payout_historico(ticker: str, cnpj: str, meses: int = 24, session=None) -> tuple[pd.DataFrame, int]:
    rows = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.rentab_efetiva,
            RelatorioMensal.rentab_patrim,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.rentab_efetiva.isnot(None),
            RelatorioMensal.rentab_patrim.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(meses)
    ).all()

    if not rows:
        return pd.DataFrame(columns=["data_referencia", "rentab_efetiva_pct", "rentab_patrimonial_pct", "distribuindo_mais_que_gera"]), 0

    records = []
    for r in reversed(rows):
        ef = float(r.rentab_efetiva) if r.rentab_efetiva is not None else None
        pa = float(r.rentab_patrim) if r.rentab_patrim is not None else None
        records.append({
            "data_referencia": r.data_referencia,
            "rentab_efetiva_pct": ef,
            "rentab_patrimonial_pct": pa,
            "distribuindo_mais_que_gera": ef is not None and pa is not None and ef > pa,
        })

    df = pd.DataFrame(records)
    meses_consec = 0
    for val in reversed(df["distribuindo_mais_que_gera"].tolist()):
        if val:
            meses_consec += 1
        else:
            break

    return df, meses_consec


def get_dy_medias(ticker: str, cnpj: str, session=None) -> dict:
    ultimo = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    if ultimo is None:
        return {"dy_12m_atual": None, "media_dy_2anos": None, "media_dy_5anos": None, "percentil_na_serie_completa": None}

    dy_12m = get_dy_n_meses(ticker, ultimo, 12, session)
    dy_24m = get_dy_n_meses(ticker, ultimo, 24, session)
    dy_60m = get_dy_n_meses(ticker, ultimo, 60, session)

    relatorios = session.execute(
        select(RelatorioMensal.dy_mes_pct)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.dy_mes_pct.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.asc())
    ).scalars().all()

    pct = None
    if relatorios and dy_12m is not None:
        dy_mensal = [float(d) for d in relatorios]
        dy_mensal_anualizado = [d * 12 for d in dy_mensal if d is not None]
        if dy_mensal_anualizado:
            dy_anual = dy_12m * 100
            pct = float(sum(1 for d in dy_mensal_anualizado if d <= dy_anual) / len(dy_mensal_anualizado) * 100)

    return {
        "dy_12m_atual": dy_12m,
        "media_dy_2anos": dy_24m,
        "media_dy_5anos": dy_60m,
        "percentil_na_serie_completa": pct,
    }


def get_pvp_medias(ticker: str, cnpj: str, session=None) -> dict:
    ultimo = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    if ultimo is None:
        return {"pvp_atual": None, "media_pvp_2anos": None, "media_pvp_5anos": None, "serie_pvp": pd.Series(dtype=float)}

    pvp_atual = get_pvp(ticker, ultimo, session)

    serie_df = get_pvp_serie(ticker, session)
    if serie_df.empty:
        return {"pvp_atual": pvp_atual, "media_pvp_2anos": None, "media_pvp_5anos": None, "serie_pvp": pd.Series(dtype=float)}

    serie_pvp = serie_df.set_index("data")["pvp"].dropna()

    janela_2a = serie_pvp.iloc[-504:] if len(serie_pvp) >= 504 else serie_pvp
    janela_5a = serie_pvp.iloc[-1260:] if len(serie_pvp) >= 1260 else serie_pvp

    return {
        "pvp_atual": pvp_atual,
        "media_pvp_2anos": float(janela_2a.mean()) if len(janela_2a) > 0 else None,
        "media_pvp_5anos": float(janela_5a.mean()) if len(janela_5a) > 0 else None,
        "serie_pvp": serie_pvp,
    }


def get_pl_cotas_historico(ticker: str, cnpj: str, meses: int = 36, session=None) -> pd.DataFrame:
    rows = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.patrimonio_liq,
            RelatorioMensal.cotas_emitidas,
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
        return pd.DataFrame(columns=["data_referencia", "patrimonio_liq", "cotas_emitidas", "vp_por_cota"])

    records = []
    for r in reversed(rows):
        records.append({
            "data_referencia": r.data_referencia,
            "patrimonio_liq": float(r.patrimonio_liq) if r.patrimonio_liq is not None else None,
            "cotas_emitidas": int(r.cotas_emitidas) if r.cotas_emitidas is not None else None,
            "vp_por_cota": float(r.vp_por_cota) if r.vp_por_cota is not None else None,
        })

    return pd.DataFrame(records)
