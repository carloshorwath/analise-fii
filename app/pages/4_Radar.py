import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import radar_heatmap
from app.components.snapshot_ui import load_radar_snapshot, render_snapshot_info
from app.components.tables import render_radar_matriz
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.components.carteira_ui import load_carteira_db
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.config import TICKERS, tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.radar import radar_matriz
import pandas as pd

safe_set_page_config(page_title="Radar", page_icon="satellite", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Radar", "Operar")
    render_page_header(
        "Radar",
        "Matriz booleana combinando o universo curado e a sua carteira para triagem rapida. A tela responde onde vale olhar primeiro, sem condensar tudo em um score arbitrario.",
        "Operar",
    )
    render_inline_note(
        "Trate o radar como filtro inicial. Quando um nome parecer interessante, siga para Analise FII ou Fundamentos para leitura completa."
    )

    meta, df = load_radar_snapshot("curado")

    with get_session_ctx() as session:
        ativos_set = set(tickers_ativos(session))
        curado = [t for t in TICKERS if t in ativos_set]
        
        carteira = load_carteira_db()
        carteira_tickers = [h["ticker"] for h in carteira if h["ticker"] in ativos_set]
        
        universo_alvo = sorted(set(curado + carteira_tickers))

        if meta is None or df.empty:
            # Fallback total: calcular na hora para o universo alvo
            df = radar_matriz(tickers=universo_alvo, session=session)
            if df.empty:
                st.warning("Nenhum dado disponivel para o radar. Execute os scripts de ingestao.")
                st.stop()
            st.caption("Calculado em tempo real (snapshot nao disponivel).")
        else:
            # Snapshot curado existe. Verificar se ha tickers da carteira faltando
            tickers_no_snapshot = set(df["ticker"].tolist())
            tickers_faltantes = [t for t in universo_alvo if t not in tickers_no_snapshot]
            
            if tickers_faltantes:
                # Calcular radar na hora apenas para os faltantes
                df_faltantes = radar_matriz(tickers=tickers_faltantes, session=session)
                if not df_faltantes.empty:
                    df = pd.concat([df, df_faltantes], ignore_index=True)
                st.caption(f"Snapshot curado carregado. {len(tickers_faltantes)} FII(s) da carteira calculados em tempo real.")
            else:
                render_snapshot_info(meta)

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
                    "Usa janela rolling de 504 pregões.")

    with st.expander("Filtro: DY Gap Alto (percentil > 70)"):
        st.markdown("**O que significa:** O DY Gap (DY 12m - CDI 12m) esta no percentil historico mais alto (acima de 70%), "
                    "sugerindo que o dividend yield esta elevado em relacao a taxa livre de risco. "
                    "Usa janela rolling de 504 pregões.")

    with st.expander("Filtro: Saude OK"):
        st.markdown("**O que significa:** Nenhuma destruicao de capital detectada. "
                    "Verifica tres condicoes alinhadas: rentabilidade efetiva > patrimonial por 3+ meses consecutivos, "
                    "cotas estaveis, e VP/cota sem tendencia positiva.")

    with st.expander("Filtro: Liquidez OK"):
        st.markdown("**O que significa:** Volume financeiro medio dos ultimos 21 pregões acima do piso configurado "
                    "(default: R$ 500.000). Garante que ha liquidez suficiente para entrada/saida.")

    st.markdown("---")

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Exportar CSV", csv, "radar_fii.csv", "text/csv", key="download_csv")

    render_footer()


main()
