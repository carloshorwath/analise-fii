import numpy as np
import pandas as pd
from scipy import stats


def event_study(windows_df: pd.DataFrame) -> pd.DataFrame:
    if windows_df.empty:
        return pd.DataFrame(columns=["dia_relativo", "retorno_medio", "retorno_acumulado", "n_eventos"])

    agg = (
        windows_df.groupby("dia_relativo")
        .agg(retorno_medio=("retorno", "mean"), n_eventos=("data_com", "nunique"))
        .reset_index()
    )
    agg = agg.sort_values("dia_relativo").reset_index(drop=True)
    agg["retorno_acumulado"] = agg["retorno_medio"].cumsum().shift(1, fill_value=0.0)
    return agg[["dia_relativo", "retorno_medio", "retorno_acumulado", "n_eventos"]]


def test_pre_vs_post(windows_df: pd.DataFrame) -> dict:
    pre = windows_df[(windows_df["dia_relativo"] >= -10) & (windows_df["dia_relativo"] <= -1)]
    post = windows_df[(windows_df["dia_relativo"] >= 1) & (windows_df["dia_relativo"] <= 10)]

    pre_cum = pre.groupby("data_com")["retorno"].sum()
    post_cum = post.groupby("data_com")["retorno"].sum()

    eventos = pre_cum.index.intersection(post_cum.index)
    pre_vals = pre_cum.loc[eventos].values
    post_vals = post_cum.loc[eventos].values

    if len(eventos) < 2:
        return {
            "pre_mean": float(pre_vals.mean()) if len(pre_vals) > 0 else None,
            "post_mean": float(post_vals.mean()) if len(post_vals) > 0 else None,
            "pre_std": float(pre_vals.std()) if len(pre_vals) > 0 else None,
            "post_std": float(post_vals.std()) if len(post_vals) > 0 else None,
            "n_eventos": len(eventos),
            "ttest_stat": None,
            "ttest_pvalue": None,
            "mw_stat": None,
            "mw_pvalue": None,
        }

    t_res = stats.ttest_rel(pre_vals, post_vals)
    mw_res = stats.mannwhitneyu(pre_vals, post_vals, alternative="two-sided")

    return {
        "pre_mean": float(pre_vals.mean()),
        "post_mean": float(post_vals.mean()),
        "pre_std": float(pre_vals.std(ddof=1)),
        "post_std": float(post_vals.std(ddof=1)),
        "n_eventos": len(eventos),
        "ttest_stat": float(t_res.statistic),
        "ttest_pvalue": float(t_res.pvalue),
        "mw_stat": float(mw_res.statistic),
        "mw_pvalue": float(mw_res.pvalue),
    }


def test_day0_return(windows_df: pd.DataFrame) -> dict:
    day0 = windows_df[windows_df["dia_relativo"] == 0]["retorno"].dropna().values

    if len(day0) < 2:
        return {
            "mean": float(day0.mean()) if len(day0) > 0 else None,
            "std": float(day0.std()) if len(day0) > 0 else None,
            "n": len(day0),
            "tstat": None,
            "pvalue": None,
        }

    t_res = stats.ttest_1samp(day0, 0.0)

    return {
        "mean": float(day0.mean()),
        "std": float(day0.std(ddof=1)),
        "n": len(day0),
        "tstat": float(t_res.statistic),
        "pvalue": float(t_res.pvalue),
    }
