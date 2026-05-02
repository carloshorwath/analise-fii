"""Conteudo de Analise FII renderizavel sem decorators ou page_config.

Importavel do dossie ou da pagina autonoma 2_Analise_FII.py.
"""
from __future__ import annotations

import streamlit as st

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
from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital, tendencia_pl
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

    tab_val, tab_saude, tab_div, tab_comp, tab_price, tab_radar, tab_datas = st.tabs(
        ["Valuation", "Saude", "Dividendos", "Composicao", "Preco & Volume", "Radar", "Datas-Com"]
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
