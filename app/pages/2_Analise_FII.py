import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import (
    composicao_pie,
    pl_trend_chart,
    pvp_gauge,
    pvp_historico_com_bandas,
)
from app.components.data_loader import (
    load_composicao,
    load_dy_atual,
    load_dy_gap,
    load_dy_gap_percentil,
    load_panorama,
    load_pvp_atual,
    load_pvp_percentil,
    load_pvp_serie,
    load_pl_historico,
    load_proximas_datas_com,
    load_saude,
    load_ticker_info,
    load_tickers_ativos,
    load_ultimo_preco,
)
from app.components.tables import format_currency, format_pct, format_number
from app.state import render_footer

st.set_page_config(page_title="Analise FII", page_icon="magnifying_glass", layout="wide")
st.title("Analise por FII")

tickers = load_tickers_ativos()
if not tickers:
    st.warning("Nenhum ticker ativo encontrado.")
    st.stop()

ticker = st.selectbox("Selecione o FII:", tickers)

info = load_ticker_info(ticker)
if info:
    st.caption(f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
               f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}")

st.markdown("---")

# --- 1. Valuation ---
st.header("1. Valuation")
col_v1, col_v2 = st.columns([1, 2])

with col_v1:
    pvp = load_pvp_atual(ticker)
    st.plotly_chart(pvp_gauge(pvp, ticker), use_container_width=True)
    pvp_pct_val = load_pvp_percentil(ticker)
    st.metric("P/VP Percentil (504d)", f"{pvp_pct_val:.1f}%" if pvp_pct_val else "n/d")
    dy = load_dy_atual(ticker)
    st.metric("DY 12m (trailing)", f"{dy:.2%}" if dy else "n/d")
    dy_gap = load_dy_gap(ticker)
    st.metric("DY Gap vs CDI", f"{dy_gap:.2%}" if dy_gap else "n/d")

with col_v2:
    pvp_df = load_pvp_serie(ticker)
    st.plotly_chart(pvp_historico_com_bandas(pvp_df, ticker), use_container_width=True)

st.markdown("---")

# --- 2. Saude ---
st.header("2. Saude Financeira")
saude = load_saude(ticker)

col_s1, col_s2 = st.columns(2)
with col_s1:
    destr = saude["destruicao"]
    if destr["destruicao"]:
        st.error(f"DESTRUICAO DE CAPITAL detectada! {destr['motivo']}")
    else:
        st.success(f"Sem destruicao de capital. {destr['motivo']}")

    tend = saude["tendencia_pl"]
    for periodo, dados in tend.items():
        coef = dados.get("coef_angular")
        r2 = dados.get("r2")
        n = dados.get("n", 0)
        st.write(f"**PL {periodo}m:** coef={format_number(coef, 4) if coef else 'n/d'}, "
                 f"R2={format_number(r2) if r2 else 'n/d'}, n={n}")

    emissoes = saude["emissoes"]
    if emissoes:
        st.warning(f"{len(emissoes)} emissoes recentes (>1% cotas)")
        for e in emissoes:
            st.write(f"  - {e['data_ref']}: +{e['variacao_pct']:.1f}% cotas")
    else:
        st.info("Sem emissoes recentes significativas.")

with col_s2:
    pl_df = load_pl_historico(ticker, 24)
    st.plotly_chart(pl_trend_chart(pl_df, ticker), use_container_width=True)

st.markdown("---")

# --- 3. Composicao ---
st.header("3. Composicao do Ativo")
comp = load_composicao(ticker)

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

# --- 4. Event Study ---
st.header("4. Event Study")
st.info("Para rodar o event study completo com CriticAgent, use a pagina dedicada 'Event Study'.")

st.markdown("---")

# --- 5. Proxima data-com ---
st.header("5. Proximas Datas-Com")
proximas = load_proximas_datas_com(ticker)
if proximas:
    for p in proximas:
        valor = f"R$ {p['valor_cota']:.4f}" if p["valor_cota"] else "n/d"
        st.write(f"**{p['data_com']}** — {valor}/cota")
else:
    st.info("Nenhuma data-com futura encontrada.")

st.markdown("---")

# --- 6. Radar ---
st.header("6. Filtros Radar")
pvp_pct = load_pvp_percentil(ticker)
dy_gap_pct = load_dy_gap_percentil(ticker)

col_r1, col_r2, col_r3, col_r4 = st.columns(4)
col_r1.metric("P/VP Baixo (pct<30)", f"{pvp_pct:.1f}% {'PASSOU' if pvp_pct and pvp_pct < 30 else 'FALHOU'}" if pvp_pct else "n/d")
col_r2.metric("DY Gap Alto (pct>70)", f"{dy_gap_pct:.1f}% {'PASSOU' if dy_gap_pct and dy_gap_pct > 70 else 'FALHOU'}" if dy_gap_pct else "n/d")
col_r3.metric("Saude OK", "PASSOU" if not saude["destruicao"]["destruicao"] else "FALHOU")

vol_medio = None
pan = load_panorama()
row_pan = pan[pan["ticker"] == ticker]
if not row_pan.empty:
    vol_medio = row_pan.iloc[0].get("volume_medio_21d")

from src.fii_analysis.config_yaml import get_piso_liquidez
piso = get_piso_liquidez()
col_r4.metric("Liquidez OK", f"{'PASSOU' if vol_medio and vol_medio >= piso else 'FALHOU'}")

preco_info = load_ultimo_preco(ticker)
if preco_info:
    st.caption(f"Ultimo preco: {preco_info['data']} | Coletado em: {preco_info.get('coletado_em', 'n/d')}")

render_footer()
