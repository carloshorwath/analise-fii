"""Conteudo de Walk-Forward renderizavel sem decorators ou page_config."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.carteira_ui import load_tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.models.walk_forward_rolling import walk_forward_roll

WALK_FORWARD_RESULT_VERSION = "buy_sell_dividends_cdi_v6"
STRATEGY_COLOR = "#2ca02c"
HOLD_COLOR = "#7f7f7f"
SELL_COLOR = "#b42318"
SIMULATION_INFO = """
**Premissas da Simulação Operacional**
- Capital fora da posição rende 100% do CDI.
- Compras usam preço bruto no fechamento do dia do sinal.
- Vendas ocorrem apenas no sinal de SELL; sem SELL, a posição permanece aberta e o valor final fica marcado a mercado.
- Dividendos entram como caixa separado com elegibilidade na `data_com` e crédito no pregão seguinte como proxy, porque o banco não guarda `data_pagamento`.
"""


def render(*, key_prefix: str = "wf") -> None:
    """Renderiza walk-forward (sem header/footer)."""
    st.caption(
        "Validacao out-of-sample genuina: treina em janela rolante, "
        "prediz o periodo seguinte, avanca. Cada previsao usa somente "
        "dados passados. Nao ha selecao de parametros viciada."
    )

    tickers = load_tickers_ativos()
    ticker = st.selectbox("Ticker", tickers, key=f"{key_prefix}_ticker")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        train_m = st.selectbox("Treino (meses)", [6, 12, 18, 24], index=2, key=f"{key_prefix}_train")
    with col2:
        pred_m = st.selectbox("Predicao (meses)", [1, 2, 3], index=0, key=f"{key_prefix}_pred")
    with col3:
        buy_pct = st.selectbox("BUY P/VP percentil <", [5, 10, 15, 20], index=2, key=f"{key_prefix}_buy")
    with col4:
        sell_pct = st.selectbox("SELL P/VP percentil >", [80, 85, 90, 95], index=1, key=f"{key_prefix}_sell")

    run_key = f"wf_{WALK_FORWARD_RESULT_VERSION}_{ticker}_{train_m}_{pred_m}_{buy_pct}_{sell_pct}"

    if st.button("Rodar Walk-Forward", type="primary", key=f"{key_prefix}_run"):
        with st.spinner("Executando walk-forward..."):
            with get_session_ctx() as session:
                result = walk_forward_roll(ticker, session, train_m, pred_m, buy_pct, sell_pct)
                if "error" in result:
                    st.error(result["error"])
                    return
                st.session_state[run_key] = result

    if run_key not in st.session_state:
        return

    result = st.session_state[run_key]
    signals_df = result["signals"]
    summary = result["summary"]
    comparison = result["comparison"]
    cumulative = result["cumulative"]
    params = result["params"]
    follow_buy = cumulative["follow_buy"]
    hold = cumulative["hold"]

    st.caption(
        f"Treino: {params['train_months']}m | Predicao: {params['predict_months']}m | "
        f"BUY: P/VP < p{params['pvp_pct_buy']} | SELL: P/VP > p{params['pvp_pct_sell']} | "
        f"Forward: {params['forward_days']}d | Steps: {result['n_steps']}"
    )

    # ── Sinal Atual (extrapolado) ─────────────────────────────────────────────
    sinal_hoje = result.get("sinal_hoje", {})
    if sinal_hoje and sinal_hoje.get("sinal") != "INDISPONIVEL":
        sinal = sinal_hoje["sinal"]
        pvp_v = sinal_hoje.get("pvp_atual")
        pvp_p = sinal_hoje.get("pvp_pct_atual")
        thr_b = sinal_hoje.get("threshold_buy")
        thr_s = sinal_hoje.get("threshold_sell")
        ult_oos = sinal_hoje.get("data_ultimo_sinal_oos", "?")
        cores = {"BUY": "#2e7d32", "SELL": "#c62828", "NEUTRO": "#e65100"}
        cor = cores.get(sinal, "#555")
        st.markdown(
            f"**Sinal atual (extrapolado):** "
            f"<span style='color:{cor};font-weight:800;font-size:1.1em'>{sinal}</span> &nbsp;·&nbsp; "
            f"P/VP = {pvp_v:.4f}" + (f" (p{pvp_p:.0f}%)" if pvp_p is not None else "") +
            (f" &nbsp;·&nbsp; Limiar BUY < {thr_b:.4f} · SELL > {thr_s:.4f}" if thr_b is not None else "") +
            f"<br><small style='color:#888'>Último sinal OOS: {ult_oos} · Extrapolado, sem retorno futuro validado</small>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

    tab_sim, tab_oos = st.tabs(["Simulação Operacional", "Validade Estatística"])

    with tab_oos:
        _render_oos_tab(signals_df, summary, comparison, ticker)

    with tab_sim:
        _render_simulation_tab(ticker, follow_buy, hold)


def _render_oos_tab(signals_df, summary, comparison, ticker):
    st.subheader("Distribuicao dos Sinais")
    signal_counts = signals_df["signal"].value_counts()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de sinais", len(signals_df))
    c2.metric("BUY", signal_counts.get("BUY", 0))
    c3.metric("SELL", signal_counts.get("SELL", 0))
    c4.metric("NEUTRO", signal_counts.get("NEUTRO", 0))

    st.markdown("---")
    col_b, col_s = st.columns(2)

    with col_b:
        st.markdown("### BUY (out-of-sample)")
        sb = summary.get("BUY", {})
        if sb.get("n", 0) == 0:
            st.info("Nenhum sinal BUY gerado.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("n (bruto)", sb["n"])
            c1.caption(f"n_efetivo: {sb.get('n_effective', '?')}")
            c2.metric("Retorno Medio", f"{sb['mean']*100:+.2f}%")
            c2.caption(f"Bruto: {sb.get('mean_raw', 0)*100:+.2f}%")
            c3.metric("Win Rate", f"{sb['win_rate']:.0%}" if sb.get("win_rate") is not None else "n/d")
            if sb.get("ci_lower") is not None:
                st.caption(f"IC 95%: [{sb['ci_lower']*100:+.2f}%, {sb['ci_upper']*100:+.2f}%]")
            if sb.get("p_value") is not None:
                sig = "Sim" if sb["p_value"] < 0.05 else "Nao"
                st.caption(f"t-test (thinned): p={sb['p_value']:.4f} | significativo: {sig}")

    with col_s:
        st.markdown("### SELL (out-of-sample)")
        ss = summary.get("SELL", {})
        if ss.get("n", 0) == 0:
            st.info("Nenhum sinal SELL gerado.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("n (bruto)", ss["n"])
            c1.caption(f"n_efetivo: {ss.get('n_effective', '?')}")
            c2.metric("Retorno Medio", f"{ss['mean']*100:+.2f}%")
            c2.caption(f"Bruto: {ss.get('mean_raw', 0)*100:+.2f}%")
            c3.metric("Win Rate", f"{ss['win_rate']:.0%}" if ss.get("win_rate") is not None else "n/d")
            if ss.get("ci_lower") is not None:
                st.caption(f"IC 95%: [{ss['ci_lower']*100:+.2f}%, {ss['ci_upper']*100:+.2f}%]")
            if ss.get("p_value") is not None:
                sig = "Sim" if ss["p_value"] < 0.05 else "Nao"
                st.caption(f"t-test (thinned): p={ss['p_value']:.4f} | significativo: {sig}")

    if comparison:
        st.markdown("---")
        st.subheader("BUY vs SELL")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("BUY medio", f"{comparison['buy_mean']*100:+.2f}%")
        c2.metric("SELL medio", f"{comparison['sell_mean']*100:+.2f}%")
        c3.metric("Spread", f"{comparison['spread']*100:+.2f}%")
        sig = "SIGNIFICATIVO" if comparison["mw_pvalue"] < 0.05 else "NAO SIGNIFICATIVO"
        c4.metric("Mann-Whitney p", f"{comparison['mw_pvalue']:.3f} | {sig}")

    st.markdown("---")
    st.subheader("Timeline de Sinais")

    fig_tl = go.Figure()
    color_map = {"BUY": STRATEGY_COLOR, "SELL": SELL_COLOR, "NEUTRO": HOLD_COLOR}

    for sig in ["BUY", "SELL", "NEUTRO"]:
        subset = signals_df[signals_df["signal"] == sig]
        if not subset.empty:
            fig_tl.add_trace(go.Scatter(
                x=subset["data"],
                y=subset["pvp"],
                mode="markers",
                name=sig,
                marker=dict(color=color_map[sig], size=5, opacity=0.65),
            ))

    fig_tl.add_hline(y=1.0, line_dash="dash", line_color=HOLD_COLOR)
    fig_tl.update_layout(
        title=f"{ticker} | P/VP e Sinais Walk-Forward",
        xaxis_title="Data",
        yaxis_title="P/VP",
        template="plotly_white",
        height=400,
        hovermode="x unified",
    )
    fig_tl.update_xaxes(type="date", tickformat="%m/%y")
    st.plotly_chart(fig_tl, use_container_width=True)

    with st.expander("Ver todos os sinais"):
        display = signals_df.copy()
        display["fwd_ret"] = display["fwd_ret"].apply(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "")
        display["pvp"] = display["pvp"].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "")
        display["pvp_buy_thr"] = display["pvp_buy_thr"].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "")
        display["pvp_sell_thr"] = display["pvp_sell_thr"].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "")
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption("""
    **Metodologia estatística:** Janela de treino rolante sem look-ahead.
    Thresholds de P/VP definidos pelo percentil historico do treino em cada step.
    Os testes estatisticos seguem usando retorno forward fixo para avaliar a qualidade do sinal.
    Inferencia estatistica usa apenas observacoes nao sobrepostas, separadas por pelo menos `forward_days` pregoes.
    """)


def _render_simulation_tab(ticker, follow_buy, hold):
    ret_strategy = float(follow_buy["cumulative"][-1]) if follow_buy.get("cumulative") else float(follow_buy.get("final", 0.0))
    ret_hold = float(hold["cumulative"][-1]) if hold.get("cumulative") else float(hold.get("final", 0.0))
    excess = ret_strategy - ret_hold

    c1, c2, c3 = st.columns(3)
    c1.metric("Retorno Estratégia", f"{ret_strategy*100:+.2f}%")
    c2.metric("Retorno Buy & Hold", f"{ret_hold*100:+.2f}%")
    c3.metric("Excesso (Alpha)", f"{excess*100:+.2f}%", delta=f"{excess*100:+.2f}%")

    st.info(SIMULATION_INFO)

    st.subheader("Curva de Capital")

    fig_cum = go.Figure()

    if follow_buy.get("dates"):
        fig_cum.add_trace(go.Scatter(
            x=follow_buy["dates"],
            y=(np.array(follow_buy["cumulative"]) * 100),
            mode="lines",
            name="Estratégia",
            line=dict(color=STRATEGY_COLOR, width=3),
        ))

    if hold.get("dates"):
        fig_cum.add_trace(go.Scatter(
            x=hold["dates"],
            y=(np.array(hold["cumulative"]) * 100),
            mode="lines",
            name="Buy & Hold",
            line=dict(color=HOLD_COLOR, dash="dash", width=2),
        ))

    fig_cum.add_hline(y=0, line_color=HOLD_COLOR, line_dash="dot")
    fig_cum.update_layout(
        title=f"{ticker} | Estratégia BUY→SELL + CDI vs Buy & Hold",
        xaxis_title="Data",
        yaxis_title="Retorno Acumulado (%)",
        template="plotly_white",
        height=450,
        hovermode="x unified",
    )
    fig_cum.update_xaxes(type="date", tickformat="%m/%y")
    st.plotly_chart(fig_cum, use_container_width=True)

    if follow_buy.get("open_position"):
        st.warning(
            f"Ha uma posicao aberta desde {follow_buy['open_entry_date'].date() if hasattr(follow_buy.get('open_entry_date'), 'date') else follow_buy.get('open_entry_date')} "
            "que nao entrou no lucro realizado porque ainda nao houve SELL."
        )

    st.markdown("---")
    st.subheader("Trades Fechados")
    trades = follow_buy.get("trades", [])

    if not trades:
        st.info("Nenhum trade BUY→SELL foi fechado no periodo analisado.")
        return

    hold_map = {d: c for d, c in zip(hold.get("dates", []), hold.get("cumulative", []))}
    trades_df = pd.DataFrame(trades).copy()
    trades_df["trade"] = range(1, len(trades_df) + 1)
    trades_df["buy_and_hold_acum"] = trades_df["data_saida"].map(hold_map)
    trades_df["excesso_vs_hold"] = trades_df["cum_ret"] - trades_df["buy_and_hold_acum"]

    show_df = trades_df[[
        "trade",
        "data_entrada",
        "preco_entrada",
        "data_saida",
        "preco_saida",
        "dias_uteis",
        "ret_preco",
        "dividendos_trade",
        "ret",
        "capital_apos_trade",
        "cum_ret",
        "buy_and_hold_acum",
        "excesso_vs_hold",
    ]].copy()

    show_df["preco_entrada"] = show_df["preco_entrada"].map(lambda x: f"{x:.2f}")
    show_df["preco_saida"] = show_df["preco_saida"].map(lambda x: f"{x:.2f}")
    show_df["dividendos_trade"] = show_df["dividendos_trade"].map(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "0.00%")
    show_df["capital_apos_trade"] = show_df["capital_apos_trade"].map(lambda x: f"{x:.4f}x" if pd.notna(x) else "n/d")
    for col in ["ret_preco", "ret", "cum_ret", "buy_and_hold_acum", "excesso_vs_hold"]:
        show_df[col] = show_df[col].map(lambda x: f"{x*100:+.2f}%" if pd.notna(x) else "n/d")

    st.dataframe(show_df, use_container_width=True, hide_index=True)

    t1, t2, t3 = st.columns(3)
    t1.metric("Trades Fechados", len(trades_df))
    t2.metric("Retorno Medio por Trade", f"{trades_df['ret'].mean()*100:+.2f}%")
    alpha_final = (follow_buy['final'] - hold['final']) * 100
    t3.metric("Excesso Final vs B&H", f"{alpha_final:+.2f}%", delta=f"{alpha_final:+.2f}%")
