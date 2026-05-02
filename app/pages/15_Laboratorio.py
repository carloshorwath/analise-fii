import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.page_content import episodios, otimizador_v2, walkforward
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Laboratorio", page_icon="science", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Laboratorio", "Auditar")
    render_page_header(
        "Laboratorio (Backtest)",
        "Camada de auditoria estatistica e modelos. Tres ferramentas para validar robustez antes de operar com base nos sinais.",
        "Auditar",
    )
    render_inline_note(
        "Otimizador V2 ajusta thresholds com risco ajustado e diagnostico de overfitting. "
        "Episodios isola eventos extremos discretos. Walk-Forward valida out-of-sample com janela rolante. "
        "Use as abas abaixo conforme a pergunta que voce quer responder."
    )

    tab_otimizador, tab_episodios, tab_walkforward = st.tabs(
        ["Otimizador V2", "Episodios", "Walk-Forward"]
    )

    with tab_otimizador:
        otimizador_v2.render(key_prefix="lab_optv2", show_sidebar_note=False)

    with tab_episodios:
        episodios.render(key_prefix="lab_ep")

    with tab_walkforward:
        walkforward.render(key_prefix="lab_wf")

    render_footer()


main()
