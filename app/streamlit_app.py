import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.ui_shell import (
    render_home_card,
    render_inline_note,
    render_page_header,
    render_sidebar_guide,
)
from app.state import init_session_state, render_footer
from src.fii_analysis.data.database import create_tables

st.set_page_config(
    page_title="FII Analysis",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    initial_sidebar_state="expanded",
)

def render_home():
    render_sidebar_guide("Inicio", "Entrada")
    render_page_header(
        "FII Analysis",
        "Suite de analise de FIIs com separacao entre operacao diaria, investigacao por fundo e auditoria estatistica.",
        "Entrada",
    )
    render_inline_note(
        "Comece por Hoje para um veredito diario, Carteira para revisar holdings, "
        "Panorama para comparar o universo, ou Dossie para investigar um FII em profundidade."
    )

    st.subheader("Fluxo recomendado")
    col1, col2, col3 = st.columns(3)
    with col1:
        render_home_card(
            "Diario",
            "Camada de uso diario para decidir o que merece atencao agora e o que fazer com a carteira.",
            [
                "Hoje: cockpit operacional do dia",
                "Carteira: sugestoes sobre holdings",
                "Panorama e Radar: comparacao rapida do universo",
            ],
        )
    with col2:
        render_home_card(
            "Investigacao",
            "Camada para ler um fundo com profundidade antes de agir.",
            [
                "Dossie do FII: valuation + fundamentos + eventos por ticker",
                "Alertas: historico objetivo do que mudou",
                "Event Study (universo): impacto medio de data-com",
            ],
        )
    with col3:
        render_home_card(
            "Tecnico",
            "Camada para validar robustez dos sinais e interpretar os modelos com mais cuidado.",
            [
                "Laboratorio: Otimizador V2, Episodios e Walk-Forward em abas",
                "Uso principal: investigacao metodologica, baixa frequencia",
            ],
        )

    st.markdown("---")
    st.subheader("Jornada sugerida")
    st.markdown(
        """
        1. `Hoje` para saber o que merece atencao agora.
        2. `Carteira` para cruzar holdings com os sinais do dia.
        3. `Panorama` e `Radar` para comparar o universo curado.
        4. `Dossie do FII` para aprofundar um nome especifico.
        5. `Laboratorio` para auditar a robustez dos sinais antes de agir.
        """
    )

    render_footer()


init_session_state()
create_tables()

home_page = st.Page(render_home, title="Inicio", icon=":material/home:", default=True)

# Diario
hoje_page = st.Page("pages/13_Hoje.py", title="Hoje", icon=":material/today:")
carteira_page = st.Page("pages/3_Carteira.py", title="Carteira", icon=":material/account_balance_wallet:")
panorama_page = st.Page("pages/1_Panorama.py", title="Panorama", icon=":material/table_chart:")
radar_page = st.Page("pages/4_Radar.py", title="Radar", icon=":material/radar:")

# Investigacao
dossie_page = st.Page("pages/14_Dossie_FII.py", title="Dossie do FII", icon=":material/folder_open:")
alertas_page = st.Page("pages/6_Alertas.py", title="Alertas", icon=":material/notifications:")
event_study_page = st.Page("pages/5_Event_Study.py", title="Event Study (Universo)", icon=":material/science:")

# Tecnico
laboratorio_page = st.Page("pages/15_Laboratorio.py", title="Laboratorio", icon=":material/biotech:")

pg = st.navigation(
    {
        "Entrada": [home_page],
        "Diario": [hoje_page, carteira_page, panorama_page, radar_page],
        "Investigacao": [dossie_page, alertas_page, event_study_page],
        "Tecnico": [laboratorio_page],
    },
    position="sidebar",
)
pg.run()
