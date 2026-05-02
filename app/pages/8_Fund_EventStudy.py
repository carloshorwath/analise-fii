import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.page_content.fund_eventstudy import render
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Event Study CVM", page_icon="clipboard", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Fund Event Study", "Auditar")
    render_page_header(
        "Fund Event Study",
        "Event study por eventos discretos derivados dos informes CVM, com foco em impactos anormais ligados a deterioracao ou sinais de alerta.",
        "Auditar",
    )
    render_inline_note(
        "Aqui a leitura foi reorganizada para mostrar primeiro os eventos individuais, depois a distribuicao agregada e, por fim, o placebo."
    )

    render(ticker=None, key_prefix="fcs_page")
    render_footer()


main()
