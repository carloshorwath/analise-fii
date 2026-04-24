import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.data_loader import load_tickers_ativos
from app.components.tables import render_panorama_table
from app.state import render_footer
from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.portfolio import carteira_panorama
from src.fii_analysis.features.radar import radar_matriz

st.set_page_config(page_title="Panorama", page_icon="bar_chart", layout="wide")
st.title("Panorama Geral")

tickers = load_tickers_ativos()

with get_session_ctx() as session:
    radar_df = radar_matriz(session=session)

col1, col2, col3, col4 = st.columns(4)
col1.metric("FIIs Ativos", len(tickers))

with get_session_ctx() as session:
    ativos = tickers_ativos(session)
    df = carteira_panorama(ativos, session)

if not df.empty:
    avg_dy = df["dy_12m"].dropna().mean()
    avg_pvp = df["pvp"].dropna().mean()
    col2.metric("DY 12m Medio", f"{avg_dy:.2%}" if avg_dy else "n/d")
    col3.metric("P/VP Medio", f"{avg_pvp:.2f}" if avg_pvp else "n/d")
else:
    col2.metric("DY 12m Medio", "n/d")
    col3.metric("P/VP Medio", "n/d")

col4.metric("IFIX YTD", "n/d")

st.markdown("---")

if not df.empty:
    radar_pass = set()
    if not radar_df.empty:
        radar_pass = set(radar_df[radar_df["vistos"] >= 3]["ticker"].tolist())

    display = render_panorama_table(df)

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", width="small"),
            "segmento": st.column_config.TextColumn("Segmento"),
            "cvm_defasada": st.column_config.CheckboxColumn("CVM Defasada"),
        },
    )

    st.markdown(f"**FIIs com radar OK (>= 3 filtros):** {', '.join(sorted(radar_pass)) if radar_pass else 'Nenhum'}")

    coletado = df.iloc[0] if not df.empty else None
    if coletado is not None:
        st.caption("Dados calculados point-in-time. Atualize precos via CLI: `fii update-prices`")
    else:
        st.info("Nenhum dado disponivel. Execute os scripts de ingestao primeiro.")

render_footer()
