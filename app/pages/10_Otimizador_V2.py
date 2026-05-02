import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.page_content.otimizador_v2 import render
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Otimizador V2", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Otimizador V2", "Auditar")
    render_page_header(
        "Otimizador V2",
        "Camada de auditoria robusta para thresholds de P/VP, com foco em qualidade do sinal, risco ajustado e interpretacao operacional.",
        "Auditar",
    )
    render_inline_note(
        "A ordem desta tela foi reorganizada para mostrar primeiro o resultado e o comportamento operacional, deixando a auditoria mais profunda logo depois."
    )

    render(key_prefix="optv2_page")
    render_footer()


main()
