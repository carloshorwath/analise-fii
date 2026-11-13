import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.carteira_ui import load_seletor_info, rotulo_seletor
from app.components.page_content.analise_fii import render
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Analise FII", page_icon="magnifying_glass", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Analise FII", "Entender")
    render_page_header(
        "Analise por FII",
        "Leitura integrada de valuation, saude, dividendos, composicao e liquidez para um unico fundo.",
        "Entender",
    )
    render_inline_note(
        "A leitura recomendada aqui comeca em Valuation e Saude. Preco e volume ficam disponiveis como contexto, nao como ponto de partida."
    )

    tickers, notas = load_seletor_info()
    if not tickers:
        st.warning("Nenhum ticker encontrado.")
        st.stop()

    ticker = st.selectbox("Selecione o FII:", tickers, format_func=lambda t: rotulo_seletor(t, notas))
    if ticker in notas:
        st.warning(f"{ticker}: {notas[ticker]}. Os indicadores abaixo podem estar defasados.")
    render(ticker, key_prefix="afii_page")
    render_footer()


main()
