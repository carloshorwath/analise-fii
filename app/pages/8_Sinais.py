import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.tables import format_pct
from app.state import render_footer
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.sinais import sinal_atual, gerar_historico_sinais, get_sinais_config

st.set_page_config(page_title="Sinais Operacionais", page_icon="signal", layout="wide")
st.title("Sinais Operacionais (Alpha)")

cfg = get_sinais_config()
tickers_configurados = list(cfg.get("tickers", {}).keys())

if not tickers_configurados:
    st.warning("Nenhum ticker configurado na seção 'sinais' do config.yaml.")
    st.stop()

ticker = st.selectbox("Selecione o FII:", tickers_configurados)

with get_session_ctx() as session:
    with st.spinner(f"Analisando sinais para {ticker}..."):
        atual = sinal_atual(ticker, session)
        if not atual:
            st.error("Nao foi possivel calcular o sinal atual.")
            st.stop()
            
        hist = gerar_historico_sinais(ticker, session)

    # --- 1. Painel de Sinal Atual ---
    col_s1, col_s2, col_s3 = st.columns([1, 1, 2])
    
    sinal = atual["sinal"]
    score = atual["score"]
    
    with col_s1:
        st.subheader("Sinal Atual")
        if sinal == "COMPRA":
            st.markdown(f"### :green[{sinal}]")
        elif sinal == "VENDA":
            st.markdown(f"### :red[{sinal}]")
        else:
            st.markdown(f"### :grey[{sinal}]")
            
    with col_s2:
        st.subheader("Score")
        st.markdown(f"### {score}")
        
    with col_s3:
        st.subheader("Data da Analise")
        st.markdown(f"### {atual['data'].strftime('%d/%m/%Y')}")

    st.markdown("---")

    # --- 2. Detalhes das Condicoes ---
    st.header("Condicoes Detalhadas")
    
    cond_rows = []
    ticker_cfg = cfg.get("tickers", {}).get(ticker, {})
    valores = atual["valores"]
    
    # Buy Conditions
    buy_rules = ticker_cfg.get("buy", {})
    for k, v in buy_rules.items():
        met = atual["condicoes_detalhadas"].get(f"buy_{k}", False)
        
        # Dynamic value mapping
        val_key = k.replace("_max", "").replace("_min", "")
        if val_key == "pvp_percentil": val_key = "pvp_pct"
        elif val_key == "dy_gap_percentil": val_key = "dy_gap_pct"
        curr_val = valores.get(val_key)
        
        cond_rows.append({
            "Tipo": "COMPRA (+1)",
            "Condicao": k,
            "Threshold": f"<= {v}" if "max" in k else f">= {v}",
            "Valor Atual": f"{curr_val:.2f}" if isinstance(curr_val, (int, float)) and not isinstance(curr_val, bool) else str(curr_val),
            "Status": "✅ Passou" if met else "❌ Falhou"
        })

    # Sell Conditions
    sell_rules = ticker_cfg.get("sell", {})
    for k, v in sell_rules.items():
        met = atual["condicoes_detalhadas"].get(f"sell_{k}", False)

        # Dynamic value mapping
        val_key = k.replace("_max", "").replace("_min", "")
        if val_key == "pvp_percentil": val_key = "pvp_pct"
        elif val_key == "dy_gap_percentil": val_key = "dy_gap_pct"
        elif val_key == "dist_maior_geracao": val_key = "dist_maior"
        curr_val = valores.get(val_key)

        cond_rows.append({
            "Tipo": "VENDA (-1)",
            "Condicao": k,
            "Threshold": f">= {v}" if "min" in k else (f"== {v}" if "dist" in k else v),
            "Valor Atual": f"{curr_val:.2f}" if isinstance(curr_val, (int, float)) and not isinstance(curr_val, bool) else str(curr_val),
            "Status": "🚨 Gatilho" if met else "⚪ OK"
        })

    if cond_rows:
        st.table(pd.DataFrame(cond_rows))

    st.markdown("---")

    # --- 3. Confianca Historica ---
    st.header("Confianca Historica")
    conf = atual["confianca_historica"]
    
    col_c1, col_c2, col_c3, col_c4 = st.columns(4)
    col_c1.metric("Acerto COMPRA", format_pct(conf.get("pct_buy_acerto")), 
                  help="Percentual de vezes que o preco subiu nos X dias seguintes ao sinal")
    col_c2.metric("Acerto VENDA", format_pct(conf.get("pct_sell_acerto")),
                  help="Percentual de vezes que o preco caiu nos X dias seguintes ao sinal")
    col_c3.metric("Amostras Buy", conf.get("n_buy"))
    col_c4.metric("Amostras Sell", conf.get("n_sell"))
    
    st.info(f"Parametros de validacao: {cfg.get('forward_days', 20)} pregoes a frente. "
            f"CAR Medio Buy: {format_pct(conf.get('car_buy'))} | CAR Medio Sell: {format_pct(conf.get('car_sell'))}")

    st.markdown("---")

    # --- 4. Grafico Score Historico ---
    st.header("Historico de Score e Sinais")
    
    if not hist.empty:
        fig = go.Figure()
        
        # Area de Buy/Sell thresholds
        buy_thresh = cfg.get("score_buy_threshold", 2)
        sell_thresh = cfg.get("score_sell_threshold", -2)
        
        fig.add_hline(y=buy_thresh, line_dash="dash", line_color="green", annotation_text="Buy Threshold")
        fig.add_hline(y=sell_thresh, line_dash="dash", line_color="red", annotation_text="Sell Threshold")
        fig.add_hline(y=0, line_color="gray", opacity=0.3)
        
        fig.add_trace(go.Scatter(
            x=hist["data"], y=hist["score"],
            mode="lines", name="Score",
            line=dict(color="#1f77b4", width=2),
            fill='tozeroy', fillcolor='rgba(31, 119, 180, 0.1)'
        ))
        
        # Marcadores de Sinais
        buys = hist[hist["sinal"] == "COMPRA"]
        sells = hist[hist["sinal"] == "VENDA"]
        
        fig.add_trace(go.Scatter(
            x=buys["data"], y=buys["score"],
            mode="markers", name="Sinal COMPRA",
            marker=dict(symbol="triangle-up", size=10, color="green")
        ))
        
        fig.add_trace(go.Scatter(
            x=sells["data"], y=sells["score"],
            mode="markers", name="Sinal VENDA",
            marker=dict(symbol="triangle-down", size=10, color="red")
        ))
        
        fig.update_layout(
            xaxis_title="Data",
            yaxis_title="Score",
            template="plotly_white",
            height=500,
            hovermode="x unified"
        )
        
        st.plotly_chart(fig, use_container_width=True)

    # --- 5. Aviso ---
    st.markdown("---")
    st.warning("**Aviso:** Este modelo e experimental e baseado em indicadores quantitativos retroativos. "
               "Nao constitui recomendacao de investimento. Resultados passados nao garantem retornos futuros.")

render_footer()
