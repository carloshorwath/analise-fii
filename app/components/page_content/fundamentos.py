"""Conteudo de Fundamentos renderizavel sem decorators ou page_config.

Funções públicas de seção (usáveis individualmente pelo Dossiê):
    render_distribuicao_vs_geracao(ticker, *, key_prefix)
    render_dy_historico(ticker, *, key_prefix)
    render_pvp_historico(ticker, *, key_prefix)
    render_pl_cotas(ticker, *, key_prefix)
    render_risco_retorno(ticker, *, key_prefix)
    render(ticker, *, key_prefix)  — wrapper completo com st.tabs()
"""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from app.components.tables import format_number, format_pct
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.evaluation.daily_snapshots import load_risk_metrics_snapshot
from src.fii_analysis.features.data_loader import get_info_ticker
from src.fii_analysis.features.fundamentos import (
    classificar_alerta_distribuicao,
    get_alavancagem,
    get_dy_medias,
    get_efetiva_vs_patrimonial_resumo,
    get_payout_historico,
    get_pl_cotas_historico,
    get_pvp_medias,
)
from src.fii_analysis.features.risk_metrics import (
    beta_vs_ifix,
    dy_3m_anualizado as rm_dy_3m_anualizado,
    liquidez_media_21d,
    max_drawdown,
    retorno_total_12m,
    volatilidade_anualizada,
)


# ---------------------------------------------------------------------------
# Funções públicas de seção
# ---------------------------------------------------------------------------

def render_distribuicao_vs_geracao(ticker: str, *, key_prefix: str = "fund") -> None:
    """Distribuição vs Geração: payout chart + alerta efetiva vs patrimonial."""
    with get_session_ctx() as session:
        payout_df, _consec = get_payout_historico(ticker, session=session)
        if not payout_df.empty:
            resumo = get_efetiva_vs_patrimonial_resumo(ticker, session=session)
        else:
            resumo = None

    if payout_df.empty:
        st.info("Sem dados de rentabilidade disponiveis.")
        return

    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Bar(
        x=payout_df["data_referencia"],
        y=payout_df["rentab_efetiva_pct"],
        name="Rent. Efetiva %",
        marker_color="#636efa",
    ))
    fig.add_trace(go.Bar(
        x=payout_df["data_referencia"],
        y=payout_df["rentab_patrimonial_pct"],
        name="Rent. Patrimonial %",
        marker_color="#ef553b",
    ))
    alert_dates = payout_df[payout_df["distribuindo_mais_que_gera"]]["data_referencia"].tolist()
    if alert_dates:
        fig.add_trace(go.Bar(
            x=alert_dates,
            y=[0] * len(alert_dates),
            name="Efetiva > Patrimonial",
            marker_color="rgba(255,0,0,0.3)",
            showlegend=True,
        ))
    fig.update_layout(
        title=f"{ticker} — Rentabilidade Efetiva vs Patrimonial (24 meses)",
        xaxis_title="Mes", yaxis_title="% mes",
        template="plotly_white", height=400, barmode="group",
    )
    st.plotly_chart(fig, use_container_width=True)

    if resumo is not None:
        nivel, msg = classificar_alerta_distribuicao(resumo)
        if nivel == "error":
            st.error(msg)
        elif nivel == "warning":
            st.warning(msg)
        else:
            st.success(msg)


def render_dy_historico(ticker: str, *, key_prefix: str = "fund") -> None:
    """DY Histórico: médias 12m, 24m, 60m e percentil na série."""
    with get_session_ctx() as session:
        dy_data = get_dy_medias(ticker, session=session)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("DY 12m Atual",
                format_pct(dy_data["dy_12m_atual"]) if dy_data["dy_12m_atual"] else "n/d")
    col2.metric("DY 24m",
                format_pct(dy_data["media_dy_2anos"]) if dy_data["media_dy_2anos"] else "n/d")
    col3.metric("DY 60m",
                format_pct(dy_data["media_dy_5anos"]) if dy_data["media_dy_5anos"] else "n/d")
    col4.metric("Percentil na Serie",
                f"{dy_data['percentil_na_serie_completa']:.1f}%"
                if dy_data["percentil_na_serie_completa"] is not None else "n/d")


def render_pvp_historico(ticker: str, *, key_prefix: str = "fund") -> None:
    """P/VP Histórico: médias 2a/5a + gráfico com período selecionável."""
    with get_session_ctx() as session:
        pvp_data = get_pvp_medias(ticker, session=session)

    col1, col2, col3 = st.columns(3)
    col1.metric("P/VP Atual",
                format_number(pvp_data["pvp_atual"], 2) if pvp_data["pvp_atual"] else "n/d")
    col2.metric("Media 2 anos",
                format_number(pvp_data["media_pvp_2anos"], 2) if pvp_data["media_pvp_2anos"] else "n/d")
    col3.metric("Media 5 anos",
                format_number(pvp_data["media_pvp_5anos"], 2) if pvp_data["media_pvp_5anos"] else "n/d")

    serie_pvp = pvp_data.get("serie_pvp")
    if serie_pvp is None or len(serie_pvp) == 0:
        st.info("Sem serie historica de P/VP disponivel.")
        return

    periodo_pvp = st.radio(
        "Periodo P/VP",
        ["YTD", "12m", "3a", "Tudo"],
        index=1, horizontal=True,
        key=f"{key_prefix}_radio_pvp_periodo",
    )
    hoje = date.today()
    data_min = (
        date(hoje.year, 1, 1) if periodo_pvp == "YTD"
        else hoje - relativedelta(years=1) if periodo_pvp == "12m"
        else hoje - relativedelta(years=3) if periodo_pvp == "3a"
        else None
    )
    serie_plot = serie_pvp[serie_pvp.index >= data_min] if data_min is not None else serie_pvp

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=serie_plot.index, y=serie_plot.values,
        mode="lines", name="P/VP", line=dict(color="#1f77b4"),
    ))
    if pvp_data["media_pvp_2anos"] is not None:
        fig.add_hline(y=pvp_data["media_pvp_2anos"], line_dash="dash", line_color="orange",
                      annotation_text=f"Media 2a: {pvp_data['media_pvp_2anos']:.2f}")
    if pvp_data["media_pvp_5anos"] is not None:
        fig.add_hline(y=pvp_data["media_pvp_5anos"], line_dash="dot", line_color="green",
                      annotation_text=f"Media 5a: {pvp_data['media_pvp_5anos']:.2f}")
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="P/VP = 1.0")
    fig.update_layout(
        title=f"{ticker} — P/VP Historico",
        xaxis_title="Data", yaxis_title="P/VP",
        template="plotly_white", height=400,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_pl_cotas(ticker: str, *, key_prefix: str = "fund") -> None:
    """PL e Cotas: gráfico 36m (PL + cotas emitidas) + alavancagem."""
    with get_session_ctx() as session:
        pl_df = get_pl_cotas_historico(ticker, meses=36, session=session)
        alav = get_alavancagem(ticker, session=session)

    if pl_df.empty:
        st.info("Sem dados de PL e cotas disponiveis.")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=pl_df["data_referencia"],
        y=pl_df["patrimonio_liq"] / 1e6,
        name="PL (mi)", marker_color="#636efa",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=pl_df["data_referencia"],
        y=pl_df["cotas_emitidas"],
        mode="lines+markers", name="Cotas Emitidas",
        line=dict(color="#ef553b"),
    ), secondary_y=True)
    fig.update_layout(
        title=f"{ticker} — Patrimonio Liquido e Cotas (36 meses)",
        template="plotly_white", height=400,
    )
    fig.update_yaxes(title_text="PL (R$ milhoes)", secondary_y=False)
    fig.update_yaxes(title_text="Cotas Emitidas", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    ul = pl_df.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("PL Atual", f"R$ {ul['patrimonio_liq'] / 1e6:,.1f} mi" if ul.get("patrimonio_liq") else "n/d")
    c2.metric("Cotas", f"{ul['cotas_emitidas']:,.0f}" if ul.get("cotas_emitidas") else "n/d")
    c3.metric("VP/Cota", f"R$ {ul['vp_por_cota']:,.2f}" if ul.get("vp_por_cota") else "n/d")

    if alav["indice"] is not None:
        st.metric("Ativo / PL", f"{alav['indice']:.2f}x",
                  delta=f"Ativo: R$ {alav['ativo_total'] / 1e6:,.1f} mi" if alav["ativo_total"] else None)
        if alav["alavancado"]:
            st.warning(f"Fundo possivelmente alavancado (Ativo/PL = {alav['indice']:.2f}x)")
        else:
            st.success(f"Sem alavancagem significativa (Ativo/PL = {alav['indice']:.2f}x)")
    elif alav["patrimonio_liquido"] is not None:
        st.caption("Ativo total nao disponivel — impossivel calcular alavancagem")


def render_risco_retorno(ticker: str, *, key_prefix: str = "fund") -> None:
    """Risco e Retorno: snapshot recente; fallback ao vivo se snapshot indisponível."""
    with get_session_ctx() as session:
        rm = load_risk_metrics_snapshot(ticker, session)

    if rm:
        _render_risco_from_snapshot(rm)
        st.caption("Fonte: snapshot diario mais recente (status=ready).")
        return

    # Fallback: calcular ao vivo
    st.caption("Snapshot nao disponivel — calculando ao vivo...")
    with get_session_ctx() as session:
        vol = beta = mdd = liq = ret12 = dy3m = None
        for fn, attr in [
            (volatilidade_anualizada, "vol"),
            (beta_vs_ifix, "beta"),
            (max_drawdown, "mdd"),
            (liquidez_media_21d, "liq"),
            (retorno_total_12m, "ret12"),
            (rm_dy_3m_anualizado, "dy3m"),
        ]:
            try:
                val = fn(ticker, session=session)
                locals()[attr]  # touch to avoid lint; assign below
            except Exception:
                val = None
            if attr == "vol": vol = val
            elif attr == "beta": beta = val
            elif attr == "mdd": mdd = val
            elif attr == "liq": liq = val
            elif attr == "ret12": ret12 = val
            elif attr == "dy3m": dy3m = val

    c1, c2, c3 = st.columns(3)
    c1.metric("Volatilidade Anual", format_pct(vol) if vol is not None else "n/d",
              help="Desvio padrao anualizado dos log-retornos diarios (252d)")
    c2.metric("Beta vs IFIX", f"{beta:.2f}" if beta is not None else "n/d",
              help="Cov(FII, IFIX) / Var(IFIX) nos ultimos 252 pregoes.")
    c3.metric("Max Drawdown", format_pct(mdd) if mdd is not None else "n/d",
              help="Maior queda pico-a-vale nos ultimos 504 pregoes (preco ajustado)")
    c4, c5, c6 = st.columns(3)
    liq_fmt = (f"R$ {liq / 1e6:,.1f} mi" if liq is not None and liq >= 1e6
               else f"R$ {liq / 1e3:,.0f} k" if liq is not None and liq >= 1e3
               else f"R$ {liq:,.0f}" if liq is not None else "n/d")
    c4.metric("Liquidez Media 21d", liq_fmt,
              help="Volume financeiro medio diario dos ultimos 21 pregoes")
    c5.metric("Retorno Total 12m", format_pct(ret12) if ret12 is not None else "n/d",
              help="(P_hoje - P_252 + dividendos_12m) / P_252")
    c6.metric("DY 3m Anualizado", format_pct(dy3m) if dy3m is not None else "n/d",
              help="Soma de dividendos dos ultimos 63 pregoes x 4 / preco atual")

    if all(v is None for v in [vol, beta, mdd, liq, ret12, dy3m]):
        st.info("Sem dados de preco suficientes para calcular metricas de risco (minimo 63 pregoes).")


def _render_risco_from_snapshot(rm: dict) -> None:
    """Helper interno: exibe métricas de risco a partir de um dict de snapshot."""
    c1, c2, c3 = st.columns(3)
    vol = rm.get("volatilidade_anual")
    c1.metric("Volatilidade Anual", f"{vol:.1%}" if vol is not None else "n/d",
              help="Desvio padrao dos log-retornos diarios anualizado (sqrt(252)). Ultimos 252 pregoes.")
    beta = rm.get("beta_ifix")
    c2.metric("Beta vs IFIX", f"{beta:.2f}" if beta is not None else "n/d",
              help="Cov(R_FII, R_IFIX) / Var(R_IFIX). Requer dados IFIX no banco (benchmark_diario).")
    mdd = rm.get("max_drawdown")
    c3.metric("Max Drawdown (2a)", f"{mdd:.1%}" if mdd is not None else "n/d",
              help="Maior queda pico-a-vale nos ultimos 504 pregoes (fechamento ajustado).")

    c4, c5, c6 = st.columns(3)
    liq = rm.get("liquidez_21d_brl")
    liq_fmt = f"R$ {liq / 1e6:.1f} mi" if liq is not None and liq >= 1e6 else \
              f"R$ {liq / 1e3:.0f} k" if liq is not None else "n/d"
    c4.metric("Liquidez Media 21d", liq_fmt,
              help="Media do volume financeiro diario (fechamento x volume) nos ultimos 21 pregoes.")
    ret12 = rm.get("retorno_total_12m")
    c5.metric("Retorno Total 12m", f"{ret12:+.1%}" if ret12 is not None else "n/d",
              help="(P_hoje - P_252 + dividendos_12m) / P_252. Retorno total incluindo proventos.")
    dy3m = rm.get("dy_3m_anualizado")
    c6.metric("DY 3m Anualizado", f"{dy3m:.1%}" if dy3m is not None else "n/d",
              help="Soma de dividendos dos ultimos 63 pregoes x 4, dividida pelo preco atual.")


# ---------------------------------------------------------------------------
# Wrapper completo (compatibilidade com 7_Fundamentos.py)
# ---------------------------------------------------------------------------

def render(ticker: str, *, key_prefix: str = "fund") -> None:
    """Renderiza fundamentos do ticker (sem header/selectbox/footer).

    Mantido para compatibilidade retroativa com 7_Fundamentos.py.
    O Dossiê usa as funções de seção individuais diretamente.
    """
    with get_session_ctx() as session:
        info = get_info_ticker(ticker, session)
        if info:
            st.caption(
                f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
                f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}"
            )

    st.markdown("---")

    tab_dist, tab_pl, tab_dy, tab_pvp, tab_risco = st.tabs(
        ["Distribuicao vs Geracao", "PL e Cotas", "DY Historico", "P/VP Historico", "Risco e Retorno"]
    )

    with tab_dist:
        st.subheader("Distribuicao vs Geracao")
        render_distribuicao_vs_geracao(ticker, key_prefix=f"{key_prefix}_dist")

    with tab_dy:
        st.subheader("DY Historico")
        render_dy_historico(ticker, key_prefix=f"{key_prefix}_dy")

    with tab_pvp:
        st.subheader("P/VP Historico")
        render_pvp_historico(ticker, key_prefix=f"{key_prefix}_pvp")

    with tab_pl:
        st.subheader("PL e Cotas")
        render_pl_cotas(ticker, key_prefix=f"{key_prefix}_pl")

    with tab_risco:
        st.subheader("Risco e Retorno")
        render_risco_retorno(ticker, key_prefix=f"{key_prefix}_risco")
