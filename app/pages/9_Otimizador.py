import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import select
from src.fii_analysis.data.database import Ticker, get_session_ctx
from src.fii_analysis.models.threshold_optimizer import ThresholdOptimizer

st.set_page_config(page_title="Otimizador de Thresholds", layout="wide")

st.title("🎯 Otimizador de Thresholds de Sinais")
st.markdown("""
Esta ferramenta busca as melhores combinações de thresholds para sinais de BUY e SELL baseados em P/VP Percentil e Alertas de Distribuição.
A otimização utiliza um split temporal diário rigoroso (Treino/Validação/Teste) para mitigar overfitting.
""")

with get_session_ctx() as session:
    tickers = session.execute(select(Ticker.ticker).order_by(Ticker.ticker)).scalars().all()

ticker = st.selectbox("Selecione o Ticker", tickers)

if st.button("Otimizar"):
    optimizer = ThresholdOptimizer()
    
    with st.spinner(f"Otimizando thresholds para {ticker}... Isso pode levar alguns segundos."):
        with get_session_ctx() as session:
            result = optimizer.optimize(ticker, session)
            
            if "error" in result:
                st.error(result["error"])
            else:
                best_params = result["best_params"]
                train_score = result["train_score"]
                val_score = result["val_score"]
                test_result = result["test_result"]
                placebo = result["placebo"]
                n_splits = result["n_splits"]
                
                # --- SINAL ATUAL ---
                signal_data = optimizer.get_signal_hoje(ticker, session, best_params)
                sinal = signal_data["sinal"]
                inds = signal_data.get("indicators", {})
                
                st.subheader("🏁 Resultado da Otimização")
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    color = "green" if sinal == "BUY" else "red" if sinal == "SELL" else "gray"
                    st.markdown(f"**Sinal Atual:** <span style='color:{color}; font-size:24px; font-weight:bold;'>{sinal}</span>", unsafe_allow_html=True)
                with c2:
                    st.metric("P/VP Percentil", f"{inds.get('pvp_pct', 0):.1f}%")
                with c3:
                    st.metric("Meses Alerta", inds.get("meses_alerta", 0))

                # --- PARAMS ---
                st.markdown("### 🛠️ Melhores Parâmetros Encontrados")
                df_params = pd.DataFrame([best_params]).T.reset_index()
                df_params.columns = ["Parâmetro", "Valor"]
                st.table(df_params)

                # --- METRICAS ---
                st.markdown("### 📊 Performance por Split")
                col_t, col_v, col_ts = st.columns(3)
                
                with col_t:
                    st.info(f"**TREINO** ({n_splits['train']} pregões)")
                    st.metric("Retorno Médio BUY", f"{train_score['avg_return_buy']*100:.2f}%")
                    st.metric("Retorno Médio SELL", f"{train_score['avg_return_sell']*100:.2f}%")
                    st.caption(f"Eventos: B:{train_score['n_buy']} | S:{train_score['n_sell']}")
                
                with col_v:
                    st.success(f"**VALIDAÇÃO** ({n_splits['val']} pregões)")
                    st.metric("Retorno Médio BUY", f"{val_score['avg_return_buy']*100:.2f}%")
                    st.metric("Retorno Médio SELL", f"{val_score['avg_return_sell']*100:.2f}%")
                    st.caption(f"Eventos: B:{val_score['n_buy']} | S:{val_score['n_sell']}")

                with col_ts:
                    st.warning(f"**TESTE (Out-of-sample)** ({n_splits['test']} pregões)")
                    st.metric("Retorno Médio BUY", f"{test_result['avg_return_buy']*100:.2f}%")
                    st.metric("Retorno Médio SELL", f"{test_result['avg_return_sell']*100:.2f}%")
                    st.caption(f"Eventos: B:{test_result['n_buy']} | S:{test_result['n_sell']}")
                    
                    st.markdown("---")
                    st.markdown(f"**P-Value Placebo (BUY):** `{placebo['p_value_buy']:.3f}`")
                    st.markdown(f"**P-Value Placebo (SELL):** `{placebo['p_value_sell']:.3f}`")

                # --- GRÁFICO ---
                st.markdown("### 📈 Análise de Sensibilidade (P/VP Buy Threshold)")
                grid_data = result["grid_results"]
                # Filtrar combinações onde outros parâmetros são iguais ao best, variando apenas pvp_percentil_buy
                sens = []
                for r in grid_data:
                    p = r["params"]
                    if (p["pvp_percentil_sell"] == best_params["pvp_percentil_sell"] and
                        p["meses_alerta_sell"] == best_params["meses_alerta_sell"]):
                        sens.append({
                            "threshold": p["pvp_percentil_buy"],
                            "Train": r["train"]["avg_return_buy"],
                            "Val": r["val"]["avg_return_buy"]
                        })
                
                if sens:
                    df_sens = pd.DataFrame(sens).melt(id_vars="threshold", var_name="Split", value_name="Retorno")
                    fig = px.line(df_sens, x="threshold", y="Retorno", color="Split", markers=True,
                                 title="Impacto do Threshold de P/VP BUY no Retorno Médio")
                    st.plotly_chart(fig, use_container_width=True)

                st.warning("⚠️ **Modelo experimental.** Poucos eventos por split. Não usar como única base de decisão.")
                st.caption(f"Nota: Foram analisados dados diários alinhados com relatórios CVM via merge_asof.")

st.sidebar.markdown("""
### Como funciona?
1. **Grid Search**: Testa combinações de thresholds de P/VP Percentil e Alertas.
2. **Walk-Forward**: Treina nos primeiros 60% dos pregões, valida nos 20% seguintes e testa nos últimos 20%.
3. **Point-in-Time**: Todas as decisões são tomadas apenas com dados disponíveis no dia do pregão (VP e Alertas do último relatório entregue).
4. **Placebo**: Compara o retorno real com 200 simulações de datas aleatórias no período de teste.
""")
