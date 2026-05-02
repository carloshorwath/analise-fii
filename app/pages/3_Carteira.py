import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from datetime import date as _date_today

from app.components.charts import carteira_alocacao_pie, carteira_segmento_pie
from app.components.carteira_ui import (
    delete_carteira_posicao,
    load_carteira_db,
    load_tickers_ativos,
    normalize_carteira_csv,
    save_carteira_posicao,
)
from app.components.snapshot_ui import load_carteira_advices_snapshot
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from src.fii_analysis.evaluation.daily_snapshots import compute_carteira_hash
from app.components.tables import format_currency
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import create_tables, get_session_ctx
from src.fii_analysis.decision import (
    aconselhar_carteira,
    alertas_estruturais,
    decidir_universo,
    exportar_sugestoes_csv,
    exportar_sugestoes_md,
)
from src.fii_analysis.features.portfolio import carteira_panorama, herfindahl

safe_set_page_config(page_title="Carteira", page_icon="briefcase", layout="wide")

_CSS = """
<style>
.kpi-row { display: flex; gap: 16px; margin-bottom: 24px; }
.kpi-card {
    flex: 1;
    background: #ffffff;
    border-radius: 14px;
    padding: 20px 22px;
    border: 1px solid #e8eaed;
    border-top: 4px solid #1565c0;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.kpi-card.pos { border-top-color: #2e7d32; }
.kpi-card.neg { border-top-color: #c62828; }
.kpi-card.warn { border-top-color: #e65100; }
.kpi-label { font-size: 0.72rem; color: #888; text-transform: uppercase;
             letter-spacing: .07em; margin-bottom: 6px; }
.kpi-value { font-size: 1.55rem; font-weight: 700; color: #1a1a1a; line-height: 1.2; }
.kpi-sub   { font-size: 0.78rem; color: #aaa; margin-top: 4px; }

.advice-row {
    display: flex; align-items: center; gap: 14px;
    background: #fff; border-radius: 10px;
    padding: 14px 18px; margin-bottom: 8px;
    border: 1px solid #e8eaed;
    transition: box-shadow .15s;
}
.advice-row:hover { box-shadow: 0 2px 10px rgba(0,0,0,.08); }
.advice-ticker { font-size: 1.05rem; font-weight: 700; min-width: 70px; color: #1a1a1a; }
.advice-flags  { font-size: 0.78rem; color: #888; flex: 1; }
.advice-pri    { font-size: 0.78rem; color: #555; min-width: 60px; text-align: right; }

.badge {
    display: inline-block;
    padding: 4px 12px; border-radius: 20px;
    font-size: 0.78rem; font-weight: 700;
    letter-spacing: .03em; white-space: nowrap;
}
.badge-AUMENTAR          { background:#e8f5e9; color:#2e7d32; border:1px solid #a5d6a7; }
.badge-HOLD              { background:#eceff1; color:#546e7a; border:1px solid #b0bec5; }
.badge-REDUZIR           { background:#fff3e0; color:#e65100; border:1px solid #ffcc80; }
.badge-SAIR              { background:#ffebee; color:#c62828; border:1px solid #ef9a9a; }
.badge-EVITAR_NOVOS_APORTES { background:#fffde7; color:#f57f17; border:1px solid #fff176; }

.alert-banner {
    display: flex; align-items: flex-start; gap: 12px;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;
}
.alert-atencao { background:#fff8e1; border-left: 4px solid #ffa000; }
.alert-info    { background:#e3f2fd; border-left: 4px solid #1565c0; }
.alert-icon    { font-size: 1.2rem; margin-top: 1px; }
.alert-text    { font-size: 0.88rem; color: #333; }
</style>
"""


def _badge(acao: str) -> str:
    cls = f"badge-{acao}" if acao in ("AUMENTAR", "HOLD", "REDUZIR", "SAIR", "EVITAR_NOVOS_APORTES") else "badge-HOLD"
    return f'<span class="badge {cls}">{acao}</span>'


def _kpi(label: str, value: str, sub: str = "", cls: str = "") -> str:
    return (
        f'<div class="kpi-card {cls}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )


@safe_page
def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    render_sidebar_guide("Carteira", "Operar")
    render_page_header(
        "Carteira",
        "Central de posicoes do usuario, com consolidado patrimonial, sugestoes operacionais e alertas estruturais.",
        "Operar",
    )
    render_inline_note(
        "A leitura principal desta tela e Sugestoes Operacionais. A visao patrimonial completa continua disponivel na aba seguinte."
    )

    create_tables()
    tickers = load_tickers_ativos()
    posicoes = load_carteira_db()

    # ── Pre-compute shared data ──────────────────────────────────────────────
    consol = None
    advices = []
    alertas = []
    snap_used = False

    if posicoes:
        df_pos = pd.DataFrame(posicoes)
        df_pos["valor_total"] = df_pos["quantidade"] * df_pos["preco_medio"]
        consol = df_pos.groupby("ticker").agg(
            qty=("quantidade", "sum"),
            valor_total=("valor_total", "sum"),
        ).reset_index()
        consol["preco_medio"] = consol["valor_total"] / consol["qty"]

        with get_session_ctx() as session:
            pan = carteira_panorama(consol["ticker"].tolist(), session)

        pan_prices = pan[["ticker", "preco"]].rename(columns={"preco": "preco_atual"})
        consol = consol.merge(pan_prices, on="ticker", how="left")
        consol["valor_mercado"] = consol["qty"] * consol["preco_atual"]
        consol["pl_reais"] = consol["valor_mercado"] - consol["valor_total"]
        consol["pl_pct"] = (consol["pl_reais"] / consol["valor_total"] * 100).round(2)

        precos_map = {
            r["ticker"]: r["preco_atual"]
            for _, r in consol.iterrows()
            if pd.notna(r.get("preco_atual"))
        }

        # Sugestões/Alertas: ler do snapshot de carteira (evita decidir_universo())
        c_hash = compute_carteira_hash(posicoes)
        adv_meta, advices, alertas = load_carteira_advices_snapshot(c_hash)
        snap_used = adv_meta is not None and bool(advices)

        if not snap_used:
            with st.spinner("Calculando sinais (snapshot de carteira nao disponivel)..."):
                with get_session_ctx() as session:
                    tickers_dec = list(set(consol["ticker"].tolist() + tickers_ativos(session)))
                    decisoes = decidir_universo(session, tickers=tickers_dec)
                advices = aconselhar_carteira(decisoes, posicoes, precos_atuais=precos_map)
                alertas = alertas_estruturais(advices)

        # segmento para pie
        with get_session_ctx() as session:
            pan_all = carteira_panorama(tickers_ativos(session), session)
        seg_map = (
            {r["ticker"]: r.get("segmento", "n/d") for _, r in pan_all.iterrows()}
            if not pan_all.empty else {}
        )
        consol["segmento"] = consol["ticker"].map(seg_map).fillna("n/d")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab_sugestoes, tab_visao, tab_alertas, tab_gerenciar = st.tabs([
        "Sugestões Operacionais", "Visão da Carteira", "Alertas", "Gerenciar",
    ])

    # ── TAB 1: Visão Geral ────────────────────────────────────────────────────
    with tab_visao:
        if consol is None:
            st.info("Nenhuma posição na carteira. Adicione posições na aba Gerenciar.")
        else:
            total_mercado   = consol["valor_mercado"].sum()
            total_investido = consol["valor_total"].sum()
            pl_total = total_mercado - total_investido
            pl_pct   = pl_total / total_investido * 100 if total_investido else 0
            hh_result = herfindahl(consol["valor_mercado"].fillna(0).tolist())
            hh_val = f"{hh_result['hh']:.3f}" if hh_result and hh_result.get("hh") else "n/d"

            sign = "+" if pl_total >= 0 else ""
            pl_cls = "pos" if pl_total >= 0 else "neg"

            st.markdown(
                '<div class="kpi-row">'
                + _kpi("Total a Mercado", format_currency(total_mercado), f"{len(consol)} FIIs")
                + _kpi("Total Investido", format_currency(total_investido))
                + _kpi("P&L", f"{sign}{format_currency(pl_total)}", f"{sign}{pl_pct:.1f}%", pl_cls)
                + _kpi("Herfindahl", hh_val, "Índice de concentração")
                + "</div>",
                unsafe_allow_html=True,
            )

            st.subheader("Posições consolidadas")

            def _pl_color(val):
                c = "#2e7d32" if val >= 0 else "#c62828"
                return f"color:{c};font-weight:600"

            df_display = consol[[
                "ticker", "qty", "preco_medio", "preco_atual",
                "valor_mercado", "pl_reais", "pl_pct",
            ]].copy()
            df_display.columns = [
                "Ticker", "Qtd", "PM (R$)", "Preço Atual",
                "Valor Mercado", "P&L (R$)", "P&L (%)",
            ]
            styled = (
                df_display.style
                .map(_pl_color, subset=["P&L (R$)", "P&L (%)"])
                .format({
                    "PM (R$)": "R$ {:.2f}",
                    "Preço Atual": "R$ {:.2f}",
                    "Valor Mercado": "R$ {:.2f}",
                    "P&L (R$)": "R$ {:.2f}",
                    "P&L (%)": "{:.1f}%",
                })
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(
                    carteira_alocacao_pie(consol, value_col="valor_mercado"),
                    use_container_width=True,
                )
            with col2:
                st.plotly_chart(
                    carteira_segmento_pie(consol),
                    use_container_width=True,
                )

    # ── TAB 2: Sugestões ──────────────────────────────────────────────────────
    with tab_sugestoes:
        if consol is None:
            st.info("Nenhuma posição na carteira.")
        elif not advices:
            st.info("Nenhuma sugestão gerada.")
        else:
            if snap_used:
                st.caption("Sinais carregados do snapshot do dia. Acesse a pagina 'Hoje' para detalhes completos.")
            st.caption(
                "Sugestões baseadas em regras estatísticas. "
                "**Não são ordens executáveis** — validar antes de operar."
            )

            for a in advices:
                st.markdown(
                    f'<div class="advice-row">'
                    f'<span class="advice-ticker">{a.ticker}</span>'
                    f'{_badge(a.acao_recomendada)}'
                    f'<span class="advice-flags">{a.flags_resumo or ""}</span>'
                    f'<span class="advice-pri">{a.prioridade}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                with st.expander(f"Racional — {a.ticker}"):
                    c_r1, c_r2 = st.columns([1, 3])
                    c_r1.metric("Concordância", a.nivel_concordancia)
                    c_r1.metric("Peso carteira", f"{a.peso_carteira * 100:.1f}%" if a.peso_carteira else "n/d")
                    c_r1.metric("Válida até", a.valida_ate.isoformat())
                    c_r2.write(a.racional)

            st.divider()
            data_ref = _date_today.today()
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "Baixar sugestões (MD)",
                    data=exportar_sugestoes_md(advices, data_ref),
                    file_name=f"{data_ref.isoformat()}_sugestoes_carteira.md",
                    mime="text/markdown",
                )
            with c2:
                st.download_button(
                    "Baixar sugestões (CSV)",
                    data=exportar_sugestoes_csv(advices),
                    file_name=f"{data_ref.isoformat()}_sugestoes_carteira.csv",
                    mime="text/csv",
                )

    # ── TAB 3: Alertas ────────────────────────────────────────────────────────
    with tab_alertas:
        if consol is None:
            st.info("Nenhuma posição na carteira.")
        else:
            st.caption(
                "Sinais sobre a estrutura da carteira (concentração, diversificação). "
                "**Descritivos** — indicam o que está acontecendo, não prescrevem rebalanceamento."
            )
            if not alertas:
                st.success("Sem alertas estruturais — carteira dentro dos parâmetros.")
            else:
                for al in alertas:
                    icon = "⚠️" if al.severidade == "atencao" else "ℹ️"
                    cls  = "alert-atencao" if al.severidade == "atencao" else "alert-info"
                    st.markdown(
                        f'<div class="alert-banner {cls}">'
                        f'<span class="alert-icon">{icon}</span>'
                        f'<span class="alert-text">{al.descricao}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # ── TAB 4: Gerenciar ──────────────────────────────────────────────────────
    with tab_gerenciar:
        st.subheader("Adicionar posição")
        with st.form("add_posicao"):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                novo_ticker = st.selectbox("Ticker", tickers)
            with col2:
                novo_qty = st.number_input("Quantidade", min_value=1, value=10, step=1)
            with col3:
                novo_preco = st.number_input("Preço Médio (R$)", min_value=0.01, value=100.0, step=0.01)
            with col4:
                novo_data = st.date_input("Data Compra", value=date.today())
            if st.form_submit_button("Adicionar", type="primary"):
                save_carteira_posicao(novo_ticker, novo_qty, novo_preco, novo_data)
                st.success(f"Posição adicionada: {novo_qty}x {novo_ticker} a R$ {novo_preco:.2f}")
                st.rerun()

        st.divider()

        st.subheader("Upload CSV")
        st.caption(
            "Formatos aceitos: `ticker,quantidade,preco_medio,data_compra` "
            "ou export consolidado com `Ativo,Qtd,Preço médio`."
        )
        csv_file = st.file_uploader("Escolha um arquivo CSV", type=["csv"])
        if csv_file is not None:
            try:
                df_csv = pd.read_csv(csv_file)
                records, source = normalize_carteira_csv(df_csv, default_date=date.today())
                for row in records:
                    save_carteira_posicao(
                        row["ticker"], row["quantidade"],
                        row["preco_medio"], row["data_compra"],
                    )
                if source == "broker_export":
                    st.warning("CSV sem data de compra original: foi usada a data de hoje como placeholder.")
                st.success(f"{len(records)} posições importadas com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar CSV: {e}")

        st.divider()

        st.subheader("Remover posição")
        if posicoes:
            df_pos2 = pd.DataFrame(posicoes)
            to_delete = st.selectbox(
                "Selecione a posição:",
                options=[""] + [
                    f"ID {r['id']}: {r['ticker']} {r['quantidade']}x {format_currency(r['preco_medio'])}"
                    for _, r in df_pos2.iterrows()
                ],
            )
            if to_delete and st.button("Confirmar remoção", type="secondary"):
                pos_id = int(to_delete.split(":")[0].replace("ID ", ""))
                delete_carteira_posicao(pos_id)
                st.success("Posição removida!")
                st.rerun()
        else:
            st.info("Nenhuma posição para remover.")

    render_footer()


main()
