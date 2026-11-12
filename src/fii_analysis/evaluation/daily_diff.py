from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import (
    SnapshotRun,
    SnapshotTickerMetrics,
    SnapshotDecisions,
    SnapshotRadar,
    SnapshotOpportunities,
    SnapshotStructuralAlerts,
    SnapshotPortfolioAdvices,
    Dividendo,
)


@dataclass
class DailyDiff:
    data_atual: date
    data_anterior: date
    mudacoes_acao: list[dict] = field(default_factory=list)
    mudacoes_radar: list[dict] = field(default_factory=list)
    mudacoes_score: list[dict] = field(default_factory=list)
    oportunidades_novas: list[dict] = field(default_factory=list)
    oportunidades_expiradas: list[dict] = field(default_factory=list)
    proximas_datas_com: list[dict] = field(default_factory=list)
    alertas_novos: list[dict] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return (
            not self.mudacoes_acao
            and not self.mudacoes_radar
            and not self.mudacoes_score
            and not self.oportunidades_novas
            and not self.oportunidades_expiradas
            and not self.alertas_novos
        )


def calcular_diff_diario(session: Session, run_id_atual: int, run_id_anterior: int) -> DailyDiff:
    """Compara dois snapshots e identifica todas as mudanças ocorridas no intervalo."""
    run_act = session.get(SnapshotRun, run_id_atual)
    run_ant = session.get(SnapshotRun, run_id_anterior)

    dt_act = run_act.data_referencia if run_act else date.today()
    dt_ant = run_ant.data_referencia if run_ant else date.today()

    diff = DailyDiff(data_atual=dt_act, data_anterior=dt_ant)

    # 1. Carregar Ticker Metrics
    rows_act_met = session.execute(select(SnapshotTickerMetrics).where(SnapshotTickerMetrics.run_id == run_id_atual)).scalars().all()
    rows_ant_met = session.execute(select(SnapshotTickerMetrics).where(SnapshotTickerMetrics.run_id == run_id_anterior)).scalars().all()
    met_act = {m.ticker: m for m in rows_act_met}
    met_ant = {m.ticker: m for m in rows_ant_met}

    # 2. Carregar Decisions
    rows_act_dec = session.execute(select(SnapshotDecisions).where(SnapshotDecisions.run_id == run_id_atual)).scalars().all()
    rows_ant_dec = session.execute(select(SnapshotDecisions).where(SnapshotDecisions.run_id == run_id_anterior)).scalars().all()
    dec_act = {d.ticker: d for d in rows_act_dec}
    dec_ant = {d.ticker: d for d in rows_ant_dec}

    # 3. Carregar Advices
    rows_act_adv = session.execute(select(SnapshotPortfolioAdvices).where(SnapshotPortfolioAdvices.run_id == run_id_atual)).scalars().all()
    rows_ant_adv = session.execute(select(SnapshotPortfolioAdvices).where(SnapshotPortfolioAdvices.run_id == run_id_anterior)).scalars().all()
    adv_act = {a.ticker: a for a in rows_act_adv}
    adv_ant = {a.ticker: a for a in rows_ant_adv}

    # 4. Carregar Radar
    rows_act_rad = session.execute(select(SnapshotRadar).where(SnapshotRadar.run_id == run_id_atual)).scalars().all()
    rows_ant_rad = session.execute(select(SnapshotRadar).where(SnapshotRadar.run_id == run_id_anterior)).scalars().all()
    rad_act = {r.ticker: r for r in rows_act_rad}
    rad_ant = {r.ticker: r for r in rows_ant_rad}

    # Analisar mudanças por ticker
    all_tickers = sorted(list(set(dec_act.keys()) | set(dec_ant.keys())))

    for t in all_tickers:
        d_act = dec_act.get(t)
        d_ant = dec_ant.get(t)

        a_act = adv_act.get(t)
        a_ant = adv_ant.get(t)

        # A. Mudança de Ação/Badge
        if d_act and d_ant:
            acao_nv = d_act.acao
            acao_ant = d_ant.acao
            badge_nv = a_act.badge if a_act else "HOLD"
            badge_ant = a_ant.badge if a_ant else "HOLD"

            if acao_nv != acao_ant or badge_nv != badge_ant:
                diff.mudacoes_acao.append({
                    "ticker": t,
                    "acao_ant": acao_ant,
                    "acao_nv": acao_nv,
                    "badge_ant": badge_ant,
                    "badge_nv": badge_nv
                })

        # B. Mudança de Radar
        r_act = rad_act.get(t)
        r_ant = rad_ant.get(t)
        if r_act and r_ant:
            for f in ["pvp_baixo", "dy_gap_alto", "saude_ok", "liquidez_ok"]:
                val_act = bool(getattr(r_act, f))
                val_ant = bool(getattr(r_ant, f))
                if val_act != val_ant:
                    diff.mudacoes_radar.append({
                        "ticker": t,
                        "filtro": f,
                        "ant": val_ant,
                        "nv": val_act
                    })

        # C. Mudança de Score total >= 5
        m_act = met_act.get(t)
        m_ant = met_ant.get(t)
        if m_act and m_ant:
            s_act = m_act.score_total
            s_ant = m_ant.score_total
            if s_act is not None and s_ant is not None:
                delta = s_act - s_ant
                if abs(delta) >= 5:
                    diff.mudacoes_score.append({
                        "ticker": t,
                        "score_ant": s_ant,
                        "score_nv": s_act,
                        "delta": delta
                    })

    # 5. Oportunidades de Rotação
    opps_act = session.execute(select(SnapshotOpportunities).where(SnapshotOpportunities.run_id == run_id_atual)).scalars().all()
    opps_ant = session.execute(select(SnapshotOpportunities).where(SnapshotOpportunities.run_id == run_id_anterior)).scalars().all()

    pairs_act = {(o.vender, o.comprar): o for o in opps_act}
    pairs_ant = {(o.vender, o.comprar): o for o in opps_ant}

    for pair, o in pairs_act.items():
        if pair not in pairs_ant:
            diff.oportunidades_novas.append({
                "vender": o.vender,
                "comprar": o.comprar,
                "spread_liquido_pct": float(o.spread_liquido_pct),
                "delta_score": float(o.delta_score)
            })

    for pair, o in pairs_ant.items():
        if pair not in pairs_act:
            diff.oportunidades_expiradas.append({
                "vender": o.vender,
                "comprar": o.comprar,
                "spread_liquido_pct": float(o.spread_liquido_pct)
            })

    # 6. Alertas Estruturais — apenas os NOVOS em relação ao run anterior.
    # Alertas persistentes (ex.: concentração) repetem todo dia; listá-los
    # sempre tornaria o "Nada mudou" inalcançável.
    alerts_act = session.execute(select(SnapshotStructuralAlerts).where(SnapshotStructuralAlerts.run_id == run_id_atual)).scalars().all()
    alerts_ant = session.execute(select(SnapshotStructuralAlerts).where(SnapshotStructuralAlerts.run_id == run_id_anterior)).scalars().all()
    chaves_ant = {(a.tipo, a.severidade) for a in alerts_ant}
    for a in alerts_act:
        if (a.tipo, a.severidade) in chaves_ant:
            continue
        diff.alertas_novos.append({
            "tipo": a.tipo,
            "severidade": a.severidade,
            "descricao": a.descricao,
            "valor": float(a.valor) if a.valor is not None else None
        })

    # 7. Próximas Datas-Com (próximos 7 dias corridos ~ 5 dias úteis)
    today = dt_act
    end_date = today + timedelta(days=7)
    divs = session.execute(
        select(Dividendo)
        .where(Dividendo.data_com >= today, Dividendo.data_com <= end_date)
        .order_by(Dividendo.data_com.asc())
    ).scalars().all()

    for d in divs:
        diff.proximas_datas_com.append({
            "ticker": d.ticker,
            "data_com": d.data_com,
            "valor_cota": float(d.valor_cota)
        })

    return diff


def render_diff_markdown(diff: DailyDiff) -> str:
    """Gera o sumário de mudanças diárias estruturado em Markdown."""
    lines = []
    lines.append(f"## 1. O que mudou desde ontem ({diff.data_anterior.strftime('%d/%m/%Y')} ➔ {diff.data_atual.strftime('%d/%m/%Y')})")
    lines.append("")

    if diff.empty:
        lines.append("*Nada mudou no comportamento quantitativo e de recomendações desde ontem.*")
        lines.append("")
    else:
        # Ações recomendadas
        if diff.mudacoes_acao:
            lines.append("### 🟢 Recomendações e Sugestões Alteradas")
            for m in diff.mudacoes_acao:
                lines.append(
                    f"- **{m['ticker']}**: Ação: `{m['acao_ant']}` ➔ `{m['acao_nv']}` | "
                    f"Badge: `{m['badge_ant']}` ➔ `{m['badge_nv']}`"
                )
            lines.append("")

        # Filtros de Radar
        if diff.mudacoes_radar:
            lines.append("### 🔍 Alterações no Radar (Filtros de Entrada/Saída)")
            for m in diff.mudacoes_radar:
                ant_str = "✓" if m["ant"] else "✗"
                nv_str = "✓" if m["nv"] else "✗"
                lines.append(f"- **{m['ticker']}**: Filtro `{m['filtro']}` mudou de `{ant_str}` para `{nv_str}`")
            lines.append("")

        # Scores
        if diff.mudacoes_score:
            lines.append("### 📈 Mudanças Relevantes de Score (Δ ≥ 5)")
            for m in diff.mudacoes_score:
                lines.append(f"- **{m['ticker']}**: Score `{m['score_ant']}` ➔ `{m['score_nv']}` ({m['delta']:+d} pts)")
            lines.append("")

        # Oportunidades Novas
        if diff.oportunidades_novas:
            lines.append("### 🔄 Novas Oportunidades de Rotação Recomendadas")
            for o in diff.oportunidades_novas:
                lines.append(
                    f"- **VENDER {o['vender']}** ➔ **COMPRAR {o['comprar']}** | "
                    f"Spread Líq: `{o['spread_liquido_pct']:+.1f} pp` | Δ Score: `{o['delta_score']:+.0f}`"
                )
            lines.append("")

        # Alertas estruturais
        if diff.alertas_novos:
            lines.append("### ⚠️ Alertas Estruturais de Concentração")
            for a in diff.alertas_novos:
                lines.append(f"- **[{a['severidade']}] {a['tipo']}**: {a['descricao']}")
            lines.append("")

    # Próximas datas-com
    lines.append("## 2. Próximas Datas-Com Previstas (Próximos 5 dias úteis)")
    lines.append("")
    if not diff.proximas_datas_com:
        lines.append("*Nenhuma data-com prevista para os próximos dias.*")
        lines.append("")
    else:
        for d in diff.proximas_datas_com:
            lines.append(f"- **{d['ticker']}**: Data-com em `{d['data_com'].strftime('%d/%m/%Y')}` | Valor: `R$ {d['valor_cota']:.4f}`")
        lines.append("")

    return "\n".join(lines)
