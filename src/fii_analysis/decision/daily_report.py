"""Cockpit diario: agrega decisoes do universo, carteira e exportacao.

Centraliza a camada operacional do projeto:
- calcula params do otimizador por ticker
- consolida decisoes do recommender
- cruza com holdings da carteira
- monta secoes escaneaveis para a pagina 13_Hoje.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Optional

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.decision.portfolio_advisor import (
    AlertaEstrutural,
    HoldingAdvice,
    aconselhar_carteira,
    alertas_estruturais,
)
from src.fii_analysis.decision.recommender import TickerDecision, decidir_universo
from src.fii_analysis.features.portfolio import carteira_panorama
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2


@dataclass
class DailyCommandCenter:
    """Pacote unico para a home operacional do dia."""

    data_referencia: date
    universe_size: int
    decisions: list[TickerDecision]
    action_today: list[TickerDecision]
    watchlist: list[TickerDecision]
    risks: list[TickerDecision]
    holding_advices: list[HoldingAdvice]
    structural_alerts: list[AlertaEstrutural]


def _build_optimizer_params_map(session, tickers: list[str]) -> dict[str, dict]:
    """Roda o otimizador por ticker e extrai best_params quando houver dados."""
    optimizer = ThresholdOptimizerV2()
    params_map: dict[str, dict] = {}
    for ticker in tickers:
        try:
            result = optimizer.optimize(ticker, session)
        except Exception:
            continue
        if "error" not in result and result.get("best_params"):
            params_map[ticker] = result["best_params"]
    return params_map


def _action_rank(decision: TickerDecision) -> tuple[int, int, str]:
    action_order = {"COMPRAR": 0, "VENDER": 1, "EVITAR": 2, "AGUARDAR": 3}
    level_order = {"ALTA": 0, "MEDIA": 1, "VETADA": 2, "BAIXA": 3}
    return (
        action_order.get(decision.acao, 9),
        level_order.get(decision.nivel_concordancia, 9),
        decision.ticker,
    )


def _is_watchlist_candidate(decision: TickerDecision) -> bool:
    if decision.acao != "AGUARDAR":
        return False

    has_partial_signal = any(
        signal in {"BUY", "SELL"}
        for signal in [
            decision.sinal_otimizador,
            decision.sinal_episodio,
            decision.sinal_walkforward,
        ]
    )
    has_context = (
        decision.janela_captura_aberta
        or decision.episodio_eh_novo is False
        or decision.episodio_eh_novo is True
    )
    return has_partial_signal or has_context


def _is_risk_case(decision: TickerDecision) -> bool:
    return any([
        decision.flag_destruicao_capital,
        decision.flag_emissao_recente,
        decision.flag_pvp_caro,
        decision.flag_dy_gap_baixo,
        decision.nivel_concordancia == "VETADA",
    ])


def _prices_map_for_holdings(session, tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    pan = carteira_panorama(sorted(set(tickers)), session)
    if pan.empty:
        return {}
    return {
        row["ticker"]: row["preco"]
        for _, row in pan.iterrows()
        if row.get("preco") is not None
    }


def build_daily_command_center(
    session,
    *,
    holdings: Optional[list[dict]] = None,
    tickers: Optional[list[str]] = None,
    forward_days: int = 20,
) -> DailyCommandCenter:
    """Monta a camada operacional unica do dia."""
    holdings = holdings or []
    monitored = tickers or tickers_ativos(session)
    params_map = _build_optimizer_params_map(session, monitored)
    decisions = decidir_universo(
        session,
        tickers=monitored,
        optimizer_params_por_ticker=params_map,
        forward_days=forward_days,
    )
    decisions.sort(key=_action_rank)

    prices_map = _prices_map_for_holdings(
        session,
        [h["ticker"] for h in holdings],
    )
    holding_advices = aconselhar_carteira(decisions, holdings, precos_atuais=prices_map)
    structural = alertas_estruturais(holding_advices)

    action_today = [
        d for d in decisions
        if d.acao in {"COMPRAR", "VENDER", "EVITAR"}
    ]
    watchlist = [d for d in decisions if _is_watchlist_candidate(d)]
    risks = [d for d in decisions if _is_risk_case(d)]

    action_today.sort(key=_action_rank)
    watchlist.sort(key=_action_rank)
    risks.sort(key=_action_rank)

    data_ref = max((d.data_referencia for d in decisions), default=date.today())
    return DailyCommandCenter(
        data_referencia=data_ref,
        universe_size=len(monitored),
        decisions=decisions,
        action_today=action_today,
        watchlist=watchlist,
        risks=risks,
        holding_advices=holding_advices,
        structural_alerts=structural,
    )


def export_daily_report_md(report: DailyCommandCenter) -> str:
    """Markdown operacional com secoes escaneaveis."""
    out: list[str] = []
    out.append(f"# Painel do Dia - {report.data_referencia.isoformat()}")
    out.append("")
    out.append("> SUGESTOES operacionais geradas por regras estatisticas. Nao sao ordens executaveis.")
    out.append("")

    out.append("## Acoes Hoje")
    if not report.action_today:
        out.append("- Nenhuma acao taticamente prioritaria hoje.")
    else:
        for d in report.action_today:
            flags = _flags_summary(d)
            out.append(
                f"- **{d.ticker}** | {d.acao} | {d.nivel_concordancia} | "
                f"Ot/Ep/WF: {d.sinal_otimizador}/{d.sinal_episodio}/{d.sinal_walkforward} | "
                f"P/VP pct: {_fmt_pct(d.pvp_percentil)} | Flags: {flags}"
            )
    out.append("")

    out.append("## Watchlist")
    if not report.watchlist:
        out.append("- Nenhum ticker em observacao especial.")
    else:
        for d in report.watchlist:
            gatilhos = []
            if d.janela_captura_aberta:
                gatilhos.append("janela captura")
            if d.episodio_eh_novo is True:
                gatilhos.append("episodio novo")
            elif d.episodio_eh_novo is False:
                gatilhos.append("episodio em continuacao")
            if d.sinal_otimizador == "BUY":
                gatilhos.append("otimizador BUY")
            if d.sinal_walkforward == "BUY":
                gatilhos.append("walk-forward BUY")
            out.append(f"- **{d.ticker}** | {', '.join(gatilhos) if gatilhos else 'observacao'}")
    out.append("")

    out.append("## Carteira")
    if not report.holding_advices:
        out.append("- Sem posicoes cadastradas.")
    else:
        for a in report.holding_advices:
            out.append(
                f"- **{a.ticker}** | {a.badge} | {a.prioridade} | "
                f"Peso: {_fmt_weight(a.peso_carteira)} | {a.racional}"
            )
    out.append("")

    out.append("## Riscos")
    if not report.risks:
        out.append("- Sem riscos destacados alem do baseline do sistema.")
    else:
        for d in report.risks:
            out.append(f"- **{d.ticker}** | {_flags_summary(d)}")
    out.append("")

    return "\n".join(out)


def export_daily_report_csv(report: DailyCommandCenter) -> str:
    """CSV flat para planilha com coluna de secao."""
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "section", "ticker", "acao", "nivel_concordancia",
        "sinal_otimizador", "sinal_episodio", "sinal_walkforward",
        "pvp_percentil", "dy_gap_percentil", "preco_referencia",
        "flags", "extra",
    ])

    for d in report.action_today:
        writer.writerow([
            "acoes_hoje", d.ticker, d.acao, d.nivel_concordancia,
            d.sinal_otimizador, d.sinal_episodio, d.sinal_walkforward,
            d.pvp_percentil, d.dy_gap_percentil, d.preco_referencia,
            _flags_summary(d), "; ".join(d.rationale[:2]),
        ])
    for d in report.watchlist:
        writer.writerow([
            "watchlist", d.ticker, d.acao, d.nivel_concordancia,
            d.sinal_otimizador, d.sinal_episodio, d.sinal_walkforward,
            d.pvp_percentil, d.dy_gap_percentil, d.preco_referencia,
            _flags_summary(d), "; ".join(d.rationale[:2]),
        ])
    for a in report.holding_advices:
        writer.writerow([
            "carteira", a.ticker, a.badge, a.prioridade,
            "", "", "", "", "", a.preco_atual,
            a.flags_resumo, a.racional,
        ])
    for d in report.risks:
        writer.writerow([
            "riscos", d.ticker, d.acao, d.nivel_concordancia,
            d.sinal_otimizador, d.sinal_episodio, d.sinal_walkforward,
            d.pvp_percentil, d.dy_gap_percentil, d.preco_referencia,
            _flags_summary(d), "; ".join(d.rationale[:2]),
        ])

    return buf.getvalue()


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/d"
    return f"{value:.1f}%"


def _fmt_weight(value: Optional[float]) -> str:
    if value is None:
        return "n/d"
    return f"{value * 100:.1f}%"


def _flags_summary(decision: TickerDecision) -> str:
    flags = []
    if decision.flag_destruicao_capital:
        flags.append("destr.capital")
    if decision.flag_emissao_recente:
        flags.append("emissao")
    if decision.flag_pvp_caro:
        flags.append("P/VP>p95")
    if decision.flag_dy_gap_baixo:
        flags.append("DYgap<p5")
    return ", ".join(flags) if flags else "-"
