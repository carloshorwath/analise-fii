import sys
from datetime import date
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import (
    composicao_pie,
    dividend_heatmap,
    pl_trend_chart,
    price_volume_chart,
    pvp_gauge,
    pvp_historico_com_bandas,
)
from app.components.data_loader import load_tickers_ativos
from app.components.tables import format_currency, format_number
from app.state import render_footer
from src.fii_analysis.config_yaml import get_piso_liquidez, get_threshold
from src.fii_analysis.data.database import get_session_ctx, get_ultimo_preco_date
from src.fii_analysis.features.composicao import classificar_fii, composicao_ativo
from src.fii_analysis.features.data_loader import (
    get_benchmark_ifix,
    get_dias_desatualizado,
    get_dividendos_historico,
    get_dy_gap_anterior,
    get_historico_pl,
    get_info_ticker,
    get_proximas_datas_com,
    get_pvp_anterior,
    get_serie_preco_volume,
    get_ultimo_preco,
    get_volume_medio_21d_ticker,
    resolve_periodo,
)
from src.fii_analysis.features.indicators import get_dy_serie, get_dy_trailing, get_pvp, get_pvp_serie
from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital, tendencia_pl
from src.fii_analysis.features.valuation import (
    get_dy_gap,
    get_dy_gap_percentil,
    get_dy_n_meses,
    get_pvp_percentil,
)

st.set_page_config(page_title="Analise FII", page_icon="magnifying_glass", layout="wide")
st.title("Analise por FII")

tickers = load_tickers_ativos()
if not tickers:
    st.warning("Nenhum ticker ativo encontrado.")
    st.stop()

ticker = st.selectbox("Selecione o FII:", tickers)

with get_session_ctx() as session:
    info = get_info_ticker(ticker, session)
    if info:
        st.caption(f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
                   f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}")

st.markdown("---")

PERIODOS = ["1m", "6m", "1a", "YTD", "2a", "3a", "Max"]
if "periodo" not in st.session_state:
    st.session_state.periodo = "1a"

col_p1, col_p2, col_p3, col_p4, col_p5, col_p6, col_p7 = st.columns(7)
periodo_cols = [col_p1, col_p2, col_p3, col_p4, col_p5, col_p6, col_p7]
for i, p in enumerate(PERIODOS):
    with periodo_cols[i]:
        if st.button(p, key=f"btn_{p}", use_container_width=True,
                     type="primary" if st.session_state.periodo == p else "secondary"):
            st.session_state.periodo = p
            st.rerun()

periodo = st.session_state.periodo
with get_session_ctx() as session:
    inicio = resolve_periodo(periodo, ticker, session)

with get_session_ctx() as session:
    dias_desat = get_dias_desatualizado(ticker, session)
if dias_desat is not None and dias_desat > 3:
    st.warning(f"Ultimo preco disponivel ha {dias_desat} dias uteis. Dados podem estar desatualizados. "
               f"Execute `C:/ProgramData/anaconda3/python.exe scripts/load_database.py` para atualizar.")

st.markdown("---")

# --- 0. Preco + Volume ---
st.header("0. Preco e Volume")
with get_session_ctx() as session:
    pv_df = get_serie_preco_volume(ticker, session)
if inicio is not None and not pv_df.empty:
    pv_df_plot = pv_df[pv_df["data"] >= inicio]
else:
    pv_df_plot = pv_df
st.plotly_chart(price_volume_chart(pv_df_plot, ticker), use_container_width=True)

st.markdown("---")

# --- 1. Valuation ---
st.header("1. Valuation")
col_v1, col_v2 = st.columns([1, 2])

with col_v1:
    with get_session_ctx() as session:
        ultimo = get_ultimo_preco_date(ticker, session)
        pvp = get_pvp(ticker, ultimo, session) if ultimo else None
    st.plotly_chart(pvp_gauge(pvp, ticker), use_container_width=True)

    with get_session_ctx() as session:
        pvp_pct_val, jan_val = get_pvp_percentil(ticker, ultimo, 504, session) if ultimo else (None, 0)
    st.metric(f"P/VP Percentil ({jan_val}d)", f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d")

    with get_session_ctx() as session:
        pvp_ant = get_pvp_anterior(ticker, session)
    if pvp is not None and pvp_ant is not None:
        delta_pvp = pvp - pvp_ant
        st.metric("P/VP (atual)", f"{pvp:.4f}", delta=f"{delta_pvp:+.4f}")
    else:
        st.metric("P/VP (atual)", f"{pvp:.4f}" if pvp else "n/d")

    with get_session_ctx() as session:
        dy = get_dy_trailing(ticker, ultimo, session) if ultimo else None
    st.metric("DY 12m (trailing)", f"{dy:.2%}" if dy else "n/d")

    with get_session_ctx() as session:
        dy_gap = get_dy_gap(ticker, ultimo, session) if ultimo else None
        dy_gap_ant = get_dy_gap_anterior(ticker, session)
    if dy_gap is not None and dy_gap_ant is not None:
        delta_gap = dy_gap - dy_gap_ant
        st.metric("DY Gap vs CDI", f"{dy_gap:.2%}", delta=f"{delta_gap:+.2%}")
    else:
        st.metric("DY Gap vs CDI", f"{dy_gap:.2%}" if dy_gap else "n/d")

with col_v2:
    with get_session_ctx() as session:
        pvp_df = get_pvp_serie(ticker, session)
    if inicio is not None and not pvp_df.empty:
        pvp_df_plot = pvp_df[pvp_df["data"] >= inicio]
    else:
        pvp_df_plot = pvp_df
    st.plotly_chart(pvp_historico_com_bandas(pvp_df_plot, ticker), use_container_width=True)

st.markdown("---")

# --- 1b. Dividendos ---
st.header("1b. Dividendos — Yield Mensal")
with get_session_ctx() as session:
    divs_df = get_dividendos_historico(ticker, session)
if not divs_df.empty and not pv_df.empty:
    st.plotly_chart(dividend_heatmap(divs_df, pv_df, ticker), use_container_width=True)
else:
    st.info("Sem dados de dividendos para este periodo.")

st.markdown("---")

# --- 2. Saude ---
st.header("2. Saude Financeira")
with get_session_ctx() as session:
    tend = tendencia_pl(ticker, session=session)
    destruicao = flag_destruicao_capital(ticker, session)
    emissoes = emissoes_recentes(ticker, session=session)
    saude = {"tendencia_pl": tend, "destruicao": destruicao, "emissoes": emissoes}

col_s1, col_s2 = st.columns(2)
with col_s1:
    destr = saude["destruicao"]
    if destr["destruicao"]:
        st.error(f"DESTRUICAO DE CAPITAL detectada! {destr['motivo']}")
    else:
        st.success(f"Sem destruicao de capital. {destr['motivo']}")

    tend_data = saude["tendencia_pl"]
    for periodo_t, dados in tend_data.items():
        coef = dados.get("coef_angular")
        r2 = dados.get("r2")
        n = dados.get("n", 0)
        st.write(f"**PL {periodo_t}m:** coef={format_number(coef, 4) if coef else 'n/d'}, "
                 f"R2={format_number(r2) if r2 else 'n/d'}, n={n}")

    emissoes_data = saude["emissoes"]
    if emissoes_data:
        st.warning(f"{len(emissoes_data)} emissoes recentes (>1% cotas)")
        for e in emissoes_data:
            st.write(f"  - {e['data_ref']}: +{e['variacao_pct']:.1f}% cotas")
    else:
        st.info("Sem emissoes recentes significativas.")

with col_s2:
    with get_session_ctx() as session:
        pl_df = get_historico_pl(ticker, session, 24)
    st.plotly_chart(pl_trend_chart(pl_df, ticker), use_container_width=True)

st.markdown("---")

# --- 3. Composicao ---
st.header("3. Composicao do Ativo")
with get_session_ctx() as session:
    comp = composicao_ativo(ticker, session)
    tipo = classificar_fii(ticker, session)
    comp["tipo"] = tipo

col_c1, col_c2 = st.columns(2)
with col_c1:
    st.metric("Tipo", comp.get("tipo", "n/d"))
    st.metric("% Imoveis", f"{comp['pct_imoveis']:.1%}" if comp.get("pct_imoveis") is not None else "n/d")
    st.metric("% Recebiveis", f"{comp['pct_recebiveis']:.1%}" if comp.get("pct_recebiveis") is not None else "n/d")
    st.metric("% Caixa", f"{comp['pct_caixa']:.1%}" if comp.get("pct_caixa") is not None else "n/d")
    if comp.get("ativo_total"):
        st.metric("Ativo Total", format_currency(comp["ativo_total"]))
    if comp.get("data_ref"):
        st.caption(f"Ref: {comp['data_ref']}")

with col_c2:
    st.plotly_chart(composicao_pie(comp, ticker), use_container_width=True)

st.markdown("---")

# --- 4. Proximas Datas-Com ---
st.header("4. Proximas Datas-Com")
with get_session_ctx() as session:
    proximas = get_proximas_datas_com(ticker, session)
if proximas:
    for p in proximas:
        valor = f"R$ {p['valor_cota']:.4f}" if p["valor_cota"] else "n/d"
        st.write(f"**{p['data_com']}** — {valor}/cota")
else:
    st.info("Nenhuma data-com futura encontrada.")

st.markdown("---")

# --- 5. Radar ---
st.header("5. Filtros Radar")
with get_session_ctx() as session:
    pvp_pct, jan_radar = get_pvp_percentil(ticker, ultimo, 504, session) if ultimo else (None, 0)
    dy_gap_pct = get_dy_gap_percentil(ticker, ultimo, get_threshold("dy_janela_pregoes", 252), session) if ultimo else None

col_r1, col_r2, col_r3, col_r4 = st.columns(4)
pvp_thr = get_threshold("pvp_percentil_barato", 30)
dy_gap_thr = get_threshold("dy_gap_percentil_caro", 70)
col_r1.metric(f"P/VP Baixo ({jan_radar}d)", f"{pvp_pct:.1f}% {'PASSOU' if pvp_pct and pvp_pct < pvp_thr else 'FALHOU'}" if pvp_pct is not None else "n/d")
col_r2.metric(f"DY Gap Alto (pct>{dy_gap_thr})", f"{dy_gap_pct:.1f}% {'PASSOU' if dy_gap_pct and dy_gap_pct > dy_gap_thr else 'FALHOU'}" if dy_gap_pct else "n/d")
col_r3.metric("Saude OK", "PASSOU" if not saude["destruicao"]["destruicao"] else "FALHOU")

with get_session_ctx() as session:
    vol_medio = get_volume_medio_21d_ticker(ticker, session)
piso = get_piso_liquidez()
col_r4.metric("Liquidez OK", f"{'PASSOU' if vol_medio and vol_medio >= piso else 'FALHOU'}")

with get_session_ctx() as session:
    preco_info = get_ultimo_preco(ticker, session)
if preco_info:
    st.caption(f"Ultimo preco: {preco_info['data']} | Coletado em: {preco_info.get('coletado_em', 'n/d')}")

render_footer()
