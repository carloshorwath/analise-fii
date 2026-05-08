"""Conteudo de Otimizador V2 renderizavel sem decorators ou page_config."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.carteira_ui import load_tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2

STRATEGY_COLOR = "#2ca02c"
HOLD_COLOR = "#7f7f7f"
SIMULATION_INFO = """
**Premissas da Simulação Operacional**
- Capital fora da posição rende 100% do CDI.
- Compras usam preço bruto no fechamento do dia do sinal.
- Vendas ocorrem apenas no sinal de SELL; sem SELL, a posição permanece aberta e o valor final fica marcado a mercado.
- Dividendos entram como caixa separado com elegibilidade na `data_com` e crédito no pregão seguinte como proxy, porque o banco não guarda `data_pagamento`.
"""

_SIDEBAR_NOTE = """
### Otimizador V2 — Robustez

Diferencial vs V1:
- Metricas de risco ajustado (Sharpe, Sortino, Max DD)
- Diagnostico de overfitting (degradacao treino->teste)
- Intervalos de confianca via bootstrap
- Sensibilidade 2D (heatmap)
- Custos de transacao modelados
- Analise por regime de mercado

**Nao e recomendacao de investimento.** Modelo experimental com poucos eventos.
"""


def render(*, key_prefix: str = "optv2", show_sidebar_note: bool = True) -> None:
    """Renderiza otimizador V2 (sem header/footer)."""
    if show_sidebar_note:
        st.sidebar.markdown(_SIDEBAR_NOTE)

    st.caption(
        "Extende o Otimizador V1 com metricas de risco ajustado, diagnostico de overfitting, "
        "intervalos de confianca bootstrap, sensibilidade 2D e modelagem de custos. "
        "Domain boundary: sinais P/VP percentil + meses alerta + DY Gap. "
        "Forward return em janela fixa de 20 pregões."
    )

    tickers = load_tickers_ativos()
    ticker = st.selectbox("Selecione o Ticker", tickers, key=f"{key_prefix}_ticker")

    run_key = f"optv2_{ticker}"

    if st.button("Otimizar com Analise de Robustez", type="primary", key=f"{key_prefix}_run"):
        optimizer = ThresholdOptimizerV2()

        with st.spinner(f"Otimizando {ticker} com metricas estendidas..."):
            with get_session_ctx() as session:
                result = optimizer.optimize_v2(ticker, session)

            if "error" in result:
                st.error(result["error"])
            else:
                st.session_state[run_key] = result

    if run_key not in st.session_state:
        return

    result = st.session_state[run_key]
    v2 = result["v2"]
    best_params = result["best_params"]
    test_result = result["test_result"]
    n_splits = result["n_splits"]

    tab_res, tab_sim, tab_risk, tab_overfit, tab_sens, tab_regime, tab_grid = st.tabs([
        "Resultado & Sinal", "Simulação Operacional", "Risco Ajustado", "Overfitting", "Sensibilidade 2D", "Regime", "Grid Completo"
    ])

    with tab_res:
        st.subheader("Sinal Atual e Melhores Parametros")

        with get_session_ctx() as session:
            optimizer = ThresholdOptimizerV2()
            signal_data = optimizer.get_signal_hoje(ticker, session, best_params)
        sinal = signal_data["sinal"]
        inds = signal_data.get("indicators", {})

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            color = "green" if sinal == "BUY" else "red" if sinal == "SELL" else "gray"
            st.markdown(f"**Sinal Atual:** <span style='color:{color}; font-size:24px; font-weight:bold;'>{sinal}</span>",
                        unsafe_allow_html=True)
        with c2:
            st.metric("P/VP Percentil", f"{inds.get('pvp_pct', 0):.1f}%")
        with c3:
            st.metric("Meses Alerta", inds.get("meses_alerta", 0))
        with c4:
            dy_gap_val = inds.get("dy_gap_pct")
            st.metric("DY Gap Percentil", f"{dy_gap_val:.1f}%" if dy_gap_val is not None else "n/d")

        st.markdown("#### Melhores Parametros")
        df_params = pd.DataFrame([best_params]).T.reset_index()
        df_params.columns = ["Parametro", "Valor"]
        st.dataframe(df_params, hide_index=True, use_container_width=True)

        st.markdown("#### Performance por Split (Retorno Medio)")
        col_t, col_v, col_ts = st.columns(3)

        def _sig(p):
            if p < 0.01: return "p<0.01"
            if p < 0.05: return "p<0.05"
            return "ns"

        def _render_split(score, label, n_obs, color_fn):
            color_fn(f"**{label}** ({n_obs} pregoes)")
            st.metric("BUY", f"{score['avg_return_buy']*100:.2f}%")
            degen_buy = score.get("buy_se_degenerate", False)
            st.caption(
                f"p={score['p_value_buy']:.3f} {_sig(score['p_value_buy'])} | "
                f"media_indep={score.get('avg_return_buy_independent', 0)*100:+.2f}% | "
                f"n_bruto={score['n_buy']} | n_indep={score.get('n_buy_thinned', 0)}"
                + (" SE=0" if degen_buy else "")
            )
            st.metric("SELL", f"{score['avg_return_sell']*100:.2f}%")
            degen_sell = score.get("sell_se_degenerate", False)
            st.caption(
                f"p={score['p_value_sell']:.3f} {_sig(score['p_value_sell'])} "
                f"| excesso_indep={score.get('sell_excess_vs_market_independent', 0)*100:+.2f}% "
                f"| n_bruto={score['n_sell']} | n_indep={score.get('n_sell_thinned', 0)}"
                + (" SE=0" if degen_sell else "")
            )
            if degen_buy or degen_sell:
                st.warning("SE=0 detectado: retornos constantes neste split. Verificar liquidez do ticker ou mascara de sinal.")

        with col_t:
            _render_split(result["train_score"], "TREINO", n_splits["train"], st.info)

        with col_v:
            _render_split(result["val_score"], "VALIDACAO", n_splits["val"], st.success)

        with col_ts:
            n_comb = result.get("n_combinations", 1)
            pb_raw = test_result['p_value_buy']
            pb_bon = min(1.0, pb_raw * n_comb)
            st.warning(f"**TESTE** ({n_splits['test']} pregoes)")
            degen_buy_t = test_result.get("buy_se_degenerate", False)
            degen_sell_t = test_result.get("sell_se_degenerate", False)
            st.metric("BUY", f"{test_result['avg_return_buy']*100:.2f}%")
            st.caption(
                f"p={pb_raw:.3f} | Bonf={pb_bon:.3f} {_sig(pb_bon)} | "
                f"media_indep={test_result.get('avg_return_buy_independent', 0)*100:+.2f}% | "
                f"n_bruto={test_result['n_buy']} | n_indep={test_result.get('n_buy_thinned', 0)}"
                + (" SE=0" if degen_buy_t else "")
            )
            st.metric("SELL", f"{test_result['avg_return_sell']*100:.2f}%")
            st.caption(
                f"Excesso vs mercado (indep): {test_result.get('sell_excess_vs_market_independent', 0)*100:+.2f}% | "
                f"n_bruto={test_result['n_sell']} | n_indep={test_result.get('n_sell_thinned', 0)}"
                + (" SE=0" if degen_sell_t else "")
            )
            if degen_buy_t or degen_sell_t:
                st.error("SE=0 no TESTE: resultado do teste estatistico invalido. Verificar dados.")

        st.markdown("#### Teste Placebo")
        placebo = result["placebo"]
        pc1, pc2 = st.columns(2)
        with pc1:
            pb = placebo['p_value_buy']
            st.metric("Placebo BUY (bicaudal)", f"{pb:.3f}")
            st.caption("Robusto" if pb < 0.05 else "Indistinguivel de ruido")
        with pc2:
            ps = placebo['p_value_sell']
            st.metric("Placebo SELL (unicaudal)", f"{ps:.3f}")
            st.caption("Sinal de saida valido" if ps < 0.05 else "Captura regime, nao reversao")

    with tab_risk:
        st.subheader("Metricas de Risco Ajustado (Conjunto de Teste)")

        buy_risk = v2["buy_risk"]
        sell_risk = v2["sell_risk"]
        buy_ci = v2["buy_ci"]
        sell_ci = v2["sell_ci"]
        buy_after_cost = v2["buy_risk_after_cost"]
        cost = v2["cost_per_trade"]

        st.caption(f"Custo de transacao modelado: {cost*100:.3f}% round-trip (emolumentos B3)")

        col_buy, col_sell = st.columns(2)

        with col_buy:
            st.markdown("#### BUY Signal")
            _render_risk_table(buy_risk, "BUY")

            n_eff = buy_risk.get("n_effective", buy_risk["n"])
            if n_eff < 5:
                st.error(f"**n_efetivo = {n_eff}** (observacoes independentes). Inferencia estatistica nao e confiavel com menos de 5 observacoes independentes.")
            else:
                st.caption(f"n_bruto={buy_risk['n']} | n_efetivo (independente)={n_eff}")

            if buy_ci.get("warning"):
                st.warning(f"IC 95%: {buy_ci['warning']}")
            elif buy_ci["lower"] is not None:
                st.markdown(f"**IC 95% (bootstrap i.i.d., n independente):** [{buy_ci['lower']*100:+.2f}%, {buy_ci['upper']*100:+.2f}%]")
                st.caption(f"Largura do IC: {buy_ci['width']*100:.2f}% — {'ESTREITO' if buy_ci['width'] < 0.05 else 'LARGO (baixa confianca)'}")
            if buy_after_cost.get("mean_after_cost") is not None and buy_after_cost["mean_after_cost"] != buy_risk["mean"]:
                cost_impact = (buy_after_cost["mean_after_cost"] - buy_risk["mean"]) * 100
                st.markdown(f"**Retorno pos-custo:** {buy_after_cost['mean_after_cost']*100:+.2f}% (impacto: {cost_impact:+.3f}%)")

        with col_sell:
            st.markdown("#### SELL Signal")
            _render_risk_table(sell_risk, "SELL")

            n_eff_sell = sell_risk.get("n_effective", sell_risk["n"])
            if n_eff_sell < 5:
                st.warning(f"**n_efetivo = {n_eff_sell}** (observacoes independentes). Resultados frageis.")
            else:
                st.caption(f"n_bruto={sell_risk['n']} | n_efetivo (independente)={n_eff_sell}")

            if sell_ci.get("warning"):
                st.warning(f"IC 95%: {sell_ci['warning']}")
            elif sell_ci["lower"] is not None:
                st.markdown(f"**IC 95% (bootstrap i.i.d., n independente):** [{sell_ci['lower']*100:+.2f}%, {sell_ci['upper']*100:+.2f}%]")
                st.caption(f"Largura do IC: {sell_ci['width']*100:.2f}%")

        st.markdown("---")
        st.subheader("Caveats e Assumcoes")
        st.warning("""
        **Assumcoes explicitas do modelo:**
        - Forward return em janela fixa de 20 pregões (nao execução real com entrada/saída)
        - Custo de transacao fixo (emolumentos B3, sem corretagem, sem spread)
        - Sem modelagem de slippage ou impacto de mercado
        - Sinais baseados em indicadores point-in-time (VP do último relatório entregue à CVM)
        - Inferencia (p-value, IC, n_efetivo) usa apenas observacoes nao sobrepostas, separadas por >= 20 pregões
        - Não considera IR (20% sobre ganho de capital) nem compensação de prejuízo
        """)

    with tab_overfit:
        st.subheader("Diagnostico de Overfitting")
        overfit = v2["overfit"]

        cls = overfit["classification"]
        cls_color = {
            "ROBUSTO": "success", "MODERADO": "info",
            "SUSPEITO": "warning", "SEVERO": "error", "SEM_SINAL": "warning",
        }
        getattr(st, cls_color.get(cls, "info"))(f"**Classificacao: {cls}**")

        c1, c2, c3 = st.columns(3)
        c1.metric("Retorno BUY Treino", f"{overfit['train_buy']*100:.2f}%")
        c2.metric("Retorno BUY Validacao", f"{overfit['val_buy']*100:.2f}%")
        c3.metric("Retorno BUY Teste", f"{overfit['test_buy']*100:.2f}%")

        st.markdown("---")

        val_deg = overfit.get("val_degradation")
        test_deg = overfit.get("test_degradation")

        if val_deg is None or test_deg is None:
            st.info("Sem sinal treinavel no treino — metricas de degradacao indisponives.")
        else:
            d1, d2, d3 = st.columns(3)
            d1.metric("Degradacao Treino→Validacao", f"{val_deg*100:.1f}%",
                       delta="Preocupante" if val_deg > 0.5 else "Aceitavel",
                       delta_color="inverse")
            d2.metric("Degradacao Treino→Teste", f"{test_deg*100:.1f}%",
                       delta="Preocupante" if test_deg > 0.5 else "Aceitavel",
                       delta_color="inverse")
            d3.metric("Rank Consistente (BUY>SELL)", "SIM" if overfit["rank_consistent"] else "NAO")

        st.markdown("---")
        st.caption("""
        **Como interpretar:**
        - **ROBUSTO**: degradacao < 20% val, < 30% teste. Modelo generaliza bem.
        - **MODERADO**: degradacao 20-50%. Sinal existe mas magnitude incerta.
        - **SUSPEITO**: degradacao 50-80%. Provavel overfitting no treino.
        - **SEVERO**: degradacao > 80%. Sinal do treino nao se repete fora da amostra.
        - **SEM_SINAL**: sem observacoes BUY suficientes no treino — diagnostico de degradacao invalido.
        """)

        labels = ["Treino", "Validacao", "Teste"]
        values = [
            (overfit.get("train_buy") or 0.0) * 100,
            (overfit.get("val_buy") or 0.0) * 100,
            (overfit.get("test_buy") or 0.0) * 100,
        ]
        fig_deg = go.Figure(go.Bar(x=labels, y=values, marker_color=["#636efa", "#2ca02c", "#ef553b"]))
        fig_deg.add_hline(y=0, line_color="gray", line_dash="dash")
        fig_deg.update_layout(
            title="Retorno Medio BUY por Split",
            yaxis_title="Retorno (%)", template="plotly_white", height=300,
        )
        st.plotly_chart(fig_deg, use_container_width=True)

    with tab_sens:
        st.subheader("Analise de Sensibilidade 2D")
        sens_df = v2["sensitivity_2d"]

        if sens_df.empty:
            st.info("Dados insuficientes para sensibilidade 2D.")
        else:
            st.markdown("#### Retorno BUY no Teste por Par de Thresholds")
            pivot = sens_df.pivot_table(
                index="pvp_percentil_sell", columns="pvp_percentil_buy",
                values="test_buy_return", aggfunc="mean",
            )
            fig_heat = go.Figure(go.Heatmap(
                z=pivot.values * 100,
                x=[str(c) for c in pivot.columns],
                y=[str(i) for i in pivot.index],
                colorscale="RdYlGn",
                text=np.round(pivot.values * 100, 2),
                texttemplate="%{text:.2f}%",
                colorbar=dict(title="Retorno BUY (%)"),
            ))
            fig_heat.update_layout(
                title="Retorno Medio BUY (%) no Teste — P/VP Buy vs P/VP Sell",
                xaxis_title="P/VP Percentil BUY", yaxis_title="P/VP Percentil SELL",
                height=400,
            )
            best_x = str(best_params["pvp_percentil_buy"])
            best_y = str(best_params["pvp_percentil_sell"])
            if best_x in [str(c) for c in pivot.columns] and best_y in [str(i) for i in pivot.index]:
                fig_heat.add_annotation(x=best_x, y=best_y, text="MELHOR",
                                        showarrow=True, arrowhead=2, font=dict(color="black", size=12))
            st.plotly_chart(fig_heat, use_container_width=True)

            st.markdown("#### Spread BUY-SELL na Validacao")
            pivot_val = sens_df.pivot_table(
                index="pvp_percentil_sell", columns="pvp_percentil_buy",
                values="val_spread", aggfunc="mean",
            )
            fig_val = go.Figure(go.Heatmap(
                z=pivot_val.values * 100,
                x=[str(c) for c in pivot_val.columns],
                y=[str(i) for i in pivot_val.index],
                colorscale="RdYlGn",
                text=np.round(pivot_val.values * 100, 2),
                texttemplate="%{text:.2f}%",
                colorbar=dict(title="Spread (%)"),
            ))
            fig_val.update_layout(
                title="Spread BUY-SELL (%) na Validacao — P/VP Buy vs P/VP Sell",
                xaxis_title="P/VP Percentil BUY", yaxis_title="P/VP Percentil SELL",
                height=400,
            )
            st.plotly_chart(fig_val, use_container_width=True)

            st.caption("Valores positivos = BUY supera SELL. Melhor combinacao marcada com seta.")

    with tab_regime:
        st.subheader("Analise por Regime de Mercado (ex-ante via P/VP)")
        regime = v2["regime"]

        if regime["classification"] == "INSUFICIENTE":
            st.info("Dados insuficientes para analise de regime.")
        else:
            pvp_thr = regime.get("pvp_median_threshold", None)
            src = regime.get("pvp_median_source", "teste")
            if pvp_thr is not None:
                st.caption(
                    f"Mediana P/VP = {pvp_thr:.1f} (calculada no **{src}**). "
                    "Premio = P/VP acima da mediana. Desconto = abaixo."
                )

            r1, r2 = st.columns(2)
            with r1:
                st.metric("Pregoes Premio (P/VP > mediana)", regime["n_premium"])
                st.metric("Retorno Incondicional Premio", f"{regime['premium_unconditional']*100:.2f}%")
                if regime["premium_excess"] is not None:
                    st.metric("Excesso BUY em Premio", f"{regime['premium_excess']*100:+.2f}%")
            with r2:
                st.metric("Pregoes Desconto (P/VP <= mediana)", regime["n_discount"])
                st.metric("Retorno Incondicional Desconto", f"{regime['discount_unconditional']*100:.2f}%")
                if regime["discount_excess"] is not None:
                    st.metric("Excesso BUY em Desconto", f"{regime['discount_excess']*100:+.2f}%")

            st.markdown("---")
            st.caption("""
            **Como interpretar:**
            - **Excesso positivo em Desconto** = sinal BUY funciona melhor quando o mercado esta barato — esperado.
            - **Excesso positivo em Premio** = sinal BUY funciona mesmo quando mercado esta caro — sinal robusto.
            - **Excesso negativo em qualquer regime** = sinal nao tem vantagem nesse cenario.
            - Regime definido pelo nivel P/VP (variavel de valuation ex-ante), **nao por retornos futuros**.
            """)

            labels = ["Premio", "Desconto"]
            uncond = [regime["premium_unconditional"] * 100, regime["discount_unconditional"] * 100]
            excess_vals = [
                regime["premium_excess"] * 100 if regime["premium_excess"] is not None else 0,
                regime["discount_excess"] * 100 if regime["discount_excess"] is not None else 0,
            ]
            fig_regime = go.Figure()
            fig_regime.add_trace(go.Bar(x=labels, y=uncond, name="Incondicional (%)", marker_color="#636efa"))
            fig_regime.add_trace(go.Bar(x=labels, y=excess_vals, name="Excesso BUY (%)", marker_color="#2ca02c"))
            fig_regime.add_hline(y=0, line_color="gray", line_dash="dash")
            fig_regime.update_layout(
                title="Performance por Regime (P/VP: Premio vs Desconto)",
                yaxis_title="Retorno (%)", template="plotly_white", height=350, barmode="group",
            )
            st.plotly_chart(fig_regime, use_container_width=True)

    with tab_grid:
        st.subheader('Heatmap: Todas as Combinacoes Buy x Sell')
        grid_results = result.get('grid_results', [])
        if not grid_results:
            st.info('Sem dados de grid. Execute a otimizacao.')
        else:
            metrica_opcoes = {
                'Retorno Medio Val (%)': ('val', 'avg_return_buy_independent'),
                'Win Rate Val': ('val', 'win_rate_independent'),
                'N Trades Val (thinned)': ('val', 'n_buy_thinned'),
                'P-Value Buy Val': ('val', 'p_value_buy'),
            }
            metrica_label = st.selectbox('Metrica do heatmap', list(metrica_opcoes.keys()), key=f'{key_prefix}_grid_metrica')
            split_key, field_key = metrica_opcoes[metrica_label]

            # Agregar por buy_pct x sell_pct (media sobre meses_alerta e dy_gap)
            from collections import defaultdict
            agg = defaultdict(list)
            for row in grid_results:
                p = row['params']
                v = row.get(split_key, {}).get(field_key)
                if v is not None:
                    agg[(p['pvp_percentil_buy'], p['pvp_percentil_sell'])].append(v)

            if not agg:
                st.warning('Sem dados suficientes para o heatmap.')
            else:
                rows_list = []
                for (buy_pct, sell_pct), vals in agg.items():
                    media = float(sum(vals) / len(vals))
                    if metrica_label == 'Retorno Medio Val (%)':
                        media = round(media * 100, 2)
                    rows_list.append({'buy_pct': buy_pct, 'sell_pct': sell_pct, 'valor': media})
                df_grid = pd.DataFrame(rows_list)
                pivot = df_grid.pivot(index='sell_pct', columns='buy_pct', values='valor')
                pivot = pivot.sort_index(ascending=False)

                best_buy = best_params.get('pvp_percentil_buy')
                best_sell = best_params.get('pvp_percentil_sell')

                fig = go.Figure(data=go.Heatmap(
                    z=pivot.values.tolist(),
                    x=[str(c) for c in pivot.columns],
                    y=[str(r) for r in pivot.index],
                    colorscale='RdYlGn',
                    text=[[f'{v:.2f}' if v is not None else '' for v in row] for row in pivot.values.tolist()],
                    texttemplate='%{text}',
                    hovertemplate='Buy: %{x}<br>Sell: %{y}<br>Valor: %{z:.4f}<extra></extra>',
                    showscale=True,
                ))
                if best_buy is not None and best_sell is not None:
                    fig.add_shape(type='rect',
                        x0=str(best_buy), x1=str(best_buy),
                        y0=str(best_sell), y1=str(best_sell),
                        xref='x', yref='y',
                        line=dict(color='blue', width=3))
                    fig.add_annotation(
                        x=str(best_buy), y=str(best_sell),
                        text='MELHOR', showarrow=True, arrowhead=2,
                        font=dict(color='blue', size=11))
                fig.update_layout(
                    title=f'{metrica_label} — Buy (X) vs Sell (Y)',
                    xaxis_title='Threshold Compra (P/VP percentil)',
                    yaxis_title='Threshold Venda (P/VP percentil)',
                    height=500,
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    f'Total de combinacoes no grid: {len(grid_results)} | '
                    f'Exibindo media por par buy/sell (agrega meses_alerta e dy_gap). '
                    f'Melhor combinacao (azul): buy={best_buy}, sell={best_sell}.'
                )

    with tab_sim:
        sim = v2.get("simulation")

        if not sim:
            st.subheader("Simulação Operacional (Conjunto de Teste)")
            st.info("Dados de simulação não disponíveis na saída do otimizador.")
        else:
            follow_buy = sim.get("follow_buy", {})
            hold = sim.get("hold", {})

            if not follow_buy.get("dates") or not hold.get("dates"):
                st.subheader("Simulação Operacional (Conjunto de Teste)")
                st.warning("Sem dados suficientes de capital para plotar a simulação.")
            else:
                ret_sim = float(follow_buy["cumulative"][-1]) if follow_buy["cumulative"] else 0.0
                ret_hold = float(hold["cumulative"][-1]) if hold["cumulative"] else 0.0
                alpha = (ret_sim - ret_hold) * 100

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Retorno Estratégia", f"{ret_sim*100:+.2f}%")
                with c2:
                    st.metric("Retorno Buy & Hold", f"{ret_hold*100:+.2f}%")
                with c3:
                    st.metric("Excesso (Alpha)", f"{alpha:+.2f}%", delta=f"{alpha:+.2f}%")

                st.info(SIMULATION_INFO)

                st.subheader("Curva de Capital")

                df_sim = pd.DataFrame({
                    "Data": follow_buy["dates"],
                    "Estratégia": [(x + 1.0) for x in follow_buy["cumulative"]],
                }).set_index("Data")

                df_hold = pd.DataFrame({
                    "Data": hold["dates"],
                    "Buy & Hold": [(x + 1.0) for x in hold["cumulative"]],
                }).set_index("Data")

                df_plot = df_sim.join(df_hold, how="outer").ffill().reset_index()

                fig_sim = go.Figure()
                fig_sim.add_trace(go.Scatter(
                    x=df_plot["Data"],
                    y=df_plot["Estratégia"],
                    mode="lines",
                    name="Estratégia",
                    line=dict(color=STRATEGY_COLOR, width=3),
                ))
                fig_sim.add_trace(go.Scatter(
                    x=df_plot["Data"],
                    y=df_plot["Buy & Hold"],
                    mode="lines",
                    name="Buy & Hold",
                    line=dict(color=HOLD_COLOR, dash="dash", width=2),
                ))
                fig_sim.update_layout(
                    title="Evolução Patrimonial (Base = 1.0)",
                    yaxis_title="Capital Acumulado",
                    template="plotly_white",
                    height=500,
                    yaxis_tickformat=".2f",
                    hovermode="x unified",
                )

                st.plotly_chart(fig_sim, use_container_width=True)

                if follow_buy.get("open_position"):
                    st.warning(
                        f"Há uma posição aberta desde {follow_buy['open_entry_date'].date() if hasattr(follow_buy.get('open_entry_date'), 'date') else follow_buy.get('open_entry_date')} "
                        "no fim do conjunto de teste. O valor final da estratégia inclui marcação a mercado dessa posição, não lucro realizado."
                    )

    st.markdown("---")
    st.error("""
    **MODELO EXPERIMENTAL.** Nao usar como unica base de decisao de investimento.
    - Poucos eventos por split (n tipicamente < 50).
    - Metricas pos-custo ainda nao modelam slippage real, spread bid-ask, ou IR.
    - Resultados simulados nao garantem performance futura.
    - Sempre cruzar com analise fundamentalista e contexto de mercado.
    """)


def _render_risk_table(risk: dict, label: str):
    """Renderiza tabela de metricas de risco."""
    n_eff = risk.get("n_effective", "?")
    data = {
        "Metrica": [
            "N observacoes (bruto)",
            "N efetivo (independente)",
            "Retorno Medio (bruto)",
            "Retorno Medio (indep.)",
            "Retorno Mediana (indep.)",
            "Desvio Padrao (indep.)",
            "Sharpe Ratio (anual, h-days)",
            "Sortino Ratio (anual, h-days)",
            "Max Drawdown",
            "Win Rate (bruto)",
            "Win Rate (indep.)",
            "Profit Factor",
            "Skewness",
            "Kurtosis",
        ],
        "Valor": [
            f"{risk['n']}",
            f"{n_eff}",
            f"{risk['mean_raw']*100:+.3f}%",
            f"{risk['mean_independent']*100:+.3f}%" if risk.get("mean_independent") is not None else "n/d",
            f"{risk['median_independent']*100:+.3f}%" if risk.get("median_independent") is not None else "n/d",
            f"{risk['std_independent']*100:.3f}%" if risk.get("std_independent") is not None else "n/d",
            f"{risk['sharpe']:.2f}" if risk["sharpe"] is not None else "n/d",
            f"{risk['sortino']:.2f}" if risk["sortino"] is not None else "n/d (sem perdas)",
            f"{risk['max_drawdown']*100:.2f}%" if risk.get("max_drawdown") is not None else "0.00%",
            f"{risk['win_rate']:.1%}" if risk.get("win_rate") is not None else "n/d",
            f"{risk['win_rate_independent']:.1%}" if risk.get("win_rate_independent") is not None else "n/d",
            f"{risk['profit_factor']:.2f}" if risk["profit_factor"] is not None else "n/d (sem perdas)",
            f"{risk['skewness']:.2f}" if risk["skewness"] is not None else "n/d",
            f"{risk['kurtosis']:.2f}" if risk["kurtosis"] is not None else "n/d",
        ],
    }
    st.table(pd.DataFrame(data).set_index("Metrica"))
