"""Conteudo de Fundamentos renderizavel sem decorators ou page_config."""
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


def render(ticker: str, *, key_prefix: str = "fund") -> None:
    """Renderiza fundamentos do ticker (sem header/selectbox/footer)."""
    with get_session_ctx() as session:
        info = get_info_ticker(ticker, session)
        if info:
            st.caption(f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
                       f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}")

    st.markdown("---")

    tab_dist, tab_pl, tab_dy, tab_pvp, tab_risco = st.tabs(
        ["Distribuicao vs Geracao", "PL e Cotas", "DY Historico", "P/VP Historico", "Risco e Retorno"]
    )

    with tab_dist:
        with get_session_ctx() as session:
            st.header("1. Distribuicao vs Geracao")

            payout_df, consec = get_payout_historico(ticker, session=session)

            if not payout_df.empty:
                fig_payout = make_subplots(rows=1, cols=1)
                fig_payout.add_trace(go.Bar(
                    x=payout_df["data_referencia"],
                    y=payout_df["rentab_efetiva_pct"],
                    name="Rent. Efetiva %",
                    marker_color="#636efa",
                ))
                fig_payout.add_trace(go.Bar(
                    x=payout_df["data_referencia"],
                    y=payout_df["rentab_patrimonial_pct"],
                    name="Rent. Patrimonial %",
                    marker_color="#ef553b",
                ))

                alert_dates = payout_df[payout_df["distribuindo_mais_que_gera"]]["data_referencia"].tolist()
                if alert_dates:
                    fig_payout.add_trace(go.Bar(
                        x=alert_dates,
                        y=[0] * len(alert_dates),
                        name="Efetiva > Patrimonial",
                        marker_color="rgba(255,0,0,0.3)",
                        showlegend=True,
                    ))

                fig_payout.update_layout(
                    title=f"{ticker} — Rentabilidade Efetiva vs Patrimonial (24 meses)",
                    xaxis_title="Mes", yaxis_title="% mes",
                    template="plotly_white", height=400, barmode="group",
                )
                st.plotly_chart(fig_payout, use_container_width=True)

                resumo = get_efetiva_vs_patrimonial_resumo(ticker, session=session)
                nivel, msg = classificar_alerta_distribuicao(resumo)
                if nivel == "error":
                    st.error(msg)
                elif nivel == "warning":
                    st.warning(msg)
                else:
                    st.success(msg)
            else:
                st.info("Sem dados de rentabilidade disponiveis.")

    with tab_dy:
        with get_session_ctx() as session:
            st.header("2. DY Historico")

            dy_data = get_dy_medias(ticker, session=session)

            col_dy1, col_dy2, col_dy3, col_dy4 = st.columns(4)
            col_dy1.metric("DY 12m Atual", format_pct(dy_data["dy_12m_atual"]) if dy_data["dy_12m_atual"] else "n/d")
            col_dy2.metric("DY 24m", format_pct(dy_data["media_dy_2anos"]) if dy_data["media_dy_2anos"] else "n/d")
            col_dy3.metric("DY 60m", format_pct(dy_data["media_dy_5anos"]) if dy_data["media_dy_5anos"] else "n/d")
            col_dy4.metric("Percentil na Serie",
                           f"{dy_data['percentil_na_serie_completa']:.1f}%" if dy_data["percentil_na_serie_completa"] is not None else "n/d")

    with tab_pvp:
        with get_session_ctx() as session:
            st.header("3. P/VP Historico")

            pvp_data = get_pvp_medias(ticker, session=session)

            col_pvp1, col_pvp2, col_pvp3 = st.columns(3)
            col_pvp1.metric("P/VP Atual", format_number(pvp_data["pvp_atual"], 2) if pvp_data["pvp_atual"] else "n/d")
            col_pvp2.metric("Media 2 anos", format_number(pvp_data["media_pvp_2anos"], 2) if pvp_data["media_pvp_2anos"] else "n/d")
            col_pvp3.metric("Media 5 anos", format_number(pvp_data["media_pvp_5anos"], 2) if pvp_data["media_pvp_5anos"] else "n/d")

            serie_pvp = pvp_data.get("serie_pvp")
            if serie_pvp is not None and len(serie_pvp) > 0:
                periodo_pvp = st.radio(
                    "Periodo P/VP",
                    ["YTD", "12m", "3a", "Tudo"],
                    index=1, horizontal=True,
                    key=f"{key_prefix}_radio_pvp_periodo",
                )

                hoje = date.today()
                if periodo_pvp == "YTD":
                    data_min = date(hoje.year, 1, 1)
                elif periodo_pvp == "12m":
                    data_min = hoje - relativedelta(years=1)
                elif periodo_pvp == "3a":
                    data_min = hoje - relativedelta(years=3)
                else:
                    data_min = None

                if data_min is not None:
                    serie_pvp_plot = serie_pvp[serie_pvp.index >= data_min]
                else:
                    serie_pvp_plot = serie_pvp

                fig_pvp = go.Figure()
                fig_pvp.add_trace(go.Scatter(
                    x=serie_pvp_plot.index, y=serie_pvp_plot.values,
                    mode="lines", name="P/VP", line=dict(color="#1f77b4"),
                ))

                if pvp_data["media_pvp_2anos"] is not None:
                    fig_pvp.add_hline(
                        y=pvp_data["media_pvp_2anos"], line_dash="dash", line_color="orange",
                        annotation_text=f"Media 2a: {pvp_data['media_pvp_2anos']:.2f}",
                    )
                if pvp_data["media_pvp_5anos"] is not None:
                    fig_pvp.add_hline(
                        y=pvp_data["media_pvp_5anos"], line_dash="dot", line_color="green",
                        annotation_text=f"Media 5a: {pvp_data['media_pvp_5anos']:.2f}",
                    )

                fig_pvp.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="P/VP = 1.0")
                fig_pvp.update_layout(
                    title=f"{ticker} — P/VP Historico",
                    xaxis_title="Data", yaxis_title="P/VP",
                    template="plotly_white", height=400,
                )
                st.plotly_chart(fig_pvp, use_container_width=True)
            else:
                st.info("Sem serie historica de P/VP disponivel.")

    with tab_risco:
        with get_session_ctx() as session:
            rm = load_risk_metrics_snapshot(ticker, session)

        st.header("Risco e Retorno")

        if not rm:
            st.info("Metricas de risco nao disponiveis. Execute o snapshot diario primeiro.")
        else:
            col_r1, col_r2, col_r3 = st.columns(3)

            vol = rm.get("volatilidade_anual")
            col_r1.metric(
                "Volatilidade Anual",
                f"{vol:.1%}" if vol is not None else "n/d",
                help="Desvio padrao dos log-retornos diarios anualizado (sqrt(252)). Ultimos 252 pregoes.",
            )

            beta = rm.get("beta_ifix")
            col_r2.metric(
                "Beta vs IFIX",
                f"{beta:.2f}" if beta is not None else "n/d",
                help="Cov(R_FII, R_IFIX) / Var(R_IFIX). Requer dados IFIX no banco (benchmark_diario).",
            )

            mdd = rm.get("max_drawdown")
            col_r3.metric(
                "Max Drawdown (2a)",
                f"{mdd:.1%}" if mdd is not None else "n/d",
                help="Maior queda pico-a-vale nos ultimos 504 pregoes (fechamento ajustado).",
            )

            col_r4, col_r5, col_r6 = st.columns(3)

            liq = rm.get("liquidez_21d_brl")
            if liq is not None:
                liq_fmt = f"R$ {liq / 1e6:.1f} mi" if liq >= 1e6 else f"R$ {liq / 1e3:.0f} k"
            else:
                liq_fmt = "n/d"
            col_r4.metric(
                "Liquidez Media 21d",
                liq_fmt,
                help="Media do volume financeiro diario (fechamento x volume) nos ultimos 21 pregoes.",
            )

            ret12 = rm.get("retorno_total_12m")
            col_r5.metric(
                "Retorno Total 12m",
                f"{ret12:+.1%}" if ret12 is not None else "n/d",
                help="(P_hoje - P_252 + dividendos_12m) / P_252. Retorno total incluindo proventos.",
            )

            dy3m = rm.get("dy_3m_anualizado")
            col_r6.metric(
                "DY 3m Anualizado",
                f"{dy3m:.1%}" if dy3m is not None else "n/d",
                help="Soma de dividendos dos ultimos 63 pregoes x 4, dividida pelo preco atual.",
            )

            st.caption("Fonte: snapshot diario mais recente (status=ready). Calculos sobre precos ajustados yfinance.")

    with tab_pl:
        with get_session_ctx() as session:
            st.header("4. PL e Cotas")

            pl_df = get_pl_cotas_historico(ticker, meses=36, session=session)

            if not pl_df.empty:
                fig_pl = make_subplots(specs=[[{"secondary_y": True}]])

                fig_pl.add_trace(go.Bar(
                    x=pl_df["data_referencia"],
                    y=pl_df["patrimonio_liq"] / 1e6,
                    name="PL (mi)",
                    marker_color="#636efa",
                ), secondary_y=False)

                fig_pl.add_trace(go.Scatter(
                    x=pl_df["data_referencia"],
                    y=pl_df["cotas_emitidas"],
                    mode="lines+markers",
                    name="Cotas Emitidas",
                    line=dict(color="#ef553b"),
                ), secondary_y=True)

                fig_pl.update_layout(
                    title=f"{ticker} — Patrimonio Liquido e Cotas (36 meses)",
                    template="plotly_white", height=400,
                )
                fig_pl.update_yaxes(title_text="PL (R$ milhoes)", secondary_y=False)
                fig_pl.update_yaxes(title_text="Cotas Emitidas", secondary_y=True)
                st.plotly_chart(fig_pl, use_container_width=True)

                col_pl1, col_pl2, col_pl3 = st.columns(3)
                ultimo_pl = pl_df.iloc[-1]
                col_pl1.metric("PL Atual", f"R$ {ultimo_pl['patrimonio_liq'] / 1e6:,.1f} mi" if ultimo_pl.get("patrimonio_liq") else "n/d")
                col_pl2.metric("Cotas", f"{ultimo_pl['cotas_emitidas']:,.0f}" if ultimo_pl.get("cotas_emitidas") else "n/d")
                col_pl3.metric("VP/Cota", f"R$ {ultimo_pl['vp_por_cota']:,.2f}" if ultimo_pl.get("vp_por_cota") else "n/d")

                alav = get_alavancagem(ticker, session=session)
                if alav["indice"] is not None:
                    st.metric("Ativo / PL", f"{alav['indice']:.2f}x",
                              delta=f"Ativo: R$ {alav['ativo_total'] / 1e6:,.1f} mi" if alav["ativo_total"] else None)
                    if alav["alavancado"]:
                        st.warning(f"Fundo possivelmente alavancado (Ativo/PL = {alav['indice']:.2f}x)")
                    else:
                        st.success(f"Sem alavancagem significativa (Ativo/PL = {alav['indice']:.2f}x)")
                elif alav["patrimonio_liquido"] is not None:
                    st.caption("Ativo total nao disponivel — impossivel calcular alavancagem")
            else:
                st.info("Sem dados de PL e cotas disponiveis.")

    with tab_risco:
        with get_session_ctx() as session:
            st.header("5. Risco e Retorno")

            vol = None
            beta = None
            mdd = None
            liq = None
            ret12 = None
            dy3m = None
            try:
                vol = volatilidade_anualizada(ticker, session=session)
            except Exception:
                pass
            try:
                beta = beta_vs_ifix(ticker, session=session)
            except Exception:
                pass
            try:
                mdd = max_drawdown(ticker, session=session)
            except Exception:
                pass
            try:
                liq = liquidez_media_21d(ticker, session=session)
            except Exception:
                pass
            try:
                ret12 = retorno_total_12m(ticker, session=session)
            except Exception:
                pass
            try:
                dy3m = rm_dy_3m_anualizado(ticker, session=session)
            except Exception:
                pass

            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric(
                "Volatilidade Anual",
                format_pct(vol) if vol is not None else "n/d",
                help="Desvio padrao anualizado dos log-retornos diarios (252d)",
            )
            col_r2.metric(
                "Beta vs IFIX",
                f"{beta:.2f}" if beta is not None else "n/d",
                help="Cov(FII, IFIX) / Var(IFIX) nos ultimos 252 pregoes. n/d se IFIX sem dados.",
            )
            col_r3.metric(
                "Max Drawdown",
                format_pct(mdd) if mdd is not None else "n/d",
                help="Maior queda pico-a-vale nos ultimos 504 pregoes (preco ajustado)",
            )

            col_r4, col_r5, col_r6 = st.columns(3)
            col_r4.metric(
                "Liquidez Media 21d",
                f"R$ {liq / 1e6:,.1f} mi" if liq is not None and liq >= 1e6
                else (f"R$ {liq / 1e3:,.0f} k" if liq is not None and liq >= 1e3
                      else (f"R$ {liq:,.0f}" if liq is not None else "n/d")),
                help="Volume financeiro medio diario (fechamento x volume) dos ultimos 21 pregoes",
            )
            col_r5.metric(
                "Retorno Total 12m",
                format_pct(ret12) if ret12 is not None else "n/d",
                help="(P_hoje - P_252 + dividendos_12m) / P_252",
            )
            col_r6.metric(
                "DY 3m Anualizado",
                format_pct(dy3m) if dy3m is not None else "n/d",
                help="Soma de dividendos dos ultimos 63 pregoes x 4 / preco atual",
            )

            if all(v is None for v in [vol, beta, mdd, liq, ret12, dy3m]):
                st.info("Sem dados de preco suficientes para calcular metricas de risco (minimo 63 pregoes).")
