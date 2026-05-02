import functools
import logging
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))
if str(PROJECT_ROOT.parent / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent / "src"))

logger = logging.getLogger(__name__)


def safe_set_page_config(**kwargs):
    """Configura a página quando rodando isoladamente.

    Com `st.navigation`, o page config deve ser definido apenas no entrypoint
    do app. As páginas filhas continuam podendo rodar isoladas durante
    desenvolvimento, então ignoramos a exceção específica nesse contexto.
    """
    try:
        st.set_page_config(**kwargs)
    except Exception as exc:
        if exc.__class__.__name__ != "StreamlitSetPageConfigMustBeFirstCommandError":
            raise


def init_session_state():
    defaults = {
        "carteira_dirty": True,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_footer():
    from src.fii_analysis.data.database import get_ultima_coleta

    result = get_ultima_coleta()
    if result is not None:
        ts = result.strftime("%d/%m/%Y %H:%M") if hasattr(result, "strftime") else str(result)
        st.sidebar.caption(f"Dados atualizados em: {ts}")
    else:
        st.sidebar.caption("Dados atualizados em: n/d")


def safe_page(func):
    """Decorator que captura excecoes nao tratadas em paginas Streamlit.

    Evita tracebacks Python crus para o usuario. Mostra mensagem amigavel
    e garante que o footer seja renderizado mesmo em caso de erro.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Erro na pagina {func.__name__}")
            st.error(f"Erro ao carregar esta pagina: {e}")
            st.caption("Verifique se os dados estao atualizados via CLI: `fii update-prices` e `fii load-database`")
            render_footer()
    return wrapper
