import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import radar_heatmap
from app.components.carteira_ui import load_carteira_db
from app.components.aviso_ui import render_aviso_evidencia
from app.components.snapshot_ui import (
    RADAR_N_CRITERIOS,
    load_universo_snapshot,
    tickers_universo_exibido,
)
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.radar import radar_matriz

safe_set_page_config(page_title="Radar", page_icon="satellite", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# CSS — cards do radar
# ─────────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
.radar-card {
    border-radius: 12px;
    border: 1px solid #e8eaed;
    border-top: 5px solid #90a4ae;
    padding: 14px 16px;
    margin-bottom: 14px;
    background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
    transition: box-shadow .15s;
}
.radar-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,.09); }
.radar-card-3 { border-top-color: #2e7d32; }
.radar-card-2 { border-top-color: #558b2f; }
.radar-card-1 { border-top-color: #f57f17; }
.radar-card-0 { border-top-color: #c62828; }

.radar-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}
.radar-ticker {
    font-size: 1.1rem;
    font-weight: 800;
    color: #1a1a1a;
}
.radar-score {
    font-size: 0.82rem;
    font-weight: 600;
    color: #555;
}
.radar-criterion {
    font-size: 0.85rem;
    padding: 3px 0;
    display: flex;
    align-items: center;
    gap: 6px;
}
.radar-criterion .val {
    font-size: 0.78rem;
    color: #888;
    margin-left: auto;
}
.radar-criterion.fail { color: #555; }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _score_dots(vistos: int) -> str:
    filled = "●" * vistos
    empty  = "○" * (RADAR_N_CRITERIOS - vistos)
    return f"{filled}{empty} {vistos}/{RADAR_N_CRITERIOS}"


def _fmt_brl(val) -> str:
    if val is None or pd.isna(val):
        return "n/d"
    if val >= 1_000_000:
        return f"R$ {val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"R$ {val/1_000:.0f}k"
    return f"R$ {val:.0f}"


def _clean(v):
    """Retorna None se v for None ou qualquer variante de NaN (float, numpy, etc)."""
    if v is None:
        return None
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def _render_radar_card(row: dict) -> None:
    """Renderiza um card com os critérios do radar + regime (DY Gap) à parte."""
    vistos = int(row.get("vistos", 0))
    ticker = row["ticker"]

    # Linha P/VP ↓ — mostra o que estiver disponível
    pvp_val = _clean(row.get("pvp_atual"))
    pvp_pct = _clean(row.get("pvp_percentil"))
    if pvp_val is not None and pvp_pct is not None:
        pvp_str = f"P/VP {pvp_val:.2f} · p{pvp_pct:.0f}%"
    elif pvp_val is not None:
        pvp_str = f"P/VP {pvp_val:.2f}"
    else:
        pvp_str = ""

    # Linha DY Gap ↑ — mostra o que estiver disponível
    dy_gap_v = _clean(row.get("dy_gap_valor"))
    dy_gap_p = _clean(row.get("dy_gap_percentil"))
    if dy_gap_v is not None and dy_gap_p is not None:
        sign = "+" if dy_gap_v >= 0 else ""
        dygap_str = f"{sign}{dy_gap_v*100:.1f}% · p{dy_gap_p:.0f}%"
    elif dy_gap_v is not None:
        sign = "+" if dy_gap_v >= 0 else ""
        dygap_str = f"{sign}{dy_gap_v*100:.1f}%"
    elif dy_gap_p is not None:
        dygap_str = f"p{dy_gap_p:.0f}%"
    else:
        dygap_str = ""

    # Linha Saúde — só exibe motivo quando FALHOU
    saude_ok     = bool(row.get("saude_ok", True))
    saude_motivo = row.get("saude_motivo") or ""
    saude_extra  = f" — {saude_motivo}" if (not saude_ok and saude_motivo) else ""

    # Linha Liquidez
    vol     = _clean(row.get("volume_21d"))
    vol_str = _fmt_brl(vol) if vol is not None else "n/d"

    def _crit(passou: bool, label: str, valor: str = "") -> str:
        icon = "✅" if passou else "❌"
        cls  = "" if passou else " fail"
        val_html = f'<span class="val">{valor}</span>' if valor else ""
        return (
            f'<div class="radar-criterion{cls}">'
            f'{icon} {label}{val_html}'
            f'</div>'
        )

    card_html = f"""
<div class="radar-card radar-card-{vistos}">
  <div class="radar-card-header">
    <span class="radar-ticker">{ticker}</span>
    <span class="radar-score">{_score_dots(vistos)}</span>
  </div>
  {_crit(bool(row.get("pvp_baixo")),  "P/VP baixo", pvp_str)}
  {_crit(bool(row.get("saude_ok")),   f"Saúde{saude_extra}", "")}
  {_crit(bool(row.get("liquidez_ok")), "Liquidez", vol_str)}
  <div class="radar-criterion fail" style="border-top:1px dashed #ddd;margin-top:4px">
    Regime de mercado: DY Gap {"alto" if row.get("dy_gap_alto") else "não alto"}
    <span class="val">{dygap_str}</span>
  </div>
</div>
"""
    st.markdown(card_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@safe_page
def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    render_sidebar_guide("Radar", "Operar")
    render_page_header(
        "Radar",
        "Matriz booleana descritiva — estado de cada fundo nos critérios, sem score arbitrário.",
        "Operar",
    )
    render_inline_note(
        "3 critérios: P/VP ↓ (percentil < 30) · Saúde (sem destruição de capital) · "
        "Liquidez (vol 21d > R$ 500k). DY Gap ↑ (percentil > 70) aparece à parte, como regime de mercado. "
        "Descreve o estado atual — siga para o Dossiê para aprofundar."
    )
    render_aviso_evidencia()

    # ── Carga de dados (snapshot-first, universo unico: carteira + curados) ──
    carteira_tickers = [h["ticker"] for h in load_carteira_db()]
    universo_alvo = tickers_universo_exibido(carteira_tickers)
    ver_ifix = st.toggle("Ver o universo IFIX inteiro do snapshot", value=False, key="radar_ifix")
    meta, df_pan, df, _ = load_universo_snapshot(None if ver_ifix else tuple(universo_alvo))

    if meta is None or df.empty:
        with get_session_ctx() as session:
            with st.spinner("Calculando dados em tempo real (snapshot nao disponivel)..."):
                df = radar_matriz(tickers=universo_alvo, session=session)
        if df.empty:
            st.warning("Nenhum dado disponível. Execute os scripts de ingestaão e gere o snapshot.")
            st.stop()
        st.caption("⚡ Calculado em tempo real (snapshot não disponível).")
    else:
        if not df_pan.empty:
            # Enriquecer flags do radar com dados numéricos do panorama do snapshot
            num_cols = ["ticker", "pvp", "pvp_percentil", "dy_gap", "dy_gap_percentil", "volume_medio_21d"]
            df_num = df_pan[[c for c in num_cols if c in df_pan.columns]].rename(columns={
                "pvp": "pvp_atual",
                "dy_gap": "dy_gap_valor",
                "volume_medio_21d": "volume_21d",
            })
            df = df.merge(df_num, on="ticker", how="left")
        ts = meta.get("finalizado_em")
        ts_str = ts.strftime("%d/%m %H:%M") if ts else "?"
        if meta.get("is_stale", False):
            st.warning(f"⚠️ Snapshot desatualizado (gerado em {ts_str}).")
        else:
            st.caption(f"📦 Dados do snapshot de {ts_str} (referência {meta['data_referencia']:%d/%m}).")
    df = df.sort_values(["vistos", "ticker"], ascending=[False, True]).reset_index(drop=True)

    if df.empty:
        st.info("Nenhum dado no radar.")
        render_footer()
        return

    # ── KPIs rápidos ─────────────────────────────────────────────────────────
    n = RADAR_N_CRITERIOS
    n_full  = int((df["vistos"] == n).sum())
    n_2     = int((df["vistos"] >= n - 1).sum())
    n_total = len(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("FIIs no radar", n_total)
    c2.metric(f"Passou {n}/{n}", n_full,
              help="Todos os critérios satisfeitos")
    c3.metric(f"Passou ≥{n - 1}/{n}", n_2,
              help="Ao menos n-1 critérios satisfeitos (descritivo)")
    c4.metric(f"Passou 0/{n}", int((df["vistos"] == 0).sum()),
              help="Nenhum critério satisfeito")

    st.markdown("---")

    # ── Heatmap visão macro ───────────────────────────────────────────────────
    st.plotly_chart(radar_heatmap(df), use_container_width=True)

    st.markdown("---")

    # ── Cards por ticker em 3 colunas ────────────────────────────────────────
    st.subheader("Detalhes por FII")

    records = df.to_dict(orient="records")
    # 3 colunas
    col_a, col_b, col_c = st.columns(3)
    cols_cycle = [col_a, col_b, col_c]
    for i, row in enumerate(records):
        with cols_cycle[i % 3]:
            _render_radar_card(row)

    # ── Rodapé ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "**P/VP ↓**: percentil histórico < 30% (504 pregões) — "
        "**Saúde**: sem destruição de capital detectada — "
        "**Liquidez**: volume médio 21d ≥ R$ 500k — "
        "**Regime**: DY Gap com percentil histórico > 70% (252 pregões), fora da contagem"
    )

    # Export com colunas legíveis
    _export_cols = {
        "ticker": "Ticker",
        "vistos": f"Criterios (0-{RADAR_N_CRITERIOS})",
        "pvp_baixo": "P/VP Baixo",
        "dy_gap_alto": "Regime DY Gap Alto",
        "saude_ok": "Saude OK",
        "liquidez_ok": "Liquidez OK",
        "pvp_atual": "P/VP Atual",
        "pvp_percentil": "P/VP %ile",
        "dy_gap_valor": "DY Gap",
        "dy_gap_percentil": "DY Gap %ile",
        "volume_21d": "Volume 21d",
        "saude_motivo": "Motivo Saude",
    }
    df_exp = df[[c for c in _export_cols if c in df.columns]].rename(columns=_export_cols)
    for col in ["P/VP Baixo", "Regime DY Gap Alto", "Saude OK", "Liquidez OK"]:
        if col in df_exp.columns:
            df_exp[col] = df_exp[col].map({True: "Sim", False: "Nao"}).fillna("n/d")
    csv = df_exp.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Exportar CSV", csv, "radar_fii.csv", "text/csv", key="download_csv_radar"
    )

    render_footer()


main()
