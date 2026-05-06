"""Helpers de UI para leitura de snapshots diários.

Encapsula queries às tabelas snapshot_*, transforma linhas em DataFrames
ou objetos prontos para renderização, e centraliza mensagens de frescor.

Todas as funções de carga usam @st.cache_data(ttl=300) para evitar
queries repetidas durante re-renders da mesma sessão.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.fii_analysis.data.database import (
    SnapshotDecisions,
    SnapshotPortfolioAdvices,
    SnapshotRadar,
    SnapshotRun,
    SnapshotStructuralAlerts,
    SnapshotTickerMetrics,
    get_latest_ready_snapshot_run,
    get_session_ctx,
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _run_to_meta(run: SnapshotRun) -> dict:
    ts = run.finalizado_em
    return {
        "run_id": run.id,
        "data_referencia": run.data_referencia,
        "scope": run.universe_scope,
        "engine_version": run.engine_version_global,
        "finalizado_em": ts,
        "carteira_hash": run.carteira_hash,
        "tickers_falhos": json.loads(run.tickers_falhos) if run.tickers_falhos else [],
        "is_stale": run.data_referencia < date.today(),
        # Focus BCB
        "focus_data_referencia": getattr(run, "focus_data_referencia", None),
        "focus_coletado_em": getattr(run, "focus_coletado_em", None),
        "focus_selic_3m": getattr(run, "focus_selic_3m", None),
        "focus_selic_6m": getattr(run, "focus_selic_6m", None),
        "focus_selic_12m": getattr(run, "focus_selic_12m", None),
        "focus_status": getattr(run, "focus_status", None),
    }


# ---------------------------------------------------------------------------
# Funções de carga (cache 5 min)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner=False)
def load_latest_snapshot_meta(
    scope: str = "curado",
    carteira_hash: str | None = None,
) -> dict | None:
    """Retorna metadados do snapshot mais recente ready, ou None."""
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session, scope=scope, carteira_hash=carteira_hash)
        return _run_to_meta(run) if run else None


@st.cache_data(ttl=300, show_spinner=False)
def load_panorama_snapshot(scope: str = "curado") -> tuple[dict | None, pd.DataFrame]:
    """Retorna (meta, df) com métricas por ticker do último snapshot ready.

    Colunas: ticker, preco, vp, pvp, pvp_percentil, dy_12m, dy_24m,
             rent_12m, rent_24m, dy_gap, dy_gap_percentil,
             volume_medio_21d, cvm_defasada, segmento, dy_mes.
    """
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session, scope=scope)
        if run is None:
            return None, pd.DataFrame()
        meta = _run_to_meta(run)
        rows = session.execute(
            select(SnapshotTickerMetrics)
            .where(SnapshotTickerMetrics.run_id == run.id)
            .order_by(SnapshotTickerMetrics.ticker)
        ).scalars().all()
        if not rows:
            return meta, pd.DataFrame()
        records = [
            {
                "ticker": r.ticker,
                "preco": float(r.preco) if r.preco is not None else None,
                "vp": float(r.vp) if r.vp is not None else None,
                "pvp": float(r.pvp) if r.pvp is not None else None,
                "pvp_percentil": float(r.pvp_percentil) if r.pvp_percentil is not None else None,
                "dy_12m": float(r.dy_12m) if r.dy_12m is not None else None,
                "dy_24m": float(r.dy_24m) if r.dy_24m is not None else None,
                "rent_12m": float(r.rent_12m) if r.rent_12m is not None else None,
                "rent_24m": float(r.rent_24m) if r.rent_24m is not None else None,
                "dy_gap": float(r.dy_gap) if r.dy_gap is not None else None,
                "dy_gap_percentil": (
                    float(r.dy_gap_percentil) if r.dy_gap_percentil is not None else None
                ),
                "volume_medio_21d": float(r.volume_21d) if r.volume_21d is not None else None,
                "cvm_defasada": bool(r.cvm_defasada) if r.cvm_defasada is not None else False,
                "segmento": r.segmento,
                "dy_mes": None,  # not in snapshot — shim for render_panorama_table
                # Fase 1.5 — risk_metrics
                "volatilidade_anual": float(getattr(r, "volatilidade_anual", None) or 0) or None,
                "beta_ifix": float(getattr(r, "beta_ifix", None) or 0) if getattr(r, "beta_ifix", None) is not None else None,
                "max_drawdown": float(getattr(r, "max_drawdown", None) or 0) if getattr(r, "max_drawdown", None) is not None else None,
                "liquidez_21d_brl": float(getattr(r, "liquidez_21d_brl", None) or 0) or None,
                "retorno_total_12m": float(getattr(r, "retorno_total_12m", None) or 0) if getattr(r, "retorno_total_12m", None) is not None else None,
                "dy_3m_anualizado": float(getattr(r, "dy_3m_anualizado", None) or 0) if getattr(r, "dy_3m_anualizado", None) is not None else None,
                # Fase 2 — score
                "score_total": int(getattr(r, "score_total", None) or 0) if getattr(r, "score_total", None) is not None else None,
                "score_valuation": int(getattr(r, "score_valuation", None) or 0) if getattr(r, "score_valuation", None) is not None else None,
                "score_risco": int(getattr(r, "score_risco", None) or 0) if getattr(r, "score_risco", None) is not None else None,
                "score_liquidez": int(getattr(r, "score_liquidez", None) or 0) if getattr(r, "score_liquidez", None) is not None else None,
                "score_historico": int(getattr(r, "score_historico", None) or 0) if getattr(r, "score_historico", None) is not None else None,
            }
            for r in rows
        ]
        return meta, pd.DataFrame(records)


@st.cache_data(ttl=300, show_spinner=False)
def load_radar_snapshot(scope: str = "curado") -> tuple[dict | None, pd.DataFrame]:
    """Retorna (meta, df) com flags booleanas do radar do último snapshot ready.

    Colunas: ticker, pvp_baixo, dy_gap_alto, saude_ok, liquidez_ok,
             vistos (int 0–4), saude_motivo.
    """
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session, scope=scope)
        if run is None:
            return None, pd.DataFrame()
        meta = _run_to_meta(run)
        rows = session.execute(
            select(SnapshotRadar)
            .where(SnapshotRadar.run_id == run.id)
            .order_by(SnapshotRadar.ticker)
        ).scalars().all()
        if not rows:
            return meta, pd.DataFrame()
        records = [
            {
                "ticker": r.ticker,
                "pvp_baixo": bool(r.pvp_baixo) if r.pvp_baixo is not None else False,
                "dy_gap_alto": bool(r.dy_gap_alto) if r.dy_gap_alto is not None else False,
                "saude_ok": bool(r.saude_ok) if r.saude_ok is not None else True,
                "liquidez_ok": bool(r.liquidez_ok) if r.liquidez_ok is not None else True,
                "vistos": int(r.vistos) if r.vistos is not None else 0,
                "saude_motivo": r.saude_motivo,
            }
            for r in rows
        ]
        return meta, pd.DataFrame(records)


@st.cache_data(ttl=300, show_spinner=False)
def load_portfolio_advices_snapshot(
    scope: str = "curado",
    carteira_hash: str | None = None,
) -> tuple[dict | None, pd.DataFrame]:
    """Retorna (meta, df) com conselhos de carteira do último snapshot ready.

    Se carteira_hash for fornecido, filtra apenas advices para aquele hash.
    df vazio significa que o snapshot não inclui a carteira atual.
    """
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(
            session,
            scope=scope,
            carteira_hash=carteira_hash if scope == "carteira" else None,
        )
        if run is None:
            return None, pd.DataFrame()
        meta = _run_to_meta(run)
        q = select(SnapshotPortfolioAdvices).where(
            SnapshotPortfolioAdvices.run_id == run.id
        )
        if carteira_hash is not None:
            q = q.where(SnapshotPortfolioAdvices.carteira_hash == carteira_hash)
        rows = session.execute(q.order_by(SnapshotPortfolioAdvices.ticker)).scalars().all()
        if not rows:
            return meta, pd.DataFrame()
        records = [
            {
                "ticker": r.ticker,
                "quantidade": r.quantidade,
                "preco_medio": float(r.preco_medio) if r.preco_medio is not None else 0.0,
                "preco_atual": float(r.preco_atual) if r.preco_atual is not None else None,
                "valor_mercado": float(r.valor_mercado) if r.valor_mercado is not None else None,
                "peso_carteira": float(r.peso_carteira) if r.peso_carteira is not None else None,
                "badge": r.badge,
                "prioridade": r.prioridade,
                "acao_recomendada": r.acao_recomendada,
                "nivel_concordancia": r.nivel_concordancia,
                "flags_resumo": r.flags_resumo,
                "racional": r.racional,
                "valida_ate": r.valida_ate,
            }
            for r in rows
        ]
        return meta, pd.DataFrame(records)


@st.cache_data(ttl=300, show_spinner=False)
def load_structural_alerts_snapshot(
    scope: str = "curado",
    carteira_hash: str | None = None,
) -> tuple[dict | None, pd.DataFrame]:
    """Retorna (meta, df) com alertas estruturais do último snapshot ready."""
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(
            session,
            scope=scope,
            carteira_hash=carteira_hash if scope == "carteira" else None,
        )
        if run is None:
            return None, pd.DataFrame()
        meta = _run_to_meta(run)
        q = select(SnapshotStructuralAlerts).where(
            SnapshotStructuralAlerts.run_id == run.id
        )
        if carteira_hash is not None:
            q = q.where(SnapshotStructuralAlerts.carteira_hash == carteira_hash)
        rows = session.execute(q).scalars().all()
        if not rows:
            return meta, pd.DataFrame()
        records = [
            {
                "tipo": r.tipo,
                "severidade": r.severidade,
                "descricao": r.descricao,
                "valor": float(r.valor) if r.valor is not None else 0.0,
            }
            for r in rows
        ]
        return meta, pd.DataFrame(records)


@st.cache_data(ttl=300, show_spinner=False)
def load_command_center_snapshot(
    scope: str = "curado",
    holdings_key: tuple[tuple[str, int], ...] = (),
):
    """Reconstrói SnapshotCommandCenter a partir do snapshot sem recomputar motores.

    holdings_key: tupla de (ticker, quantidade) — usada como chave de cache e para
    derivar carteira_hash quando scope="carteira", garantindo que o run correto seja
    selecionado quando houver múltiplos snapshots com carteiras diferentes no banco.
    Retorna None se nenhum snapshot ready existe para o scope.
    """
    import hashlib

    from src.fii_analysis.evaluation.daily_snapshots import (
        reconstruct_command_center_from_snapshot,
    )

    c_hash: str | None = None
    if scope == "carteira" and holdings_key:
        c_hash = hashlib.md5(
            ",".join(f"{t}:{q}" for t, q in sorted(holdings_key)).encode()
        ).hexdigest()[:12]

    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session, scope=scope, carteira_hash=c_hash)
        if run is None:
            return None
        # holdings=None é correto aqui: o run já foi filtrado pelo c_hash, então
        # todos os advices desse run pertencem à carteira certa
        return reconstruct_command_center_from_snapshot(session, run.id, holdings=None)


@st.cache_data(ttl=300, show_spinner=False)
def load_carteira_advices_snapshot(
    carteira_hash: str,
):
    """Retorna (meta, list[HoldingAdvice], list[AlertaEstrutural]) do snapshot de carteira.

    Filtra por scope=carteira e carteira_hash exatos.
    Retorna (None, [], []) se nenhum snapshot existe para essa carteira.
    """
    from src.fii_analysis.evaluation.daily_snapshots import (
        load_snapshot_holding_advices,
        load_snapshot_structural_alerts_objs,
    )

    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(
            session, scope="carteira", carteira_hash=carteira_hash
        )
        if run is None:
            return None, [], []
        meta = _run_to_meta(run)
        advices = load_snapshot_holding_advices(session, run.id, carteira_hash=carteira_hash)
        alerts = load_snapshot_structural_alerts_objs(
            session, run.id, carteira_hash=carteira_hash
        )
        return meta, advices, alerts


@st.cache_data(ttl=300, show_spinner=False)
def load_decisions_snapshot(scope: str = "curado") -> tuple[dict | None, pd.DataFrame]:
    """Retorna (meta, df) com decisões do último snapshot ready.

    Colunas: ticker, acao, nivel_concordancia, sinal_otimizador,
             sinal_episodio, sinal_walkforward, flag_destruicao_capital.
    """
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session, scope=scope)
        if run is None:
            return None, pd.DataFrame()
        meta = _run_to_meta(run)
        rows = session.execute(
            select(SnapshotDecisions)
            .where(SnapshotDecisions.run_id == run.id)
            .order_by(SnapshotDecisions.ticker)
        ).scalars().all()
        if not rows:
            return meta, pd.DataFrame()
        records = [
            {
                "ticker": r.ticker,
                "acao": r.acao,
                "nivel_concordancia": r.nivel_concordancia,
                "sinal_otimizador": r.sinal_otimizador,
                "sinal_episodio": r.sinal_episodio,
                "sinal_walkforward": r.sinal_walkforward,
                "flag_destruicao_capital": bool(r.flag_destruicao_capital) if r.flag_destruicao_capital is not None else False,
            }
            for r in rows
        ]
        return meta, pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Renderização de frescor
# ---------------------------------------------------------------------------


def render_snapshot_info(meta: dict | None, *, stale_carteira: bool = False) -> None:
    """Mostra banner de frescor do snapshot (info/warning conforme estado)."""
    if meta is None:
        st.warning(
            "Nenhum snapshot disponivel. "
            "Execute: `python scripts/generate_daily_snapshots.py` para gerar os dados do dia."
        )
        return
    ts = meta.get("finalizado_em")
    ts_str = ts.strftime("%d/%m %H:%M") if ts else "?"
    scope = meta.get("scope", "curado")
    if meta.get("is_stale"):
        st.warning(
            f"Snapshot desatualizado — gerado em {ts_str} (scope: {scope}). "
            "Execute `python scripts/generate_daily_snapshots.py` para atualizar."
        )
    elif stale_carteira:
        st.warning(
            f"Snapshot de {ts_str}: carteira atual nao consta no cache. "
            "Execute `python scripts/generate_daily_snapshots.py --scope carteira` para incluir."
        )
    else:
        st.info(f"Dados do snapshot de {ts_str}.")
    falhos = meta.get("tickers_falhos", [])
    if falhos:
        st.caption(f"Tickers com falha no snapshot: {', '.join(falhos)}")
