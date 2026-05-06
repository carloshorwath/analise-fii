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

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ── KPI cards ── */
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

/* ── Badge ── */
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

/* ── Advice card ── */
.advice-card {
    background: #fff;
    border-radius: 12px;
    border: 1px solid #e8eaed;
    border-left: 5px solid #546e7a;
    padding: 16px 20px;
    margin-bottom: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
    transition: box-shadow .15s;
}
.advice-card:hover { box-shadow: 0 3px 14px rgba(0,0,0,.10); }
.advice-card-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
}
.advice-card-ticker {
    font-size: 1.15rem;
    font-weight: 800;
    color: #1a1a1a;
    min-width: 76px;
}
.advice-card-pri {
    margin-left: auto;
    font-size: 0.80rem;
    color: #555;
    font-weight: 600;
    white-space: nowrap;
}
.advice-card-ctx {
    font-size: 0.82rem;
    color: #666;
    margin-bottom: 10px;
}
.advice-card-rational {
    font-size: 0.93rem;
    color: #222;
    line-height: 1.6;
    margin-bottom: 10px;
    padding: 10px 14px;
    background: #f8f9fa;
    border-radius: 8px;
}
.advice-card-footer {
    font-size: 0.78rem;
    color: #777;
}
.advice-card-footer strong { color: #444; }

/* ── Alertas estruturais ── */
.alert-banner {
    display: flex; align-items: flex-start; gap: 12px;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;
}
.alert-atencao { background:#fff8e1; border-left: 4px solid #ffa000; }
.alert-info    { background:#e3f2fd; border-left: 4px solid #1565c0; }
.alert-icon    { font-size: 1.2rem; margin-top: 1px; }
.alert-text    { font-size: 0.88rem; color: #333; }

/* ── Priority dividers ── */
.priority-header {
    font-size: 0.88rem;
    font-weight: 700;
    color: #555;
    text-transform: uppercase;
    letter-spacing: .08em;
    margin: 20px 0 10px 0;
    padding-bottom: 6px;
    border-bottom: 2px solid #e8eaed;
}
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers de renderização
# ─────────────────────────────────────────────────────────────────────────────

_BADGE_BORDER = {
    "AUMENTAR": "#2e7d32",
    "HOLD": "#90a4ae",
    "REDUZIR": "#e65100",
    "SAIR": "#c62828",
    "EVITAR_NOVOS_APORTES": "#f57f17",
}

_PRI_LABEL = {
    "ALTA":  "⚡ ALTA",
    "MEDIA": "👀 MÉDIA",
    "BAIXA": "💤 BAIXA",
}

_PRI_SECTION = {
    "ALTA":  "⚡ Ação Imediata",
    "MEDIA": "👀 Observar",
    "BAIXA": "💤 Manter",
}


def _badge(acao: str) -> str:
    cls = f"badge-{acao}" if acao in (
        "AUMENTAR", "HOLD", "REDUZIR", "SAIR", "EVITAR_NOVOS_APORTES"
    ) else "badge-HOLD"
    return f'<span class="badge {cls}">{acao}</span>'


def _kpi(label: str, value: str, sub: str = "", cls: str = "") -> str:
    return (
        f'<div class="kpi-card {cls}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f'</div>'
    )


def _render_advice_card(a) -> None:
    """Renderiza um card rico e legível para um HoldingAdvice."""
    # P&L da posição (preço atual vs preço médio de entrada)
    pl_str = "n/d"
    pl_color = "#888"
    if a.preco_atual is not None and a.preco_medio and a.preco_medio > 0:
        pl_pct = (a.preco_atual - a.preco_medio) / a.preco_medio * 100
        sign = "+" if pl_pct >= 0 else ""
        pl_str = f"{sign}{pl_pct:.1f}%"
        pl_color = "#2e7d32" if pl_pct >= 0 else "#c62828"

    # Linha de contexto: preço atual · peso · PM · P&L
    ctx_parts = []
    if a.preco_atual is not None:
        ctx_parts.append(f"R$ {a.preco_atual:.2f} atual")
    if a.peso_carteira is not None:
        ctx_parts.append(f"Peso {a.peso_carteira * 100:.1f}%")
    if a.preco_medio:
        ctx_parts.append(f"PM R$ {a.preco_medio:.2f}")
    if pl_str != "n/d":
        ctx_parts.append(
            f"P&L <span style='color:{pl_color};font-weight:600'>{pl_str}</span>"
        )
    ctx_html = " &nbsp;·&nbsp; ".join(ctx_parts) if ctx_parts else "—"

    # Flags (destaque vermelho se há alguma)
    has_flags = a.flags_resumo and a.flags_resumo != "—"
    flags_html = (
        f"<span style='color:#c62828;font-weight:600'>{a.flags_resumo}</span>"
        if has_flags
        else "<span style='color:#999'>nenhuma</span>"
    )

    border_color = _BADGE_BORDER.get(a.acao_recomendada, "#90a4ae")
    pri_label = _PRI_LABEL.get(a.prioridade, a.prioridade)

    card_html = f"""
<div class="advice-card" style="border-left-color:{border_color}">
  <div class="advice-card-header">
    <span class="advice-card-ticker">{a.ticker}</span>
    {_badge(a.acao_recomendada)}
    <span class="advice-card-pri">{pri_label}</span>
  </div>
  <div class="advice-card-ctx">{ctx_html}</div>
  <div class="advice-card-rational">{a.racional}</div>
  <div class="advice-card-footer">
    Concordância: <strong>{a.nivel_concordancia}</strong>
    &nbsp;·&nbsp;
    Flags: {flags_html}
    &nbsp;·&nbsp;
    Válido até: <strong>{a.valida_ate.isoformat()}</strong>
  </div>
</div>
"""
    st.markdown(card_html, unsafe_allow_html=True)


def _render_advices_grouped(advices: list) -> None:
    """Renderiza os cards agrupados por prioridade com separadores visuais."""
    current_priority = None
    for a in advices:
        if a.prioridade != current_priority:
            current_priority = a.prioridade
            section_label = _PRI_SECTION.get(current_priority, current_priority)
            st.markdown(
                f'<div class="priority-header">{section_label}</div>',
                unsafe_allow_html=True,
            )
        _render_advice_card(a)


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@safe_page
def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    render_sidebar_guide("Carteira", "Operar")
    render_page_header(
        "Carteira",
        "Central de posicoes com consolidado patrimonial, sugestoes operacionais e alertas estruturais.",
        "Operar",
    )
    render_inline_note(
        "Comece pela aba Visão Geral para entender o patrimônio consolidado. "
        "Depois acesse Sugestões para as orientações táticas por posição."
    )

    create_tables()
    tickers = load_tickers_ativos()
    posicoes = load_carteira_db()

    # ── Pré-computação compartilhada ─────────────────────────────────────────
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

        # Sugestões/Alertas: preferir snapshot (evita decidir_universo() que é lento)
        c_hash = compute_carteira_hash(posicoes)
        adv_meta, advices, alertas = load_carteira_advices_snapshot(c_hash)
        snap_used = adv_meta is not None and bool(advices)

        if not snap_used:
            with st.spinner("Calculando sinais (snapshot de carteira nao disponivel)..."):
                from src.fii_analysis.models.threshold_optimizer_v2 import load_optimizer_cache
                with get_session_ctx() as session:
                    tickers_dec = list(set(consol["ticker"].tolist() + tickers_ativos(session)))
                    opt_params = {
                        t: load_optimizer_cache(t)
                        for t in tickers_dec
                        if load_optimizer_cache(t) is not None
                    }
                    decisoes = decidir_universo(
                        session, tickers=tickers_dec,
                        optimizer_params_por_ticker=opt_params or None,
                    )
                advices = aconselhar_carteira(decisoes, posicoes, precos_atuais=precos_map)
                alertas = alertas_estruturais(advices)

        # Segmento para pie chart
        with get_session_ctx() as session:
            pan_all = carteira_panorama(tickers_ativos(session), session)
        seg_map = (
            {r["ticker"]: r.get("segmento", "n/d") for _, r in pan_all.iterrows()}
            if not pan_all.empty else {}
        )
        consol["segmento"] = consol["ticker"].map(seg_map).fillna("n/d")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab_visao, tab_sugestoes, tab_alertas, tab_gerenciar = st.tabs([
        "📊 Visão Geral", "💡 Sugestões", "⚠️ Alertas", "⚙️ Gerenciar",
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
            # % de cada posição sobre o total a mercado
            consol["pct_carteira"] = (
                consol["valor_mercado"] / total_mercado * 100
                if total_mercado > 0 else 0.0
            )

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
                "valor_mercado", "pct_carteira", "pl_reais", "pl_pct",
            ]].copy()
            df_display.columns = [
                "Ticker", "Qtd", "PM (R$)", "Preço Atual",
                "Valor Mercado", "% Carteira", "P&L (R$)", "P&L (%)",
            ]
            styled = (
                df_display.style
                .map(_pl_color, subset=["P&L (R$)", "P&L (%)"])
                .format({
                    "PM (R$)": "R$ {:.2f}",
                    "Preço Atual": "R$ {:.2f}",
                    "Valor Mercado": "R$ {:.2f}",
                    "% Carteira": "{:.1f}%",
                    "P&L (R$)": "R$ {:.2f}",
                    "P&L (%)": "{:.1f}%",
                })
            )
            # Altura calculada para exibir todas as linhas sem scroll interno
            # ~35px por linha + ~38px de header
            tbl_height = 38 + 35 * len(df_display)
            st.dataframe(styled, use_container_width=True, hide_index=True, height=tbl_height)

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
            st.info("Nenhuma posição na carteira. Adicione posições na aba Gerenciar.")
        elif not advices:
            st.info("Nenhuma sugestão gerada. Execute o snapshot diário ou aguarde o cálculo automático.")
        else:
            if snap_used:
                st.caption(
                    "✅ Sinais carregados do snapshot do dia. "
                    "Acesse a página 'Hoje' para detalhes técnicos completos."
                )
            st.caption(
                "Sugestões baseadas em regras estatísticas. "
                "**Não são ordens executáveis** — validar com julgamento próprio antes de operar."
            )

            _render_advices_grouped(advices)

            st.divider()
            data_ref = _date_today.today()
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇️ Baixar sugestões (MD)",
                    data=exportar_sugestoes_md(advices, data_ref),
                    file_name=f"{data_ref.isoformat()}_sugestoes_carteira.md",
                    mime="text/markdown",
                )
            with c2:
                st.download_button(
                    "⬇️ Baixar sugestões (CSV)",
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
                st.success("✅ Sem alertas estruturais — carteira dentro dos parâmetros.")
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
