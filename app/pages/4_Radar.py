import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import radar_heatmap
from app.components.data_loader import load_radar
from app.components.tables import render_radar_matriz
from app.state import render_footer

st.set_page_config(page_title="Radar", page_icon="satellite", layout="wide")
st.title("Radar — Matriz Booleana")

df = load_radar()

if df.empty:
    st.warning("Nenhum dado disponivel para o radar. Execute os scripts de ingestao.")
    st.stop()

st.plotly_chart(radar_heatmap(df), use_container_width=True)

st.markdown("---")
st.header("Detalhes por FII")

display = render_radar_matriz(df)
st.dataframe(display, use_container_width=True, hide_index=True)

st.markdown("---")

saude_motivos = []
for _, row in df.iterrows():
    if not row.get("saude_ok", True) and row.get("saude_motivo"):
        saude_motivos.append(f"**{row['ticker']}**: {row['saude_motivo']}")
if saude_motivos:
    st.subheader("Motivos de falha na saude")
    for m in saude_motivos:
        st.markdown(f"- {m}")

st.markdown("---")

with st.expander("Filtro: P/VP Baixo (percentil < 30)"):
    st.markdown("**O que significa:** O P/VP do FII esta no percentil historico mais baixo (abaixo de 30%), "
                "sugerindo que pode estar negociando abaixo do seu valor patrimonial historico. "
                "Usa janela rolling de 504 pregOes.")

with st.expander("Filtro: DY Gap Alto (percentil > 70)"):
    st.markdown("**O que significa:** O DY Gap (DY 12m - CDI 12m) esta no percentil historico mais alto (acima de 70%), "
                "sugerindo que o dividend yield esta elevado em relacao a taxa livre de risco. "
                "Usa janela rolling de 504 pregOes.")

with st.expander("Filtro: Saude OK"):
    st.markdown("**O que significa:** Nenhuma destruicao de capital detectada. "
                "Verifica tres condicoes alinhadas: rentabilidade efetiva > patrimonial por 3+ meses consecutivos, "
                "cotas estaveis, e VP/cota sem tendencia positiva.")

with st.expander("Filtro: Liquidez OK"):
    st.markdown("**O que significa:** Volume financeiro medio dos ultimos 21 pregOes acima do piso configurado "
                "(default: R$ 500.000). Garante que ha liquidez suficiente para entrada/saida.")

st.markdown("---")

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("Exportar CSV", csv, "radar_fii.csv", "text/csv", key="download_csv")

render_footer()
