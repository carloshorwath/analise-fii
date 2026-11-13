import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.aviso_ui import rotulo_acao
from app.components.carteira_ui import load_carteira_db
from app.components.snapshot_ui import (
    RADAR_N_CRITERIOS,
    load_universo_snapshot,
    tickers_universo_exibido,
)
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.data_loader import get_ifix_ytd
from src.fii_analysis.features.portfolio import carteira_panorama
from src.fii_analysis.features.radar import radar_matriz

safe_set_page_config(page_title="Panorama", page_icon="bar_chart", layout="wide")

# Colunas a exibir na tabela (ordem visual definitiva)
_COLS_DISPLAY = [
    "ticker", "segmento", "acao",
    "preco", "pvp", "pvp_percentil",
    "dy_12m", "dy_gap", "dy_gap_percentil", "dy_gap_alto",
    "volume_medio_21d",
    "score_total",
    "vistos", "pvp_baixo", "saude_ok", "liquidez_ok",
    "cvm_defasada",
]

# Colunas percentuais armazenadas como decimais (0.117 → 11.7%)
# que devem ser multiplicadas por 100 antes de exibir no st.dataframe
_PCT_DECIMAL_COLS = ["dy_12m", "dy_gap"]


def _build_display_df(
    df: pd.DataFrame,
    radar_df: pd.DataFrame,
    decisions_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Monta DataFrame pronto para st.dataframe com valores numéricos."""
    display = df.copy()

    # Converter porcentagens decimais → valor em % (para format="%.1f%%")
    for col in _PCT_DECIMAL_COLS:
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce") * 100

    # Merge radar inline
    if not radar_df.empty and "ticker" in radar_df.columns:
        radar_cols = [
            c for c in
            ["ticker", "pvp_baixo", "dy_gap_alto", "saude_ok", "liquidez_ok", "vistos"]
            if c in radar_df.columns
        ]
        display = display.merge(radar_df[radar_cols], on="ticker", how="left")
        for bool_col in ["pvp_baixo", "dy_gap_alto", "saude_ok", "liquidez_ok"]:
            if bool_col in display.columns:
                display[bool_col] = display[bool_col].fillna(False).astype(bool)
        if "vistos" in display.columns:
            display["vistos"] = display["vistos"].fillna(0).astype(int)

    # Merge decisions inline (acao do dia)
    if decisions_df is not None and not decisions_df.empty and "ticker" in decisions_df.columns:
        dec_cols = [c for c in ["ticker", "acao"] if c in decisions_df.columns]
        display = display.merge(decisions_df[dec_cols], on="ticker", how="left")
        if "acao" in display.columns:
            display["acao"] = display["acao"].map(lambda a: rotulo_acao(a) if isinstance(a, str) else None)

    # Ordenação padrão: DY Gap %ile descendente
    if "dy_gap_percentil" in display.columns:
        display = display.sort_values(
            "dy_gap_percentil", ascending=False, na_position="last"
        )

    # Retornar apenas colunas disponíveis na ordem definida
    cols = [c for c in _COLS_DISPLAY if c in display.columns]
    return display[cols]


def _column_config() -> dict:
    return {
        "ticker": st.column_config.TextColumn(
            "Ticker", width="small"
        ),
        "segmento": st.column_config.TextColumn(
            "Segmento", width="medium"
        ),
        "acao": st.column_config.TextColumn(
            "Leitura do dia",
            help="Estado descritivo dos indicadores (favoraveis, desfavoraveis, neutro, alerta de risco). Nao e recomendacao.",
            width="small",
        ),
        "preco": st.column_config.NumberColumn(
            "Preço", format="R$ %.2f",
            help="Último preço de fechamento disponível"
        ),
        "pvp": st.column_config.NumberColumn(
            "P/VP", format="%.2f",
            help="Preço / Valor Patrimonial por cota (point-in-time)"
        ),
        "pvp_percentil": st.column_config.NumberColumn(
            "P/VP %ile", format="%.0f%%",
            help="Percentil histórico do P/VP (504 pregões). Menor = mais barato historicamente."
        ),
        "dy_12m": st.column_config.NumberColumn(
            "DY 12m %", format="%.1f%%",
            help="Dividend Yield trailing 12 meses"
        ),
        "dy_gap": st.column_config.NumberColumn(
            "DY Gap %", format="%.1f%%",
            help="DY 12m − CDI 12m. Positivo = FII paga mais que o CDI."
        ),
        "dy_gap_percentil": st.column_config.NumberColumn(
            "DY Gap %ile", format="%.0f%%",
            help="Percentil histórico do DY Gap. Maior = DY gap alto em relação à própria história do fundo."
        ),
        "volume_medio_21d": st.column_config.NumberColumn(
            "Vol 21d", format="R$ %.0f",
            help="Volume financeiro médio dos últimos 21 pregões"
        ),
        "score_total": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d",
            help="Score composto 0–100 (Valuation 35% + Risco 30% + Liquidez 20% + Histórico 15%)"
        ),
        "vistos": st.column_config.ProgressColumn(
            "Radar", min_value=0, max_value=RADAR_N_CRITERIOS, format=f"%d/{RADAR_N_CRITERIOS}",
            help="Número de critérios do radar satisfeitos: P/VP↓, Saúde, Liquidez. DY Gap↑ é mostrado à parte (regime)."
        ),
        "pvp_baixo": st.column_config.CheckboxColumn(
            "P/VP ↓",
            help="P/VP no percentil barato (< p30 histórico)"
        ),
        "dy_gap_alto": st.column_config.CheckboxColumn(
            "Regime (DY Gap ↑)",
            help="Indicador de regime de mercado (DY Gap > p70 histórico). Fora da contagem do radar."
        ),
        "saude_ok": st.column_config.CheckboxColumn(
            "Saúde ✓",
            help="Sem flag de destruição de capital"
        ),
        "liquidez_ok": st.column_config.CheckboxColumn(
            "Liquidez ✓",
            help="Volume médio 21d acima do piso mínimo de liquidez"
        ),
        "cvm_defasada": st.column_config.CheckboxColumn(
            "CVM !",
            help="Dados CVM com mais de 45 dias sem atualização"
        ),
    }


@safe_page
def main():
    render_sidebar_guide("Panorama", "Operar")
    render_page_header(
        "Panorama",
        "Comparacao rapida do universo exibido (carteira + curados) — metricas ponto-no-tempo e radar em uma unica tabela.",
        "Operar",
    )
    render_inline_note(
        "Tabela ordenável por qualquer coluna. Use P/VP %ile e DY Gap %ile para triagem rápida. "
        "Clique em um ticker para ir ao Dossiê e aprofundar a análise."
    )

    # ── Carga de dados ───────────────────────────────────────────────────────
    carteira_tickers = [h["ticker"] for h in load_carteira_db()]
    ver_ifix = st.toggle("Ver o universo IFIX inteiro do snapshot", value=False, key="pan_ifix")
    meta, df, radar_df, decisions_df = load_universo_snapshot(
        None if ver_ifix else tuple(tickers_universo_exibido(carteira_tickers))
    )

    with get_session_ctx() as session:
        ifix_ytd = get_ifix_ytd(session)
        if meta is None or df.empty:
            with st.spinner("Calculando dados em tempo real (snapshot nao disponivel)..."):
                curado = tickers_universo_exibido(carteira_tickers)
                df = carteira_panorama(curado, session)
                radar_df = radar_matriz(tickers=curado, session=session)
                n_tickers = len(curado)
        else:
            n_tickers = len(df)

    # ── Badge de frescor (caption discreto, não st.info de bloco inteiro) ───
    if meta is not None:
        ts = meta.get("finalizado_em")
        ts_str = ts.strftime("%d/%m %H:%M") if ts else "?"
        stale = meta.get("is_stale", False)
        if stale:
            st.warning(
                f"⚠️ Snapshot desatualizado — gerado em {ts_str}. "
                "Execute `fii update-prices` para atualizar."
            )
        else:
            st.caption(
                f"📦 Dados do snapshot de {ts_str} · universo: "
                + ("IFIX inteiro" if ver_ifix else "carteira + curados")
            )
        falhos = meta.get("tickers_falhos", [])
        if falhos:
            st.caption(f"Tickers com falha: {', '.join(falhos)}")
    else:
        st.caption("⚡ Calculado em tempo real (snapshot não disponível).")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    radar_ok_count = 0
    if not radar_df.empty and "vistos" in radar_df.columns:
        radar_ok_count = int((radar_df["vistos"] >= RADAR_N_CRITERIOS).sum())

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("FIIs no universo", n_tickers)

    if not df.empty:
        avg_dy = df["dy_12m"].dropna().mean()
        avg_pvp = df["pvp"].dropna().mean()
        col2.metric(
            "DY 12m Médio",
            f"{avg_dy:.2%}" if pd.notna(avg_dy) else "—"
        )
        col3.metric(
            "P/VP Médio",
            f"{avg_pvp:.2f}" if pd.notna(avg_pvp) else "—",
            delta="desconto" if avg_pvp < 0.98 else "ágio" if avg_pvp > 1.02 else "neutro",
            delta_color="inverse" if avg_pvp < 0.98 or avg_pvp > 1.02 else "off"
        )
    else:
        col2.metric("DY 12m Médio", "—")
        col3.metric("P/VP Médio", "—")

    col4.metric(
        f"Radar {RADAR_N_CRITERIOS}/{RADAR_N_CRITERIOS}",
        str(radar_ok_count),
        delta=f"{(radar_ok_count/n_tickers)*100:.1f}% da base" if n_tickers > 0 else None,
        delta_color="off",
        help="FIIs satisfazendo todos os critérios do radar (descritivo, sem poder preditivo comprovado)"
    )
    col5.metric(
        "IFIX YTD",
        f"{ifix_ytd:.2%}" if ifix_ytd is not None else "—"
    )

    st.markdown("---")

    # ── Tabela principal ──────────────────────────────────────────────────────
    if df.empty:
        st.info("Nenhum dado disponível. Execute `fii update-prices` e gere o snapshot.")
    else:
        display = _build_display_df(df, radar_df, decisions_df)

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            height=38 + 35 * len(display),
            column_config=_column_config(),
        )

        st.caption(
            "Colunas P/VP %ile e DY Gap %ile são percentis históricos (504 pregões). "
            "Radar: P/VP ↓ · Saúde ✓ · Liquidez ✓ (DY Gap ↑ à parte, como regime). "
            "Dados calculados point-in-time. Atualize via CLI: `fii update-prices`"
        )

    render_footer()


main()
