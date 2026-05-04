"""Score numérico 0–100 para FIIs com decomposição em sub-scores.

Arquitetura:
    Score(FII) = 0.35 × ScoreValuation
               + 0.30 × ScoreRisco
               + 0.20 × ScoreLiquidez
               + 0.15 × ScoreHistórico

Sub-scores (0–100 cada):
    ScoreValuation : P/VP percentil invertido + DY Gap percentil
    ScoreRisco     : volatilidade, beta, drawdown vs universo (percentil relativo)
    ScoreLiquidez  : faixas fixas em R$/dia
    ScoreHistórico : consistência do DY 24m (coeficiente de variação invertido)

O score é uma camada de *comunicação* — não substitui nem altera os sinais
estatísticos do motor (otimizador/episódios/walk-forward). Usar
calcular_score() nos snapshots diários e nunca na inferência.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select

from src.fii_analysis.data.database import RelatorioMensal, get_cnpj_by_ticker


@dataclass
class ScoreFII:
    ticker: str
    data_referencia: date
    score_total: int           # 0–100
    score_valuation: int       # 0–100
    score_risco: int           # 0–100
    score_liquidez: int        # 0–100
    score_historico: int       # 0–100
    # campos auxiliares para auditoria
    pvp_percentil: float | None = None
    dy_gap_percentil: float | None = None
    pvp_zscore: float | None = None
    volatilidade: float | None = None
    beta: float | None = None
    max_drawdown: float | None = None
    liquidez_21d_brl: float | None = None
    dy_3m_anualizado: float | None = None
    detalhes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sub-scores individuais
# ---------------------------------------------------------------------------


def score_valuation(pvp_percentil: float | None, dy_gap_percentil: float | None, pvp_zscore: float | None = None) -> int:
    """P/VP baixo = bom; DY Gap alto = bom. Pesos: 60/40 ou 50/30/20 com z-score."""
    pvp_score = (100.0 - pvp_percentil) if pvp_percentil is not None else 50.0
    gap_score = dy_gap_percentil if dy_gap_percentil is not None else 50.0
    if pvp_zscore is not None:
        zscore_score = max(0.0, min(100.0, 50.0 - pvp_zscore * 20.0))
        raw = 0.50 * pvp_score + 0.30 * gap_score + 0.20 * zscore_score
    else:
        raw = 0.60 * pvp_score + 0.40 * gap_score
    return _clamp(round(raw))


def score_risco(
    vol: float | None,
    beta: float | None,
    mdd: float | None,
    vol_universe: list[float],
    beta_universe: list[float],
    mdd_universe: list[float],
) -> int:
    """Risco alto = score baixo. Normaliza cada métrica pelo percentil no universo."""
    scores: list[float] = []

    if vol is not None and vol_universe:
        pct = _percentil_rank(vol, vol_universe)
        scores.append(100.0 - pct)  # vol alta → pct alto → score baixo

    if beta is not None and beta_universe:
        abs_beta = abs(beta)
        abs_universe = [abs(b) for b in beta_universe if b is not None]
        if abs_universe:
            pct = _percentil_rank(abs_beta, abs_universe)
            scores.append(100.0 - pct)

    if mdd is not None and mdd_universe:
        abs_mdd = abs(mdd)
        abs_universe = [abs(m) for m in mdd_universe if m is not None]
        if abs_universe:
            pct = _percentil_rank(abs_mdd, abs_universe)
            scores.append(100.0 - pct)

    if not scores:
        return 50
    return _clamp(round(sum(scores) / len(scores)))


def score_liquidez(liquidez_21d_brl: float | None) -> int:
    """Faixas fixas em R$/dia — independente do universo."""
    if liquidez_21d_brl is None:
        return 20
    liq = liquidez_21d_brl
    if liq < 200_000:
        return 20
    if liq < 1_000_000:
        return 50
    if liq < 5_000_000:
        return 75
    return 90


def score_historico(ticker: str, session=None) -> int:
    """Consistência do DY mensal nos últimos 24 meses (CV invertido).

    CV = std / mean. CV baixo = DY consistente = score alto.
    """
    if session is None:
        return 50

    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return 50

    rows = session.execute(
        select(RelatorioMensal.dy_mes_pct)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.dy_mes_pct.isnot(None),
            RelatorioMensal.dy_mes_pct > 0,
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(24)
    ).scalars().all()

    vals = [float(v) for v in rows if v is not None]
    if len(vals) < 6:
        return 50

    mean_val = sum(vals) / len(vals)
    if mean_val <= 0:
        return 50

    variance = sum((v - mean_val) ** 2 for v in vals) / len(vals)
    std_val = math.sqrt(variance)
    cv = std_val / mean_val  # 0 = perfeitamente consistente

    # CV típico de FIIs: 0–0.5. Mapear linearmente invertido para 0–100.
    # CV=0 → 100 pts; CV≥0.5 → 0 pts; clampar.
    raw = (1.0 - min(cv / 0.5, 1.0)) * 100.0
    return _clamp(round(raw))


# ---------------------------------------------------------------------------
# Função pública principal
# ---------------------------------------------------------------------------


def calcular_score(
    ticker: str,
    *,
    pvp_percentil: float | None = None,
    dy_gap_percentil: float | None = None,
    pvp_zscore: float | None = None,
    volatilidade: float | None = None,
    beta: float | None = None,
    mdd: float | None = None,
    liquidez_21d_brl: float | None = None,
    todos_tickers: list[str] | None = None,
    session=None,
) -> ScoreFII:
    """Calcula o score composto 0–100 de um FII.

    Parâmetros de risco são relativos ao universo `todos_tickers` quando
    fornecidos. Se o universo não for informado, score_risco usa apenas
    as métricas absolutas disponíveis (sem normalização relativa).

    Args:
        ticker: Código do FII (ex: "KNIP11")
        pvp_percentil: Percentil P/VP 0–100
        dy_gap_percentil: Percentil DY Gap 0–100
        volatilidade: Volatilidade anualizada (ex: 0.11 = 11%)
        beta: Beta vs IFIX (None se indisponível)
        mdd: Max Drawdown (valor negativo, ex: -0.09)
        liquidez_21d_brl: Volume médio 21d em R$
        todos_tickers: Lista de tickers para normalização relativa do risco
        session: Sessão SQLAlchemy (necessária para score_historico)
    """
    data_ref = date.today()

    sv = score_valuation(pvp_percentil, dy_gap_percentil, pvp_zscore)
    sl = score_liquidez(liquidez_21d_brl)
    sh = score_historico(ticker, session)

    # Risco: busca métricas dos outros tickers se universo fornecido
    vol_univ: list[float] = []
    beta_univ: list[float] = []
    mdd_univ: list[float] = []

    if todos_tickers and session is not None:
        from src.fii_analysis.features.risk_metrics import (
            beta_vs_ifix,
            max_drawdown,
            volatilidade_anualizada,
        )
        for t in todos_tickers:
            try:
                v = volatilidade_anualizada(t, session=session)
                if v is not None:
                    vol_univ.append(v)
            except Exception:
                pass
            try:
                b = beta_vs_ifix(t, session=session)
                if b is not None:
                    beta_univ.append(b)
            except Exception:
                pass
            try:
                m = max_drawdown(t, session=session)
                if m is not None:
                    mdd_univ.append(m)
            except Exception:
                pass

    sr = score_risco(volatilidade, beta, mdd, vol_univ, beta_univ, mdd_univ)

    total = round(0.35 * sv + 0.30 * sr + 0.20 * sl + 0.15 * sh)

    return ScoreFII(
        ticker=ticker,
        data_referencia=data_ref,
        score_total=_clamp(total),
        score_valuation=sv,
        score_risco=sr,
        score_liquidez=sl,
        score_historico=sh,
        pvp_percentil=pvp_percentil,
        dy_gap_percentil=dy_gap_percentil,
        pvp_zscore=pvp_zscore,
        volatilidade=volatilidade,
        beta=beta,
        max_drawdown=mdd,
        liquidez_21d_brl=liquidez_21d_brl,
        detalhes={
            "vol_universe_size": len(vol_univ),
            "beta_universe_size": len(beta_univ),
            "mdd_universe_size": len(mdd_univ),
        },
    )


def calcular_score_batch(
    tickers: list[str],
    metricas: dict[str, dict],
    session=None,
) -> dict[str, ScoreFII]:
    """Calcula score para uma lista de tickers com normalização cruzada.

    Args:
        tickers: Lista de tickers ativos
        metricas: Dict ticker → dict com chaves:
            pvp_percentil, dy_gap_percentil, volatilidade, beta, mdd, liquidez_21d_brl
        session: Sessão SQLAlchemy para score_historico
    Returns:
        Dict ticker → ScoreFII
    """
    vol_univ = [m.get("volatilidade") for m in metricas.values() if m.get("volatilidade") is not None]
    beta_univ = [m.get("beta") for m in metricas.values() if m.get("beta") is not None]
    mdd_univ = [m.get("mdd") for m in metricas.values() if m.get("mdd") is not None]

    results: dict[str, ScoreFII] = {}
    for ticker in tickers:
        m = metricas.get(ticker, {})
        sv = score_valuation(m.get("pvp_percentil"), m.get("dy_gap_percentil"), m.get("pvp_zscore"))
        sl = score_liquidez(m.get("liquidez_21d_brl"))
        sh = score_historico(ticker, session)
        sr = score_risco(
            m.get("volatilidade"),
            m.get("beta"),
            m.get("mdd"),
            vol_univ, beta_univ, mdd_univ,
        )
        total = _clamp(round(0.35 * sv + 0.30 * sr + 0.20 * sl + 0.15 * sh))
        results[ticker] = ScoreFII(
            ticker=ticker,
            data_referencia=date.today(),
            score_total=total,
            score_valuation=sv,
            score_risco=sr,
            score_liquidez=sl,
            score_historico=sh,
            pvp_percentil=m.get("pvp_percentil"),
            dy_gap_percentil=m.get("dy_gap_percentil"),
            pvp_zscore=m.get("pvp_zscore"),
            volatilidade=m.get("volatilidade"),
            beta=m.get("beta"),
            max_drawdown=m.get("mdd"),
            liquidez_21d_brl=m.get("liquidez_21d_brl"),
            detalhes={
                "vol_universe_size": len(vol_univ),
                "beta_universe_size": len(beta_univ),
                "mdd_universe_size": len(mdd_univ),
            },
        )
    return results


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _clamp(val: int | float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(val)))


def _percentil_rank(value: float, universe: list[float]) -> float:
    """Percentil do valor dentro do universo (0–100). Sem interpolação."""
    if not universe:
        return 50.0
    below = sum(1 for v in universe if v < value)
    return (below / len(universe)) * 100.0
