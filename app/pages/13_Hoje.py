import hashlib
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.aviso_ui import AVISO_CURTO, render_aviso_evidencia, rotulo_acao, rotulo_flags
from app.components.carteira_ui import load_carteira_db
from app.components.snapshot_ui import (
    load_command_center_snapshot,
    load_latest_snapshot_meta,
    load_panorama_snapshot,
    load_ultima_data_preco,
    render_carteira_alterada,
    render_snapshot_info,
    load_opportunities_snapshot,
    sufixo_preco_parado,
)
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.decision import (
    export_daily_report_csv,
    export_daily_report_md,
)
from src.fii_analysis.evaluation.daily_diff import calcular_diff_diario, render_diff_markdown, rotulo_periodo_diff
from src.fii_analysis.data.database import SnapshotRun, get_session_ctx
from sqlalchemy import select
from src.fii_analysis.decision.suporte import rationale_legivel, rotulo_sinal

safe_set_page_config(page_title="Hoje", page_icon="compass", layout="wide")

_CSS = """
<style>
.hoje-card {
    background:#fff; border-radius:12px; border:1px solid #e8eaed;
    border-left:5px solid #546e7a; padding:14px 18px; margin-bottom:10px;
    box-shadow:0 1px 4px rgba(0,0,0,.05); transition:box-shadow .15s;
}
.hoje-card:hover{box-shadow:0 3px 12px rgba(0,0,0,.09);}
.hoje-card-COMPRAR{border-left-color:#2e7d32;}
.hoje-card-VENDER {border-left-color:#c62828;}
.hoje-card-AGUARDAR{border-left-color:#f57f17;}
.hoje-card-EVITAR {border-left-color:#6a1a8a;}
.hoje-card-header{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
.hoje-ticker{font-size:1.1rem;font-weight:800;color:#1a1a1a;min-width:72px;}
.hoje-conc{margin-left:auto;font-size:.8rem;font-weight:600;color:#555;}
.hoje-signals{font-size:.83rem;color:#444;margin-bottom:7px;}
.hoje-metrics{font-size:.8rem;color:#666;margin-bottom:6px;}
.hoje-rationale{font-size:.88rem;color:#333;background:#f8f9fa;border-radius:6px;padding:7px 10px;margin-bottom:6px;line-height:1.5;}
.hoje-flags{font-size:.76rem;color:#c62828;font-weight:600;}
.badge{display:inline-block;padding:3px 10px;border-radius:16px;font-size:.76rem;font-weight:700;}
.badge-COMPRAR,.badge-BUY{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7;}
.badge-VENDER,.badge-SELL{background:#ffebee;color:#c62828;border:1px solid #ef9a9a;}
.badge-AGUARDAR{background:#fff3e0;color:#e65100;border:1px solid #ffcc80;}
.badge-EVITAR{background:#f3e5f5;color:#6a1a8a;border:1px solid #ce93d8;}
.badge-HOLD{background:#eceff1;color:#546e7a;border:1px solid #b0bec5;}
.badge-AUMENTAR{background:#e8f5e9;color:#2e7d32;border:1px solid #a5d6a7;}
.badge-REDUZIR{background:#fff3e0;color:#e65100;border:1px solid #ffcc80;}
.badge-SAIR{background:#ffebee;color:#c62828;border:1px solid #ef9a9a;}
</style>
"""


@safe_page
def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    render_sidebar_guide("Hoje", "Operar")
    render_page_header(
        "Hoje",
        "Painel descritivo do dia. Esta pagina concentra os destaques dos indicadores, a watchlist e o cruzamento da carteira com os sinais do projeto.",
        "Operar",
    )
    render_inline_note(
        "Use esta tela como leitura diaria do estado dos fundos. Para ver o racional estatistico dos sinais, siga para Otimizador V2, Episodios ou Walk-Forward."
    )
    render_aviso_evidencia()

    holdings = load_carteira_db()
    holdings_key = tuple(sorted(
        (h["ticker"], int(h.get("quantidade", 0) or 0))
        for h in holdings
    ))
    has_holdings = bool(holdings_key)
    snapshot_scope = "carteira" if has_holdings else "curado"

    if st.button("Atualizar Painel", type="primary"):
        load_command_center_snapshot.clear()
        load_latest_snapshot_meta.clear()
        st.rerun()

    with st.spinner("Carregando snapshot do dia..."):
        report = load_command_center_snapshot(snapshot_scope, holdings_key)
        if report is None and has_holdings:
            report = load_command_center_snapshot("curado", ())
            snapshot_scope = "curado"

    if report is None:
        st.info(
            "Nenhum snapshot disponivel para hoje. "
            "Execute `fii update-prices` para atualizar precos e gerar o snapshot do dia."
        )
        render_footer()
        return

    # Quando scope=carteira, passar o hash para garantir meta do run correto
    meta_hash: str | None = None
    if snapshot_scope == "carteira" and holdings_key:
        meta_hash = hashlib.md5(
            ",".join(f"{t}:{q}" for t, q in sorted(holdings_key)).encode()
        ).hexdigest()[:12]
    meta = load_latest_snapshot_meta(snapshot_scope, carteira_hash=meta_hash)
    stale_carteira = has_holdings and not report.holding_advices
    render_snapshot_info(meta, stale_carteira=stale_carteira)
    render_carteira_alterada(meta, holdings)

    # Datas do ultimo preco por ticker + motivos de bloqueio de compra (B4)
    tickers_rep = tuple(sorted({d.ticker for d in report.decisions} | {a.ticker for a in report.holding_advices}))
    datas_preco = load_ultima_data_preco(tickers_rep)
    bloqueios = {
        d.ticker: d.bloqueio_compra
        for d in report.decisions
        if getattr(d, "bloqueio_compra", None)
    }

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Destaques Hoje", len(report.action_today))
    col2.metric("Watchlist", len(report.watchlist))
    col3.metric("Riscos", len(report.risks))
    col4.metric("Holdings", len(report.holding_advices))
    col5.metric("Universo", report.universe_size)
    col6.metric("Snapshot", snapshot_scope.title(), delta=report.data_referencia.isoformat())

    st.markdown("---")
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "Baixar Relatorio (MD)",
            data=f"> {AVISO_CURTO}\n\n" + export_daily_report_md(report),
            file_name=f"{report.data_referencia.isoformat()}_hoje.md",
            mime="text/markdown",
        )
    with dl2:
        st.download_button(
            "Baixar Relatorio (CSV)",
            data=export_daily_report_csv(report),
            file_name=f"{report.data_referencia.isoformat()}_hoje.csv",
            mime="text/csv",
        )

    st.caption(
        "Os rotulos abaixo descrevem o estado dos indicadores (favoravel, desfavoravel, neutro, "
        "alerta de risco). Nao sao ordens nem recomendacao de compra ou venda."
    )

    # ── Seção: O que mudou desde ontem ─────────────────────────────────────────
    with get_session_ctx() as session:
        runs = session.execute(
            select(SnapshotRun)
            .where(SnapshotRun.status == "ready")
            .order_by(SnapshotRun.data_referencia.desc(), SnapshotRun.criado_em.desc())
            .limit(2)
        ).scalars().all()
        
        diff_md = None
        diff_rotulo = "desde o snapshot anterior"
        if len(runs) >= 2:
            diff_obj = calcular_diff_diario(session, runs[0].id, runs[1].id)
            diff_md = render_diff_markdown(diff_obj)
            diff_rotulo = rotulo_periodo_diff(diff_obj.data_anterior, diff_obj.data_atual)

    if diff_md:
        with st.expander(f"🔍 O que mudou {diff_rotulo}", expanded=True):
            st.markdown(diff_md)

    # ── Seção: Oportunidades de Rotação (Top 3) ──────────────────────────────────
    with st.spinner("Buscando pares de rotação..."):
        _, opps_df = load_opportunities_snapshot()
    
    if not opps_df.empty:
        with st.expander("🔄 Pares de rotação identificados (Top 3)", expanded=True):
            st.markdown("Pares com maior spread líquido e sem vetos ativos (descritivo, sem validação de retorno futuro):")
            top_3 = opps_df.head(3)
            for _, o in top_3.iterrows():
                st.markdown(
                    f"- **{o['vender']}** ➔ **{o['comprar']}** | "
                    f"Spread Líq: **`{o['spread_liquido_pct']:+.1f} pp`** | "
                    f"Delta Score: **`{o['delta_score']:+.0f}`** | "
                    f"Persistência: `{o['dias_persistencia']} dias` | "
                    f"Critic: `{o['critic_veredicto']}`"
                )
            st.markdown("*(Acesse o menu lateral **Pares de Rotacao** para ver detalhes, gerar prompts e registrar decisões)*")
    else:
        with st.expander("🔄 Pares de rotação identificados (Top 3)", expanded=False):
            st.info("Nenhum par de rotação ativo hoje.")

    # Carregar scores do snapshot para exibir badges coloridos
    _, snap_df = load_panorama_snapshot(snapshot_scope)
    scores: dict[str, int | None] = {}
    if not snap_df.empty and "ticker" in snap_df.columns and "score_total" in snap_df.columns:
        for _, row in snap_df.iterrows():
            scores[row["ticker"]] = row.get("score_total")

    tab_actions, tab_holdings, tab_watchlist, tab_risks, tab_cdi = st.tabs(
        ["🎯 Destaques do Dia", "💼 Carteira Cruzada", "👁️ Watchlist", "⚠️ Riscos e Vetos", "📉 Contexto de Juros"]
    )
    with tab_actions:
        _render_actions_today(report, scores)
    with tab_holdings:
        _render_holdings(report, bloqueios, datas_preco)
    with tab_watchlist:
        _render_watchlist(report, scores, bloqueios, datas_preco)
    with tab_risks:
        _render_risks(report, bloqueios, datas_preco)
    with tab_cdi:
        _render_cdi_context(report, snapshot_scope, meta_hash)

    render_footer()


def _rot(d, chave: str, sinal) -> str:
    """Sinal com rotulo "(info)" quando sem suporte estatistico (nao vota)."""
    return rotulo_sinal(sinal, (getattr(d, "suporte_sinais", None) or {}).get(chave))


def _sig_icon(sinal: str, acao: str) -> str:
    """Ícone do sinal de cada motor vs ação do dia."""
    s = (sinal or "").upper()
    if s == "INDISPONIVEL" or not s:
        return "❓"
    if s == "NEUTRO":
        return "⚪"
    # Congruente com ação?
    a = (acao or "").upper()
    if (s == "BUY" and a in ("COMPRAR",)) or (s == "SELL" and a in ("VENDER",)):
        return "✅"
    if (s == "BUY" and a in ("VENDER",)) or (s == "SELL" and a in ("COMPRAR",)):
        return "❌"
    return "🔵"


def _score_color(s) -> str:
    if s is None:
        return "#888"
    if s >= 80: return "#2e7d32"
    if s >= 65: return "#558b2f"
    if s >= 50: return "#f57f17"
    return "#c62828"


def _score_label(s) -> str:
    if s is None: return "n/d"
    if s >= 80: return f"{s} Excelente"
    if s >= 65: return f"{s} Bom"
    if s >= 50: return f"{s} Neutro"
    return f"{s} Fraco"


def _render_action_card(d, scores: dict | None) -> None:
    score_val = (scores or {}).get(d.ticker)
    # VETADA override: score color turns gray + warning prefix to avoid false-positive green
    if d.nivel_concordancia == "VETADA" and score_val is not None:
        sc = "#888"
        sl = f"⚠️ {score_val} (VETADA)"
    else:
        sc = _score_color(score_val)
        sl = _score_label(score_val)
    conc_icon = {"ALTA": "⚡", "MEDIA": "👀", "BAIXA": "💤", "VETADA": "🚫"}.get(d.nivel_concordancia, "")
    pvp_str = f"P/VP p{d.pvp_percentil:.0f}%" if d.pvp_percentil is not None else ""
    dy_str  = f"DY Gap p{d.dy_gap_percentil:.0f}%" if d.dy_gap_percentil is not None else ""
    metrics_parts = [x for x in [pvp_str, dy_str] if x]
    metrics_html = " &nbsp;·&nbsp; ".join(metrics_parts) if metrics_parts else ""
    flags = _flags_text(d)
    flags_html = f'<div class="hoje-flags">⚠️ {flags}</div>' if flags != "-" else ""
    if getattr(d, "bloqueio_compra", None):
        flags_html += f'<div class="hoje-flags">🚫 Compra bloqueada: {d.bloqueio_compra}</div>'
    rat_legivel = rationale_legivel(d.rationale)
    rationale_line = rat_legivel[0] if rat_legivel else ""
    rat_html = f'<div class="hoje-rationale">{rationale_line}</div>' if rationale_line else ""
    badge_cls = f"badge-{d.acao}"
    card_cls  = f"hoje-card-{d.acao}"
    sig_html = (
        f'{_sig_icon(d.sinal_otimizador, d.acao)} Otim <strong>{_rot(d, "otimizador", d.sinal_otimizador)}</strong>'
        f' &nbsp;·&nbsp; '
        f'{_sig_icon(d.sinal_episodio, d.acao)} Epi <strong>{_rot(d, "episodio", d.sinal_episodio)}</strong>'
        f' &nbsp;·&nbsp; '
        f'{_sig_icon(d.sinal_walkforward, d.acao)} WF <strong>{_rot(d, "walkforward", d.sinal_walkforward)}</strong>'
    )
    html = f"""
<div class="hoje-card {card_cls}">
  <div class="hoje-card-header">
    <span class="hoje-ticker">{d.ticker}</span>
    <span class="badge {badge_cls}">{rotulo_acao(d.acao)}</span>
    <span style="font-size:.83rem;color:{sc};font-weight:700">{sl}/100</span>
    <span class="hoje-conc">{conc_icon} {d.nivel_concordancia}</span>
  </div>
  <div class="hoje-signals">{sig_html}</div>
  {f'<div class="hoje-metrics">{metrics_html}</div>' if metrics_html else ''}
  {rat_html}
  {flags_html}
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def _render_actions_today(report, scores: dict | None = None):
    st.subheader("Destaques do Dia")
    if not report.action_today:
        st.info("Nenhum destaque prioritario nos indicadores hoje.")
        return

    # ── Tabela completa — sempre visível ───────────────────────────────────
    def _score_badge(ticker):
        s = (scores or {}).get(ticker)
        if s is None: return "n/d"
        return _score_label(s)
    df = pd.DataFrame([{
        "Ticker": d.ticker, "Leitura": rotulo_acao(d.acao),
        "Score": _score_badge(d.ticker), "Confianca": d.nivel_concordancia,
        "Otimizador": _rot(d, "otimizador", d.sinal_otimizador),
        "Episodios": _rot(d, "episodio", d.sinal_episodio),
        "WalkForward": _rot(d, "walkforward", d.sinal_walkforward),
        "P/VP pct": f"{d.pvp_percentil:.1f}%" if d.pvp_percentil is not None else "n/d",
        "DY Gap pct": f"{d.dy_gap_percentil:.1f}%" if d.dy_gap_percentil is not None else "n/d",
        "Sensibilidade Juros": f"{d.cdi_repricing_12m * 100:+.1f}%" if getattr(d, "cdi_repricing_12m", None) is not None else "n/d",
        "Flags": _flags_text(d),
    } for d in report.action_today])
    st.dataframe(df, use_container_width=True, hide_index=True,
                 height=38 + 35 * len(df))

    # ── Cards detalhados — ALTA concordância + top 3 MÉDIA ─────────────────
    alta  = [d for d in report.action_today if d.nivel_concordancia == "ALTA"]
    media = sorted(
        [d for d in report.action_today if d.nivel_concordancia == "MEDIA"],
        key=lambda d: (scores or {}).get(d.ticker) or 0, reverse=True
    )[:3]
    cards_to_show = alta + media

    if cards_to_show:
        with st.expander(f"Ver detalhes ({len(cards_to_show)} prioritários — ALTA + top 3 MÉDIA)"):
            for d in cards_to_show:
                _render_action_card(d, scores)

    with st.expander("Ver racional dos destaques do dia"):
        for d in report.action_today:
            score_val = (scores or {}).get(d.ticker)
            score_txt = f" | Score: {score_val}/100" if score_val is not None else ""
            st.markdown(f"**{d.ticker}** - {rotulo_acao(d.acao)} ({d.nivel_concordancia}){score_txt}")
            for item in rationale_legivel(d.rationale):
                st.write(f"- {item}")
            st.markdown("---")



def _render_watchlist(report, scores: dict | None = None, bloqueios: dict | None = None, datas: dict | None = None):
    st.subheader("Watchlist")
    if not report.watchlist:
        st.info("Nenhum ticker em observacao especial hoje.")
        return

    df = pd.DataFrame([{
        "Ticker": d.ticker + sufixo_preco_parado(d.ticker, datas or {}, report.data_referencia),
        "Estado": rotulo_acao(d.acao),
        "Score": f"{scores.get(d.ticker, 'n/d')}/100" if scores and scores.get(d.ticker) is not None else "n/d",
        "Otimizador": _rot(d, "otimizador", d.sinal_otimizador),
        "Episodios": _rot(d, "episodio", d.sinal_episodio),
        "WalkForward": _rot(d, "walkforward", d.sinal_walkforward),
        "Episodio Hoje": _episode_text(d),
        "Captura Div.": "Aberta" if d.janela_captura_aberta else "Nao",
        "Prox. Data-com": (
            d.proxima_data_com_estimada.isoformat()
            if d.proxima_data_com_estimada and d.proxima_data_com_estimada >= report.data_referencia
            else "n/d"
        ),
        "Flags": _flags_text(d),
        "Compra bloqueada": (bloqueios or {}).get(d.ticker, "-"),
    } for d in report.watchlist])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _badge_html(acao: str) -> str:
    cls = f"badge-{acao}" if acao in ("AUMENTAR","HOLD","REDUZIR","SAIR","EVITAR_NOVOS_APORTES","COMPRAR","VENDER") else "badge-HOLD"
    return f'<span class="badge {cls}">{rotulo_acao(acao)}</span>'


def _pri_prefix(p: str) -> str:
    return {"ALTA": "⚡ ALTA", "MEDIA": "👀 MÉDIA", "BAIXA": "💤 BAIXA"}.get(p, p)


def _render_holdings(report, bloqueios: dict | None = None, datas: dict | None = None):
    st.subheader("Carteira Cruzada com Sinais")
    if not report.holding_advices:
        st.info("Sem posicoes cadastradas na carteira ou snapshot sem dados de carteira.")
        return

    for a in report.holding_advices:
        pl_pct = None
        if a.preco_atual and a.preco_medio and a.preco_medio > 0:
            pl_pct = (a.preco_atual - a.preco_medio) / a.preco_medio * 100
        pl_str = (f"<span style='color:{'#2e7d32' if pl_pct>=0 else '#c62828'};font-weight:600'>"
                  f"{'+'if pl_pct>=0 else ''}{pl_pct:.1f}%</span>") if pl_pct is not None else "n/d"
        peso_str = f"{a.peso_carteira*100:.1f}%" if a.peso_carteira else "n/d"
        flags_ok = a.flags_resumo and a.flags_resumo != "—"
        flags_html = f"<span style='color:#c62828;font-size:.78rem'>⚠️ {rotulo_flags(a.flags_resumo)}</span>" if flags_ok else ""
        st.markdown(
            f"{_badge_html(a.acao_recomendada)} &nbsp;"
            f"<strong>{a.ticker}</strong>{sufixo_preco_parado(a.ticker, datas or {}, report.data_referencia)} &nbsp;"
            f"{_pri_prefix(a.prioridade)} &nbsp;·&nbsp;"
            f"Peso {peso_str} &nbsp;·&nbsp; PM R$ {a.preco_medio:.2f} &nbsp;·&nbsp; P&L {pl_str}"
            f"{'&nbsp;·&nbsp;'+flags_html if flags_ok else ''}",
            unsafe_allow_html=True
        )
        st.caption(a.racional)
        if (bloqueios or {}).get(a.ticker):
            st.caption(f"🚫 Compra bloqueada: {bloqueios[a.ticker]}")
        st.divider()

    if report.structural_alerts:
        st.caption("Alertas estruturais da carteira")
        for alert in report.structural_alerts:
            if alert.severidade == "atencao":
                st.warning(alert.descricao)
            else:
                st.info(alert.descricao)


def _render_risks(report, bloqueios: dict | None = None, datas: dict | None = None):
    st.subheader("Riscos e Vetos")
    if not report.risks:
        st.info("Sem vetos ou flags de risco destacados hoje.")
        return

    df = pd.DataFrame([{
        "Ticker": d.ticker + sufixo_preco_parado(d.ticker, datas or {}, report.data_referencia),
        "Leitura": rotulo_acao(d.acao),
        "Confianca": d.nivel_concordancia,
        "Flags": _flags_text(d),
        "Motivo destr.": d.motivo_destruicao or "-",
        "Compra bloqueada": (bloqueios or {}).get(d.ticker, "-"),
    } for d in report.risks])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _flags_text(decision) -> str:
    flags = []
    if decision.flag_destruicao_capital:
        flags.append("alerta de risco: VP/cota em queda")
    if decision.flag_emissao_recente:
        flags.append("emissao")
    if decision.flag_pvp_caro:
        flags.append("P/VP>p95")
    if decision.flag_dy_gap_baixo:
        flags.append("DYgap<p5")
    return ", ".join(flags) if flags else "-"


def _episode_text(decision) -> str:
    if decision.episodio_eh_novo is True:
        return "Novo"
    if decision.episodio_eh_novo is False:
        if decision.pregoes_desde_ultimo_episodio is None:
            return "Continuacao"
        return f"Continuacao ({decision.pregoes_desde_ultimo_episodio} preg.)"
    return "-"


def _render_cdi_context(report, snapshot_scope, meta_hash):
    """Tab de Contexto de Juros — diagnostico CDI + Focus BCB, NAO altera acao."""
    st.subheader("Contexto de Juros (CDI + Focus BCB)")
    st.caption(
        "Diagnostico de sensibilidade ao CDI e expectativas de mercado (Focus BCB). "
        "NAO altera nenhum rotulo — serve para interpretar se P/VP alto "
        "pode ser repricing racional em regime de queda de juros."
    )

    # --- Focus BCB a partir do snapshot run ---
    try:
        meta = load_latest_snapshot_meta(
            snapshot_scope,
            carteira_hash=meta_hash,
        )
    except Exception:
        meta = None

    focus_3m = meta.get("focus_selic_3m") if meta else None
    focus_6m = meta.get("focus_selic_6m") if meta else None
    focus_12m = meta.get("focus_selic_12m") if meta else None
    focus_status = meta.get("focus_status") if meta else None

    if focus_status and focus_status != "SEM_DADOS":
        st.subheader("Expectativas Focus BCB (Selic)")
        fc1, fc2, fc3, fc4 = st.columns(4)
        fc1.metric("Focus 3m", f"{focus_3m:.2%}" if focus_3m is not None else "n/d")
        fc2.metric("Focus 6m", f"{focus_6m:.2%}" if focus_6m is not None else "n/d")
        fc3.metric("Focus 12m", f"{focus_12m:.2%}" if focus_12m is not None else "n/d")
        fc4.metric("Status", focus_status or "n/d")
    else:
        st.info("Dados Focus BCB nao disponiveis neste snapshot.")

    # --- Sensibilidade CDI por ticker ---
    has_cdi = any(
        getattr(d, "cdi_status", None) not in (None, "SEM_CDI", "DADOS_INSUFICIENTES")
        for d in report.decisions
    )

    has_focus_ticker = any(
        getattr(d, "cdi_delta_focus_12m", None) is not None
        or getattr(d, "cdi_repricing_12m", None) is not None
        for d in report.decisions
    )

    if not has_cdi and not has_focus_ticker:
        st.info("Sem dados de sensibilidade CDI disponiveis para este snapshot.")
        return

    rows = []
    for d in report.decisions:
        status = getattr(d, "cdi_status", None) or "n/d"
        beta = getattr(d, "cdi_beta", None)
        r2 = getattr(d, "cdi_r_squared", None)
        pval = getattr(d, "cdi_p_value", None)
        resid = getattr(d, "cdi_residuo_atual", None)
        resid_pct = getattr(d, "cdi_residuo_percentil", None)
        delta_f = getattr(d, "cdi_delta_focus_12m", None)
        repricing = getattr(d, "cdi_repricing_12m", None)
        rows.append({
            "Ticker": d.ticker,
            "Status": status,
            "Beta CDI": f"{beta:.4f}" if beta is not None else "n/d",
            "R2": f"{r2:.3f}" if r2 is not None else "n/d",
            "p-valor": f"{pval:.4f}" if pval is not None else "n/d",
            "Residuo": f"{resid:.3f}" if resid is not None else "n/d",
            "Residuo pct": f"{resid_pct:.1f}%" if resid_pct is not None else "n/d",
            "Delta Focus 12m": f"{delta_f:+.2%}" if delta_f is not None else "n/d",
            "Repricing 12m": f"{repricing:+.3f}" if repricing is not None else "n/d",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 height=38 + 35 * len(df))
    st.caption(
        "**R² > 0.3**: CDI explica bem o P/VP &nbsp;·&nbsp; "
        "**p-valor < 0.05**: relação estatisticamente significante &nbsp;·&nbsp; "
        "**Resíduo pct alto**: P/VP acima do que o CDI justificaria"
    )

    # --- Leitura macro por ticker ---
    st.subheader("Leitura Macro por Ticker")
    st.caption(
        "Interpretacao contextual gerada pelo sistema a partir de beta, Focus, residuo e R2. "
        "NAO altera nenhum rotulo."
    )
    macro_found = False
    for d in report.decisions:
        macro_lines = [
            line for line in d.rationale
            if any(kw in line for kw in (
                "Leitura macro:", "CDI-ajustado:", "CDI 12m atual",
                "Repricing estimado", "Focus aponta", "cenário de juros",
                "Queda esperada", "alta de juros", "repricing racional",
                "Residuo CDI", "residuo segue", "CDI explica",
                "Dados insuficientes", "Sem dados de CDI", "Regressão CDI",
                "Sensibilidade CDI", "Focus BCB indisponivel",
            ))
        ]
        if macro_lines:
            macro_found = True
            with st.expander(f"**{d.ticker}** — Contexto de Juros"):
                for line in macro_lines:
                    # Remove prefixo "Leitura macro: " para limpar visual
                    clean = line.replace("Leitura macro: ", "")
                    st.write(f"- {clean}")

    if not macro_found:
        st.info("Nenhuma leitura macro disponivel neste snapshot.")

    with st.expander("Como interpretar"):
        st.markdown(
            "- **Beta CDI**: sensibilidade do P/VP ao CDI acumulado 12m. "
            "Beta negativo = P/VP sobe quando CDI cai (tipico de FIIs de tijolo).\n"
            "- **R2**: % da variacao do P/VP explicada pelo CDI.\n"
            "- **p-valor**: significancia estatistica do beta (< 0.05 = significativo).\n"
            "- **Residuo**: diferenca entre P/VP observado e o que o modelo CDI esperaria.\n"
            "- **Residuo pct**: em que percentil historico esta o residuo atual. "
            "Residuo positivo alto = P/VP acima do que o CDI justificaria.\n"
            "- **Delta Focus 12m**: diferenca entre expectativa Selic 12m e CDI 12m atual. "
            "Negativo = mercado espera queda de juros.\n"
            "- **Repricing 12m**: estimativa de impacto no P/VP caso a Selic siga o Focus 12m. "
            "Positivo = P/VP tenderia a subir em cenário de queda de juros."
        )


main()
