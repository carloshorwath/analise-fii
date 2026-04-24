import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app.components.charts import car_plot
from app.components.data_loader import load_tickers_ativos
from app.state import render_footer
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.models.critic import shuffle_test, placebo_test, subperiod_stability, veredito_critic
from src.fii_analysis.models.statistical import event_study, test_pre_vs_post, test_day0_return
from src.fii_analysis.models.walk_forward import make_splits

st.set_page_config(page_title="Event Study", page_icon="microscope", layout="wide")
st.title("Event Study")

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

        st.success(f"{windows['data_com'].nunique()} eventos encontrados.")

        splits = make_splits(windows)
        train_df = splits["train"]
        test_df = splits["test"]

        col_info1, col_info2, col_info3 = st.columns(3)
        col_info1.metric("Eventos Treino", splits["n_train"])
        col_info2.metric("Eventos Teste", splits["n_test"])
        col_info3.metric("Total", len(windows))

        if splits["train_end"]:
            st.caption(f"Treino ate: {splits['train_end']} | Teste a partir de: {splits['test_start'] or 'n/d'}")

        # Event study - full
        es_full = event_study(windows)
        st.header("CAR — Todos os Eventos")
        st.plotly_chart(car_plot(es_full, ticker, " (Todos)"), use_container_width=True)

        # Test pre vs post
        st.header("Teste Pre vs Post")
        pre_post = test_pre_vs_post(windows)
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
        if day0["mean"] is not None:
            col_d1, col_d2, col_d3 = st.columns(3)
            col_d1.metric("Media Dia 0", f"{day0['mean']:.4%}")
            col_d2.metric("t-stat", f"{day0['tstat']:.4f}" if day0["tstat"] else "n/d")
            col_d3.metric("p-value", f"{day0['pvalue']:.4f}" if day0["pvalue"] else "n/d")

        # Train/Test split
        if not train_df.empty:
            st.header("CAR — Treino")
            es_train = event_study(train_df)
            st.plotly_chart(car_plot(es_train, ticker, " (Treino)"), use_container_width=True)

        if not test_df.empty:
            st.header("CAR — Teste")
            es_test = event_study(test_df)
            st.plotly_chart(car_plot(es_test, ticker, " (Teste)"), use_container_width=True)

        # CriticAgent
        st.header("CriticAgent — Falsificacao")
        with st.spinner("Rodando CriticAgent (shuffle, placebo, estabilidade)..."):
            col_cr1, col_cr2, col_cr3 = st.columns(3)

            shuffle = shuffle_test(windows)
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
