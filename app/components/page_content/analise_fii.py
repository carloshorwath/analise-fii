"""Conteudo de Analise FII renderizavel sem decorators ou page_config.

Importavel do dossie ou da pagina autonoma 2_Analise_FII.py.

Funções públicas de seção (chamadas individualmente pelo Dossiê):
    load_dados_analise(ticker, session) -> dict  — carrega todos os dados
    render_visao_geral(ticker, dados, *, key_prefix)
    render_valuation(ticker, dados, *, key_prefix)
    render_saude(ticker, dados, *, key_prefix)
    render_dividendos(ticker, dados, *, key_prefix)
    render_composicao(ticker, dados, *, key_prefix)
    render_preco_volume(ticker, dados, *, key_prefix)
    render_datas_com(ticker, dados, *, key_prefix)
    render_radar_check(ticker, dados, *, key_prefix)
    render_score(ticker, *, key_prefix)           — abre própria sessão
    render(ticker, *, key_prefix)                 — wrapper completo com st.tabs()
"""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from app.components.charts import (
    composicao_pie,
    dividend_heatmap,
    pl_trend_chart,
    price_volume_chart,
    pvp_gauge,
    pvp_historico_com_bandas,
)
from app.components.tables import format_currency, format_number
from src.fii_analysis.config_yaml import get_piso_liquidez, get_threshold
from src.fii_analysis.data.database import get_session_ctx, get_ultimo_preco_date
from src.fii_analysis.features.composicao import classificar_fii, composicao_ativo
from src.fii_analysis.features.data_loader import (
    get_dias_desatualizado,
    get_dividendos_historico,
    get_dy_gap_anterior,
    get_historico_pl,
    get_info_ticker,
    get_proximas_datas_com,
    get_pvp_anterior,
    get_serie_preco_volume,
    get_ultimo_preco,
    get_volume_medio_21d_ticker,
    resolve_periodo,
)
from src.fii_analysis.features.indicators import get_dy_trailing, get_pvp, get_pvp_serie
from src.fii_analysis.features.risk_metrics import (
    beta_vs_ifix,
    liquidez_media_21d,
    max_drawdown,
    volatilidade_anualizada,
)
from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital, tendencia_pl
from src.fii_analysis.features.score import ScoreFII, calcular_score
from src.fii_analysis.features.valuation import (
    get_dy_gap,
    get_dy_gap_percentil,
    get_pvp_percentil,
)


# ---------------------------------------------------------------------------
# Carregamento centralizado de dados
# ---------------------------------------------------------------------------

def load_dados_analise(ticker: str, session, periodo: str = "1a") -> dict:
    """Carrega todos os dados necessários para a análise do ticker em uma sessão.

    Retorna um dict que pode ser passado para as funções render_* individuais,
    evitando múltiplas sessões SQLAlchemy quando chamado pelo Dossiê.
    """
    inicio = resolve_periodo(periodo, ticker, session)
    dias_desat = get_dias_desatualizado(ticker, session)
    pv_df = get_serie_preco_volume(ticker, session)
    ultimo = get_ultimo_preco_date(ticker, session)
    pvp = get_pvp(ticker, ultimo, session) if ultimo else None
    pvp_pct_val, jan_val = get_pvp_percentil(ticker, ultimo, 504, session) if ultimo else (None, 0)
    pvp_ant = get_pvp_anterior(ticker, session)
    dy = get_dy_trailing(ticker, ultimo, session) if ultimo else None
    dy_gap = get_dy_gap(ticker, ultimo, session) if ultimo else None
    dy_gap_ant = get_dy_gap_anterior(ticker, session)
    pvp_df = get_pvp_serie(ticker, session)
    divs_df = get_dividendos_historico(ticker, session)
    tend = tendencia_pl(ticker, session=session)
    destruicao = flag_destruicao_capital(ticker, session)
    emissoes = emissoes_recentes(ticker, session=session)
    pl_df = get_historico_pl(ticker, session, 24)
    comp = composicao_ativo(ticker, session)
    tipo = classificar_fii(ticker, session)
    comp["tipo"] = tipo
    proximas = get_proximas_datas_com(ticker, session)
    preco_info = get_ultimo_preco(ticker, session)
    info = get_info_ticker(ticker, session)
    vol_medio = get_volume_medio_21d_ticker(ticker, session)

    return dict(
        info=info, inicio=inicio, dias_desat=dias_desat,
        pv_df=pv_df, ultimo=ultimo,
        pvp=pvp, pvp_pct_val=pvp_pct_val, jan_val=jan_val, pvp_ant=pvp_ant,
        dy=dy, dy_gap=dy_gap, dy_gap_ant=dy_gap_ant,
        pvp_df=pvp_df, divs_df=divs_df,
        tend=tend, destruicao=destruicao, emissoes=emissoes,
        pl_df=pl_df, comp=comp,
        proximas=proximas, preco_info=preco_info,
        vol_medio=vol_medio, periodo=periodo,
    )


# ---------------------------------------------------------------------------
# Funções públicas de seção
# ---------------------------------------------------------------------------

def render_visao_geral(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Visão Geral: 5 KPIs + Radar + Score resumido."""
    preco_info = dados["preco_info"]
    pvp = dados["pvp"]
    pvp_pct_val = dados["pvp_pct_val"]
    jan_val = dados["jan_val"]
    dy = dados["dy"]
    dy_gap = dados["dy_gap"]
    saude = {"tendencia_pl": dados["tend"], "destruicao": dados["destruicao"], "emissoes": dados["emissoes"]}
    vol_medio = dados["vol_medio"]
    dias_desat = dados["dias_desat"]

    if dias_desat is not None and dias_desat > 3:
        st.warning(
            f"Ultimo preco disponivel ha {dias_desat} dias uteis. "
            "Execute `fii update-prices` para atualizar."
        )

    # — Sinal do dia (snapshot) —
    try:
        from app.components.snapshot_ui import load_decisions_snapshot
        _, dec_df = load_decisions_snapshot("curado")
        if not dec_df.empty and "ticker" in dec_df.columns:
            row = dec_df[dec_df["ticker"] == ticker]
            if not row.empty:
                acao = row.iloc[0].get("acao", "")
                conc = row.iloc[0].get("nivel_concordancia", "")
                _ACAO_COLORS = {
                    "COMPRAR": "#2e7d32", "VENDER": "#c62828",
                    "AGUARDAR": "#e65100", "EVITAR": "#6a1a8a",
                }
                cor = _ACAO_COLORS.get(acao, "#546e7a")
                conc_icon = {"ALTA": "⚡", "MEDIA": "👀", "BAIXA": "💤", "VETADA": "🚫"}.get(conc, "")
                st.markdown(
                    f"**Sinal do dia:** "
                    f"<span style='color:{cor};font-weight:800;font-size:1.05em'>{acao}</span>"
                    f" &nbsp;·&nbsp; Concordância: {conc_icon} {conc}",
                    unsafe_allow_html=True,
                )
    except Exception:
        pass

    # — 5 KPIs principais —
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Preco Atual",
        f"R$ {preco_info['fechamento']:.2f}"
        if preco_info and preco_info.get("fechamento") is not None else "n/d",
        help="Ultimo preco de fechamento disponivel"
    )
    c2.metric("P/VP", f"{pvp:.2f}" if pvp is not None else "n/d", help="Preco sobre Valor Patrimonial")
    c3.metric(f"P/VP Percentil ({jan_val}d)", f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d", help=f"Percentil do P/VP nos ultimos {jan_val} dias")
    c4.metric("DY 12m", f"{dy:.2%}" if dy is not None else "n/d", help="Dividend Yield trailing 12 meses")
    c5.metric("DY Gap vs CDI", f"{dy_gap:.2%}" if dy_gap is not None else "n/d", help="DY 12m - CDI 12m. Positivo significa que o fundo paga mais que o CDI")

    st.markdown("---")

    # — Radar 4 critérios —
    st.subheader("Critérios de Radar")
    pvp_thr = get_threshold("pvp_percentil_barato", 30)
    dy_gap_thr = get_threshold("dy_gap_percentil_caro", 70)
    piso = get_piso_liquidez()

    with get_session_ctx() as session:
        ultimo = dados["ultimo"]
        dy_gap_pct = (
            get_dy_gap_percentil(ticker, ultimo, get_threshold("dy_janela_pregoes", 252), session)
            if ultimo else None
        )

    r1, r2, r3, r4 = st.columns(4)
    _badge(r1, f"P/VP < {pvp_thr}%",
           pvp_pct_val is not None and pvp_pct_val < pvp_thr,
           f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d")
    _badge(r2, f"DY Gap > {dy_gap_thr}%",
           dy_gap_pct is not None and dy_gap_pct > dy_gap_thr,
           f"{dy_gap_pct:.1f}%" if dy_gap_pct is not None else "n/d")
    _badge(r3, "Saude OK",
           not saude["destruicao"]["destruicao"], "")
    _badge(r4, "Liquidez OK",
           vol_medio is not None and vol_medio >= piso, "")

    if preco_info:
        st.caption(
            f"Ultimo preco: {preco_info['data']} | "
            f"Coletado em: {preco_info.get('coletado_em', 'n/d')}"
        )


def _badge(col, label: str, passou: bool, valor: str) -> None:
    """Exibe um critério de radar com cor verde/vermelha."""
    icon = "✅" if passou else "❌"
    status = "PASSOU" if passou else "FALHOU"
    col.metric(label, f"{icon} {status}", delta=valor if valor else None,
               delta_color="off" if not valor else "normal")


def render_valuation(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Valuation: gauge P/VP + série histórica com bandas + métricas."""
    pvp = dados["pvp"]
    pvp_pct_val = dados["pvp_pct_val"]
    jan_val = dados["jan_val"]
    pvp_ant = dados["pvp_ant"]
    dy = dados["dy"]
    dy_gap = dados["dy_gap"]
    dy_gap_ant = dados["dy_gap_ant"]
    pvp_df = dados["pvp_df"]
    inicio = dados["inicio"]

    col_v1, col_v2 = st.columns([1, 2])
    with col_v1:
        st.plotly_chart(pvp_gauge(pvp, ticker), use_container_width=True)
        st.metric(f"P/VP Percentil ({jan_val}d)", f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d")

        if pvp is not None and pvp_ant is not None:
            st.metric("P/VP (atual)", f"{pvp:.4f}", delta=f"{pvp - pvp_ant:+.4f}", help="Preco sobre Valor Patrimonial")
        else:
            st.metric("P/VP (atual)", f"{pvp:.4f}" if pvp else "n/d", help="Preco sobre Valor Patrimonial")

        st.metric("DY 12m (trailing)", f"{dy:.2%}" if dy else "n/d", help="Dividend Yield trailing 12 meses")

        if dy_gap is not None and dy_gap_ant is not None:
            st.metric("DY Gap vs CDI", f"{dy_gap:.2%}", delta=f"{dy_gap - dy_gap_ant:+.2%}", help="DY 12m - CDI 12m. Positivo significa que o fundo paga mais que o CDI")
        else:
            st.metric("DY Gap vs CDI", f"{dy_gap:.2%}" if dy_gap else "n/d", help="DY 12m - CDI 12m. Positivo significa que o fundo paga mais que o CDI")

    with col_v2:
        pvp_df_plot = pvp_df[pvp_df["data"] >= inicio] if inicio is not None and not pvp_df.empty else pvp_df
        st.plotly_chart(pvp_historico_com_bandas(pvp_df_plot, ticker), use_container_width=True)


def render_saude(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Saúde: flag destruição capital + tendência PL + emissões + gráfico."""
    destruicao = dados["destruicao"]
    tend = dados["tend"]
    emissoes = dados["emissoes"]
    pl_df = dados["pl_df"]

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if destruicao["destruicao"]:
            st.error(f"DESTRUICAO DE CAPITAL detectada! {destruicao['motivo']}")
        else:
            st.success(f"Sem destruicao de capital. {destruicao['motivo']}")

        for periodo_t, dados_t in tend.items():
            coef = dados_t.get("coef_angular")
            r2 = dados_t.get("r2")
            n = dados_t.get("n", 0)
            st.write(
                f"**PL {periodo_t}m:** coef={format_number(coef, 4) if coef else 'n/d'}, "
                f"R2={format_number(r2) if r2 else 'n/d'}, n={n}"
            )

        if emissoes:
            st.warning(f"{len(emissoes)} emissoes recentes (>1% cotas)")
            for e in emissoes:
                st.write(f"  - {e['data_ref']}: +{e['variacao_pct']:.1f}% cotas")
        else:
            st.info("Sem emissoes recentes significativas.")

    with col_s2:
        st.plotly_chart(pl_trend_chart(pl_df, ticker), use_container_width=True)


def render_dividendos(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Dividendos: heatmap mensal de dividendos."""
    divs_df = dados["divs_df"]
    pv_df = dados["pv_df"]

    if not divs_df.empty and not pv_df.empty:
        st.plotly_chart(dividend_heatmap(divs_df, pv_df, ticker), use_container_width=True)
    else:
        st.info("Sem dados de dividendos para este periodo.")


def render_composicao(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Composição: tipo Tijolo/Papel/Híbrido + pie chart."""
    comp = dados["comp"]

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.metric("Tipo", comp.get("tipo", "n/d"))
        st.metric("% Imoveis",
                  f"{comp['pct_imoveis']:.1%}" if comp.get("pct_imoveis") is not None else "n/d")
        st.metric("% Recebiveis",
                  f"{comp['pct_recebiveis']:.1%}" if comp.get("pct_recebiveis") is not None else "n/d")
        st.metric("% Caixa",
                  f"{comp['pct_caixa']:.1%}" if comp.get("pct_caixa") is not None else "n/d")
        if comp.get("ativo_total"):
            st.metric("Ativo Total", format_currency(comp["ativo_total"]))
        if comp.get("data_ref"):
            st.caption(f"Ref: {comp['data_ref']}")
    with col_c2:
        st.plotly_chart(composicao_pie(comp, ticker), use_container_width=True)


def render_preco_volume(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Preço & Volume: gráfico OHLCV com período selecionável."""
    pv_df = dados["pv_df"]
    inicio = dados["inicio"]

    pv_df_plot = pv_df[pv_df["data"] >= inicio] if inicio is not None and not pv_df.empty else pv_df
    st.plotly_chart(price_volume_chart(pv_df_plot, ticker), use_container_width=True)


def render_datas_com(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Datas-Com: próximas datas com e valor por cota."""
    proximas = dados["proximas"]

    if proximas:
        for p in proximas:
            valor = f"R$ {p['valor_cota']:.4f}" if p["valor_cota"] else "n/d"
            st.write(f"**{p['data_com']}** — {valor}/cota")
    else:
        st.info("Nenhuma data-com futura encontrada.")


def render_radar_check(ticker: str, dados: dict, *, key_prefix: str = "afii") -> None:
    """Tab Radar: 4 critérios booleanos detalhados."""
    pvp_pct_val = dados["pvp_pct_val"]
    jan_val = dados["jan_val"]
    destruicao = dados["destruicao"]
    vol_medio = dados["vol_medio"]
    preco_info = dados["preco_info"]
    ultimo = dados["ultimo"]

    with get_session_ctx() as session:
        dy_gap_pct = (
            get_dy_gap_percentil(ticker, ultimo, get_threshold("dy_janela_pregoes", 252), session)
            if ultimo else None
        )

    pvp_thr = get_threshold("pvp_percentil_barato", 30)
    dy_gap_thr = get_threshold("dy_gap_percentil_caro", 70)
    piso = get_piso_liquidez()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"P/VP Baixo ({jan_val}d)",
              f"{pvp_pct_val:.1f}% {'PASSOU' if pvp_pct_val and pvp_pct_val < pvp_thr else 'FALHOU'}"
              if pvp_pct_val is not None else "n/d")
    c2.metric(f"DY Gap Alto (pct>{dy_gap_thr})",
              f"{dy_gap_pct:.1f}% {'PASSOU' if dy_gap_pct and dy_gap_pct > dy_gap_thr else 'FALHOU'}"
              if dy_gap_pct else "n/d")
    c3.metric("Saude OK", "PASSOU" if not destruicao["destruicao"] else "FALHOU")
    c4.metric("Liquidez OK", f"{'PASSOU' if vol_medio and vol_medio >= piso else 'FALHOU'}")

    if preco_info:
        st.caption(f"Ultimo preco: {preco_info['data']} | Coletado em: {preco_info.get('coletado_em', 'n/d')}")


def render_score(ticker: str, *, key_prefix: str = "afii") -> None:
    """Tab Score: score 0-100 com decomposição visual. Abre própria sessão."""
    with get_session_ctx() as session:
        sc: ScoreFII | None = None
        try:
            ultimo = get_ultimo_preco_date(ticker, session)
            pvp_pct_s, _ = get_pvp_percentil(ticker, ultimo, 504, session) if ultimo else (None, 0)
            dy_gap_pct_s = get_dy_gap_percentil(ticker, ultimo, 252, session) if ultimo else None
            vol_s = volatilidade_anualizada(ticker, session=session)
            beta_s = beta_vs_ifix(ticker, session=session)
            mdd_s = max_drawdown(ticker, session=session)
            liq_s = liquidez_media_21d(ticker, session=session)
            sc = calcular_score(
                ticker,
                pvp_percentil=pvp_pct_s,
                dy_gap_percentil=dy_gap_pct_s,
                volatilidade=vol_s,
                beta=beta_s,
                mdd=mdd_s,
                liquidez_21d_brl=liq_s,
                session=session,
            )
        except Exception:
            pass

    if sc is None:
        st.info("Nao foi possivel calcular o score. Verifique se ha dados suficientes no banco.")
    else:
        _render_score_breakdown(sc)


# ---------------------------------------------------------------------------
# Wrapper completo (compatibilidade com 2_Analise_FII.py)
# ---------------------------------------------------------------------------

def render(ticker: str, *, key_prefix: str = "afii") -> None:
    """Renderiza analise integrada do ticker (sem header/selectbox/footer).

    Mantido para compatibilidade retroativa com 2_Analise_FII.py.
    O Dossiê usa as funções de seção individuais diretamente.
    """
    periodo = st.session_state.get("periodo", "1a")

    with get_session_ctx() as session:
        dados = load_dados_analise(ticker, session, periodo=periodo)

    info = dados["info"]
    if info:
        st.caption(
            f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
            f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}"
        )

    st.markdown("---")

    PERIODOS = ["1m", "6m", "1a", "YTD", "2a", "3a", "Max"]
    if "periodo" not in st.session_state:
        st.session_state.periodo = "1a"

    periodo = st.radio(
        "Periodo", PERIODOS,
        index=PERIODOS.index(st.session_state.get("periodo", "1a")),
        horizontal=True, key=f"{key_prefix}_radio_periodo",
    )

    dias_desat = dados["dias_desat"]
    if dias_desat is not None and dias_desat > 3:
        st.warning(
            f"Ultimo preco disponivel ha {dias_desat} dias uteis. "
            "Execute `fii update-prices` para atualizar."
        )

    st.markdown("---")

    # Recarregar com período atualizado se mudou
    preco_info = dados["preco_info"]
    pvp = dados["pvp"]
    pvp_pct_val = dados["pvp_pct_val"]
    dy = dados["dy"]
    dy_gap = dados["dy_gap"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preco Atual",
              f"R$ {preco_info['fechamento']:.2f}"
              if preco_info and preco_info.get("fechamento") is not None else "n/d")
    c2.metric("P/VP", f"{pvp:.2f}" if pvp is not None else "n/d")
    c3.metric("P/VP Percentil", f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d")
    c4.metric("DY 12m", f"{dy:.2%}" if dy is not None else "n/d")
    c5.metric("DY Gap", f"{dy_gap:.2%}" if dy_gap is not None else "n/d")

    st.markdown("---")

    tab_val, tab_saude, tab_div, tab_comp, tab_price, tab_radar, tab_datas, tab_score = st.tabs(
        ["Valuation", "Saude", "Dividendos", "Composicao", "Preco & Volume", "Radar", "Datas-Com", "Score"]
    )

    with tab_val:
        render_valuation(ticker, dados, key_prefix=f"{key_prefix}_val")
    with tab_saude:
        render_saude(ticker, dados, key_prefix=f"{key_prefix}_sau")
    with tab_div:
        render_dividendos(ticker, dados, key_prefix=f"{key_prefix}_div")
    with tab_comp:
        render_composicao(ticker, dados, key_prefix=f"{key_prefix}_comp")
    with tab_price:
        render_preco_volume(ticker, dados, key_prefix=f"{key_prefix}_pv")
    with tab_radar:
        render_radar_check(ticker, dados, key_prefix=f"{key_prefix}_rad")
    with tab_datas:
        render_datas_com(ticker, dados, key_prefix=f"{key_prefix}_dat")
    with tab_score:
        render_score(ticker, key_prefix=f"{key_prefix}_sc")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _render_score_breakdown(sc: ScoreFII) -> None:
    """Renderiza o score 0-100 com decomposição visual em barras horizontais."""
    total = sc.score_total

    if total >= 80:
        badge_color, badge_label = "#1a7e3f", "EXCELENTE"
    elif total >= 65:
        badge_color, badge_label = "#3a8a2e", "BOM"
    elif total >= 50:
        badge_color, badge_label = "#b8960c", "NEUTRO"
    else:
        badge_color, badge_label = "#c0392b", "FRACO"

    st.markdown(
        f"<h2 style='color:{badge_color}'>Score: {total}/100 — {badge_label}</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        "O score e uma camada de *comunicacao* — resume os indicadores para leitura rapida. "
        "Nao substitui o sinal estatistico (motor P/VP + walk-forward + episodios)."
    )

    sub_scores = {
        "Valuation (P/VP + DY Gap)": sc.score_valuation,
        "Risco (Vol + Beta + Drawdown)": sc.score_risco,
        "Liquidez (Volume 21d)": sc.score_liquidez,
        "Historico (Consistencia DY 24m)": sc.score_historico,
    }
    pesos = [0.35, 0.30, 0.20, 0.15]

    fig = go.Figure()
    colors = ["#2ecc71" if v >= 65 else ("#f39c12" if v >= 50 else "#e74c3c")
              for v in sub_scores.values()]

    for i, (label, value) in enumerate(sub_scores.items()):
        fig.add_trace(go.Bar(
            name=label, x=[value], y=[label], orientation="h",
            marker_color=colors[i],
            text=f"{value}/100 (peso {pesos[i]:.0%})",
            textposition="inside",
        ))

    fig.add_vline(x=total, line_dash="dash", line_color="white",
                  annotation_text=f"Total: {total}", annotation_position="top right")
    fig.update_layout(
        title=f"{sc.ticker} — Decomposicao do Score",
        xaxis=dict(range=[0, 100], title="Score 0-100"),
        yaxis=dict(title=""),
        template="plotly_dark", height=280,
        showlegend=False, barmode="overlay",
    )
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valuation", f"{sc.score_valuation}/100",
              help="P/VP percentil invertido (60%) + DY Gap percentil (40%)")
    c2.metric("Risco", f"{sc.score_risco}/100",
              help="Volatilidade + Beta + Drawdown normalizados vs universo")
    c3.metric("Liquidez", f"{sc.score_liquidez}/100",
              help="< R$200k=20 | 200k-1M=50 | 1M-5M=75 | >5M=90")
    c4.metric("Historico", f"{sc.score_historico}/100",
              help="Consistencia do DY mensal (CV invertido, 24 meses)")
