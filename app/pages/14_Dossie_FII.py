import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.carteira_ui import load_tickers_ativos
from app.components.page_content import analise_fii, fund_eventstudy, fundamentos
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Dossie FII", page_icon="folder", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Dossie FII", "Investigar")
    render_page_header(
        "Dossie do FII",
        "Visao consolidada de um fundo: valuation, fundamentos e eventos discretos CVM em uma unica tela.",
        "Investigar",
    )
    render_inline_note(
        "Selecione um ticker no topo. As tres abas abaixo cobrem todo o ciclo de investigacao: "
        "Analise (preco, valuation, saude, composicao), Fundamentos (DY, P/VP, PL, distribuicao), "
        "Eventos CVM (event study por sinais discretos)."
    )

    tickers = load_tickers_ativos()
    if not tickers:
        st.warning("Nenhum ticker ativo encontrado.")
        st.stop()

    if "dossie_ticker" not in st.session_state or st.session_state.dossie_ticker not in tickers:
        st.session_state.dossie_ticker = tickers[0]

    ticker = st.selectbox(
        "Ticker em investigacao",
        tickers,
        index=tickers.index(st.session_state.dossie_ticker),
        key="dossie_ticker_select",
    )
    st.session_state.dossie_ticker = ticker

    st.markdown("---")

    tab_analise, tab_fundamentos, tab_eventos = st.tabs(
        ["Analise FII", "Fundamentos", "Eventos CVM"]
    )

    with tab_analise:
        analise_fii.render(ticker, key_prefix="dossie_afii")

    with tab_fundamentos:
        fundamentos.render(ticker, key_prefix="dossie_fund")

    with tab_eventos:
        fund_eventstudy.render(ticker=ticker, key_prefix="dossie_fcs")

    render_footer()


main()
