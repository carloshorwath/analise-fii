"""
Event Study com CAR Ajustado — remove efeito mecanico do dividendo no dia +1.

Para cada ticker:
  1. Busca janelas de dividendos (±10 pregoes)
  2. Split temporal treino/validacao/teste com gap (make_splits)
  3. Ajusta retorno do dia +1: retorno_adj = retorno + (dividendo / abertura_dia+1)
  4. Event study (CAR) original e ajustado no TREINO
  5. Testes estatisticos no TREINO (pre vs post, day 0) para ambos
  6. CriticAgent nos retornos ajustados
  7. Tabela comparativa: CAR_original vs CAR_ajustado
  8. Salva em dados/event_study_car_ajustado.json
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fii_analysis.config import TICKERS, TRAIN_START, TRAIN_END
from src.fii_analysis.data.database import get_session, PrecoDiario
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.models.critic import (
    run_critic,
    shuffle_test,
    placebo_test,
    subperiod_stability,
)
from src.fii_analysis.models.statistical import event_study, test_pre_vs_post, test_day0_return
from src.fii_analysis.models.walk_forward import make_splits, print_splits_summary, validate_no_leakage


DADOS_DIR = Path(__file__).resolve().parents[1] / "dados"


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def _float(val):
    if val is None:
        return None
    return float(val)


def _fmt(val):
    return f"{val:.4f}" if val is not None else "N/A"


def adjust_windows(windows_df: pd.DataFrame, ticker: str, session) -> pd.DataFrame:
    df = windows_df.copy()

    day1_rows = df[df["dia_relativo"] == 1][["data_com", "data"]].copy()
    if day1_rows.empty:
        df["retorno_adj"] = df["retorno"]
        return df

    day1_dates = day1_rows["data"].tolist()
    aberturas = session.execute(
        select(PrecoDiario.data, PrecoDiario.abertura)
        .where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data.in_(day1_dates),
            PrecoDiario.abertura.isnot(None),
        )
    ).all()
    abertura_map = {a.data: float(a.abertura) for a in aberturas}

    div_map = (
        df[df["dia_relativo"] == 0][["data_com", "valor_cota"]]
        .dropna(subset=["valor_cota"])
        .set_index("data_com")["valor_cota"]
        .to_dict()
    )

    df["retorno_adj"] = df["retorno"]
    mask = df["dia_relativo"] == 1
    for idx in df[mask].index:
        dc = df.loc[idx, "data_com"]
        d = df.loc[idx, "data"]
        ret = df.loc[idx, "retorno"]
        abert = abertura_map.get(d)
        div = div_map.get(dc)
        if ret is not None and abert and abert > 0 and div is not None:
            df.loc[idx, "retorno_adj"] = ret + (div / abert)

    return df


def run_ticker(ticker: str, session) -> dict:
    print("\n" + "=" * 78)
    print(f"  EVENT STUDY CAR AJUSTADO — {ticker}")
    print(f"  Treino: {TRAIN_START} a {TRAIN_END}")
    print("=" * 78)

    windows = get_dividend_windows(ticker, session)
    if windows.empty:
        print(f"  {ticker}: sem janelas de dividendos.")
        return {"ticker": ticker, "status": "SEM_DADOS"}

    splits = make_splits(windows)
    print_splits_summary(splits)

    errors = validate_no_leakage(splits, windows)
    if errors:
        print("  >>> LEAKAGE DETECTADO:")
        for e in errors:
            print(f"      {e}")
        return {"ticker": ticker, "status": "LEAKAGE", "leakage_errors": errors}

    train_df = splits["train"]
    if train_df.empty:
        print(f"  {ticker}: treino vazio apos gap.")
        return {"ticker": ticker, "status": "TREINO_VAZIO"}

    n_eventos = train_df["data_com"].nunique()

    train_adj = adjust_windows(train_df, ticker, session)

    train_adj_for_study = train_adj.copy()
    train_adj_for_study["retorno"] = train_adj_for_study["retorno_adj"]

    es_orig = event_study(train_df)
    es_adj = event_study(train_adj_for_study)

    car_orig = _float(es_orig["retorno_acumulado"].iloc[-1]) if not es_orig.empty else None
    car_adj = _float(es_adj["retorno_acumulado"].iloc[-1]) if not es_adj.empty else None

    pp_orig = test_pre_vs_post(train_df)
    pp_adj = test_pre_vs_post(train_adj_for_study)

    d0_orig = test_day0_return(train_df)
    d0_adj = test_day0_return(train_adj_for_study)

    print(f"\n  --- COMPARACAO TREINO ({n_eventos} eventos) ---")
    print(f"  {'':>22}  {'Original':>10}  {'Ajustado':>10}")
    print(f"  {'CAR acumulado':>22}  {_fmt(car_orig*100) if car_orig else 'N/A':>10}%  "
          f"{_fmt(car_adj*100) if car_adj else 'N/A':>10}%")
    print(f"  {'Pre media':>22}  {_fmt(pp_orig['pre_mean']*100) if pp_orig['pre_mean'] else 'N/A':>10}%  "
          f"{_fmt(pp_adj['pre_mean']*100) if pp_adj['pre_mean'] else 'N/A':>10}%")
    print(f"  {'Post media':>22}  {_fmt(pp_orig['post_mean']*100) if pp_orig['post_mean'] else 'N/A':>10}%  "
          f"{_fmt(pp_adj['post_mean']*100) if pp_adj['post_mean'] else 'N/A':>10}%")
    print(f"  {'t-test p (pre/post)':>22}  {_fmt(pp_orig['ttest_pvalue']):>10}  {_fmt(pp_adj['ttest_pvalue']):>10}")
    print(f"  {'MW p (pre/post)':>22}  {_fmt(pp_orig['mw_pvalue']):>10}  {_fmt(pp_adj['mw_pvalue']):>10}")
    print(f"  {'Dia 0 media':>22}  {_fmt(d0_orig['mean']*100) if d0_orig['mean'] else 'N/A':>10}%  "
          f"{_fmt(d0_adj['mean']*100) if d0_adj['mean'] else 'N/A':>10}%")
    print(f"  {'Dia 0 t-test p':>22}  {_fmt(d0_orig['pvalue']):>10}  {_fmt(d0_adj['pvalue']):>10}")

    print(f"\n  --- CAR POR DIA (ajustado) ---")
    print(f"  {'Dia':>4}  {'CAR_orig%':>10}  {'CAR_adj%':>10}  {'diff%':>8}")
    for _, row_orig in es_orig.iterrows():
        dia = int(row_orig["dia_relativo"])
        car_o = row_orig["retorno_acumulado"] * 100
        adj_row = es_adj[es_adj["dia_relativo"] == dia]
        if adj_row.empty:
            continue
        car_a = float(adj_row["retorno_acumulado"].values[0]) * 100
        diff = car_a - car_o
        marker = " <-- ex-div" if dia == 1 else ""
        print(f"  {dia:>4}  {car_o:>+10.4f}  {car_a:>+10.4f}  {diff:>+8.4f}{marker}")

    print(f"\n  --- CriticAgent (retornos ajustados) ---")
    shuffle = shuffle_test(train_adj_for_study)
    placebo = placebo_test(ticker, session)
    stability = subperiod_stability(train_adj_for_study)

    shuffle_ok = shuffle["p_value_permutation"] is not None and shuffle["p_value_permutation"] < 0.05
    placebo_ok = placebo["mw_pvalue"] is not None and placebo["mw_pvalue"] < 0.05
    stability_ok = stability["ttest_pvalue"] is not None and stability["ttest_pvalue"] > 0.05
    all_pass_adj = shuffle_ok and placebo_ok and stability_ok

    run_critic(ticker, train_adj_for_study, session)

    veredicto_adj = "SINAL REAL" if all_pass_adj else "RUIDO"
    print(f"\n  >>> VEREDICTO CAR AJUSTADO: {veredicto_adj}")
    print("=" * 78)

    return {
        "ticker": ticker,
        "status": "OK",
        "n_eventos_treino": n_eventos,
        "n_eventos_total": len(windows),
        "splits": {
            "n_train": splits["n_train"],
            "n_val": splits["n_val"],
            "n_test": splits["n_test"],
        },
        "original": {
            "car_acumulado": car_orig,
            "pre_vs_post": {
                "pre_mean": _float(pp_orig["pre_mean"]),
                "post_mean": _float(pp_orig["post_mean"]),
                "ttest_pvalue": _float(pp_orig["ttest_pvalue"]),
                "mw_pvalue": _float(pp_orig["mw_pvalue"]),
                "n_eventos": pp_orig["n_eventos"],
            },
            "day0": {
                "mean": _float(d0_orig["mean"]),
                "pvalue": _float(d0_orig["pvalue"]),
                "n": d0_orig["n"],
            },
        },
        "ajustado": {
            "car_acumulado": car_adj,
            "pre_vs_post": {
                "pre_mean": _float(pp_adj["pre_mean"]),
                "post_mean": _float(pp_adj["post_mean"]),
                "ttest_pvalue": _float(pp_adj["ttest_pvalue"]),
                "mw_pvalue": _float(pp_adj["mw_pvalue"]),
                "n_eventos": pp_adj["n_eventos"],
            },
            "day0": {
                "mean": _float(d0_adj["mean"]),
                "pvalue": _float(d0_adj["pvalue"]),
                "n": d0_adj["n"],
            },
        },
        "critic_ajustado": {
            "shuffle_p": _float(shuffle["p_value_permutation"]),
            "shuffle_ok": shuffle_ok,
            "placebo_p": _float(placebo["mw_pvalue"]),
            "placebo_ok": placebo_ok,
            "stability_p": _float(stability["ttest_pvalue"]),
            "stability_ok": stability_ok,
        },
        "veredicto_ajustado": veredicto_adj,
    }


def print_comparativo(resultados: list) -> None:
    print("\n\n" + "=" * 100)
    print("  COMPARATIVO — CAR ORIGINAL vs CAR AJUSTADO")
    print(f"  Treino: {TRAIN_START} a {TRAIN_END}")
    print("=" * 100)
    print(f"  {'Ticker':>8}  {'N':>4}  {'CAR_orig%':>10}  {'CAR_adj%':>10}  {'Diff%':>8}  "
          f"{'t-orig p':>9}  {'t-adj p':>9}  {'Shuffle p':>9}  {'Placebo p':>9}  {'Estab p':>9}  "
          f"{'Veredicto':>10}")
    print("-" * 100)

    for r in resultados:
        if r["status"] != "OK":
            print(f"  {r['ticker']:>8}  {r['status']}")
            continue

        n = r["n_eventos_treino"]
        co = r["original"]["car_acumulado"]
        ca = r["ajustado"]["car_acumulado"]
        car_o = f"{co*100:+.4f}" if co is not None else "N/A"
        car_a = f"{ca*100:+.4f}" if ca is not None else "N/A"
        diff = f"{(ca - co)*100:+.4f}" if co is not None and ca is not None else "N/A"

        tp_o = r["original"]["pre_vs_post"]["ttest_pvalue"]
        tp_a = r["ajustado"]["pre_vs_post"]["ttest_pvalue"]
        sp = r["critic_ajustado"]["shuffle_p"]
        pp = r["critic_ajustado"]["placebo_p"]
        ep = r["critic_ajustado"]["stability_p"]

        print(f"  {r['ticker']:>8}  {n:>4}  {car_o:>10}  {car_a:>10}  {diff:>8}  "
              f"{_fmt(tp_o):>9}  {_fmt(tp_a):>9}  {_fmt(sp):>9}  {_fmt(pp):>9}  {_fmt(ep):>9}  "
              f"{r['veredicto_ajustado']:>10}")

    print("=" * 100)
    print("  CAR ajustado = CAR original + ajuste do dividendo no dia +1 (ex-date)")
    print("  Ajuste: retorno_adj[dia+1] = retorno[dia+1] + (dividendo / abertura_dia+1)")
    print("=" * 100)


def main():
    session = get_session()
    resultados = []
    for ticker in TICKERS:
        resultados.append(run_ticker(ticker, session))

    print_comparativo(resultados)

    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    output = DADOS_DIR / "event_study_car_ajustado.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(resultados, f, cls=DateTimeEncoder, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em {output}")

    session.close()


if __name__ == "__main__":
    main()
