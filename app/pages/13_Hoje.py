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

from app.components.carteira_ui import load_carteira_db
from app.components.snapshot_ui import (
    load_command_center_snapshot,
    load_latest_snapshot_meta,
    load_panorama_snapshot,
    render_snapshot_info,
)
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.decision import (
    export_daily_report_csv,
    export_daily_report_md,
)

safe_set_page_config(page_title="Hoje", page_icon="compass", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Hoje", "Operar")
    render_page_header(
        "Hoje",
        "Cockpit operacional do sistema. Esta pagina concentra as sugestoes do dia, a watchlist e o cruzamento da carteira com os sinais do projeto.",
        "Operar",
    )
    render_inline_note(
        "Use esta tela como entrada diaria. Se quiser validar o racional estatistico por tras das sugestoes, siga depois para Otimizador V2, Episodios ou Walk-Forward."
    )

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

    report = load_command_center_snapshot(snapshot_scope, holdings_key)
    if report is None and has_holdings:
        report = load_command_center_snapshot("curado", ())
        snapshot_scope = "curado"

    if report is None:
        st.info(
            "Nenhum snapshot disponivel para hoje. "
            "Execute `python scripts/generate_daily_snapshots.py` para "
            "pre-calcular os sinais do dia."
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

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Acoes Hoje", len(report.action_today))
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
            data=export_daily_report_md(report),
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

    st.info(
        "As acoes abaixo sao SUGESTOES operacionais geradas por regras estatisticas do sistema. "
        "Nao sao ordens executaveis e devem ser validadas antes de operar."
    )

    # Carregar scores do snapshot para exibir badges coloridos
    _, snap_df = load_panorama_snapshot(snapshot_scope)
    scores: dict[str, int | None] = {}
    if not snap_df.empty and "ticker" in snap_df.columns and "score_total" in snap_df.columns:
        for _, row in snap_df.iterrows():
            scores[row["ticker"]] = row.get("score_total")

    tab_actions, tab_holdings, tab_watchlist, tab_risks, tab_cdi = st.tabs(
        ["Acoes do Dia", "Carteira Cruzada", "Watchlist", "Riscos e Vetos", "Contexto de Juros"]
    )
    with tab_actions:
        _render_actions_today(report, scores)
    with tab_holdings:
        _render_holdings(report)
    with tab_watchlist:
        _render_watchlist(report, scores)
    with tab_risks:
        _render_risks(report)
    with tab_cdi:
        _render_cdi_context(report, snapshot_scope, meta_hash)

    render_footer()


def _render_actions_today(report, scores: dict | None = None):
    st.markdown("---")
    st.subheader("Acoes Hoje")
    if not report.action_today:
        st.info("Nenhuma acao tatica prioritaria hoje.")
        return

    def _score_badge(ticker: str) -> str:
        if scores is None:
            return "n/d"
        s = scores.get(ticker)
        if s is None:
            return "n/d"
        if s >= 80:
            return f"{s} (Excelente)"
        if s >= 65:
            return f"{s} (Bom)"
        if s >= 50:
            return f"{s} (Neutro)"
        return f"{s} (Fraco)"

    df = pd.DataFrame([{
        "Ticker": d.ticker,
        "Acao": d.acao,
        "Score": _score_badge(d.ticker),
        "Confianca": d.nivel_concordancia,
        "Otimizador": d.sinal_otimizador,
        "Episodios": d.sinal_episodio,
        "WalkForward": d.sinal_walkforward,
        "P/VP pct": f"{d.pvp_percentil:.1f}%" if d.pvp_percentil is not None else "n/d",
        "DY Gap pct": f"{d.dy_gap_percentil:.1f}%" if d.dy_gap_percentil is not None else "n/d",
        "Preco Ref": f"{d.preco_referencia:.2f}" if d.preco_referencia is not None else "n/d",
        "Flags": _flags_text(d),
    } for d in report.action_today])
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Ver racional das acoes do dia"):
        for d in report.action_today:
            score_val = scores.get(d.ticker) if scores else None
            score_txt = f" | Score: {score_val}/100" if score_val is not None else ""
            st.markdown(f"**{d.ticker}** - {d.acao} ({d.nivel_concordancia}){score_txt}")
            for item in d.rationale:
                st.write(f"- {item}")
            st.markdown("---")


def _render_watchlist(report, scores: dict | None = None):
    st.markdown("---")
    st.subheader("Watchlist")
    if not report.watchlist:
        st.info("Nenhum ticker em observacao especial hoje.")
        return

    df = pd.DataFrame([{
        "Ticker": d.ticker,
        "Estado": d.acao,
        "Score": f"{scores.get(d.ticker, 'n/d')}/100" if scores and scores.get(d.ticker) is not None else "n/d",
        "Otimizador": d.sinal_otimizador,
        "Episodios": d.sinal_episodio,
        "WalkForward": d.sinal_walkforward,
        "Episodio Hoje": _episode_text(d),
        "Captura Div.": "Aberta" if d.janela_captura_aberta else "Nao",
        "Prox. Data-com": d.proxima_data_com_estimada.isoformat() if d.proxima_data_com_estimada else "n/d",
        "Flags": _flags_text(d),
    } for d in report.watchlist])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_holdings(report):
    st.markdown("---")
    st.subheader("Carteira Cruzada com Sinais")
    if not report.holding_advices:
        st.info("Sem posicoes cadastradas na carteira ou snapshot sem dados de carteira.")
        return

    df = pd.DataFrame([{
        "Ticker": a.ticker,
        "Badge": a.badge,
        "Prioridade": a.prioridade,
        "Qtd": a.quantidade,
        "Preco Medio": f"{a.preco_medio:.2f}",
        "Preco Atual": f"{a.preco_atual:.2f}" if a.preco_atual is not None else "n/d",
        "Peso": f"{a.peso_carteira * 100:.1f}%" if a.peso_carteira is not None else "n/d",
        "Acao Sistema": a.acao_recomendada,
        "Confianca": a.nivel_concordancia,
        "Flags": a.flags_resumo,
        "Valida ate": a.valida_ate.isoformat(),
    } for a in report.holding_advices])
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Ver racional da carteira"):
        for a in report.holding_advices:
            st.markdown(f"**{a.ticker}** - {a.badge} ({a.prioridade})")
            st.write(a.racional)
            st.markdown("---")

    if report.structural_alerts:
        st.caption("Alertas estruturais da carteira")
        for alert in report.structural_alerts:
            if alert.severidade == "atencao":
                st.warning(alert.descricao)
            else:
                st.info(alert.descricao)


def _render_risks(report):
    st.markdown("---")
    st.subheader("Riscos e Vetos")
    if not report.risks:
        st.info("Sem vetos ou flags de risco destacados hoje.")
        return

    df = pd.DataFrame([{
        "Ticker": d.ticker,
        "Acao": d.acao,
        "Confianca": d.nivel_concordancia,
        "Flags": _flags_text(d),
        "Motivo destr.": d.motivo_destruicao or "-",
    } for d in report.risks])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _flags_text(decision) -> str:
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
    st.markdown("---")
    st.subheader("Contexto de Juros (CDI + Focus BCB)")
    st.caption(
        "Diagnostico de sensibilidade ao CDI e expectativas de mercado (Focus BCB). "
        "NAO altera a decisao de compra/venda — serve para interpretar se P/VP alto "
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
        st.markdown("#### Expectativas Focus BCB (Selic)")
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
    st.dataframe(df, use_container_width=True, hide_index=True)

    # --- Leitura macro por ticker ---
    st.markdown("#### Leitura Macro por Ticker")
    st.caption(
        "Interpretacao contextual gerada pelo sistema a partir de beta, Focus, residuo e R2. "
        "NAO altera a decisao de compra/venda."
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
