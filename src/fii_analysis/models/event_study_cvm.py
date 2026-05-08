"""Event Study — Eventos Discretos CVM.

CAR calculado somando retornos diários anormais dentro da janela forward.
Modelo de mercado estimado em [-200, -20] quando IFIX disponível.
Testes estatísticos: NW HAC, block bootstrap placebo.
"""

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.data.database import (
    BenchmarkDiario,
    PrecoDiario,
    RelatorioMensal,
    get_cnpj_by_ticker,
)

try:
    from statsmodels.regression.linear_model import OLS
    from statsmodels.stats.sandwich_covariance import cov_hac
    _HAS_SM = True
except ImportError:
    _HAS_SM = False


def _bdays_between(d1, d2, bdays_series):
    """Conta dias úteis entre duas datas usando a série de pregões disponível."""
    return int(((bdays_series >= min(d1, d2)) & (bdays_series <= max(d1, d2))).sum())


def get_events(ticker, sinal_key, session, forward_days, bdays_series):
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return []

    relatorios = session.execute(
        select(RelatorioMensal)
        .where(RelatorioMensal.cnpj == cnpj)
        .order_by(RelatorioMensal.data_entrega.asc())
    ).scalars().all()

    if not relatorios:
        return []

    eventos = []
    for i, rel in enumerate(relatorios):
        t = rel.data_entrega
        if not t:
            continue

        trading_date = session.execute(
            select(PrecoDiario.data)
            .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= t)
            .order_by(PrecoDiario.data.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not trading_date:
            continue

        is_event = False

        if sinal_key == "dist_gt_gen":
            if rel.dy_mes_pct is not None and rel.rentab_patrim is not None:
                is_event = float(rel.dy_mes_pct) > float(rel.rentab_patrim)

        elif sinal_key == "destruc_consec_2":
            if i >= 1:
                rel_ant = relatorios[i - 1]
                if rel.rentab_patrim is not None and rel_ant.rentab_patrim is not None:
                    is_event = float(rel.rentab_patrim) < 0 and float(rel_ant.rentab_patrim) < 0

        elif sinal_key == "pl_queda_2pct":
            if i >= 1:
                rel_ant = relatorios[i - 1]
                pl_t = rel.patrimonio_liq
                pl_ant = rel_ant.patrimonio_liq
                cotas_t = rel.cotas_emitidas
                cotas_ant = rel_ant.cotas_emitidas
                if all(x is not None for x in [pl_t, pl_ant, cotas_t, cotas_ant]):
                    # sem emissão significativa (< 1% de crescimento de cotas)
                    crescimento_cotas = (float(cotas_t) - float(cotas_ant)) / float(cotas_ant) if float(cotas_ant) > 0 else 0
                    queda_pl = (float(pl_t) - float(pl_ant)) / float(pl_ant) if float(pl_ant) > 0 else 0
                    is_event = queda_pl < -0.02 and crescimento_cotas < 0.01

        elif sinal_key == "corte_dy_20pct":
            if i >= 6 and rel.dy_mes_pct is not None:
                dy_atual = float(rel.dy_mes_pct)
                dys_6m = [float(relatorios[j].dy_mes_pct) for j in range(i - 6, i)
                          if relatorios[j].dy_mes_pct is not None]
                if len(dys_6m) >= 4:
                    media_6m = np.mean(dys_6m)
                    is_event = media_6m > 0 and dy_atual < media_6m * 0.8

        elif sinal_key == "dist_baixa_efetiva":
            if rel.dy_mes_pct is not None and rel.rentab_efetiva is not None:
                ef = float(rel.rentab_efetiva)
                if ef > 0:
                    is_event = float(rel.dy_mes_pct) < ef * 0.70

        elif sinal_key == "emissao_cotas":
            if i >= 1:
                rel_ant = relatorios[i - 1]
                if rel.cotas_emitidas is not None and rel_ant.cotas_emitidas is not None:
                    crescimento = (float(rel.cotas_emitidas) - float(rel_ant.cotas_emitidas)) / float(rel_ant.cotas_emitidas)
                    is_event = crescimento > 0.02

        if is_event:
            eventos.append(trading_date)

    # Filtro greedy em dias úteis (não dias corridos)
    eventos_filtrados = []
    ultima_data = None
    for ev in sorted(eventos):
        if ultima_data is None or _bdays_between(ultima_data, ev, bdays_series) >= forward_days + 5:
            eventos_filtrados.append(ev)
            ultima_data = ev

    return eventos_filtrados


def calculate_car(ticker, events, forward_days, session, info_callback=None):
    """CAR = soma de retornos diários anormais na janela [0, forward_days].
    Modelo de mercado estimado em [-200, -20] quando IFIX disponível.

    Parameters
    ----------
    info_callback : callable or None
        Se fornecida, chamada com mensagens informativas (ex: contagem de
        modelo de mercado vs fallback). Na UI Streamlit, passar ``st.info``.
    """
    precos_rows = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()

    if not precos_rows:
        return pd.DataFrame(), pd.DataFrame()

    df_p = pd.DataFrame(precos_rows, columns=["data", "fechamento_aj"])
    df_p["fechamento_aj"] = df_p["fechamento_aj"].astype(float)
    df_p["ret"] = df_p["fechamento_aj"].pct_change()
    df_p = df_p.set_index("data")

    ifix_rows = session.execute(
        select(BenchmarkDiario.data, BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == "XFIX11")
        .order_by(BenchmarkDiario.data.asc())
    ).all()

    df_ifix = pd.DataFrame(ifix_rows, columns=["data", "fechamento_ifix"])
    has_ifix = not df_ifix.empty
    if has_ifix:
        df_ifix["fechamento_ifix"] = df_ifix["fechamento_ifix"].astype(float)
        df_ifix["ret_ifix"] = df_ifix["fechamento_ifix"].pct_change()
        df_ifix = df_ifix.set_index("data")
        df_p = df_p.join(df_ifix[["ret_ifix"]], how="left")
    else:
        df_p["ret_ifix"] = np.nan

    df_p = df_p.reset_index()

    results = []
    n_mm, n_fallback = 0, 0

    for t in events:
        mask = df_p["data"] >= t
        if not mask.any():
            continue
        idx0 = df_p[mask].index[0]

        # Janela forward [idx0, idx0 + forward_days]
        idx_end = idx0 + forward_days
        if idx_end >= len(df_p):
            continue

        # Modelo de mercado: estima alpha, beta em [-200, -20]
        ini, fim = idx0 - 200, idx0 - 20
        alpha, beta, usou_mm = 0.0, 0.0, False
        if ini >= 0:
            w = df_p.iloc[ini:fim + 1].dropna(subset=["ret", "ret_ifix"])
            if len(w) >= 30:
                res = stats.linregress(w["ret_ifix"], w["ret"])
                alpha, beta, usou_mm = res.intercept, res.slope, True

        # Benchmark pré-evento para fallback (sem look-ahead)
        # Usa média rolling dos 60 pregões anteriores ao evento
        pre_start = max(0, idx0 - 60)
        benchmark_pre = float(df_p.iloc[pre_start:idx0]["ret"].mean()) if idx0 > pre_start else 0.0

        # CAR = soma de retornos anormais diários na janela forward
        window = df_p.iloc[idx0:idx_end + 1]
        car = 0.0
        for _, row in window.iterrows():
            r = row["ret"]
            if np.isnan(r):
                continue
            if usou_mm and not np.isnan(row.get("ret_ifix", np.nan)):
                ar = r - (alpha + beta * row["ret_ifix"])
            else:
                ar = r - benchmark_pre
            car += ar

        if usou_mm:
            n_mm += 1
        else:
            n_fallback += 1

        results.append({
            "data_entrega": t,
            "car": car,
            "market_model": usou_mm,
        })

    if n_fallback > 0 and info_callback is not None:
        info_callback(f"Modelo de mercado: {n_mm} eventos com IFIX, {n_fallback} com média pré-evento (60d).")

    return pd.DataFrame(results), df_p


def _nw_pvalue(cars):
    """NW HAC SE com df efetivos, bicaudal H0: CAR=0."""
    y = np.array(cars)
    n = len(y)
    if n < 4:
        return 1.0, np.nan
    mean_car = float(np.mean(y))
    if _HAS_SM:
        nlag = max(1, int(4 * (n / 100) ** (2 / 9)))
        X = np.ones((n, 1))
        model = OLS(y, X).fit()
        hc = cov_hac(model, nlags=nlag)
        se = float(np.sqrt(hc[0, 0]))
        if se == 0:
            return 1.0, np.nan
        t_stat = mean_car / se
        p = float(2 * stats.t.sf(abs(t_stat), df=max(1, n - 1)))
        return p, t_stat
    t_stat, p = stats.ttest_1samp(y, 0.0)
    return float(p), float(t_stat)


def get_bdays_series(ticker, session) -> pd.Series:
    return pd.Series(session.execute(
        select(PrecoDiario.data).where(PrecoDiario.ticker == ticker).order_by(PrecoDiario.data)
    ).scalars().all())


def compute_study_summary(df_results: pd.DataFrame, n_signals: int) -> dict:
    n = len(df_results)
    car_medio = float(df_results["car"].mean())
    car_mediana = float(df_results["car"].median())
    sucessos = int((df_results["car"] < 0).sum())
    pct_acertos = sucessos / n

    p_nw, t_stat = _nw_pvalue(df_results["car"].tolist())
    p_bonf = min(p_nw * n_signals, 1.0)

    p_wilcoxon = 1.0
    wilcoxon_warning = None
    if n >= 10:
        try:
            _, p_wilcoxon = stats.wilcoxon(df_results["car"])
        except ValueError:
            wilcoxon_warning = "Wilcoxon: todos os CARs sao iguais (variancia zero). p-value definido como 1.0."
    else:
        wilcoxon_warning = f"Amostra insuficiente para Wilcoxon (n={n} < 10). p-value definido como 1.0."

    return {
        "n": n,
        "car_medio": car_medio,
        "car_mediana": car_mediana,
        "sucessos": sucessos,
        "pct_acertos": pct_acertos,
        "p_nw": p_nw,
        "t_stat": t_stat,
        "p_bonf": p_bonf,
        "p_wilcoxon": p_wilcoxon,
        "wilcoxon_warning": wilcoxon_warning,
    }


def _block_placebo(df_p, n_eventos, forward_days, t_stat_real, n_placebo):
    """Block bootstrap circular — tamanho de bloco = forward_days."""
    pool = df_p["ret"].dropna().values
    n_pool = len(pool)
    block = forward_days
    rng = np.random.default_rng(42)
    t_stats = []

    for _ in range(n_placebo):
        cars_sim = []
        for _ in range(n_eventos):
            # Bloco aleatório de tamanho forward_days
            start = rng.integers(0, n_pool)
            bloco = np.take(pool, np.arange(start, start + block) % n_pool)
            cars_sim.append(float(bloco.sum()))
        t_p, _ = stats.ttest_1samp(cars_sim, 0.0)
        t_stats.append(t_p)

    p_placebo = float(np.mean(np.abs(t_stats) >= abs(t_stat_real)))
    return p_placebo, t_stats
