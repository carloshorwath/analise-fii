import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))
if str(PROJECT_ROOT.parent / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent / "src"))


def init_session_state():
    defaults = {
        "carteira_dirty": True,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_footer():
    from src.fii_analysis.data.database import get_ultima_coleta

    result = get_ultima_coleta()
    if result is not None:
        ts = result.strftime("%d/%m/%Y %H:%M") if hasattr(result, "strftime") else str(result)
        st.sidebar.caption(f"Dados atualizados em: {ts}")
    else:
        st.sidebar.caption("Dados atualizados em: n/d")
