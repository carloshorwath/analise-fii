"""Conteudo de Analise FII renderizavel sem decorators ou page_config.

Importavel do dossie ou da pagina autonoma 2_Analise_FII.py.
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
from src.fii_analysis.evaluation.daily_snapshots import load_risk_metrics_snapshot
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


def render(ticker: str, *, key_prefix: str = "afii") -> None:
    """Renderiza analise integrada do ticker (sem header/selectbox/footer)."""
    periodo = st.session_state.get("periodo", "1a")

    with get_session_ctx() as session:
        info = get_info_ticker(ticker, session)
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
        saude = {"tendencia_pl": tend, "destruicao": destruicao, "emissoes": emissoes}
        pl_df = get_historico_pl(ticker, session, 24)
        comp = composicao_ativo(ticker, session)
        tipo = classificar_fii(ticker, session)
        comp["tipo"] = tipo
        proximas = get_proximas_datas_com(ticker, session)
        preco_info = get_ultimo_preco(ticker, session)

    if info:
        st.caption(f"**{info.get('nome', ticker)}** | Segmento: {info.get('segmento', 'n/d')} | "
                   f"Mandato: {info.get('mandato', 'n/d')} | Gestao: {info.get('tipo_gestao', 'n/d')}")

    st.markdown("---")

    PERIODOS = ["1m", "6m", "1a", "YTD", "2a", "3a", "Max"]
    if "periodo" not in st.session_state:
        st.session_state.periodo = "1a"

    periodo = st.radio(
        "Periodo",
        PERIODOS,
        index=PERIODOS.index(st.session_state.get("periodo", "1a")),
        horizontal=True,
        key=f"{key_prefix}_radio_periodo",
    )

    if dias_desat is not None and dias_desat > 3:
        st.warning(f"Ultimo preco disponivel ha {dias_desat} dias uteis. Dados podem estar desatualizados. "
                   f"Execute `fii update-prices` para atualizar.")

    st.markdown("---")

    quick_1, quick_2, quick_3, quick_4, quick_5 = st.columns(5)
    quick_1.metric(
        "Preco Atual",
        f"R$ {preco_info['fechamento']:.2f}" if preco_info and preco_info.get("fechamento") is not None else "n/d",
    )
    quick_2.metric("P/VP", f"{pvp:.2f}" if pvp is not None else "n/d")
    quick_3.metric("P/VP Percentil", f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d")
    quick_4.metric("DY 12m", f"{dy:.2%}" if dy is not None else "n/d")
    quick_5.metric("DY Gap", f"{dy_gap:.2%}" if dy_gap is not None else "n/d")

    st.markdown("---")

    tab_val, tab_saude, tab_div, tab_comp, tab_price, tab_radar, tab_datas, tab_score = st.tabs(
        ["Valuation", "Saude", "Dividendos", "Composicao", "Preco & Volume", "Radar", "Datas-Com", "Score"]
    )

    with tab_price:
        if inicio is not None and not pv_df.empty:
            pv_df_plot = pv_df[pv_df["data"] >= inicio]
        else:
            pv_df_plot = pv_df
        st.plotly_chart(price_volume_chart(pv_df_plot, ticker), use_container_width=True)

    with tab_val:
        col_v1, col_v2 = st.columns([1, 2])

        with col_v1:
            st.plotly_chart(pvp_gauge(pvp, ticker), use_container_width=True)

            st.metric(f"P/VP Percentil ({jan_val}d)", f"{pvp_pct_val:.1f}%" if pvp_pct_val is not None else "n/d")

            if pvp is not None and pvp_ant is not None:
                delta_pvp = pvp - pvp_ant
                st.metric("P/VP (atual)", f"{pvp:.4f}", delta=f"{delta_pvp:+.4f}")
            else:
                st.metric("P/VP (atual)", f"{pvp:.4f}" if pvp else "n/d")

            st.metric("DY 12m (trailing)", f"{dy:.2%}" if dy else "n/d")

            if dy_gap is not None and dy_gap_ant is not None:
                delta_gap = dy_gap - dy_gap_ant
                st.metric("DY Gap vs CDI", f"{dy_gap:.2%}", delta=f"{delta_gap:+.2%}")
            else:
                st.metric("DY Gap vs CDI", f"{dy_gap:.2%}" if dy_gap else "n/d")

            st.markdown("**Risco e Retorno**")
            with get_session_ctx() as _s:
                _rm = load_risk_metrics_snapshot(ticker, _s)
            if _rm:
                _vol = _rm.get("volatilidade_anual")
                _mdd = _rm.get("max_drawdown")
                _ret = _rm.get("retorno_total_12m")
                _liq = _rm.get("liquidez_21d_brl")
                st.metric("Volatilidade Anual", f"{_vol:.1%}" if _vol is not None else "n/d")
                st.metric("Max Drawdown 2a", f"{_mdd:.1%}" if _mdd is not None else "n/d")
                st.metric("Retorno Total 12m", f"{_ret:+.1%}" if _ret is not None else "n/d")
                if _liq is not None:
                    st.metric("Liquidez 21d", f"R$ {_liq/1e6:.1f} mi" if _liq >= 1e6 else f"R$ {_liq/1e3:.0f} k")

        with col_v2:
            if inicio is not None and not pvp_df.empty:
                pvp_df_plot = pvp_df[pvp_df["data"] >= inicio]
            else:
                pvp_df_plot = pvp_df
            st.plotly_chart(pvp_historico_com_bandas(pvp_df_plot, ticker), use_container_width=True)

    with tab_div:
        if not divs_df.empty and not pv_df.empty:
            st.plotly_chart(dividend_heatmap(divs_df, pv_df, ticker), use_container_width=True)
        else:
            st.info("Sem dados de dividendos para este periodo.")

    with tab_saude:
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            destr = saude["destruicao"]
            if destr["destruicao"]:
                st.error(f"DESTRUICAO DE CAPITAL detectada! {destr['motivo']}")
            else:
                st.success(f"Sem destruicao de capital. {destr['motivo']}")

            tend_data = saude["tendencia_pl"]
            for periodo_t, dados in tend_data.items():
                coef = dados.get("coef_angular")
                r2 = dados.get("r2")
                n = dados.get("n", 0)
                st.write(f"**PL {periodo_t}m:** coef={format_number(coef, 4) if coef else 'n/d'}, "
                         f"R2={format_number(r2) if r2 else 'n/d'}, n={n}")

            emissoes_data = saude["emissoes"]
            if emissoes_data:
                st.warning(f"{len(emissoes_data)} emissoes recentes (>1% cotas)")
                for e in emissoes_data:
                    st.write(f"  - {e['data_ref']}: +{e['variacao_pct']:.1f}% cotas")
            else:
                st.info("Sem emissoes recentes significativas.")

        with col_s2:
            st.plotly_chart(pl_trend_chart(pl_df, ticker), use_container_width=True)

    with tab_comp:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.metric("Tipo", comp.get("tipo", "n/d"))
            st.metric("% Imoveis", f"{comp['pct_imoveis']:.1%}" if comp.get("pct_imoveis") is not None else "n/d")
            st.metric("% Recebiveis", f"{comp['pct_recebiveis']:.1%}" if comp.get("pct_recebiveis") is not None else "n/d")
            st.metric("% Caixa", f"{comp['pct_caixa']:.1%}" if comp.get("pct_caixa") is not None else "n/d")
            if comp.get("ativo_total"):
                st.metric("Ativo Total", format_currency(comp["ativo_total"]))
            if comp.get("data_ref"):
                st.caption(f"Ref: {comp['data_ref']}")

        with col_c2:
            st.plotly_chart(composicao_pie(comp, ticker), use_container_width=True)

    with tab_datas:
        if proximas:
            for p in proximas:
                valor = f"R$ {p['valor_cota']:.4f}" if p["valor_cota"] else "n/d"
                st.write(f"**{p['data_com']}** — {valor}/cota")
        else:
            st.info("Nenhuma data-com futura encontrada.")

    with tab_radar:
        with get_session_ctx() as session:
            pvp_pct, jan_radar = get_pvp_percentil(ticker, ultimo, 504, session) if ultimo else (None, 0)
            dy_gap_pct = get_dy_gap_percentil(ticker, ultimo, get_threshold("dy_janela_pregoes", 252), session) if ultimo else None
            vol_medio = get_volume_medio_21d_ticker(ticker, session)

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        pvp_thr = get_threshold("pvp_percentil_barato", 30)
        dy_gap_thr = get_threshold("dy_gap_percentil_caro", 70)
        col_r1.metric(f"P/VP Baixo ({jan_radar}d)", f"{pvp_pct:.1f}% {'PASSOU' if pvp_pct and pvp_pct < pvp_thr else 'FALHOU'}" if pvp_pct is not None else "n/d")
        col_r2.metric(f"DY Gap Alto (pct>{dy_gap_thr})", f"{dy_gap_pct:.1f}% {'PASSOU' if dy_gap_pct and dy_gap_pct > dy_gap_thr else 'FALHOU'}" if dy_gap_pct else "n/d")
        col_r3.metric("Saude OK", "PASSOU" if not saude["destruicao"]["destruicao"] else "FALHOU")

        piso = get_piso_liquidez()
        col_r4.metric("Liquidez OK", f"{'PASSOU' if vol_medio and vol_medio >= piso else 'FALHOU'}")

        if preco_info:
            st.caption(f"Ultimo preco: {preco_info['data']} | Coletado em: {preco_info.get('coletado_em', 'n/d')}")

    with tab_score:
        with get_session_ctx() as session:
            sc: ScoreFII | None = None
            try:
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


def _render_score_breakdown(sc: ScoreFII) -> None:
    """Renderiza o score 0-100 com decomposição visual em barras horizontais."""
    total = sc.score_total

    if total >= 80:
        badge_color = "#1a7e3f"
        badge_label = "EXCELENTE"
    elif total >= 65:
        badge_color = "#3a8a2e"
        badge_label = "BOM"
    elif total >= 50:
        badge_color = "#b8960c"
        badge_label = "NEUTRO"
    else:
        badge_color = "#c0392b"
        badge_label = "FRACO"

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
    colors = ["#2ecc71" if v >= 65 else ("#f39c12" if v >= 50 else "#e74c3c") for v in sub_scores.values()]

    for i, (label, value) in enumerate(sub_scores.items()):
        fig.add_trace(go.Bar(
            name=label,
            x=[value],
            y=[label],
            orientation="h",
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
        template="plotly_dark",
        height=280,
        showlegend=False,
        barmode="overlay",
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Valuation", f"{sc.score_valuation}/100", help="P/VP percentil invertido (60%) + DY Gap percentil (40%)")
    col2.metric("Risco", f"{sc.score_risco}/100", help="Volatilidade + Beta + Drawdown normalizados vs universo")
    col3.metric("Liquidez", f"{sc.score_liquidez}/100", help="< R$200k=20 | 200k-1M=50 | 1M-5M=75 | >5M=90")
    col4.metric("Historico", f"{sc.score_historico}/100", help="Consistencia do DY mensal (CV invertido, 24 meses)")
