import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.snapshot_ui import (
    load_panorama_snapshot,
    load_radar_snapshot,
    render_snapshot_info,
)
from app.components.tables import render_panorama_table
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.config import TICKERS, tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.data_loader import get_ifix_ytd
from src.fii_analysis.features.portfolio import carteira_panorama
from src.fii_analysis.features.radar import radar_matriz

safe_set_page_config(page_title="Panorama", page_icon="bar_chart", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Panorama", "Operar")
    render_page_header(
        "Panorama",
        "Comparacao rapida do universo curado, com metricas ponto-no-tempo e leitura de radar em uma unica tela.",
        "Operar",
    )
    render_inline_note(
        "Use esta pagina para comparar nomes antes de descer para Analise FII ou Fundamentos. O foco aqui e triagem, nao aprofundamento."
    )

    meta, df = load_panorama_snapshot("curado")
    _, radar_df = load_radar_snapshot("curado")

    with get_session_ctx() as session:
        ifix_ytd = get_ifix_ytd(session)
        if meta is None or df.empty:
            # Fallback: respeitar escopo curado (TICKERS ∩ ativos no banco)
            ativos_set = set(tickers_ativos(session))
            curado = [t for t in TICKERS if t in ativos_set]
            df = carteira_panorama(curado, session)
            radar_df = radar_matriz(tickers=curado, session=session)
            n_tickers = len(curado)
        else:
            n_tickers = len(df)

    if meta is not None and not df.empty:
        render_snapshot_info(meta)
    elif meta is None:
        st.caption("Calculado em tempo real (snapshot nao disponivel).")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("FIIs Ativos", n_tickers)

    if not df.empty:
        avg_dy = df["dy_12m"].dropna().mean()
        avg_pvp = df["pvp"].dropna().mean()
        col2.metric("DY 12m Medio", f"{avg_dy:.2%}" if avg_dy else "n/d")
        col3.metric("P/VP Medio", f"{avg_pvp:.2f}" if avg_pvp else "n/d")
    else:
        col2.metric("DY 12m Medio", "n/d")
        col3.metric("P/VP Medio", "n/d")

    col4.metric("IFIX YTD", f"{ifix_ytd:.2%}" if ifix_ytd is not None else "n/d")

    st.markdown("---")

    if not df.empty:
        radar_pass = set()
        if not radar_df.empty:
            radar_pass = set(radar_df[radar_df["vistos"] >= 3]["ticker"].tolist())

        display = render_panorama_table(df)

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                "Segmento": st.column_config.TextColumn("Segmento"),
                "CVM Defasada": st.column_config.CheckboxColumn("CVM Defasada"),
            },
        )

        st.markdown(f"**FIIs com radar OK (>= 3 filtros):** {', '.join(sorted(radar_pass)) if radar_pass else 'Nenhum'}")

        st.caption("Dados calculados point-in-time. Atualize precos via CLI: `fii update-prices`")

    render_footer()


main()
