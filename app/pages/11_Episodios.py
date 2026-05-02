import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.page_content.episodios import render
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config

safe_set_page_config(page_title="Episodios P/VP", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Episodios", "Auditar")
    render_page_header(
        "Episodios",
        "Auditoria de extremos de P/VP com traducao para uma simulacao operacional legivel, sem misturar sinais sobrepostos.",
        "Auditar",
    )
    render_inline_note(
        "Nesta tela, a simulacao operacional vem primeiro para facilitar a leitura do que a regra teria feito com o capital ao longo do tempo."
    )

    render(key_prefix="ep_page")
    render_footer()


main()
