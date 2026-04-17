from datetime import date, timedelta

import numpy as np
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select

from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal, Ticker
from src.fii_analysis.data.ingestion import get_cdi_acumulado_12m


def _get_cnpj(ticker: str, session) -> str | None:
    return session.execute(
        select(Ticker.cnpj).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()


def get_pvp_serie_cached(ticker: str, session) -> list[tuple[date, float, float, float]]:
    cnpj = _get_cnpj(ticker, session)
    if cnpj is None:
        return []

    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not precos:
        return []

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

    result = []
    for d, fech in precos:
        fech_f = float(fech) if fech is not None else None
        vp_vigente = None
        for entrega, vp_val in reversed(vp_por_entrega):
            if entrega <= d:
                vp_vigente = vp_val
                break
        pvp = fech_f / vp_vigente if (fech_f is not None and vp_vigente is not None and vp_vigente != 0) else None
        if pvp is not None:
            result.append((d, fech_f, vp_vigente, pvp))
    return result


def get_pvp_percentil(ticker: str, t: date, janela: int = 504, session=None) -> float | None:
    serie = get_pvp_serie_cached(ticker, session)
    if not serie:
        return None

    datas_pvp = [s[0] for s in serie]
    pvps = [s[3] for s in serie]

    pvp_em_t = None
    idx_t = None
    for i, d in enumerate(datas_pvp):
        if d <= t:
            idx_t = i
            pvp_em_t = pvps[i]
        else:
            break

    if idx_t is None or pvp_em_t is None:
        return None

    start_idx = max(0, idx_t - janela)
    window = [pvps[i] for i in range(start_idx, idx_t) if pvps[i] is not None]

    if len(window) < 252:
        return None

    return float(np.percentile(window, 100) if pvp_em_t >= max(window) else
                 np.searchsorted(sorted(window), pvp_em_t) / len(window) * 100)


def _meses_atras(t: date, n_meses: int) -> date:
    """Retorna a data exatamente n_meses antes de t, respeitando fim de mês."""
    return (t - relativedelta(months=n_meses))


def get_dy_n_meses(ticker: str, t: date, n_meses: int, session=None) -> float | None:
    inicio = _meses_atras(t, n_meses)

    fechamento_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data == t,
        )
    ).scalar_one_or_none()

    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data >= inicio,
            PrecoDiario.data <= t,
        )
        .order_by(PrecoDiario.data.asc())
    ).all()

    if not precos:
        return None

    preco_medio = sum(float(p[1]) for p in precos if p[1] is not None) / len(precos)
    if preco_medio == 0:
        return None

    soma_div = session.execute(
        select(func.coalesce(func.sum(Dividendo.valor_cota), 0)).where(
            Dividendo.ticker == ticker,
            Dividendo.data_com >= inicio,
            Dividendo.data_com <= t,
        )
    ).scalar_one()

    if soma_div == 0:
        return None

    return float(soma_div) / preco_medio


def get_dy_gap(ticker: str, t: date, session=None) -> float | None:
    """DY Gap = DY 12m - CDI acumulado 12m em t (point-in-time via tabela cdi_diario).

    Se não houver CDI suficiente na tabela, retorna None (não usa fallback estático).
    """
    dy_12m = get_dy_n_meses(ticker, t, 12, session)
    if dy_12m is None:
        return None
    cdi = get_cdi_acumulado_12m(t, session)
    if cdi is None:
        return None
    return dy_12m - cdi


def get_dy_gap_percentil(ticker: str, t: date, janela: int = 504, session=None) -> float | None:
    """Percentil do DY Gap na janela rolling até t-1. Cada ponto usa CDI vigente em sua data."""
    precos = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= t)
        .order_by(PrecoDiario.data.asc())
    ).scalars().all()

    if len(precos) < 252:
        return None

    start_idx = max(0, len(precos) - janela)
    # exclui t do histórico (até t-1) para evitar contaminação trivial
    datas = precos[start_idx:-1] if len(precos) > start_idx + 1 else []

    if len(datas) < 252:
        return None

    gaps = []
    for d in datas:
        dy = get_dy_n_meses(ticker, d, 12, session)
        if dy is None:
            continue
        cdi = get_cdi_acumulado_12m(d, session)
        if cdi is None:
            continue
        gaps.append(dy - cdi)

    if len(gaps) < 252:
        return None

    gap_atual = get_dy_gap(ticker, t, session)
    if gap_atual is None:
        return None

    sorted_gaps = sorted(gaps)
    rank = sum(1 for g in sorted_gaps if g <= gap_atual)
    return rank / len(sorted_gaps) * 100
