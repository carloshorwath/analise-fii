from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import Dividendo, PrecoDiario
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.features.indicators import get_dy_trailing, get_pvp
from src.fii_analysis.models.statistical import event_study, test_day0_return, test_pre_vs_post


def _sig(pvalue: float | None) -> str:
    if pvalue is None:
        return ""
    if pvalue < 0.01:
        return "**"
    if pvalue < 0.05:
        return "*"
    return ""


def generate_report_data(ticker: str, session: Session) -> Optional[dict]:
    """Generate event study report data for a ticker (no printing).

    Returns dict with keys:
    - header: ticker, data_ref
    - preco_info: data_ultimo, fech_ultimo, pvp, dy
    - event_study: DataFrame with dia_relativo, retorno_medio, retorno_acumulado, n_eventos
    - tests: pre_post test results, day0 test results
    - resumo: n_eventos, data_min, data_max

    Returns None if insufficient data.
    """
    hoje = date.today()

    ultimo_preco = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).first()

    data_ultimo = ultimo_preco[0] if ultimo_preco else None
    fech_ultimo = float(ultimo_preco[1]) if ultimo_preco and ultimo_preco[1] else None

    pvp = get_pvp(ticker, data_ultimo, session) if data_ultimo else None
    dy = get_dy_trailing(ticker, data_ultimo, session) if data_ultimo else None

    windows = get_dividend_windows(ticker, session)
    if windows.empty:
        return {
            "header": {"ticker": ticker, "data_ref": hoje},
            "preco_info": {"data_ultimo": data_ultimo, "fech_ultimo": fech_ultimo, "pvp": pvp, "dy": dy},
            "event_study": None,
            "tests": None,
            "resumo": None,
        }

    ev = event_study(windows)
    pre_post = test_pre_vs_post(windows)
    day0 = test_day0_return(windows)

    eventos = windows["data_com"].unique()
    n_eventos = len(eventos)
    data_min = min(eventos)
    data_max = max(eventos)

    return {
        "header": {"ticker": ticker, "data_ref": hoje},
        "preco_info": {"data_ultimo": data_ultimo, "fech_ultimo": fech_ultimo, "pvp": pvp, "dy": dy},
        "event_study": ev,
        "tests": {"pre_post": pre_post, "day0": day0},
        "resumo": {"n_eventos": n_eventos, "data_min": data_min, "data_max": data_max},
    }


def print_report(ticker: str, session: Session) -> None:
    """Print formatted event study report. Calls generate_report_data() and formats output."""
    report_data = generate_report_data(ticker, session)
    if report_data is None:
        print("ERRO: Falha ao gerar relatório")
        return

    header = report_data["header"]
    preco = report_data["preco_info"]
    ev = report_data["event_study"]
    tests = report_data["tests"]
    resumo = report_data["resumo"]

    print("=" * 70)
    print(f"  RELATORIO FII — {header['ticker']}    ({header['data_ref'].strftime('%Y-%m-%d')})")
    print("=" * 70)

    if preco["fech_ultimo"]:
        print(f"\n  Preco mais recente:  R$ {preco['fech_ultimo']:.2f}  ({preco['data_ultimo']})")
    else:
        print("\n  Preco: indisponivel")

    if preco["pvp"]:
        print(f"  P/VP:                {preco['pvp']:.4f}")
    else:
        print("  P/VP:                indisponivel")

    if preco["dy"]:
        print(f"  DY trailing 12m:     {preco['dy'] * 100:.2f}%")
    else:
        print("  DY trailing 12m:     indisponivel")

    if ev is None:
        print("\n  Nenhum dado de janela de dividendos disponivel.")
        print("=" * 70)
        return

    print("\n" + "-" * 70)
    print("  EVENT STUDY — Janela -10 a +10 dias uteis")
    print("-" * 70)
    print(f"  {'Dia':>4}  {'Retorno Medio (%)':>17}  {'CAR (%)':>10}  {'N':>5}")
    print("  " + "-" * 44)
    for _, row in ev.iterrows():
        ret_pct = row["retorno_medio"] * 100 if row["retorno_medio"] is not None else 0.0
        car_pct = row["retorno_acumulado"] * 100 if row["retorno_acumulado"] is not None else 0.0
        print(f"  {int(row['dia_relativo']):>4}  {ret_pct:>16.4f}%  {car_pct:>9.4f}%  {int(row['n_eventos']):>5}")

    print("\n" + "-" * 70)
    print("  TESTES ESTATISTICOS")
    print("-" * 70)

    pre_post = tests["pre_post"]
    day0 = tests["day0"]

    print("\n  Pre vs Pos data-com (retornos acumulados por evento):")
    if pre_post["n_eventos"] and pre_post["n_eventos"] >= 2:
        print(f"    Pre  [-10,-1] media:  {pre_post['pre_mean'] * 100:>8.4f}%  std: {pre_post['pre_std'] * 100:.4f}%")
        print(f"    Pos  [+1,+10] media:  {pre_post['post_mean'] * 100:>8.4f}%  std: {pre_post['post_std'] * 100:.4f}%")
        print(f"    t-test pareado:       t={pre_post['ttest_stat']:.4f}  p={pre_post['ttest_pvalue']:.4f}{_sig(pre_post['ttest_pvalue'])}")
        print(f"    Mann-Whitney U:       U={pre_post['mw_stat']:.1f}  p={pre_post['mw_pvalue']:.4f}{_sig(pre_post['mw_pvalue'])}")
    else:
        print(f"    Eventos insuficientes para teste pareado (n={pre_post['n_eventos']})")

    print("\n  Retorno do dia 0 (data-com):")
    if day0["n"] and day0["n"] >= 2:
        print(f"    Media: {day0['mean'] * 100:>8.4f}%  std: {day0['std'] * 100:.4f}%  n={day0['n']}")
        print(f"    t-test (H0: media=0): t={day0['tstat']:.4f}  p={day0['pvalue']:.4f}{_sig(day0['pvalue'])}")
    else:
        print(f"    Eventos insuficientes (n={day0['n']})")

    print(f"\n  * p < 0.05   ** p < 0.01")

    print("\n" + "-" * 70)
    print("  RESUMO")
    print("-" * 70)
    print(f"  Total de eventos:      {resumo['n_eventos']}")
    print(f"  Periodo:               {resumo['data_min']} a {resumo['data_max']}")
    print()
    print("  ATENCAO: metricas calculadas sobre TODO o historico disponivel")
    print("  (sem separacao treino/teste). Usar apenas para exploracao.")
    print("=" * 70)
