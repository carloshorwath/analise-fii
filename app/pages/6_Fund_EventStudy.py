import sys
from pathlib import Path
from datetime import timedelta, date

import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.data_loader import load_tickers_ativos
from app.state import render_footer
from src.fii_analysis.data.database import get_session_ctx, RelatorioMensal, PrecoDiario, BenchmarkDiario, get_cnpj_by_ticker
from src.fii_analysis.features.valuation import get_pvp_percentil, get_dy_gap_percentil
from src.fii_analysis.features.indicators import get_pvp
from sqlalchemy import select

st.set_page_config(page_title="Event Study Fundamentalista", page_icon="📈", layout="wide")
st.title("🔬 Event Study Fundamentalista")

st.markdown("""
Esta página analisa o impacto de eventos fundamentalistas (entrega de relatórios CVM) no preço dos ativos.
Os eventos são identificados point-in-time, usando apenas informações disponíveis na **Data de Entrega** do relatório.
""")

tickers = load_tickers_ativos()
if not tickers:
    st.warning("Nenhum ticker ativo encontrado.")
    st.stop()

with st.sidebar:
    ticker = st.selectbox("Ticker:", tickers, key="f fund_es_ticker")
    
    sinais_opcoes = {
        "P/VP > 1.0 (Venda)": "pvp_gt_1",
        "P/VP < 0.9 (Compra)": "pvp_lt_09",
        "P/VP Percentil > 70% (Venda)": "pvp_perc_gt_70",
        "P/VP Percentil < 30% (Compra)": "pvp_perc_lt_30",
        "Distribuição > Geração (Venda)": "dist_gt_gen",
        "Destruição Capital Consecutiva >= 2 (Venda)": "destruc_consec_2",
        "DY Gap Percentil > 70% (Compra)": "dy_gap_perc_gt_70",
        "DY Gap Percentil < 30% (Venda)": "dy_gap_perc_lt_30",
    }
    sinal_label = st.selectbox("Sinal Candidato:", list(sinais_opcoes.keys()))
    sinal_key = sinais_opcoes[sinal_label]
    
    forward_days = st.selectbox("Janela Forward (pregões):", [10, 20, 30], index=1)
    
    n_placebo = st.number_input("Simulações Placebo:", min_value=100, max_value=1000, value=500, step=100)

def get_events(ticker, sinal_key, session, forward_days):
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return []
    
    # BUG 2: ordenar por data_entrega
    relatorios = session.execute(
        select(RelatorioMensal)
        .where(RelatorioMensal.cnpj == cnpj)
        .order_by(RelatorioMensal.data_entrega.asc())
    ).scalars().all()
    
    if not relatorios:
        return []
    
    eventos = []
    
    for i, rel in enumerate(relatorios):
        t = rel.data_entrega
        if not t:
            continue
            
        trading_date = session.execute(
            select(PrecoDiario.data)
            .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= t)
            .order_by(PrecoDiario.data.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if not trading_date:
            continue
            
        is_event = False
        
        if sinal_key == "pvp_gt_1":
            pvp = get_pvp(ticker, trading_date, session)
            if pvp and pvp > 1.0:
                is_event = True
        
        elif sinal_key == "pvp_lt_09":
            pvp = get_pvp(ticker, trading_date, session)
            if pvp and pvp < 0.9:
                is_event = True
                
        elif sinal_key == "pvp_perc_gt_70":
            perc, _ = get_pvp_percentil(ticker, trading_date, 504, session)
            if perc is not None and perc > 70:
                is_event = True
                
        elif sinal_key == "pvp_perc_lt_30":
            perc, _ = get_pvp_percentil(ticker, trading_date, 504, session)
            if perc is not None and perc < 30:
                is_event = True
                
        elif sinal_key == "dist_gt_gen":
            if rel.dy_mes_pct is not None and rel.rentab_patrim is not None:
                if float(rel.dy_mes_pct) > float(rel.rentab_patrim):
                    is_event = True
                    
        elif sinal_key == "destruc_consec_2":
            if i >= 1:
                rel_ant = relatorios[i-1]
                if rel.rentab_patrim is not None and rel_ant.rentab_patrim is not None:
                    if float(rel.rentab_patrim) < 0 and float(rel_ant.rentab_patrim) < 0:
                        is_event = True
                        
        elif sinal_key == "dy_gap_perc_gt_70":
            perc = get_dy_gap_percentil(ticker, t, 252, session)
            if perc is not None and perc > 70:
                is_event = True
                
        elif sinal_key == "dy_gap_perc_lt_30":
            perc = get_dy_gap_percentil(ticker, t, 252, session)
            if perc is not None and perc < 30:
                is_event = True
        
        if is_event:
            eventos.append(t)
    
    # FIX 3: filtro sobreposição greedy
    eventos_filtrados = []
    ultima_data = None
    for ev_data in sorted(eventos):
        if ultima_data is None or (ev_data - ultima_data).days >= forward_days * 1.4:
            eventos_filtrados.append(ev_data)
            ultima_data = ev_data
            
    return eventos_filtrados

def calculate_car(ticker, events, forward_days, session):
    # Precos do Ativo
    precos_rows = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    
    if not precos_rows:
        return None, 0, pd.DataFrame()
    
    df_precos = pd.DataFrame(precos_rows, columns=["data", "fechamento_aj"])
    df_precos["fechamento_aj"] = df_precos["fechamento_aj"].astype(float)
    df_precos["retorno_diario"] = df_precos["fechamento_aj"].pct_change()
    df_precos["retorno_fwd"] = df_precos["fechamento_aj"].shift(-forward_days) / df_precos["fechamento_aj"] - 1
    
    # Precos do IFIX (Benchmark)
    ifix_rows = session.execute(
        select(BenchmarkDiario.data, BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == "IFIX.SA")
        .order_by(BenchmarkDiario.data.asc())
    ).all()
    
    df_ifix = pd.DataFrame(ifix_rows, columns=["data", "fechamento_ifix"])
    if not df_ifix.empty:
        df_ifix["fechamento_ifix"] = df_ifix["fechamento_ifix"].astype(float)
        df_ifix["retorno_diario_ifix"] = df_ifix["fechamento_ifix"].pct_change()
        df_ifix["retorno_fwd_ifix"] = df_ifix["fechamento_ifix"].shift(-forward_days) / df_ifix["fechamento_ifix"] - 1
        df_precos = df_precos.merge(df_ifix, on="data", how="left")
    else:
        df_precos["retorno_diario_ifix"] = np.nan
        df_precos["retorno_fwd_ifix"] = np.nan
    
    # Benchmark global (fallback)
    benchmark_medio_global = df_precos["retorno_fwd"].mean()
    
    results = []
    has_warning_ifix = False
    
    for t in events:
        # Encontrar indice do evento
        mask = df_precos["data"] >= t
        if not mask.any():
            continue
        idx_evento = df_precos[mask].index[0]
        
        # FIX 4: Modelo de Mercado com IFIX
        # Janela de estimacao [-200, -20]
        idx_ini = idx_evento - 200
        idx_fim = idx_evento - 20
        
        alpha, beta = 0.0, 1.0 # default/fallback
        usou_market_model = False
        
        if idx_ini >= 0 and idx_fim < len(df_precos):
            window_data = df_precos.iloc[idx_ini : idx_fim+1].dropna(subset=["retorno_diario", "retorno_diario_ifix"])
            if len(window_data) >= 30:
                res = stats.linregress(window_data["retorno_diario_ifix"], window_data["retorno_diario"])
                alpha = res.intercept
                beta = res.slope
                usou_market_model = True
        
        if not usou_market_model and not has_warning_ifix:
            st.warning("Dados de IFIX insuficientes para modelo de mercado em alguns eventos. Usando fallback média incondicional.")
            has_warning_ifix = True
            
        ret_fwd = df_precos.loc[idx_evento, "retorno_fwd"]
        ret_fwd_ifix = df_precos.loc[idx_evento, "retorno_fwd_ifix"]
        
        if not np.isnan(ret_fwd):
            if usou_market_model and not np.isnan(ret_fwd_ifix):
                # CAR = retorno_observado - (alpha + beta * retorno_ifix_evento)
                # alpha na janela forward eh alpha_diario * forward_days
                predito = (alpha * forward_days) + (beta * ret_fwd_ifix)
                car = ret_fwd - predito
            else:
                car = ret_fwd - benchmark_medio_global
                
            results.append({
                "data_entrega": t,
                "retorno_evento": ret_fwd,
                "car": car,
                "usou_market_model": usou_market_model
            })
                
    return pd.DataFrame(results), benchmark_medio_global, df_precos

if st.button("Rodar Análise", type="primary"):
    with get_session_ctx() as session:
        with st.spinner("Identificando eventos..."):
            events = get_events(ticker, sinal_key, session, forward_days)
            
        if not events:
            st.warning(f"Nenhum evento encontrado para o sinal '{sinal_label}'.")
            st.stop()
            
        st.success(f"{len(events)} eventos encontrados.")
        
        with st.spinner("Calculando retornos e CAR..."):
            df_results, benchmark_medio, df_precos = calculate_car(ticker, events, forward_days, session)
            
        if df_results.empty:
            st.error("Não foi possível calcular retornos para os eventos encontrados (dados insuficientes após os eventos).")
            st.stop()
            
        # Métricas
        n_eventos = len(df_results)
        car_medio = df_results["car"].mean()
        
        # Direção esperada
        direcao_esperada = "compra" if "Compra" in sinal_label else "venda"
        if direcao_esperada == "compra":
            sucessos = sum(df_results["car"] > 0)
        else:
            sucessos = sum(df_results["car"] < 0)
            
        pct_acertos = sucessos / n_eventos
        
        t_stat, p_value = stats.ttest_1samp(df_results["car"], 0.0)
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Nº Eventos", n_eventos)
        col2.metric("CAR Médio", f"{car_medio:.2%}")
        col3.metric("% Acertos", f"{pct_acertos:.1%}")
        col4.metric("t-stat", f"{t_stat:.2f}")
        col5.metric("p-value", f"{p_value:.4f}")
        
        # FIX 5: Bonferroni
        p_value_corrigido = min(p_value * 8, 1.0)
        st.caption(f"**p-value corrigido (Bonferroni):** {p_value_corrigido:.4f} (considerando 8 sinais testados na página)")
        
        # Gráficos
        st.subheader("Distribuição de CARs")
        fig_hist = px.histogram(df_results, x="car", nbins=20, title="Distribuição do CAR",
                               labels={"car": "Abnormal Return Acumulado"},
                               color_discrete_sequence=["#636EFA"])
        fig_hist.add_vline(x=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig_hist, use_container_width=True)
        
        st.subheader("CARs Individuais (Waterfall)")
        df_sorted = df_results.sort_values("car").reset_index()
        fig_water = px.bar(df_sorted, x=df_sorted.index, y="car", color="car",
                          color_continuous_scale="RdYlGn",
                          title="CAR por Evento (Ordenado)",
                          labels={"index": "Evento", "car": "CAR"})
        fig_water.add_hline(y=0, line_color="black")
        st.plotly_chart(fig_water, use_container_width=True)
        
        # Placebo Test
        st.subheader("Teste Placebo")
        with st.spinner(f"Rodando {n_placebo} simulações placebo..."):
            # eligible dates for placebo (must have forward_days precos after)
            eligible_indices = df_precos.index[200:-forward_days]
            if len(eligible_indices) < n_eventos:
                st.error("Histórico insuficiente para teste placebo.")
            else:
                t_stats_placebo = []
                rng = np.random.default_rng(42)
                
                for _ in range(n_placebo):
                    indices = rng.choice(eligible_indices, size=n_eventos, replace=False)
                    rets_placebo = df_precos.loc[indices, "retorno_fwd"].values
                    
                    # FIX 6: recalcular benchmark_medio para o draw
                    # Se houver IFIX, usamos o retorno medio do IFIX nessas datas como benchmark
                    if "retorno_fwd_ifix" in df_precos.columns and not df_precos["retorno_fwd_ifix"].isna().all():
                        benchmark_medio_sim = df_precos.loc[indices, "retorno_fwd_ifix"].mean()
                    else:
                        benchmark_medio_sim = rets_placebo.mean() # fallback literal conforme pedido
                        
                    cars_placebo = rets_placebo - benchmark_medio_sim
                    t_p, _ = stats.ttest_1samp(cars_placebo, 0.0)
                    t_stats_placebo.append(t_p)
                    
                fig_placebo = px.histogram(x=t_stats_placebo, nbins=30, title="Distribuição de t-stats (Placebo)",
                                         labels={"x": "t-statistic"},
                                         color_discrete_sequence=["#AB63FA"])
                fig_placebo.add_vline(x=t_stat, line_width=3, line_color="red", 
                                    annotation_text=f"t-stat Real ({t_stat:.2f})")
                st.plotly_chart(fig_placebo, use_container_width=True)
                
                p_placebo = np.mean(np.abs(t_stats_placebo) >= np.abs(t_stat))
                st.write(f"**p-value placebo:** {p_placebo:.4f}")
                if p_placebo < 0.05:
                    st.success("O sinal é estatisticamente robusto contra o placebo (p < 0.05).")
                else:
                    st.warning("O sinal NÃO é robusto contra o placebo. Pode ser ruído estatístico.")
                
        st.info("⚠️ **Aviso:** Este é um resultado experimental. O desempenho passado não garante resultados futuros.")

render_footer()
