import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import car_plot
from app.components.carteira_ui import load_tickers_ativos
from app.components.ui_shell import render_inline_note, render_page_header, render_sidebar_guide
from app.state import render_footer, safe_page, safe_set_page_config
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.models.critic import shuffle_test, placebo_test, subperiod_stability, veredito_critic
from src.fii_analysis.models.statistical import event_study, test_pre_vs_post, test_day0_return
from src.fii_analysis.models.walk_forward import make_splits

safe_set_page_config(page_title="Event Study", page_icon="microscope", layout="wide")


@safe_page
def main():
    render_sidebar_guide("Event Study", "Auditar")
    render_page_header(
        "Event Study",
        "Analise estatistica da janela ao redor da data-com, com separacao de treino e teste e camada de falsificacao via CriticAgent.",
        "Auditar",
    )
    render_inline_note(
        "Use esta pagina para validar se existe efeito ao redor da data-com. Se quiser algo mais operacional, priorize Walk-Forward e Otimizador V2."
    )

    tickers = load_tickers_ativos()
    if not tickers:
        st.warning("Nenhum ticker ativo encontrado.")
        st.stop()

    ticker = st.selectbox("Ticker:", tickers, key="es_ticker")

    if st.button("Rodar Event Study", type="primary"):
        with get_session_ctx() as session:
            with st.spinner("Calculando janelas de dividendos..."):
                windows = get_dividend_windows(ticker, session)

                if windows.empty:
                    st.error("Nenhuma janela de dividendos encontrada para este ticker.")
                    render_footer()
                    st.stop()

            splits = make_splits(windows, forward_days=10)
            train_df = splits["train"]
            test_df = splits["test"]

            # Store results in session_state
            st.session_state["es_results"] = {
                "windows": windows,
                "splits": splits,
                "ticker": ticker,
                "session_data": {
                    "shuffle": None,
                    "placebo": None,
                    "stability": None,
                    "es_full": None,
                    "es_train": None,
                    "es_test": None,
                    "pre_post": None,
                    "day0": None,
                },
            }

            results = st.session_state["es_results"]

            col_info1, col_info2, col_info3 = st.columns(3)
            col_info1.metric("Eventos Treino", splits["n_train"])
            col_info2.metric("Eventos Teste", splits["n_test"])
            col_info3.metric("Total", len(windows))

            if splits["train_end"]:
                st.caption(f"Treino ate: {splits['train_end']} | Teste a partir de: {splits['test_start'] or 'n/d'}")

            tab_car, tab_critic, tab_tests = st.tabs(["CAR", "CriticAgent", "Testes"])

            with tab_car:
                es_full = event_study(windows)
                results["session_data"]["es_full"] = es_full
                st.header("CAR — Todos os Eventos")
                st.plotly_chart(car_plot(es_full, ticker, " (Todos)"), use_container_width=True)

                if not train_df.empty:
                    st.header("CAR — Treino")
                    es_train = event_study(train_df)
                    results["session_data"]["es_train"] = es_train
                    st.plotly_chart(car_plot(es_train, ticker, " (Treino)"), use_container_width=True)

                if not test_df.empty:
                    st.header("CAR — Teste")
                    es_test = event_study(test_df)
                    results["session_data"]["es_test"] = es_test
                    st.plotly_chart(car_plot(es_test, ticker, " (Teste)"), use_container_width=True)

            with tab_tests:
                # Test pre vs post
                st.header("Teste Pre vs Post")
                pre_post = test_pre_vs_post(windows)
                results["session_data"]["pre_post"] = pre_post
                col_pp1, col_pp2, col_pp3 = st.columns(3)
                if pre_post["pre_mean"] is not None:
                    col_pp1.metric("Retorno Medio Pre", f"{pre_post['pre_mean']:.4%}")
                    col_pp2.metric("Retorno Medio Post", f"{pre_post['post_mean']:.4%}")
                col_pp3.metric("N Eventos", pre_post["n_eventos"])

                if pre_post["ttest_pvalue"] is not None:
                    st.write(f"**t-test pareado:** stat={pre_post['ttest_stat']:.4f}, p={pre_post['ttest_pvalue']:.4f}")
                    st.write(f"**Mann-Whitney:** stat={pre_post['mw_stat']:.4f}, p={pre_post['mw_pvalue']:.4f}")

                # Day 0 test
                st.header("Retorno Dia 0 (Data-Com)")
                day0 = test_day0_return(windows)
                results["session_data"]["day0"] = day0
                if day0["mean"] is not None:
                    col_d1, col_d2, col_d3 = st.columns(3)
                    col_d1.metric("Media Dia 0", f"{day0['mean']:.4%}")
                    col_d2.metric("t-stat", f"{day0['tstat']:.4f}" if day0["tstat"] else "n/d")
                    col_d3.metric("p-value", f"{day0['pvalue']:.4f}" if day0["pvalue"] else "n/d")

            with tab_critic:
                st.header("CriticAgent — Falsificacao")
                with st.spinner("Rodando CriticAgent (shuffle, placebo, estabilidade)..."):
                    col_cr1, col_cr2, col_cr3 = st.columns(3)

                    shuffle = shuffle_test(windows)
                    results["session_data"]["shuffle"] = shuffle
                    shuffle_ok = shuffle["p_value_permutation"] is not None and shuffle["p_value_permutation"] < 0.05
                    with col_cr1:
                        st.subheader("Permutation Shuffle")
                        if shuffle["t_real"] is not None:
                            st.write(f"t-real: {shuffle['t_real']:.4f}")
                            st.write(f"p-value perm: {shuffle['p_value_permutation']:.4f}")
                        st.write(f">>> **{shuffle['conclusion']}**")
                        if shuffle_ok:
                            st.success("PASSOU")
                        else:
                            st.error("FALHOU")

                    placebo = placebo_test(ticker, session)
                    results["session_data"]["placebo"] = placebo
                    placebo_ok = placebo["mw_pvalue"] is not None and placebo["mw_pvalue"] < 0.05
                    with col_cr2:
                        st.subheader("Placebo")
                        if placebo["real_mean_day0"] is not None:
                            st.write(f"Real: {placebo['real_mean_day0']:.4%}")
                            st.write(f"Placebo: {placebo['placebo_mean_day0']:.4%}")
                            st.write(f"MW p: {placebo['mw_pvalue']:.4f}")
                        st.write(f">>> **{placebo['conclusion']}**")
                        if placebo_ok:
                            st.success("PASSOU")
                        else:
                            st.error("FALHOU")

                    stability = subperiod_stability(windows)
                    results["session_data"]["stability"] = stability
                    stability_ok = stability["ttest_pvalue"] is not None and stability["ttest_pvalue"] > 0.05
                    with col_cr3:
                        st.subheader("Subperiod Stability")
                        if stability["first_half_mean"] is not None:
                            st.write(f"1a metade: {stability['first_half_mean']:.4%} (n={stability['first_half_n']})")
                            st.write(f"2a metade: {stability['second_half_mean']:.4%} (n={stability['second_half_n']})")
                            st.write(f"t-test p: {stability['ttest_pvalue']:.4f}")
                        st.write(f">>> **{stability['conclusion']}**")
                        if stability_ok:
                            st.success("PASSOU")
                        else:
                            st.error("FALHOU")

                    st.markdown("---")
                    veredito = veredito_critic(shuffle_ok, placebo_ok, stability_ok)
                    if veredito["nivel"] == "success":
                        st.header("VEREDICTO: APROVADO")
                        st.success(veredito["mensagem"])
                    else:
                        st.header("VEREDICTO: REPROVADO")
                        st.warning(veredito["mensagem"])

    render_footer()


main()
