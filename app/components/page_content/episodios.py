"""Conteudo de Episodios renderizavel sem decorators ou page_config."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.carteira_ui import load_tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.models.episodes import get_pvp_series, identify_episodes
from src.fii_analysis.models.trade_simulator import simulate_buy_and_hold, simulate_cdi_only, simulate_trades
from src.fii_analysis.models.walk_forward_rolling import _load_cdi_series, _load_dividend_series

STRATEGY_COLOR = "#2ca02c"
HOLD_COLOR = "#7f7f7f"
CDI_COLOR = "#1f77b4"
SIMULATION_INFO = """
**Premissas da Simulação Operacional**
- Capital fora da posição rende 100% do CDI.
- Compras usam preço bruto no fechamento do dia do sinal.
- Vendas ocorrem apenas no sinal de SELL; sem SELL, a posição permanece aberta e o valor final fica marcado a mercado.
- Dividendos entram como caixa separado com elegibilidade na `data_com` e crédito no pregão seguinte como proxy, porque o banco não guarda `data_pagamento`.
"""


def render(*, key_prefix: str = "ep") -> None:
    """Renderiza analise de episodios (sem header/footer)."""
    st.caption(
        "Identifica momentos em que o P/VP entrou em territorio extremo "
        "(percentil rolling) e rastreia o retorno forward. "
        "Cada episodio e independente (thinning por intervalo minimo). "
        "Sem OR de multiplas condicoes — so P/VP percentil."
    )

    tickers = load_tickers_ativos()
    ticker = st.selectbox("Ticker", tickers, key=f"{key_prefix}_ticker")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pvp_low = st.selectbox("BUY quando P/VP pct <=", [5, 10, 15, 20], index=1, key=f"{key_prefix}_pvp_low")
    with col2:
        pvp_high = st.selectbox("SELL quando P/VP pct >=", [80, 85, 90, 95], index=2, key=f"{key_prefix}_pvp_high")
    with col3:
        fwd = st.selectbox("Forward (pregoes)", [10, 20, 30, 60], index=2, key=f"{key_prefix}_fwd")
    with col4:
        min_gap_options = [10, 20, 30, 40, 60]
        default_gap_idx = next(
            (i for i, v in enumerate(min_gap_options) if v >= fwd),
            len(min_gap_options) - 1,
        )
        min_gap_raw = st.selectbox("Gap minimo (pregoes)", min_gap_options, index=default_gap_idx, key=f"{key_prefix}_gap")
        min_gap = max(min_gap_raw, fwd)
        if min_gap_raw < fwd:
            st.warning(f"Gap ajustado para {fwd} (= forward_days). Gap < forward_days viola independencia.")

    run_key = f"ep_{ticker}_{pvp_low}_{pvp_high}_{fwd}_{min_gap}"

    if st.button("Identificar Episodios", type="primary", key=f"{key_prefix}_run"):
        with get_session_ctx() as session:
            df = get_pvp_series(ticker, session)
            if df.empty:
                st.error("Dados insuficientes.")
                return

            result = identify_episodes(df, pvp_low, pvp_high, fwd, min_gap)
            st.session_state[run_key] = {"result": result, "df": df}

    if run_key not in st.session_state:
        return

    data = st.session_state[run_key]
    result = data["result"]
    df = data["df"]
    buy_df = result["buy"]
    sell_df = result["sell"]
    summary = result["summary"]

    tab_sim, tab_res = st.tabs(["Simulação Operacional", "Resultados Estatísticos"])

    with tab_res:
        st.subheader("Resumo")
        s_buy = summary["buy"]
        s_sell = summary["sell"]

        col_b, col_s = st.columns(2)

        with col_b:
            st.markdown("### BUY Episodes (P/VP baixo)")
            if s_buy["n"] == 0:
                st.info("Nenhum episodio BUY encontrado.")
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Episodios", s_buy["n"])
                c2.metric("Retorno Medio", f"{s_buy['mean']*100:+.2f}%")
                c3.metric("Mediana", f"{s_buy['median']*100:+.2f}%")
                c4.metric("Win Rate", f"{s_buy['win_rate']:.0%}" if s_buy["win_rate"] is not None else "n/d")

                if s_buy["ci_lower"] is not None:
                    st.caption(f"IC 95%: [{s_buy['ci_lower']*100:+.2f}%, {s_buy['ci_upper']*100:+.2f}%]")
                if s_buy.get("p_value") is not None:
                    sig = "SIGNIFICATIVO" if s_buy["p_value"] < 0.05 else "NAO SIGNIFICATIVO"
                    st.caption(f"t-test H0:ret=0: t={s_buy['t_stat']:.2f}, p={s_buy['p_value']:.3f} — {sig}")

        with col_s:
            st.markdown("### SELL Episodes (P/VP alto)")
            if s_sell["n"] == 0:
                st.info("Nenhum episodio SELL encontrado.")
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Episodios", s_sell["n"])
                c2.metric("Retorno Medio", f"{s_sell['mean']*100:+.2f}%")
                c3.metric("Mediana", f"{s_sell['median']*100:+.2f}%")
                c4.metric("Win Rate", f"{s_sell['win_rate']:.0%}" if s_sell["win_rate"] is not None else "n/d")

                if s_sell["ci_lower"] is not None:
                    st.caption(f"IC 95%: [{s_sell['ci_lower']*100:+.2f}%, {s_sell['ci_upper']*100:+.2f}%]")
                if s_sell.get("p_value") is not None:
                    sig = "SIGNIFICATIVO" if s_sell["p_value"] < 0.05 else "NAO SIGNIFICATIVO"
                    st.caption(f"t-test H0:ret=0: t={s_sell['t_stat']:.2f}, p={s_sell['p_value']:.3f} — {sig}")

        comp = summary.get("comparison")
        if comp:
            st.markdown("---")
            st.subheader("BUY vs SELL")
            c1, c2, c3 = st.columns(3)
            c1.metric("Spread (BUY - SELL)", f"{comp['buy_minus_sell']*100:+.2f}%")
            if comp["mw_pvalue"] is not None:
                sig = "SIGNIFICATIVO" if comp["mw_pvalue"] < 0.05 else "NAO SIGNIFICATIVO"
                c2.metric("Mann-Whitney p", f"{comp['mw_pvalue']:.3f}")
                c3.metric("Resultado", sig)

        st.markdown("---")
        st.subheader("Serie P/VP com Episodios")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["data"], y=df["pvp"], mode="lines", name="P/VP",
            line=dict(color="#1f77b4", width=1),
        ))
        fig.add_hline(y=1.0, line_dash="dash", line_color="gray", annotation_text="P/VP = 1.0")

        if not buy_df.empty:
            fig.add_trace(go.Scatter(
                x=buy_df["data"], y=buy_df["pvp"], mode="markers", name="BUY",
                marker=dict(color="green", size=10, symbol="triangle-up"),
            ))
        if not sell_df.empty:
            fig.add_trace(go.Scatter(
                x=sell_df["data"], y=sell_df["pvp"], mode="markers", name="SELL",
                marker=dict(color="red", size=10, symbol="triangle-down"),
            ))

        fig.update_layout(
            title=f"{ticker} — P/VP Historico com Episodios",
            xaxis_title="Data", yaxis_title="P/VP",
            template="plotly_white", height=500,
        )
        fig.update_xaxes(type="date", tickformat="%m/%y")
        st.plotly_chart(fig, use_container_width=True)

        if not buy_df.empty:
            with st.expander("Detalhes BUY"):
                st.dataframe(buy_df.style.format({"fwd_ret": "{:+.3%}", "pvp": "{:.4f}", "pvp_pct": "{:.1f}%"}),
                             use_container_width=True)

        if not sell_df.empty:
            with st.expander("Detalhes SELL"):
                st.dataframe(sell_df.style.format({"fwd_ret": "{:+.3%}", "pvp": "{:.4f}", "pvp_pct": "{:.1f}%"}),
                             use_container_width=True)

        if not buy_df.empty or not sell_df.empty:
            st.subheader("Distribuicao de Retornos Forward")
            fig_dist = go.Figure()
            if not buy_df.empty:
                fig_dist.add_trace(go.Histogram(x=buy_df["fwd_ret"] * 100, name="BUY", marker_color="green", opacity=0.7))
            if not sell_df.empty:
                fig_dist.add_trace(go.Histogram(x=sell_df["fwd_ret"] * 100, name="SELL", marker_color="red", opacity=0.7))
            fig_dist.add_vline(x=0, line_dash="dash", line_color="gray")
            fig_dist.update_layout(
                title="Distribuicao de Retornos Forward por Tipo",
                xaxis_title="Retorno (%)", yaxis_title="Count",
                template="plotly_white", height=350, barmode="overlay",
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        st.markdown("---")
        st.caption("""
        **Metodologia:** Cada episodio e independente (intervalo minimo entre episodios = gap configurado).
        Retorno forward e fixo (buy-and-hold pela janela). P/VP percentil calculado com rolling window de 504 pregões.
        Nao modela custos de transacao, slippage, ou IR.
        """)

    with tab_sim:
        with get_session_ctx() as session:
            start_date = df["data"].min()
            end_date = df["data"].max()
            cdi_df = _load_cdi_series(session, start_date, end_date)
            div_df = _load_dividend_series(ticker, session, start_date, end_date)

        sim_df = df[["data", "fechamento", "pvp"]].copy()
        sim_df = sim_df.rename(columns={"fechamento": "preco"})
        sim_df["trade_idx"] = np.arange(len(sim_df))
        sim_df["signal"] = "NEUTRO"

        if not buy_df.empty:
            action_map = {idx: set() for idx in sim_df.index}
            buy_dates = set(pd.Timestamp(d) for d in buy_df["data"])
            for idx, row in sim_df.iterrows():
                if pd.Timestamp(row["data"]) in buy_dates:
                    action_map[idx].add("BUY")
                    s_idx = idx + fwd
                    if s_idx < len(sim_df):
                        action_map[s_idx].add("SELL")

            for idx, actions in action_map.items():
                if actions == {"BUY", "SELL"}:
                    sim_df.loc[idx, "signal"] = "SELL_BUY"
                elif actions == {"BUY"}:
                    sim_df.loc[idx, "signal"] = "BUY"
                elif actions == {"SELL"}:
                    sim_df.loc[idx, "signal"] = "SELL"

        sim_result = simulate_trades(sim_df, "BUY", fwd, cdi_df, div_df)
        bh_result = simulate_buy_and_hold(
            sim_df,
            sim_df["data"].tolist(),
            start_date=start_date,
            cdi_df=cdi_df,
            div_df=div_df,
        )

        cdi_result = simulate_cdi_only(sim_df[["data", "preco"]], cdi_df, valuation_dates=sim_df["data"].tolist(), start_date=start_date)

        ret_strategy = float(sim_result["cumulative"][-1]) if sim_result.get("cumulative") else float(sim_result.get("final", 0.0))
        ret_hold = float(bh_result["cumulative"][-1]) if bh_result.get("cumulative") else float(bh_result.get("final", 0.0))
        alpha = (ret_strategy - ret_hold) * 100

        c1, c2, c3 = st.columns(3)
        c1.metric("Retorno Estratégia", f"{ret_strategy*100:+.2f}%")
        c2.metric("Retorno Buy & Hold", f"{ret_hold*100:+.2f}%")
        c3.metric("Excesso (Alpha)", f"{alpha:+.2f}%", delta=f"{alpha:+.2f}%")

        st.info(SIMULATION_INFO)

        st.subheader("Curva de Capital")

        fig_sim = go.Figure()

        if sim_result["dates"]:
            fig_sim.add_trace(go.Scatter(
                x=sim_result["dates"],
                y=[x * 100 for x in sim_result["cumulative"]],
                mode="lines",
                name="Estratégia",
                line=dict(color=STRATEGY_COLOR, width=3)
            ))

        if bh_result["dates"]:
            fig_sim.add_trace(go.Scatter(
                x=bh_result["dates"],
                y=[x * 100 for x in bh_result["cumulative"]],
                mode="lines",
                name="Buy & Hold",
                line=dict(color=HOLD_COLOR, dash="dash", width=2)
            ))

        if cdi_result["dates"]:
            fig_sim.add_trace(go.Scatter(
                x=cdi_result["dates"],
                y=[x * 100 for x in cdi_result["cumulative"]],
                mode="lines",
                name="CDI 100%",
                line=dict(color=CDI_COLOR, width=1, dash="dash")
            ))

        fig_sim.update_layout(
            title=f"{ticker} — Evolução Patrimonial (Base = 0%)",
            xaxis_title="Data",
            yaxis_title="Retorno Acumulado (%)",
            template="plotly_white",
            height=500,
            hovermode="x unified",
        )
        st.plotly_chart(fig_sim, use_container_width=True)

        if sim_result.get("open_position"):
            st.warning(
                f"Ha uma posicao aberta desde {sim_result['open_entry_date'].date() if hasattr(sim_result.get('open_entry_date'), 'date') else sim_result.get('open_entry_date')} "
                "porque nao houve pregões suficientes para emitir o SELL programado em D+forward."
            )

        if sim_result["trades"]:
            trades_df = pd.DataFrame(sim_result["trades"])
            with st.expander("Histórico de Operações da Simulação"):
                show_df = trades_df.copy()
                show_df["preco_entrada"] = show_df["preco_entrada"].map(lambda x: f"{x:.2f}")
                show_df["preco_saida"] = show_df["preco_saida"].map(lambda x: f"{x:.2f}")
                show_df["dividendos_trade"] = show_df["dividendos_trade"].map(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "0.00%")
                show_df["capital_apos_trade"] = show_df["capital_apos_trade"].map(lambda x: f"{x:.4f}x" if pd.notna(x) else "n/d")
                for col in ["ret", "ret_preco", "cum_ret"]:
                    if col in show_df.columns:
                        show_df[col] = show_df[col].map(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "n/d")
                st.dataframe(show_df, use_container_width=True, hide_index=True)
