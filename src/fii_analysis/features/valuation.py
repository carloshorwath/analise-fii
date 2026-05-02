from datetime import date, timedelta

import numpy as np
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select

from src.fii_analysis.config_yaml import get_threshold
from src.fii_analysis.data.database import CdiDiario, Dividendo, PrecoDiario, RelatorioMensal, get_cnpj_by_ticker
from src.fii_analysis.data.cdi import get_cdi_acumulado_12m
from src.fii_analysis.features.indicators import get_pvp_serie


def _extract_pvp_tuples(serie_df) -> list[tuple]:
    result = []
    for _, row in serie_df.iterrows():
        pvp = row.get("pvp")
        if pvp is not None:
            result.append((row["data"], row.get("fechamento"), row.get("vp_por_cota"), pvp))
    return result


def get_pvp_percentil(ticker: str, t: date, janela: int | None = None, session=None) -> tuple[float | None, int]:
    if janela is None:
        janela = get_threshold("pvp_janela_pregoes", 504)
    serie_df = get_pvp_serie(ticker, session)
    if serie_df.empty:
        return None, 0

    serie = _extract_pvp_tuples(serie_df)
    if not serie:
        return None, 0

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
        return None, 0

    start_idx = max(0, idx_t - janela)
    window = [pvps[i] for i in range(start_idx, idx_t) if pvps[i] is not None]
    n = len(window)

    if n < 63:
        return None, 0

    percentil = float(np.percentile(window, 100) if pvp_em_t >= max(window) else
                 np.searchsorted(sorted(window), pvp_em_t) / n * 100)

    if n >= 252:
        return percentil, janela
    else:
        return percentil, n


def _meses_atras(t: date, n_meses: int) -> date:
    """Retorna a data exatamente n_meses antes de t, respeitando fim de mês."""
    return (t - relativedelta(months=n_meses))


def get_dy_n_meses(ticker: str, t: date, n_meses: int, session=None) -> float | None:
    inicio = _meses_atras(t, n_meses)

    preco_ref = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data <= t,
        )
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()

    if preco_ref is None or float(preco_ref) == 0:
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

    return float(soma_div) / float(preco_ref)


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


def get_dy_gap_percentil(ticker: str, t: date, janela: int | None = None, session=None) -> float | None:
    if janela is None:
        janela = get_threshold("dy_janela_pregoes", 252)
    """Percentil do DY Gap na janela rolling ate t-1. Batch queries em vez de N+1."""
    from math import prod

    datas_precos = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= t)
        .order_by(PrecoDiario.data.asc())
    ).scalars().all()

    if len(datas_precos) < 252:
        return None

    start_idx = max(0, len(datas_precos) - janela)
    datas = datas_precos[start_idx:-1] if len(datas_precos) > start_idx + 1 else []

    if len(datas) < max(1, janela - 2):
        return None

    data_min = datas[0]
    data_max = datas[-1]

    divs = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(
            Dividendo.ticker == ticker,
            Dividendo.data_com >= _meses_atras(data_max, 12),
            Dividendo.data_com <= data_max,
            Dividendo.valor_cota.isnot(None),
        )
        .order_by(Dividendo.data_com.asc())
    ).all()
    div_dates = [d.data_com for d in divs]
    div_vals = [float(d.valor_cota) for d in divs]

    precos_batch = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data >= _meses_atras(data_min, 12),
            PrecoDiario.data <= data_max,
            PrecoDiario.fechamento.isnot(None),
        )
        .order_by(PrecoDiario.data.asc())
    ).all()
    preco_map = {p.data: float(p.fechamento) for p in precos_batch}

    cdi_batch = session.execute(
        select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
        .where(CdiDiario.data >= _meses_atras(data_min, 12), CdiDiario.data <= data_max)
        .order_by(CdiDiario.data.asc())
    ).all()
    cdi_rows = [(c.data, float(c.taxa_diaria_pct)) for c in cdi_batch]

    def _preco_em(d):
        preco = preco_map.get(d)
        if preco is not None:
            return preco
        best = None
        for pd_date, pd_val in precos_batch:
            if pd_date <= d:
                best = pd_val
            else:
                break
        return float(best) if best is not None else None

    def _dy_12m_em(d):
        inicio = _meses_atras(d, 12)
        soma = 0.0
        for i, dd in enumerate(div_dates):
            if inicio < dd <= d:
                soma += div_vals[i]
        if soma == 0:
            return None
        p = _preco_em(d)
        if p is None or p == 0:
            return None
        return soma / p

    def _cdi_12m_em(d):
        inicio = _meses_atras(d, 12)
        taxas = [v for dt, v in cdi_rows if inicio <= dt <= d]
        if len(taxas) < 200:
            return None
        return prod(1.0 + v / 100.0 for v in taxas) - 1.0

    gaps = []
    for d in datas:
        dy = _dy_12m_em(d)
        if dy is None:
            continue
        cdi = _cdi_12m_em(d)
        if cdi is None:
            continue
        gaps.append(dy - cdi)

    if len(gaps) < max(50, len(datas) // 5):
        return None

    gap_atual = get_dy_gap(ticker, t, session)
    if gap_atual is None:
        return None

    sorted_gaps = sorted(gaps)
    rank = sum(1 for g in sorted_gaps if g <= gap_atual)
    return rank / len(sorted_gaps) * 100
