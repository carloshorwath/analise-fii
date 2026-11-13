import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.carteira_ui import load_seletor_info, rotulo_seletor
from app.components.page_content.fundamentos import render
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Fundamentos", page_icon="bar_chart", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Fundamentos", "Entender")
    render_page_header(
        "Fundamentos",
        "Leitura estrutural do fundo: distribuicao, geracao, P/VP historico, patrimonio liquido e emissao de cotas.",
        "Entender",
    )
    render_inline_note(
        "A ordem desta pagina foi ajustada para sair de sustentabilidade da distribuicao e avancar para patrimonio, deixando series historicas complementares depois."
    )

    tickers, notas = load_seletor_info()
    if not tickers:
        st.warning("Nenhum ticker encontrado.")
        st.stop()

    ticker = st.selectbox("Selecione o FII:", tickers, format_func=lambda t: rotulo_seletor(t, notas))
    if ticker in notas:
        st.warning(f"{ticker}: {notas[ticker]}. Os indicadores abaixo podem estar defasados.")
    render(ticker, key_prefix="fund_page")
    render_footer()


main()
