import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.data.database import Dividendo, PrecoDiario


def shuffle_test(windows_df: pd.DataFrame, n_simulations: int = 1000, seed: int = 42) -> dict:
    day0 = windows_df[windows_df["dia_relativo"] == 0]["retorno"].dropna().values
    if len(day0) < 2:
        return {
            "t_real": None,
            "t_simulacoes_media": None,
            "t_simulacoes_std": None,
            "p_value_permutation": None,
            "n_sim": n_simulations,
            "conclusion": "DADOS INSUFICIENTES",
        }

    t_real = stats.ttest_1samp(day0, 0.0).statistic

    rng = np.random.default_rng(seed)
    t_sims = np.empty(n_simulations)

    # Permutation test: sob H0 (média=0), cada retorno é igualmente positivo ou negativo
    # Invertemos sinais aleatoriamente e recalculamos t — distribuição nula correta
    for sim in range(n_simulations):
        signs = rng.choice([-1.0, 1.0], size=len(day0))
        t_sims[sim] = stats.ttest_1samp(day0 * signs, 0.0).statistic

    p_perm = float(np.mean(np.abs(t_sims) >= np.abs(t_real)))
    conclusion = "SINAL REAL (p<0.05)" if p_perm < 0.05 else "SINAL ESPURIO"

    return {
        "t_real": float(t_real),
        "t_simulacoes_media": float(t_sims.mean()),
        "t_simulacoes_std": float(t_sims.std()),
        "p_value_permutation": p_perm,
        "n_sim": n_simulations,
        "conclusion": conclusion,
    }


def placebo_test(ticker: str, session, n_placebo: int = 500, seed: int = 42) -> dict:
    pregoes = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if len(pregoes) < 21:
        return {
            "real_mean_day0": None,
            "placebo_mean_day0": None,
            "mw_pvalue": None,
            "n_real": 0,
            "n_placebo": 0,
            "conclusion": "PREGOES INSUFICIENTES",
        }

    datas = [p.data for p in pregoes]
    fech_map = {p.data: float(p.fechamento) for p in pregoes if p.fechamento is not None}
    datas_set = set(datas)

    dividendos_reais = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
    ).scalars().all()

    datas_com = session.execute(
        select(Dividendo.data_com).where(Dividendo.ticker == ticker)
    ).scalars().all()

    real_day0 = []
    for dc in datas_com:
        if dc not in datas_set:
            idx0 = None
            for i, d in enumerate(datas):
                if d > dc:
                    break
                idx0 = i
            if idx0 is None:
                continue
        else:
            idx0 = datas.index(dc)

        if idx0 < 1 or idx0 >= len(datas):
            continue
        f0 = fech_map.get(datas[idx0])
        f_ant = fech_map.get(datas[idx0 - 1])
        if f0 is not None and f_ant is not None and f_ant != 0:
            real_day0.append((f0 / f_ant) - 1.0)

    rng = np.random.default_rng(seed)
    eligible_indices = list(range(10, len(datas) - 10))
    placebo_day0 = []

    for _ in range(n_placebo):
        idx = rng.choice(eligible_indices)
        f0 = fech_map.get(datas[idx])
        f_ant = fech_map.get(datas[idx - 1])
        if f0 is not None and f_ant is not None and f_ant != 0:
            placebo_day0.append((f0 / f_ant) - 1.0)

    if len(real_day0) < 2 or len(placebo_day0) < 2:
        return {
            "real_mean_day0": float(np.mean(real_day0)) if real_day0 else None,
            "placebo_mean_day0": float(np.mean(placebo_day0)) if placebo_day0 else None,
            "mw_pvalue": None,
            "n_real": len(real_day0),
            "n_placebo": len(placebo_day0),
            "conclusion": "AMOSTRAS INSUFICIENTES",
        }

    mw = stats.mannwhitneyu(real_day0, placebo_day0, alternative="two-sided")
    conclusion = "PADRAO ESPECIFICO DA DATA-COM (p<0.05)" if mw.pvalue < 0.05 else "PADRAO GENERICO (nao especifico)"

    return {
        "real_mean_day0": float(np.mean(real_day0)),
        "placebo_mean_day0": float(np.mean(placebo_day0)),
        "mw_pvalue": float(mw.pvalue),
        "n_real": len(real_day0),
        "n_placebo": len(placebo_day0),
        "conclusion": conclusion,
    }


def subperiod_stability(windows_df: pd.DataFrame) -> dict:
    day0 = windows_df[windows_df["dia_relativo"] == 0][["data_com", "retorno"]].dropna()
    if len(day0) < 4:
        return {
            "first_half_mean": None,
            "second_half_mean": None,
            "first_half_n": 0,
            "second_half_n": 0,
            "ttest_pvalue": None,
            "conclusion": "EVENTOS INSUFICIENTES",
        }

    day0 = day0.sort_values("data_com")
    mid = len(day0) // 2
    first = day0.iloc[:mid]["retorno"].values
    second = day0.iloc[mid:]["retorno"].values

    if len(first) < 2 or len(second) < 2:
        return {
            "first_half_mean": float(first.mean()),
            "second_half_mean": float(second.mean()),
            "first_half_n": len(first),
            "second_half_n": len(second),
            "ttest_pvalue": None,
            "conclusion": "AMOSTRAS INSUFICIENTES",
        }

    t_res = stats.ttest_ind(first, second, equal_var=False)
    conclusion = "ESTAVEL (p>0.05)" if t_res.pvalue > 0.05 else "INSTAVEL - padrao muda entre periodos"

    return {
        "first_half_mean": float(first.mean()),
        "second_half_mean": float(second.mean()),
        "first_half_n": len(first),
        "second_half_n": len(second),
        "ttest_pvalue": float(t_res.pvalue),
        "conclusion": conclusion,
    }


def run_critic(ticker: str, windows_df: pd.DataFrame, session) -> None:
    print("=" * 70)
    print(f"  CRITIC AGENT — {ticker}")
    print("=" * 70)

    resultados = []

    print("\n--- TESTE 1: Permutation Shuffle ---")
    shuffle = shuffle_test(windows_df)
    print(f"  t-real:             {shuffle['t_real']:.4f}" if shuffle["t_real"] is not None else "  t-real:             N/A")
    print(f"  t-simulacoes media: {shuffle['t_simulacoes_media']:.4f}" if shuffle["t_simulacoes_media"] is not None else "  t-simulacoes media: N/A")
    print(f"  p-value perm:       {shuffle['p_value_permutation']:.4f}" if shuffle["p_value_permutation"] is not None else "  p-value perm:       N/A")
    print(f"  simulacoes:         {shuffle['n_sim']}")
    print(f"  >>> {shuffle['conclusion']}")
    shuffle_ok = shuffle["p_value_permutation"] is not None and shuffle["p_value_permutation"] < 0.05
    resultados.append(("Permutation Shuffle", shuffle["conclusion"], shuffle_ok))

    print("\n--- TESTE 2: Placebo (datas aleatorias) ---")
    placebo = placebo_test(ticker, session)
    print(f"  Real mean day0:     {placebo['real_mean_day0'] * 100:.4f}%" if placebo["real_mean_day0"] is not None else "  Real mean day0:     N/A")
    print(f"  Placebo mean day0:  {placebo['placebo_mean_day0'] * 100:.4f}%" if placebo["placebo_mean_day0"] is not None else "  Placebo mean day0:  N/A")
    print(f"  Mann-Whitney p:     {placebo['mw_pvalue']:.4f}" if placebo["mw_pvalue"] is not None else "  Mann-Whitney p:     N/A")
    print(f"  n_real={placebo['n_real']}  n_placebo={placebo['n_placebo']}")
    print(f"  >>> {placebo['conclusion']}")
    placebo_ok = placebo["mw_pvalue"] is not None and placebo["mw_pvalue"] < 0.05
    resultados.append(("Placebo", placebo["conclusion"], placebo_ok))

    print("\n--- TESTE 3: Subperiod Stability ---")
    stability = subperiod_stability(windows_df)
    print(f"  1a metade media:    {stability['first_half_mean'] * 100:.4f}%  (n={stability['first_half_n']})" if stability["first_half_mean"] is not None else "  1a metade: N/A")
    print(f"  2a metade media:    {stability['second_half_mean'] * 100:.4f}%  (n={stability['second_half_n']})" if stability["second_half_mean"] is not None else "  2a metade: N/A")
    print(f"  t-test p-value:     {stability['ttest_pvalue']:.4f}" if stability["ttest_pvalue"] is not None else "  t-test p-value:     N/A")
    print(f"  >>> {stability['conclusion']}")
    stability_ok = stability["ttest_pvalue"] is not None and stability["ttest_pvalue"] > 0.05
    resultados.append(("Subperiod Stability", stability["conclusion"], stability_ok))

    print("\n" + "=" * 70)
    print("  VEREDICTO")
    print("=" * 70)
    todos_passaram = all(r[2] for r in resultados)
    if todos_passaram:
        print("  APROVADO — todos os testes passaram")
    else:
        falharam = [r[0] for r in resultados if not r[2]]
        print(f"  REPROVADO — falharam: {', '.join(falharam)}")
    print("=" * 70)
