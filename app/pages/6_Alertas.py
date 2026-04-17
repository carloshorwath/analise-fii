import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.fii_analysis.evaluation.alertas import gerar_alertas_diarios, ALERTAS_DIR

st.set_page_config(page_title="Alertas", page_icon="bell", layout="wide")
st.title("Alertas Diarios")

# --- Generate now ---
if st.button("Gerar Alertas Agora", type="primary"):
    with st.spinner("Calculando alertas..."):
        gerar_alertas_diarios()
    st.success("Alertas gerados com sucesso!")
    st.rerun()

st.markdown("---")

# --- List existing alerts ---
st.header("Alertas Salvos")
alertas_dir = ALERTAS_DIR

if not alertas_dir.exists():
    st.info("Diretorio de alertas nao encontrado.")
    st.stop()

md_files = sorted(alertas_dir.glob("*.md"), reverse=True)
if not md_files:
    st.info("Nenhum alerta salvo encontrado.")
    st.stop()

selected = st.selectbox(
    "Selecione a data:",
    options=[f.stem for f in md_files],
    index=0,
)

selected_path = alertas_dir / f"{selected}.md"
if selected_path.exists():
    content = selected_path.read_text(encoding="utf-8")
    st.markdown(content)
else:
    st.warning("Arquivo nao encontrado.")
