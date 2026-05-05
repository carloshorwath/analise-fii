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
from src.fii_analysis.data.database import get_session_ctx

safe_set_page_config(page_title="Dossie FII", page_icon="folder", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Dossie FII", "Investigar")
    render_page_header(
        "Dossiê do FII",
        "Analise completa em uma unica tela: valuation, saude, dividendos, "
        "composicao, fundamentos e eventos CVM.",
        "Investigar",
    )
    render_inline_note(
        "Selecione o ticker no topo. As abas cobrem todo o ciclo de investigacao "
        "sem sub-abas aninhadas — cada aba abre diretamente no conteudo."
    )

    tickers = load_tickers_ativos()
    if not tickers:
        st.warning("Nenhum ticker ativo encontrado.")
        st.stop()

    # — Ticker persistente no session_state —
    if "dossie_ticker" not in st.session_state or st.session_state.dossie_ticker not in tickers:
        st.session_state.dossie_ticker = tickers[0]

    ticker = st.selectbox(
        "Ticker em investigacao",
        tickers,
        index=tickers.index(st.session_state.dossie_ticker),
        key="dossie_ticker_select",
    )
    st.session_state.dossie_ticker = ticker

    # — Seletor de período (afeta Valuation e Preço & Volume) —
    PERIODOS = ["1m", "6m", "1a", "YTD", "2a", "3a", "Max"]
    if "dossie_periodo" not in st.session_state:
        st.session_state.dossie_periodo = "1a"

    periodo = st.radio(
        "Período",
        PERIODOS,
        index=PERIODOS.index(st.session_state.get("dossie_periodo", "1a")),
        horizontal=True,
        key="dossie_radio_periodo",
    )
    st.session_state.dossie_periodo = periodo

    st.markdown("---")

    # — Carregamento centralizado: uma única sessão para todos os dados de analise_fii —
    with get_session_ctx() as session:
        dados = analise_fii.load_dados_analise(ticker, session, periodo=periodo)

    # Exibir info do fundo logo abaixo do seletor
    info = dados["info"]
    if info:
        st.caption(
            f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
            f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}"
        )

    st.markdown("---")

    # — 9 tabs planas (sem hierarquia aninhada) —
    (
        tab_geral, tab_val, tab_div, tab_saude, tab_comp,
        tab_dist, tab_risco, tab_preco, tab_eventos,
    ) = st.tabs([
        "📊 Visão Geral",
        "📈 Valuation",
        "💰 Dividendos",
        "🏥 Saúde & PL",
        "🧩 Composição",
        "⚖️ Distribuição vs Geração",
        "⚡ Risco & Retorno",
        "🕯️ Preço & Volume",
        "🔬 Eventos CVM",
    ])

    with tab_geral:
        analise_fii.render_visao_geral(ticker, dados, key_prefix="dossie_geral")

    with tab_val:
        st.subheader("Valuation")
        analise_fii.render_valuation(ticker, dados, key_prefix="dossie_val")
        st.markdown("---")
        st.subheader("P/VP Histórico (médias de longo prazo)")
        fundamentos.render_pvp_historico(ticker, key_prefix="dossie_pvphist")

    with tab_div:
        st.subheader("Dividendos")
        analise_fii.render_dividendos(ticker, dados, key_prefix="dossie_div")
        st.markdown("---")
        st.subheader("DY Histórico")
        fundamentos.render_dy_historico(ticker, key_prefix="dossie_dyhist")
        st.markdown("---")
        st.subheader("Próximas Datas-Com")
        analise_fii.render_datas_com(ticker, dados, key_prefix="dossie_datas")

    with tab_saude:
        st.subheader("Saúde do Fundo")
        analise_fii.render_saude(ticker, dados, key_prefix="dossie_sau")
        st.markdown("---")
        st.subheader("Patrimônio Líquido & Cotas")
        fundamentos.render_pl_cotas(ticker, key_prefix="dossie_pl")

    with tab_comp:
        st.subheader("Composição do Ativo")
        analise_fii.render_composicao(ticker, dados, key_prefix="dossie_comp")

    with tab_dist:
        st.subheader("Distribuição vs Geração")
        fundamentos.render_distribuicao_vs_geracao(ticker, key_prefix="dossie_dist")

    with tab_risco:
        st.subheader("Risco & Retorno")
        fundamentos.render_risco_retorno(ticker, key_prefix="dossie_risco")

    with tab_preco:
        st.subheader("Preço & Volume")
        analise_fii.render_preco_volume(ticker, dados, key_prefix="dossie_pv")

    with tab_eventos:
        st.subheader("Eventos CVM — Event Study Discreto")
        fund_eventstudy.render(ticker=ticker, key_prefix="dossie_fcs")

    render_footer()


main()
