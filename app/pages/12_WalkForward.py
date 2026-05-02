import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.page_content.walkforward import render
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Walk-Forward", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Walk-Forward", "Auditar")
    render_page_header(
        "Walk-Forward",
        "Validacao out-of-sample com separacao temporal genuina, acompanhada de simulacao operacional coerente com a regra BUY→SELL.",
        "Auditar",
    )
    render_inline_note(
        "A leitura prioritaria desta tela e a simulacao operacional. A aba estatistica continua disponivel para validar a qualidade do sinal OOS."
    )

    render(key_prefix="wf_page")
    render_footer()


main()
