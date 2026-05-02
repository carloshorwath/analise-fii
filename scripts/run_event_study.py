"""
Event Study — roda para todos os tickers ativos com CriticAgent.

Para cada ticker:
  1. Busca janelas de dividendos (±10 pregões)
  2. Split temporal treino/validação/teste com gap (make_splits)
  3. Event study (CAR) no TREINO
  4. Testes estatísticos no TREINO (pre vs post, day 0)
  5. CriticAgent (shuffle, placebo, estabilidade) no TREINO
  6. Veredicto: SINAL REAL ou RUIDO
  7. Salva resultados em dados/event_study_results.json
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fii_analysis.config import TICKERS, TRAIN_START, TRAIN_END
from src.fii_analysis.data.database import get_session
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.models.critic import run_critic, shuffle_test, placebo_test, subperiod_stability
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


def run_ticker(ticker: str, session) -> dict:
    print("\n" + "=" * 78)
    print(f"  EVENT STUDY — {ticker}")
    print(f"  Treino: {TRAIN_START} a {TRAIN_END}")
    print("=" * 78)

    windows = get_dividend_windows(ticker, session)
    if windows.empty:
        print(f"  {ticker}: sem janelas de dividendos.")
        return {"ticker": ticker, "status": "SEM_DADOS"}

    splits = make_splits(windows, forward_days=10)
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

    n_eventos_treino = train_df["data_com"].nunique()

    es = event_study(train_df)
    car_final = _float(es["retorno_acumulado"].iloc[-1]) if not es.empty else None

    pp = test_pre_vs_post(train_df)
    d0 = test_day0_return(train_df)

    print(f"\n  --- Resultados TREINO ({n_eventos_treino} eventos) ---")
    print(f"  CAR acumulado:        {car_final * 100:+.4f}%" if car_final is not None else "  CAR acumulado:        N/A")
    if pp["ttest_pvalue"] is not None:
        print(f"  t-test (pre vs post): stat={pp['ttest_stat']:.4f}  p={pp['ttest_pvalue']:.4f}")
        print(f"  Mann-Whitney:         stat={pp['mw_stat']:.4f}  p={pp['mw_pvalue']:.4f}")
    else:
        print(f"  t-test / Mann-Whitney: eventos insuficientes")
    print(f"  Pre media:  {pp['pre_mean'] * 100:+.4f}%" if pp["pre_mean"] is not None else "  Pre media:  N/A")
    print(f"  Post media: {pp['post_mean'] * 100:+.4f}%" if pp["post_mean"] is not None else "  Post media: N/A")
    if d0["mean"] is not None:
        print(f"  Dia 0 (data-com):     media={d0['mean'] * 100:+.4f}%  t={d0['tstat']:.4f}  p={d0['pvalue']:.4f}  n={d0['n']}")
    else:
        print(f"  Dia 0 (data-com):     dados insuficientes")

    shuffle = shuffle_test(train_df)
    placebo = placebo_test(ticker, session)
    stability = subperiod_stability(train_df)

    shuffle_ok = shuffle["p_value_permutation"] is not None and shuffle["p_value_permutation"] < 0.05
    placebo_ok = placebo["mw_pvalue"] is not None and placebo["mw_pvalue"] < 0.05
    stability_ok = stability["ttest_pvalue"] is not None and stability["ttest_pvalue"] > 0.05
    all_pass = shuffle_ok and placebo_ok and stability_ok

    run_critic(ticker, train_df, session)

    veredicto = "SINAL REAL" if all_pass else "RUIDO"
    print(f"\n  >>> VEREDICTO FINAL: {veredicto}")
    print("=" * 78)

    return {
        "ticker": ticker,
        "status": "OK",
        "n_eventos_treino": n_eventos_treino,
        "n_eventos_total": len(windows),
        "splits": {
            "n_train": splits["n_train"],
            "n_val": splits["n_val"],
            "n_test": splits["n_test"],
            "train_end": splits["train_end"],
            "test_start": splits["test_start"],
        },
        "car_acumulado": car_final,
        "pre_vs_post": {
            "pre_mean": _float(pp["pre_mean"]),
            "post_mean": _float(pp["post_mean"]),
            "ttest_stat": _float(pp["ttest_stat"]),
            "ttest_pvalue": _float(pp["ttest_pvalue"]),
            "mw_stat": _float(pp["mw_stat"]),
            "mw_pvalue": _float(pp["mw_pvalue"]),
            "n_eventos": pp["n_eventos"],
        },
        "day0": {
            "mean": _float(d0["mean"]),
            "tstat": _float(d0["tstat"]),
            "pvalue": _float(d0["pvalue"]),
            "n": d0["n"],
        },
        "critic": {
            "shuffle_p": _float(shuffle["p_value_permutation"]),
            "shuffle_ok": shuffle_ok,
            "placebo_p": _float(placebo["mw_pvalue"]),
            "placebo_ok": placebo_ok,
            "stability_p": _float(stability["ttest_pvalue"]),
            "stability_ok": stability_ok,
        },
        "veredicto": veredicto,
    }


def print_veredictos(resultados: list) -> None:
    print("\n\n" + "=" * 78)
    print("  VEREDICTO FINAL — EVENT STUDY")
    print(f"  Treino: {TRAIN_START} a {TRAIN_END}")
    print("=" * 78)
    print(f"  {'Ticker':>8}  {'N':>4}  {'CAR%':>9}  "
          f"{'t-test p':>9}  {'MW p':>9}  {'Shuffle p':>9}  "
          f"{'Placebo p':>9}  {'Estab p':>9}  {'Veredicto':>10}")
    print("-" * 78)

    for r in resultados:
        if r["status"] != "OK":
            print(f"  {r['ticker']:>8}  {r['status']}")
            continue

        n = r["n_eventos_treino"]
        car = f"{r['car_acumulado']*100:+.4f}" if r["car_acumulado"] is not None else "N/A"
        tp = r["pre_vs_post"]["ttest_pvalue"]
        mp = r["pre_vs_post"]["mw_pvalue"]
        sp = r["critic"]["shuffle_p"]
        pp = r["critic"]["placebo_p"]
        ep = r["critic"]["stability_p"]

        def _fmt(val):
            return f"{val:.4f}" if val is not None else "N/A"

        print(f"  {r['ticker']:>8}  {n:>4}  {car:>9}  "
              f"{_fmt(tp):>9}  {_fmt(mp):>9}  {_fmt(sp):>9}  "
              f"{_fmt(pp):>9}  {_fmt(ep):>9}  {r['veredicto']:>10}")

    print("=" * 78)


def main():
    session = get_session()
    resultados = []
    for ticker in TICKERS:
        resultados.append(run_ticker(ticker, session))

    print_veredictos(resultados)

    DADOS_DIR.mkdir(parents=True, exist_ok=True)
    output = DADOS_DIR / "event_study_results.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(resultados, f, cls=DateTimeEncoder, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em {output}")

    session.close()


if __name__ == "__main__":
    main()
