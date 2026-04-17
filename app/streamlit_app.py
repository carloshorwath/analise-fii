import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.state import init_session_state, render_footer
from src.fii_analysis.data.database import create_tables

st.set_page_config(
    page_title="FII Analysis",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()
create_tables()

st.title("FII Analysis Dashboard")
st.markdown("Analise estatistica de FIIs — precos, valuation, saude, event study.")
st.markdown("Use o menu lateral para navegar entre as paginas.")
render_footer()
