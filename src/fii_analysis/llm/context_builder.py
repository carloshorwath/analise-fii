from __future__ import annotations

import json
from datetime import date, timedelta
import pandas as pd
from sqlalchemy import select

from src.fii_analysis.data.database import (
    SnapshotRun,
    SnapshotTickerMetrics,
    SnapshotDecisions,
    RelatorioMensal,
    get_cnpj_by_ticker,
)
from src.fii_analysis.models.episodes import get_pvp_series


def _serialize_val(val):
    if val is None:
        return None
    if isinstance(val, date):
        return val.isoformat()
    try:
        return float(val)
    except (TypeError, ValueError):
        return str(val)


def build_ticker_context(ticker: str, session) -> dict:
    """Coleta métricas quantitativas e qualitativas de um ticker para compor o contexto da IA."""
    ticker = ticker.upper()

    # 1. Encontrar o último snapshot run de escopo curado ou ifix que esteja pronto
    run = session.execute(
        select(SnapshotRun)
        .where(SnapshotRun.status == "ready")
        .order_by(SnapshotRun.data_referencia.desc())
        .limit(1)
    ).scalar_one_or_none()

    if run is None:
        return {
            "ticker": ticker,
            "data_contexto": date.today().isoformat(),
            "erro": "Nenhum snapshot diário disponível no banco de dados."
        }

    run_id = run.id
    ref_date = run.data_referencia

    # 2. Buscar Ticker Metrics
    metric = session.execute(
        select(SnapshotTickerMetrics)
        .where(SnapshotTickerMetrics.run_id == run_id, SnapshotTickerMetrics.ticker == ticker)
    ).scalar_one_or_none()

    # 3. Buscar Ticker Decisions
    decision = session.execute(
        select(SnapshotDecisions)
        .where(SnapshotDecisions.run_id == run_id, SnapshotDecisions.ticker == ticker)
    ).scalar_one_or_none()

    context = {
        "ticker": ticker,
        "data_contexto": ref_date.isoformat(),
        "score_total": None,
        "score_breakdown": {},
        "indicadores": {},
        "decisao": {},
        "flags_risco": {},
        "historico_52w": {},
        "saude_financeira_6m": []
    }

    if metric:
        context["score_total"] = metric.score_total
        context["score_breakdown"] = {
            "valuation": metric.score_valuation,
            "risco": metric.score_risco,
            "liquidez": metric.score_liquidez,
            "historico": metric.score_historico,
        }
        context["indicadores"] = {
            "preco": _serialize_val(metric.preco),
            "vp": _serialize_val(metric.vp),
            "pvp": _serialize_val(metric.pvp),
            "pvp_percentil": _serialize_val(metric.pvp_percentil),
            "dy_12m": _serialize_val(metric.dy_12m),
            "dy_24m": _serialize_val(metric.dy_24m),
            "dy_gap": _serialize_val(metric.dy_gap),
            "dy_gap_percentil": _serialize_val(metric.dy_gap_percentil),
            "volume_21d": _serialize_val(metric.volume_21d),
            "segmento": metric.segmento,
            "cvm_defasada": bool(metric.cvm_defasada) if metric.cvm_defasada is not None else False
        }

    if decision:
        rationale = []
        if decision.rationale_json:
            try:
                rationale = json.loads(decision.rationale_json)
            except Exception:
                pass

        context["decisao"] = {
            "acao": decision.acao,
            "nivel_concordancia": decision.nivel_concordancia,
            "sinal_otimizador": decision.sinal_otimizador,
            "sinal_episodio": decision.sinal_episodio,
            "sinal_walkforward": decision.sinal_walkforward,
            "rationale": rationale,
        }

        # CDI/Focus
        context["cdi_focus"] = {
            "cdi_status": decision.cdi_status,
            "cdi_beta": _serialize_val(decision.cdi_beta),
            "cdi_r_squared": _serialize_val(decision.cdi_r_squared),
            "cdi_p_value": _serialize_val(decision.cdi_p_value),
            "cdi_residuo_atual": _serialize_val(decision.cdi_residuo_atual),
            "cdi_residuo_percentil": _serialize_val(decision.cdi_residuo_percentil),
            "cdi_delta_focus_12m": _serialize_val(decision.cdi_delta_focus_12m),
            "cdi_repricing_12m": _serialize_val(decision.cdi_repricing_12m),
        }

        # Flags de risco
        context["flags_risco"] = {
            "destruicao_capital": bool(decision.flag_destruicao_capital),
            "motivo_destruicao": decision.motivo_destruicao,
            "emissao_recente": bool(decision.flag_emissao_recente),
            "pvp_caro": bool(decision.flag_pvp_caro),
            "dy_gap_baixo": bool(decision.flag_dy_gap_baixo),
            "volume_queda_forte": bool(getattr(decision, "flag_volume_queda_forte", False)),
            "ltv_alto": bool(getattr(decision, "flag_ltv_alto", False)),
            "ltv_atual": _serialize_val(getattr(decision, "ltv_atual", None)),
            "pl_trend": getattr(decision, "pl_trend", None),
            "rentab_divergencia": bool(getattr(decision, "flag_rentab_divergencia", False)),
            "rentab_div_media": _serialize_val(getattr(decision, "rentab_div_media", None)),
            "dy_momentum": _serialize_val(getattr(decision, "dy_momentum", None)),
            "dividend_safety_flag": bool(getattr(decision, "dividend_safety_flag", False)),
            "payout_vs_caixa": _serialize_val(getattr(decision, "payout_vs_caixa", None)),
            "cortes_24m": int(getattr(decision, "cortes_24m", 0) or 0),
        }

    # 4. Histórico de 52 semanas de P/VP
    try:
        df_pvp = get_pvp_series(ticker, session)
        if not df_pvp.empty:
            df_pvp["data_parsed"] = pd.to_datetime(df_pvp["data"]).dt.date
            one_year_ago = ref_date - timedelta(days=365)
            df_52w = df_pvp[df_pvp["data_parsed"] >= one_year_ago]
            if not df_52w.empty:
                context["historico_52w"] = {
                    "pvp_max": float(df_52w["pvp"].max()),
                    "pvp_min": float(df_52w["pvp"].min()),
                    "pvp_mean": float(df_52w["pvp"].mean()),
                    "pvp_atual": float(df_52w["pvp"].iloc[-1])
                }
    except Exception:
        pass

    # 5. Saúde Financeira dos últimos 6 meses (CVM)
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj:
        try:
            reports = session.execute(
                select(RelatorioMensal)
                .where(RelatorioMensal.cnpj == cnpj)
                .order_by(RelatorioMensal.data_referencia.desc())
                .limit(6)
            ).scalars().all()

            # VP/cota na base da quantidade atual de cotas (split nao vira degrau);
            # o nominal do informe segue em `vp_por_cota`.
            from src.fii_analysis.features.indicators import get_relatorios_ajustados
            _aj = get_relatorios_ajustados(ticker, session, apenas_entregues=False)
            _vp_aj = {pd.Timestamp(x.data_referencia).date(): x.vp_aj for x in _aj.itertuples(index=False) if pd.notna(x.vp_aj)}

            for r in reports:
                context["saude_financeira_6m"].append({
                    "data_referencia": r.data_referencia.isoformat(),
                    "vp_por_cota": _serialize_val(r.vp_por_cota),
                    "vp_por_cota_ajustado": _serialize_val(_vp_aj.get(r.data_referencia)),
                    "patrimonio_liq": _serialize_val(r.patrimonio_liq),
                    "dy_mes_pct": _serialize_val(r.dy_mes_pct),
                    "rentab_efetiva": _serialize_val(r.rentab_efetiva),
                    "rentab_patrim": _serialize_val(r.rentab_patrim),
                })
        except Exception:
            pass

    return context


def build_opportunity_context(vender: str, comprar: str, session) -> dict:
    """Compila o contexto comparativo de uma oportunidade de rotação (Vender X -> Comprar Y)."""
    ctx_vender = build_ticker_context(vender, session)
    ctx_comprar = build_ticker_context(comprar, session)

    spread_pvp = None
    spread_dy = None
    delta_score = None

    if ctx_vender.get("indicadores") and ctx_comprar.get("indicadores"):
        pvp_v = ctx_vender["indicadores"].get("pvp_percentil")
        pvp_c = ctx_comprar["indicadores"].get("pvp_percentil")
        if pvp_v is not None and pvp_c is not None:
            spread_pvp = float(pvp_v) - float(pvp_c)

        dy_v = ctx_vender["indicadores"].get("dy_gap_percentil")
        dy_c = ctx_comprar["indicadores"].get("dy_gap_percentil")
        if dy_v is not None and dy_c is not None:
            spread_dy = float(dy_c) - float(dy_v)

    if ctx_vender.get("score_total") is not None and ctx_comprar.get("score_total") is not None:
        delta_score = int(ctx_comprar["score_total"]) - int(ctx_vender["score_total"])

    return {
        "vender_ticker": vender,
        "comprar_ticker": comprar,
        "segmento": ctx_vender.get("indicadores", {}).get("segmento"),
        "spread_pvp_percentil": spread_pvp,
        "spread_dy_gap_percentil": spread_dy,
        "delta_score": delta_score,
        "vender": ctx_vender,
        "comprar": ctx_comprar
    }
