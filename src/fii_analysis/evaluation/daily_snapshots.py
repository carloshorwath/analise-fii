"""Geração e leitura de snapshots diários.

Responsabilidade: orquestrar cálculo por bloco, persistir em snapshot_*,
marcar run como ready ou failed. Zero Streamlit. Zero print().

Fases cobertas:
  Fase 1 — schema (database.py)
  Fase 2 — snapshot_ticker_metrics + snapshot_radar  (generate_base_snapshots)
  Fase 3 — snapshot_decisions com versionamento por motor
  Fase 4 — snapshot_portfolio_advices + snapshot_structural_alerts

Funções públicas principais:
    generate_daily_snapshot(session, ...)       -> dict status+contadores
    generate_base_snapshots(session, ...)       -> (n_metrics, n_radar, falhos)
    build_snapshot_decisions(session, ...)      -> (n_salvos, falhos)
    build_snapshot_portfolio_advices(session, .)-> (advices, n_salvos, falhos)
    build_snapshot_structural_alerts(session, .)-> n_salvos
    resolve_snapshot_universe(session, scope)   -> list[str]
    load_snapshot_decisions(session, run_id)    -> list[TickerDecision]
    get_snapshot_decisions(session, run_id)     -> list[SnapshotDecisions]
    get_latest_ready_snapshot(session, scope)   -> SnapshotRun | None
    serialize_ticker_decision(decision, run_id) -> dict
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.fii_analysis.config import TICKERS, tickers_ativos
from src.fii_analysis.features import risk_metrics as _rm
from src.fii_analysis.data.database import (
    Carteira,
    CdiDiario,
    Dividendo,
    PrecoDiario,
    RelatorioMensal,
    SnapshotDecisions,
    SnapshotPortfolioAdvices,
    SnapshotRadar,
    SnapshotRun,
    SnapshotStructuralAlerts,
    SnapshotTickerMetrics,
    get_cnpj_by_ticker,
    get_latest_ready_snapshot_run,
)
from src.fii_analysis.decision.portfolio_advisor import (
    AlertaEstrutural,
    HoldingAdvice,
    aconselhar_carteira,
    alertas_estruturais,
)
from src.fii_analysis.decision.recommender import TickerDecision, decidir_universo
from src.fii_analysis.features.portfolio import carteira_panorama
from src.fii_analysis.features.radar import radar_matriz
from src.fii_analysis.features.risk_metrics import (
    beta_vs_ifix,
    dy_3m_anualizado as rm_dy_3m_anualizado,
    liquidez_media_21d,
    max_drawdown,
    retorno_total_12m,
    volatilidade_anualizada,
)
from src.fii_analysis.features.score import ScoreFII, calcular_score_batch
from src.fii_analysis.features.valuation import (
    get_dy_gap,
    get_dy_gap_percentil,
    get_pvp_percentil,
)
from src.fii_analysis.data.focus_bcb import FocusSelicResult, fetch_focus_selic
from src.fii_analysis.decision.cdi_focus_explainer import build_cdi_focus_explanation
from src.fii_analysis.models.cdi_sensitivity import compute_cdi_sensitivity_batch, cdi_sensitivity_to_dict
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2


ENGINE_VERSION = "snapshot_v1"
VERSION_OTIMIZADOR = "v2"
VERSION_EPISODIOS = "v1"
VERSION_WALKFORWARD = "v1"
VERSION_RECOMMENDER = "v1"

_CVM_DEFASADA_DIAS = 60


# =============================================================================
# Helpers internos
# =============================================================================


def _universe_hash(tickers: list[str]) -> str:
    return hashlib.md5(",".join(sorted(tickers)).encode()).hexdigest()[:12]


def _carteira_hash(holdings: list[dict]) -> str | None:
    if not holdings:
        return None
    key = ",".join(
        f"{h['ticker']}:{h.get('quantidade', 0)}"
        for h in sorted(holdings, key=lambda x: x["ticker"])
    )
    return hashlib.md5(key.encode()).hexdigest()[:12]


def compute_carteira_hash(holdings: list[dict]) -> str | None:
    """Wrapper público de _carteira_hash para uso na UI."""
    return _carteira_hash(holdings)


def _base_preco_ate(session: Session) -> date | None:
    return session.execute(select(func.max(PrecoDiario.data))).scalar_one_or_none()


def _base_dividendo_ate(session: Session) -> date | None:
    return session.execute(select(func.max(Dividendo.data_com))).scalar_one_or_none()


def _base_cdi_ate(session: Session) -> date | None:
    return session.execute(select(func.max(CdiDiario.data))).scalar_one_or_none()


def _build_optimizer_params_map(session: Session, tickers: list[str]) -> dict[str, dict]:
    optimizer = ThresholdOptimizerV2()
    params_map: dict[str, dict] = {}
    for ticker in tickers:
        try:
            result = optimizer.optimize(ticker, session)
        except Exception as e:
            logger.warning(f"Optimizer falhou para {ticker}: {e}")
            continue
        if "error" not in result and result.get("best_params"):
            params_map[ticker] = result["best_params"]
    return params_map


def _float_or_none(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _bool_or_none(val) -> bool | None:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    return bool(val)


def _int_or_none(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    return int(val)


# =============================================================================
# Resolução de universo
# =============================================================================


def resolve_snapshot_universe(
    session: Session,
    scope: str,
    holdings: list[dict] | None = None,
) -> list[str]:
    """Mapeia scope para lista estável de tickers.

    scope="curado"    — TICKERS do config.py filtrado pelos ativos no banco
    scope="carteira"  — tickers das holdings (ou lê da tabela carteira)
    scope="db_ativos" — todos os tickers com inativo_em IS NULL no banco
    """
    if scope == "curado":
        ativos = set(tickers_ativos(session))
        return sorted(t for t in TICKERS if t in ativos)

    if scope == "carteira":
        if holdings is not None:
            return sorted(set(h["ticker"] for h in holdings if h.get("ticker")))
        rows = session.execute(select(Carteira.ticker)).scalars().all()
        return sorted(set(rows))

    if scope == "db_ativos":
        return sorted(tickers_ativos(session))

    raise ValueError(f"scope inválido: {scope!r}. Use: curado, carteira, db_ativos")


# =============================================================================
# Bloco 1 — Ticker Metrics  (Fase 2)
# =============================================================================


def build_snapshot_ticker_metrics(
    session: Session,
    run_id: int,
    tickers: list[str],
    data_ref: date,
) -> tuple[int, list[str]]:
    """Calcula e persiste métricas point-in-time por ticker.

    Fonte primária: carteira_panorama() — reutiliza lógica já testada.
    Complemento: pvp_percentil, dy_gap, dy_gap_percentil via valuation.py.

    Retorna (n_salvos, tickers_falhos).
    """
    tickers_falhos: list[str] = []
    count = 0

    try:
        df_pan: pd.DataFrame = carteira_panorama(tickers, session)
    except Exception as e:
        logger.warning(f"carteira_panorama falhou (tickers={tickers}): {e}")
        df_pan = pd.DataFrame()

    pan_map: dict[str, dict] = {}
    if not df_pan.empty and "ticker" in df_pan.columns:
        for _, row in df_pan.iterrows():
            pan_map[row["ticker"]] = row.to_dict()

    # Pre-calcular métricas de risco para todos os tickers (normalização cruzada no score)
    risk_map: dict[str, dict] = {}
    for ticker in tickers:
        rm: dict = {}
        try:
            rm["volatilidade"] = volatilidade_anualizada(ticker, session=session)
        except Exception as e:
            logger.warning(f"volatilidade_anualizada falhou para {ticker}: {e}")
            rm["volatilidade"] = None
        try:
            rm["beta"] = beta_vs_ifix(ticker, session=session)
        except Exception as e:
            logger.warning(f"beta_vs_ifix falhou para {ticker}: {e}")
            rm["beta"] = None
        try:
            rm["mdd"] = max_drawdown(ticker, session=session)
        except Exception as e:
            logger.warning(f"max_drawdown falhou para {ticker}: {e}")
            rm["mdd"] = None
        try:
            rm["liquidez_21d_brl"] = liquidez_media_21d(ticker, session=session)
        except Exception as e:
            logger.warning(f"liquidez_media_21d falhou para {ticker}: {e}")
            rm["liquidez_21d_brl"] = None
        try:
            rm["retorno_total_12m"] = retorno_total_12m(ticker, session=session)
        except Exception as e:
            logger.warning(f"retorno_total_12m falhou para {ticker}: {e}")
            rm["retorno_total_12m"] = None
        try:
            rm["dy_3m_anualizado"] = rm_dy_3m_anualizado(ticker, session=session)
        except Exception as e:
            logger.warning(f"dy_3m_anualizado falhou para {ticker}: {e}")
            rm["dy_3m_anualizado"] = None
        risk_map[ticker] = rm

    for ticker in tickers:
        try:
            row = pan_map.get(ticker, {})

            preco = _float_or_none(row.get("preco"))
            vp = _float_or_none(row.get("vp"))
            pvp = _float_or_none(row.get("pvp"))
            dy_12m = _float_or_none(row.get("dy_12m"))
            dy_24m = _float_or_none(row.get("dy_24m"))
            rent_12m = _float_or_none(row.get("rent_12m"))
            rent_24m = _float_or_none(row.get("rent_24m"))
            segmento = row.get("segmento")
            cvm_defasada = _bool_or_none(row.get("cvm_defasada"))
            vol_21d = _float_or_none(row.get("volume_medio_21d"))

            # Campos não entregues por carteira_panorama — complementar
            pvp_pct, _ = get_pvp_percentil(ticker, data_ref, 504, session)
            dy_gap = get_dy_gap(ticker, data_ref, session)
            dy_gap_pct = get_dy_gap_percentil(ticker, data_ref, 252, session)

            rm = risk_map.get(ticker, {})
            # Armazenar para reutilizar no cálculo de score (evitar recalcular)
            rm["pvp_percentil"] = pvp_pct
            rm["dy_gap_percentil"] = dy_gap_pct

            session.add(SnapshotTickerMetrics(
                run_id=run_id,
                ticker=ticker,
                preco=preco,
                vp=vp,
                pvp=pvp,
                pvp_percentil=pvp_pct,
                dy_12m=dy_12m,
                dy_24m=dy_24m,
                rent_12m=rent_12m,
                rent_24m=rent_24m,
                dy_gap=dy_gap,
                dy_gap_percentil=dy_gap_pct,
                volume_21d=vol_21d,
                cvm_defasada=cvm_defasada,
                segmento=segmento,
                # Fase 1.5 — risk_metrics
                volatilidade_anual=rm.get("volatilidade"),
                beta_ifix=rm.get("beta"),
                max_drawdown=rm.get("mdd"),
                liquidez_21d_brl=rm.get("liquidez_21d_brl"),
                retorno_total_12m=rm.get("retorno_total_12m"),
                dy_3m_anualizado=rm.get("dy_3m_anualizado"),
            ))
            count += 1

        except Exception as e:
            logger.warning(f"Falha ao calcular métricas para {ticker}: {e}")
            tickers_falhos.append(ticker)

    session.flush()

    # Fase 2 — calcular scores com normalização cruzada e persistir
    _build_scores_into_metrics(session, run_id, tickers, pan_map, risk_map)

    return count, tickers_falhos


def _build_scores_into_metrics(
    session: Session,
    run_id: int,
    tickers: list[str],
    pan_map: dict[str, dict],
    risk_map: dict[str, dict],
) -> None:
    """Calcula scores batch e atualiza colunas score_* nos registros já inseridos."""
    from sqlalchemy import update as sa_update

    # Montar dict de métricas para calcular_score_batch (reutilizar pvp/dygap já calculados)
    metricas: dict[str, dict] = {}
    for ticker in tickers:
        rm = risk_map.get(ticker, {})
        metricas[ticker] = {
            "pvp_percentil": rm.get("pvp_percentil"),
            "dy_gap_percentil": rm.get("dy_gap_percentil"),
            "volatilidade": rm.get("volatilidade"),
            "beta": rm.get("beta"),
            "mdd": rm.get("mdd"),
            "liquidez_21d_brl": rm.get("liquidez_21d_brl"),
        }

    try:
        scores = calcular_score_batch(tickers, metricas, session)
    except Exception as e:
        logger.error(f"calcular_score_batch falhou (scores serão NULL): {e}")
        return

    for ticker, sc in scores.items():
        try:
            session.execute(
                sa_update(SnapshotTickerMetrics)
                .where(
                    SnapshotTickerMetrics.run_id == run_id,
                    SnapshotTickerMetrics.ticker == ticker,
                )
                .values(
                    score_total=sc.score_total,
                    score_valuation=sc.score_valuation,
                    score_risco=sc.score_risco,
                    score_liquidez=sc.score_liquidez,
                    score_historico=sc.score_historico,
                )
            )
        except Exception as e:
            logger.warning(f"Falha ao persistir score para {ticker}: {e}")
    session.flush()


# =============================================================================
# Bloco 2 — Radar  (Fase 2)
# =============================================================================


def build_snapshot_radar(
    session: Session,
    run_id: int,
    tickers: list[str],
) -> tuple[int, list[str]]:
    """Calcula e persiste flags do radar por ticker.

    Fonte: radar_matriz() de features/radar.py.
    Retorna (n_salvos, tickers_falhos).
    """
    tickers_falhos: list[str] = []
    count = 0

    try:
        df: pd.DataFrame = radar_matriz(tickers=tickers, session=session)
    except Exception as e:
        logger.error(f"radar_matriz falhou para run_id={run_id}: {e}")
        return 0, list(tickers)

    for _, row in df.iterrows():
        ticker = row.get("ticker")
        if not ticker:
            continue
        try:
            session.add(SnapshotRadar(
                run_id=run_id,
                ticker=ticker,
                pvp_baixo=_bool_or_none(row.get("pvp_baixo")),
                dy_gap_alto=_bool_or_none(row.get("dy_gap_alto")),
                saude_ok=_bool_or_none(row.get("saude_ok")),
                liquidez_ok=_bool_or_none(row.get("liquidez_ok")),
                vistos=_int_or_none(row.get("vistos")),
                saude_motivo=row.get("saude_motivo"),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Falha ao calcular radar para {ticker}: {e}")
            tickers_falhos.append(ticker)

    session.flush()
    return count, tickers_falhos


def generate_base_snapshots(
    session: Session,
    run_id: int,
    tickers: list[str],
    data_ref: date,
) -> tuple[int, int, list[str]]:
    """Orquestra métricas + radar. Retorna (n_metrics, n_radar, tickers_falhos)."""
    all_falhos: list[str] = []
    n_metrics, falhos_m = build_snapshot_ticker_metrics(session, run_id, tickers, data_ref)
    all_falhos.extend(falhos_m)
    n_radar, falhos_r = build_snapshot_radar(session, run_id, tickers)
    all_falhos.extend(falhos_r)
    return n_metrics, n_radar, all_falhos


# =============================================================================
# Bloco 3 — Decisions  (Fase 3)
# =============================================================================


def serialize_ticker_decision(decision: TickerDecision, run_id: int) -> dict:
    """Serializa TickerDecision para dict compatível com SnapshotDecisions."""
    return {
        "run_id": run_id,
        "ticker": decision.ticker,
        "data_referencia": decision.data_referencia,
        "sinal_otimizador": decision.sinal_otimizador,
        "sinal_episodio": decision.sinal_episodio,
        "sinal_walkforward": decision.sinal_walkforward,
        "acao": decision.acao,
        "nivel_concordancia": decision.nivel_concordancia,
        "n_concordam_buy": decision.n_concordam_buy,
        "n_concordam_sell": decision.n_concordam_sell,
        "flag_destruicao_capital": decision.flag_destruicao_capital,
        "motivo_destruicao": decision.motivo_destruicao,
        "flag_emissao_recente": decision.flag_emissao_recente,
        "flag_pvp_caro": decision.flag_pvp_caro,
        "flag_dy_gap_baixo": decision.flag_dy_gap_baixo,
        "preco_referencia": decision.preco_referencia,
        "pvp_atual": decision.pvp_atual,
        "pvp_percentil": decision.pvp_percentil,
        "dy_gap_percentil": decision.dy_gap_percentil,
        "episodio_eh_novo": decision.episodio_eh_novo,
        "pregoes_desde_ultimo_episodio": decision.pregoes_desde_ultimo_episodio,
        "janela_captura_aberta": decision.janela_captura_aberta,
        "proxima_data_com_estimada": decision.proxima_data_com_estimada,
        "dias_ate_proxima_data_com": decision.dias_ate_proxima_data_com,
        "cdi_status": decision.cdi_status,
        "cdi_beta": decision.cdi_beta,
        "cdi_r_squared": decision.cdi_r_squared,
        "cdi_p_value": decision.cdi_p_value,
        "cdi_residuo_atual": decision.cdi_residuo_atual,
        "cdi_residuo_percentil": decision.cdi_residuo_percentil,
        "cdi_delta_focus_12m": decision.cdi_delta_focus_12m,
        "cdi_repricing_12m": decision.cdi_repricing_12m,
        "rationale_json": json.dumps(decision.rationale, ensure_ascii=False),
        "version_otimizador": VERSION_OTIMIZADOR,
        "version_episodios": VERSION_EPISODIOS,
        "version_walkforward": VERSION_WALKFORWARD,
        "version_recommender": VERSION_RECOMMENDER,
    }


def build_snapshot_decisions(
    session: Session,
    run_id: int,
    tickers: list[str],
    *,
    forward_days: int = 20,
) -> tuple[int, list[str]]:
    """Calcula decisões via recommender e persiste. Retorna (n_salvos, tickers_falhos)."""
    params_map = _build_optimizer_params_map(session, tickers)

    # CDI sensitivity batch (diagnóstico — NÃO altera ação)
    cdi_sensitivity_por_ticker = None
    try:
        from src.fii_analysis.models.cdi_sensitivity import CdiSensitivityResult
        raw = compute_cdi_sensitivity_batch(tickers, session)
        cdi_sensitivity_por_ticker = {
            t: cdi_sensitivity_to_dict(r) for t, r in raw.items()
        }
    except Exception as e:
        logger.warning(f"compute_cdi_sensitivity_batch falhou: {e}")

    # Focus CDI explanation (contexto macro — NÃO altera ação)
    focus_data: FocusSelicResult | None = None
    try:
        focus_data = fetch_focus_selic()
    except Exception as e:
        logger.warning(f"fetch_focus_selic falhou: {e}")

    focus_explanation_por_ticker: dict[str, dict] | None = None
    if focus_data is not None:
        focus_explanation_por_ticker = {}
        for ticker in tickers:
            try:
                expl = build_cdi_focus_explanation(
                    ticker, session, focus_data=focus_data,
                    cdi_sensitivity=cdi_sensitivity_por_ticker.get(ticker) if cdi_sensitivity_por_ticker else None,
                )
                focus_explanation_por_ticker[ticker] = expl
            except Exception as e:
                logger.warning(f"build_cdi_focus_explanation falhou para {ticker}: {e}")

    decisions = decidir_universo(
        session,
        tickers=tickers,
        optimizer_params_por_ticker=params_map,
        cdi_sensitivity_por_ticker=cdi_sensitivity_por_ticker,
        focus_explanation_por_ticker=focus_explanation_por_ticker,
        forward_days=forward_days,
    )

    tickers_falhos: list[str] = []
    count = 0
    for decision in decisions:
        try:
            row = serialize_ticker_decision(decision, run_id)
            session.add(SnapshotDecisions(**row))
            count += 1
        except Exception as e:
            logger.warning(f"Falha ao persistir decisão para {decision.ticker}: {e}")
            tickers_falhos.append(decision.ticker)

    session.flush()
    return count, tickers_falhos


def get_snapshot_decisions(
    session: Session,
    run_id: int,
) -> list[SnapshotDecisions]:
    """Retorna linhas brutas de snapshot_decisions para um run."""
    return list(
        session.execute(
            select(SnapshotDecisions)
            .where(SnapshotDecisions.run_id == run_id)
            .order_by(SnapshotDecisions.ticker)
        ).scalars().all()
    )


# =============================================================================
# Bloco 4 — Portfolio Advices + Structural Alerts  (Fase 4)
# =============================================================================


def load_snapshot_decisions(
    session: Session,
    run_id: int,
) -> list[TickerDecision]:
    """Reconstrói TickerDecision a partir do snapshot sem recomputar.

    Campos não armazenados (n_episodios_buy, win_rate_buy, etc.) ficam com
    valores default — suficientes para aconselhar_carteira() funcionar.
    """
    rows = get_snapshot_decisions(session, run_id)
    decisions: list[TickerDecision] = []
    for row in rows:
        d = TickerDecision(
            ticker=row.ticker,
            data_referencia=row.data_referencia or date.today(),
            classificacao=None,
            sinal_otimizador=row.sinal_otimizador or "INDISPONIVEL",
            sinal_episodio=row.sinal_episodio or "INDISPONIVEL",
            sinal_walkforward=row.sinal_walkforward or "INDISPONIVEL",
            flag_destruicao_capital=bool(row.flag_destruicao_capital),
            motivo_destruicao=row.motivo_destruicao,
            flag_emissao_recente=bool(row.flag_emissao_recente),
            flag_pvp_caro=bool(row.flag_pvp_caro),
            flag_dy_gap_baixo=bool(row.flag_dy_gap_baixo),
            acao=row.acao or "AGUARDAR",
            nivel_concordancia=row.nivel_concordancia or "BAIXA",
            n_concordam_buy=row.n_concordam_buy or 0,
            n_concordam_sell=row.n_concordam_sell or 0,
            pvp_atual=row.pvp_atual,
            pvp_percentil=row.pvp_percentil,
            dy_gap_percentil=row.dy_gap_percentil,
            preco_referencia=row.preco_referencia,
            episodio_eh_novo=row.episodio_eh_novo,
            pregoes_desde_ultimo_episodio=row.pregoes_desde_ultimo_episodio,
            janela_captura_aberta=bool(row.janela_captura_aberta)
            if row.janela_captura_aberta is not None
            else False,
            proxima_data_com_estimada=row.proxima_data_com_estimada,
            dias_ate_proxima_data_com=row.dias_ate_proxima_data_com,
            cdi_status=getattr(row, "cdi_status", None),
            cdi_beta=_float_or_none(getattr(row, "cdi_beta", None)),
            cdi_r_squared=_float_or_none(getattr(row, "cdi_r_squared", None)),
            cdi_p_value=_float_or_none(getattr(row, "cdi_p_value", None)),
            cdi_residuo_atual=_float_or_none(getattr(row, "cdi_residuo_atual", None)),
            cdi_residuo_percentil=_float_or_none(getattr(row, "cdi_residuo_percentil", None)),
            cdi_delta_focus_12m=_float_or_none(getattr(row, "cdi_delta_focus_12m", None)),
            cdi_repricing_12m=_float_or_none(getattr(row, "cdi_repricing_12m", None)),
            rationale=json.loads(row.rationale_json) if row.rationale_json else [],
        )
        decisions.append(d)
    return decisions


def build_snapshot_portfolio_advices(
    session: Session,
    run_id: int,
    holdings: list[dict],
    *,
    carteira_hash: str | None = None,
) -> tuple[list[HoldingAdvice], int, list[str]]:
    """Gera e persiste conselhos por posição da carteira.

    Preços vêm de snapshot_ticker_metrics do mesmo run_id para garantir
    consistência interna — sem buscar cotação em tempo real.

    Retorna (advices_objects, n_salvos, tickers_falhos).
    """
    decisions = load_snapshot_decisions(session, run_id)

    # Preços do snapshot — mesma data, sem divergência
    metrics_rows = session.execute(
        select(SnapshotTickerMetrics).where(SnapshotTickerMetrics.run_id == run_id)
    ).scalars().all()
    precos_snapshot = {
        r.ticker: float(r.preco)
        for r in metrics_rows
        if r.preco is not None
    }

    advices: list[HoldingAdvice] = aconselhar_carteira(
        decisions, holdings, precos_atuais=precos_snapshot
    )

    tickers_falhos: list[str] = []
    count = 0
    for advice in advices:
        try:
            session.add(SnapshotPortfolioAdvices(
                run_id=run_id,
                carteira_hash=carteira_hash,
                ticker=advice.ticker,
                quantidade=advice.quantidade,
                preco_medio=advice.preco_medio,
                preco_atual=advice.preco_atual,
                valor_mercado=advice.valor_mercado,
                peso_carteira=advice.peso_carteira,
                badge=advice.badge,
                prioridade=advice.prioridade,
                acao_recomendada=advice.acao_recomendada,
                nivel_concordancia=advice.nivel_concordancia,
                flags_resumo=advice.flags_resumo,
                racional=advice.racional,
                valida_ate=advice.valida_ate,
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Falha ao persistir advice para {advice.ticker}: {e}")
            tickers_falhos.append(advice.ticker)

    session.flush()
    return advices, count, tickers_falhos


def build_snapshot_structural_alerts(
    session: Session,
    run_id: int,
    advices: list[HoldingAdvice],
    *,
    carteira_hash: str | None = None,
) -> int:
    """Persiste alertas estruturais de concentração. Retorna n_salvos."""
    alerts = alertas_estruturais(advices)
    count = 0
    for alerta in alerts:
        session.add(SnapshotStructuralAlerts(
            run_id=run_id,
            carteira_hash=carteira_hash,
            tipo=alerta.tipo,
            severidade=alerta.severidade,
            descricao=alerta.descricao,
            valor=alerta.valor,
        ))
        count += 1
    session.flush()
    return count


# =============================================================================
# Helpers de Fase 2 — score
# =============================================================================


def _sync_score_to_decisions(session: Session, run_id: int) -> None:
    """Copia score_total de SnapshotTickerMetrics para SnapshotDecisions (mesmo run_id)."""
    from sqlalchemy import update as sa_update

    rows = session.execute(
        select(SnapshotTickerMetrics.ticker, SnapshotTickerMetrics.score_total)
        .where(SnapshotTickerMetrics.run_id == run_id, SnapshotTickerMetrics.score_total.isnot(None))
    ).all()

    for ticker, score in rows:
        try:
            session.execute(
                sa_update(SnapshotDecisions)
                .where(SnapshotDecisions.run_id == run_id, SnapshotDecisions.ticker == ticker)
                .values(score_total=score)
            )
        except Exception as e:
            logger.warning(f"Falha ao sincronizar score para {ticker}: {e}")
    try:
        session.flush()
    except Exception as e:
        logger.warning(f"Flush falhou em _sync_score_to_decisions: {e}")


def backfill_scores_for_run(session: Session, run_id: int) -> int:
    """Calcula e preenche score_* para um run existente cujos scores são NULL.

    Útil quando a migração das colunas de score foi aplicada depois que o
    snapshot foi gerado. Lê as métricas já armazenadas nas colunas e
    recalcula sem precisar re-executar o snapshot completo.

    Retorna o número de tickers atualizados.
    """
    from sqlalchemy import update as sa_update

    rows = session.execute(
        select(SnapshotTickerMetrics)
        .where(SnapshotTickerMetrics.run_id == run_id)
    ).scalars().all()

    if not rows:
        logger.warning(f"Nenhuma métrica encontrada para run_id={run_id}")
        return 0

    tickers = [r.ticker for r in rows]
    metricas: dict[str, dict] = {
        r.ticker: {
            "pvp_percentil": float(r.pvp_percentil) if r.pvp_percentil is not None else None,
            "dy_gap_percentil": float(r.dy_gap_percentil) if r.dy_gap_percentil is not None else None,
            "volatilidade": float(r.volatilidade_anual) if r.volatilidade_anual is not None else None,
            "beta": float(r.beta_ifix) if r.beta_ifix is not None else None,
            "mdd": float(r.max_drawdown) if r.max_drawdown is not None else None,
            "liquidez_21d_brl": float(r.liquidez_21d_brl) if r.liquidez_21d_brl is not None else None,
        }
        for r in rows
    }

    try:
        scores = calcular_score_batch(tickers, metricas, session)
    except Exception as e:
        logger.error(f"calcular_score_batch falhou no backfill run_id={run_id}: {e}")
        return 0

    updated = 0
    for ticker, sc in scores.items():
        try:
            session.execute(
                sa_update(SnapshotTickerMetrics)
                .where(SnapshotTickerMetrics.run_id == run_id, SnapshotTickerMetrics.ticker == ticker)
                .values(
                    score_total=sc.score_total,
                    score_valuation=sc.score_valuation,
                    score_risco=sc.score_risco,
                    score_liquidez=sc.score_liquidez,
                    score_historico=sc.score_historico,
                )
            )
            updated += 1
        except Exception as e:
            logger.warning(f"Falha ao atualizar score para {ticker} run_id={run_id}: {e}")

    session.flush()
    _sync_score_to_decisions(session, run_id)
    session.commit()
    logger.info(f"Backfill scores: {updated}/{len(tickers)} tickers atualizados (run_id={run_id})")
    return updated


# =============================================================================
# Orquestrador principal
# =============================================================================


def generate_daily_snapshot(
    session: Session,
    *,
    scope: str = "curado",
    tickers: list[str] | None = None,
    holdings: list[dict] | None = None,
    force: bool = False,
    forward_days: int = 20,
) -> dict:
    """Gera snapshot completo para a data de hoje.

    Fluxo:
      1. resolve_snapshot_universe()
      2. generate_base_snapshots()  — métricas + radar
      3. build_snapshot_decisions() — sinais com versionamento por motor
      4. build_snapshot_portfolio_advices() + structural_alerts (se holdings)

    Idempotente por padrão: se já existe run ready para hoje+scope, retorna
    sem recalcular. Use force=True para regenerar.

    holdings: lista de dicts com ticker/quantidade/preco_medio. Se None,
              portfolio advices não são gerados.
    """
    today = date.today()
    c_hash = _carteira_hash(holdings) if holdings else None

    if not force:
        q = select(SnapshotRun).where(
            SnapshotRun.data_referencia == today,
            SnapshotRun.status == "ready",
            SnapshotRun.universe_scope == scope,
        )
        if scope == "carteira" and c_hash is not None:
            q = q.where(SnapshotRun.carteira_hash == c_hash)
        existing = session.execute(q.limit(1)).scalar_one_or_none()
        if existing is not None:
            return {
                "run_id": existing.id,
                "status": "already_ready",
                "data_referencia": today,
                "mensagem": (
                    f"Snapshot já existe (run_id={existing.id}). "
                    "Use force=True para regenerar."
                ),
            }

    resolved_tickers: list[str] = tickers or resolve_snapshot_universe(
        session, scope, holdings
    )
    u_hash = _universe_hash(resolved_tickers)

    run = SnapshotRun(
        data_referencia=today,
        criado_em=datetime.now(timezone.utc),
        status="running",
        engine_version_global=ENGINE_VERSION,
        universe_scope=scope,
        universe_hash=u_hash,
        carteira_hash=c_hash,
        base_preco_ate=_base_preco_ate(session),
        base_dividendo_ate=_base_dividendo_ate(session),
        base_cdi_ate=_base_cdi_ate(session),
    )
    session.add(run)
    session.commit()
    run_id = run.id

    all_falhos: list[str] = []

    try:
        n_metrics, n_radar, falhos_base = generate_base_snapshots(
            session, run_id, resolved_tickers, today
        )
        all_falhos.extend(falhos_base)

        n_decisions, falhos_d = build_snapshot_decisions(
            session, run_id, resolved_tickers, forward_days=forward_days
        )
        all_falhos.extend(falhos_d)

        # Fase 2: propagar score_total de metrics → decisions
        _sync_score_to_decisions(session, run_id)

        n_advices = 0
        n_alerts = 0
        if holdings:
            advices_objs, n_advices, falhos_adv = build_snapshot_portfolio_advices(
                session, run_id, holdings, carteira_hash=c_hash
            )
            all_falhos.extend(falhos_adv)
            n_alerts = build_snapshot_structural_alerts(
                session, run_id, advices_objs, carteira_hash=c_hash
            )

        # Persistir Focus BCB no run
        try:
            focus = fetch_focus_selic()
            run_obj = session.get(SnapshotRun, run_id)
            run_obj.focus_data_referencia = focus.focus_data_referencia
            run_obj.focus_coletado_em = focus.focus_coletado_em
            run_obj.focus_selic_3m = focus.focus_selic_3m
            run_obj.focus_selic_6m = focus.focus_selic_6m
            run_obj.focus_selic_12m = focus.focus_selic_12m
            run_obj.focus_status = focus.focus_status
        except Exception as e:
            logger.warning(f"Falha ao persistir focus_data no run_id={run_id}: {e}")

        run = session.get(SnapshotRun, run_id)
        run.status = "ready"
        run.finalizado_em = datetime.now(timezone.utc)
        if all_falhos:
            run.tickers_falhos = json.dumps(list(set(all_falhos)))
        session.commit()

        return {
            "run_id": run_id,
            "status": "ready",
            "data_referencia": today,
            "n_metrics": n_metrics,
            "n_radar": n_radar,
            "n_decisions": n_decisions,
            "n_advices": n_advices,
            "n_alerts": n_alerts,
            "tickers_falhos": list(set(all_falhos)),
            "mensagem": "Snapshot gerado com sucesso.",
        }

    except Exception as exc:
        session.rollback()
        failed_run = session.get(SnapshotRun, run_id)
        if failed_run:
            failed_run.status = "failed"
            failed_run.mensagem_erro = str(exc)[:500]
            failed_run.finalizado_em = datetime.now(timezone.utc)
            session.commit()
        return {
            "run_id": run_id,
            "status": "failed",
            "data_referencia": today,
            "mensagem": f"Snapshot falhou: {exc}",
        }


# =============================================================================
# Bloco 5 — Reconstrução de objetos a partir de snapshot  (Fase 5)
# =============================================================================


@dataclass
class SnapshotCommandCenter:
    """Cockpit diário reconstruído de snapshot. Interface idêntica a DailyCommandCenter."""

    data_referencia: date
    universe_size: int
    decisions: list = field(default_factory=list)
    action_today: list = field(default_factory=list)
    watchlist: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    holding_advices: list = field(default_factory=list)
    structural_alerts: list = field(default_factory=list)


def load_snapshot_holding_advices(
    session: Session,
    run_id: int,
    carteira_hash: str | None = None,
) -> list[HoldingAdvice]:
    """Reconstrói HoldingAdvice a partir de snapshot_portfolio_advices."""
    q = select(SnapshotPortfolioAdvices).where(SnapshotPortfolioAdvices.run_id == run_id)
    if carteira_hash is not None:
        q = q.where(SnapshotPortfolioAdvices.carteira_hash == carteira_hash)
    rows = session.execute(q.order_by(SnapshotPortfolioAdvices.ticker)).scalars().all()

    advices: list[HoldingAdvice] = []
    for row in rows:
        try:
            advices.append(HoldingAdvice(
                ticker=row.ticker,
                quantidade=row.quantidade or 0,
                preco_medio=float(row.preco_medio) if row.preco_medio is not None else 0.0,
                preco_atual=float(row.preco_atual) if row.preco_atual is not None else None,
                valor_mercado=float(row.valor_mercado) if row.valor_mercado is not None else None,
                peso_carteira=float(row.peso_carteira) if row.peso_carteira is not None else None,
                badge=row.badge or "HOLD",
                racional=row.racional or "",
                prioridade=row.prioridade or "BAIXA",
                acao_recomendada=row.acao_recomendada or "AGUARDAR",
                nivel_concordancia=row.nivel_concordancia or "BAIXA",
                flags_resumo=row.flags_resumo or "—",
                valida_ate=row.valida_ate or date.today(),
            ))
        except Exception as e:
            logger.warning(f"Falha ao desserializar HoldingAdvice (ticker={getattr(row, 'ticker', '?')}): {e}")
    return advices


def load_snapshot_structural_alerts_objs(
    session: Session,
    run_id: int,
    carteira_hash: str | None = None,
) -> list[AlertaEstrutural]:
    """Reconstrói AlertaEstrutural a partir de snapshot_structural_alerts."""
    q = select(SnapshotStructuralAlerts).where(SnapshotStructuralAlerts.run_id == run_id)
    if carteira_hash is not None:
        q = q.where(SnapshotStructuralAlerts.carteira_hash == carteira_hash)
    rows = session.execute(q).scalars().all()

    result: list[AlertaEstrutural] = []
    for row in rows:
        try:
            result.append(AlertaEstrutural(
                tipo=row.tipo or "",
                severidade=row.severidade or "info",
                descricao=row.descricao or "",
                valor=float(row.valor) if row.valor is not None else 0.0,
            ))
        except Exception as e:
            logger.warning(f"Falha ao desserializar AlertaEstrutural: {e}")
    return result


def reconstruct_command_center_from_snapshot(
    session: Session,
    run_id: int,
    holdings: list[dict] | None = None,
) -> SnapshotCommandCenter:
    """Reconstrói SnapshotCommandCenter a partir de snapshot sem recomputar motores.

    Compatível com DailyCommandCenter para uso nas páginas de UI.
    """
    decisions = load_snapshot_decisions(session, run_id)

    action_today = [d for d in decisions if d.acao in {"COMPRAR", "VENDER", "EVITAR"}]
    watchlist = [
        d for d in decisions
        if d.acao == "AGUARDAR" and (
            any(s in {"BUY", "SELL"} for s in [d.sinal_otimizador, d.sinal_episodio, d.sinal_walkforward])
            or d.janela_captura_aberta
            or d.episodio_eh_novo is not None
        )
    ]
    risks = [
        d for d in decisions
        if any([
            d.flag_destruicao_capital,
            d.flag_emissao_recente,
            d.flag_pvp_caro,
            d.flag_dy_gap_baixo,
            d.nivel_concordancia == "VETADA",
        ])
    ]

    c_hash = _carteira_hash(holdings) if holdings else None
    holding_advices = load_snapshot_holding_advices(session, run_id, carteira_hash=c_hash)
    structural_alerts = load_snapshot_structural_alerts_objs(session, run_id, carteira_hash=c_hash)

    data_ref = max((d.data_referencia for d in decisions), default=date.today())

    return SnapshotCommandCenter(
        data_referencia=data_ref,
        universe_size=len(decisions),
        decisions=decisions,
        action_today=action_today,
        watchlist=watchlist,
        risks=risks,
        holding_advices=holding_advices,
        structural_alerts=structural_alerts,
    )


def get_latest_ready_snapshot(
    session: Session,
    scope: str | None = None,
) -> SnapshotRun | None:
    """Retorna o SnapshotRun mais recente com status=ready."""
    return get_latest_ready_snapshot_run(session, scope=scope)


def load_risk_metrics_snapshot(ticker: str, session: Session) -> dict:
    """Retorna risk metrics do snapshot mais recente para o ticker.

    Retorna dict com chaves: volatilidade_anual, beta_ifix, max_drawdown,
    liquidez_21d_brl, retorno_total_12m, dy_3m_anualizado.
    Todos os valores podem ser None se o snapshot não tiver dados.
    """
    run = get_latest_ready_snapshot_run(session)
    if run is None:
        return {}
    row = session.execute(
        select(SnapshotTickerMetrics)
        .where(
            SnapshotTickerMetrics.run_id == run.id,
            SnapshotTickerMetrics.ticker == ticker,
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return {}
    return {
        "volatilidade_anual": _float_or_none(getattr(row, "volatilidade_anual", None)),
        "beta_ifix": _float_or_none(getattr(row, "beta_ifix", None)),
        "max_drawdown": _float_or_none(getattr(row, "max_drawdown", None)),
        "liquidez_21d_brl": _float_or_none(getattr(row, "liquidez_21d_brl", None)),
        "retorno_total_12m": _float_or_none(getattr(row, "retorno_total_12m", None)),
        "dy_3m_anualizado": _float_or_none(getattr(row, "dy_3m_anualizado", None)),
    }
