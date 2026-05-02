"""Conteudo de Fund Event Study CVM renderizavel sem decorators ou page_config."""
from __future__ import annotations

import numpy as np
import plotly.express as px
import streamlit as st

from app.components.carteira_ui import load_tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.models.event_study_cvm import (
    _block_placebo,
    calculate_car,
    compute_study_summary,
    get_bdays_series,
    get_events,
)

SINAIS = {
    "Distribuição > Geração (Venda)": "dist_gt_gen",
    "Destruição Patrimonial Consecutiva ≥ 2 meses (Venda)": "destruc_consec_2",
    "Queda PL > 2% MoM sem emissão (Venda)": "pl_queda_2pct",
    "Corte DY > 20% vs média 6m (Venda)": "corte_dy_20pct",
    "Dist < 70% da Rentab Efetiva (Alerta)": "dist_baixa_efetiva",
    "Emissão de Cotas (Diluição)": "emissao_cotas",
}


def render(ticker: str | None = None, *, key_prefix: str = "fcs") -> None:
    """Renderiza event study CVM. Se ticker=None, mostra selectbox proprio."""
    st.markdown("""
    Testa se eventos **discretos** vinculados à entrega de relatórios CVM têm impacto anormal no preço.
    CAR calculado somando retornos diários anormais dentro da janela forward (não retorno forward × β).
    Sinais de estado contínuo (P/VP, DY Gap) estão na página **Otimizador**.
    """)

    N_SINAIS = len(SINAIS)

    tickers = load_tickers_ativos()
    if not tickers:
        st.warning("Nenhum ticker ativo encontrado.")
        return

    col1, col2 = st.columns(2)
    with col1:
        if ticker is None:
            ticker = st.selectbox("Ticker", tickers, key=f"{key_prefix}_ticker")
        else:
            st.caption(f"Ticker: **{ticker}**")
        sinal_label = st.selectbox("Sinal", list(SINAIS.keys()), key=f"{key_prefix}_sinal")
    with col2:
        forward_days = st.selectbox(
            "Janela Forward (pregões)", [10, 20, 30], index=1, key=f"{key_prefix}_forward"
        )
        n_placebo = st.number_input(
            "Simulações Placebo", min_value=100, max_value=1000,
            value=500, step=100, key=f"{key_prefix}_nplacebo",
        )
    sinal_key = SINAIS[sinal_label]

    run_key = f"cvm_es_{ticker}_{sinal_key}_{forward_days}"

    if st.button("Rodar Análise", type="primary", key=f"{key_prefix}_run"):
        with get_session_ctx() as session:
            with st.spinner("Identificando eventos..."):
                bdays = get_bdays_series(ticker, session)
                events = get_events(ticker, sinal_key, session, forward_days, bdays)

            if not events:
                st.warning(f"Nenhum evento encontrado para '{sinal_label}'.")
                return

            st.success(f"{len(events)} eventos encontrados (após filtro de sobreposição em dias úteis).")

            with st.spinner("Calculando CARs..."):
                df_results, df_precos = calculate_car(
                    ticker, events, forward_days, session, info_callback=st.info
                )

            if df_results.empty:
                st.error("Retornos insuficientes após os eventos.")
                return

            st.session_state[run_key] = {
                "df_results": df_results,
                "df_precos": df_precos,
                "n_events": len(events),
                "forward_days": forward_days,
                "n_placebo": n_placebo,
                "N_SINAIS": N_SINAIS,
            }

    if run_key in st.session_state:
        data = st.session_state[run_key]
        df_results = data["df_results"]
        df_precos = data["df_precos"]
        forward_days = data["forward_days"]
        n_placebo = data["n_placebo"]
        N_SINAIS = data["N_SINAIS"]

        summary = compute_study_summary(df_results, N_SINAIS)
        n_eventos = summary["n"]
        car_medio = summary["car_medio"]
        car_mediana = summary["car_mediana"]
        pct_acertos = summary["pct_acertos"]
        p_nw = summary["p_nw"]
        t_stat = summary["t_stat"]
        p_bonf = summary["p_bonf"]
        p_wilcoxon = summary["p_wilcoxon"]

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Eventos", n_eventos)
        c2.metric("CAR Medio", f"{car_medio:.2%}")
        c3.metric("CAR Mediana", f"{car_mediana:.2%}")
        c4.metric("Acertos (CAR<0)", f"{pct_acertos:.1%}")
        c5.metric("t-stat (NW)", f"{t_stat:.2f}" if t_stat is not np.nan else "n/a")
        c6.metric("p-value (NW)", f"{p_nw:.4f}")

        sig_nw = "PASS" if p_nw < 0.05 else "FAIL"
        sig_bonf = "PASS" if p_bonf < 0.05 else "FAIL"
        sig_wcx = "PASS" if p_wilcoxon < 0.05 else "FAIL"
        st.caption(
            f"**Bonferroni** (x{N_SINAIS}): p={p_bonf:.4f} {sig_bonf} | "
            f"**Wilcoxon**: p={p_wilcoxon:.4f} {sig_wcx} | "
            f"**NW**: p={p_nw:.4f} {sig_nw}"
        )

        if summary["wilcoxon_warning"]:
            st.warning(summary["wilcoxon_warning"])

        tab_events, tab_dist, tab_placebo = st.tabs(["CARs por Evento", "Distribuição de CARs", "Placebo"])

        with tab_dist:
            fig = px.histogram(df_results, x="car", nbins=20, labels={"car": "CAR"},
                               color_discrete_sequence=["#636EFA"])
            fig.add_vline(x=0, line_dash="dash", line_color="red")
            fig.add_vline(x=car_medio, line_dash="dot", line_color="orange",
                          annotation_text=f"média {car_medio:.2%}")
            st.plotly_chart(fig, use_container_width=True)

        with tab_events:
            df_s = df_results.sort_values("car").reset_index(drop=True)
            fig2 = px.bar(df_s, x=df_s.index, y="car", color="car",
                          color_continuous_scale="RdYlGn", labels={"index": "Evento", "car": "CAR"})
            fig2.add_hline(y=0, line_color="black")
            st.plotly_chart(fig2, use_container_width=True)

        with tab_placebo:
            with st.spinner(f"{n_placebo} simulações..."):
                if t_stat is None or np.isnan(t_stat):
                    st.error("t-stat inválido para placebo.")
                else:
                    p_placebo, t_stats_placebo = _block_placebo(
                        df_precos, n_eventos, forward_days, t_stat, n_placebo,
                    )

                    fig3 = px.histogram(
                        x=t_stats_placebo, nbins=30, labels={"x": "t-statistic"},
                        title=f"Distribuição t-stats Placebo (block={forward_days}d)",
                        color_discrete_sequence=["#AB63FA"],
                    )
                    fig3.add_vline(x=t_stat, line_width=3, line_color="red",
                                   annotation_text=f"t real ({t_stat:.2f})")
                    st.plotly_chart(fig3, use_container_width=True)

                    st.metric("p-value Placebo (block bootstrap)", f"{p_placebo:.4f}")
                    if p_placebo < 0.05:
                        st.success("Sinal robusto ao placebo (p < 0.05).")
                    else:
                        st.warning("Sinal NÃO robusto ao placebo — pode ser ruído.")
