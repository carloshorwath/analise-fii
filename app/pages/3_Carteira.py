import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import carteira_alocacao_pie, carteira_segmento_pie
from app.components.data_loader import (
    delete_carteira_posicao,
    load_carteira_db,
    load_panorama,
    load_tickers_ativos,
    save_carteira_posicao,
)
from app.components.tables import format_currency
from src.fii_analysis.data.database import create_tables
from src.fii_analysis.features.portfolio import herfindahl

st.set_page_config(page_title="Carteira", page_icon="briefcase", layout="wide")
st.title("Carteira")

create_tables()

tickers = load_tickers_ativos()

# --- Add position ---
st.header("Adicionar Posicao")
with st.form("add_posicao"):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        novo_ticker = st.selectbox("Ticker", tickers)
    with col2:
        novo_qty = st.number_input("Quantidade", min_value=1, value=10, step=1)
    with col3:
        novo_preco = st.number_input("Preco Medio (R$)", min_value=0.01, value=100.0, step=0.01)
    with col4:
        novo_data = st.date_input("Data Compra", value=date.today())

    submitted = st.form_submit_button("Adicionar")
    if submitted:
        save_carteira_posicao(novo_ticker, novo_qty, novo_preco, novo_data)
        st.success(f"Posicao adicionada: {novo_qty}x {novo_ticker} a R$ {novo_preco:.2f}")
        st.rerun()

st.markdown("---")

# --- CSV Upload ---
st.header("Upload CSV")
st.markdown("Formato esperado: `ticker,quantidade,preco_medio,data_compra`")
csv_file = st.file_uploader("Escolha um arquivo CSV", type=["csv"])
if csv_file is not None:
    try:
        df_csv = pd.read_csv(csv_file)
        required = {"ticker", "quantidade", "preco_medio", "data_compra"}
        if not required.issubset(set(df_csv.columns)):
            st.error(f"Colunas obrigatorias: {required}. Encontradas: {set(df_csv.columns)}")
        else:
            for _, row in df_csv.iterrows():
                dt = pd.to_datetime(row["data_compra"]).date()
                save_carteira_posicao(
                    str(row["ticker"]).upper().strip(),
                    int(row["quantidade"]),
                    float(row["preco_medio"]),
                    dt,
                )
            st.success(f"{len(df_csv)} posicoes importadas com sucesso!")
            st.rerun()
    except Exception as e:
        st.error(f"Erro ao processar CSV: {e}")

st.markdown("---")

# --- Current positions ---
st.header("Posicoes Atuais")
posicoes = load_carteira_db()

if not posicoes:
    st.info("Nenhuma posicao na carteira. Adicione posicoes acima.")
else:
    df_pos = pd.DataFrame(posicoes)
    df_pos["valor_total"] = df_pos["quantidade"] * df_pos["preco_medio"]

    to_delete = st.selectbox("Remover posicao (selecione e clique abaixo):",
                             options=[""] + [f"ID {r['id']}: {r['ticker']} {r['quantidade']}x {format_currency(r['preco_medio'])}" for _, r in df_pos.iterrows()])
    if to_delete and st.button("Confirmar Remocao"):
        pos_id = int(to_delete.split(":")[0].replace("ID ", ""))
        delete_carteira_posicao(pos_id)
        st.success("Posicao removida!")
        st.rerun()

    st.markdown("---")

    for _, row in df_pos.iterrows():
        st.write(f"**{row['ticker']}** — {row['quantidade']} cotas a {format_currency(row['preco_medio'])} "
                 f"= {format_currency(row['valor_total'])} (comprado em {row['data_compra']})")

    st.markdown("---")

    # --- Consolidated view ---
    st.header("Consolidado")
    consol = df_pos.groupby("ticker").agg(
        qty=("quantidade", "sum"),
        preco_medio=("preco_medio", "mean"),
        valor_total=("valor_total", "sum"),
    ).reset_index()

    total_carteira = consol["valor_total"].sum()

    col_c1, col_c2, col_c3 = st.columns(3)
    col_c1.metric("Total Investido", format_currency(total_carteira))
    col_c2.metric("FIIs na Carteira", len(consol))

    pesos = consol["valor_total"].tolist()
    hh = herfindahl(pesos)
    col_c3.metric("Herfindahl (HH)", f"{hh['hh']:.3f}" if hh["hh"] else "n/d")

    st.dataframe(consol, use_container_width=True, hide_index=True)

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.plotly_chart(carteira_alocacao_pie(consol), use_container_width=True)
    with col_chart2:
        pan = load_panorama()
        seg_map = {}
        if not pan.empty:
            for _, r in pan.iterrows():
                seg_map[r["ticker"]] = r.get("segmento", "n/d")
        consol["segmento"] = consol["ticker"].map(seg_map).fillna("n/d")
        st.plotly_chart(carteira_segmento_pie(consol), use_container_width=True)
