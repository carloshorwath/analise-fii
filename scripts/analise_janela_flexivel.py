"""
CLI: Análise de Janela Flexível para Dividend Capture
=====================================================
Pergunta: comprando no menor preço da janela pré-data-com,
em quantos ciclos existe pelo menos 1 dia pós onde o retorno
ajustado atinge um target mínimo?
"""

import sys
sys.path.insert(0, ".")

from collections import Counter

from src.fii_analysis.config import TEST_END, TEST_START, TICKERS, TRAIN_END, TRAIN_START
from src.fii_analysis.data.database import get_session
from src.fii_analysis.models.div_capture import analisar_janela_flexivel

JANELA_PRE = 10
JANELA_POS = 10
TARGETS = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02]


def imprimir_analise(ticker: str, ciclos: list, periodo: str) -> None:
    n = len(ciclos)
    if n == 0:
        print(f"  {ticker}: sem ciclos no período {periodo}")
        return

    print(f"\n{'='*80}")
    print(f"  {ticker} — Janela Flexível — {periodo} ({n} ciclos)")
    print(f"  Janela compra: melhor preço em -{JANELA_PRE} a -1 pregões")
    print(f"  Janela venda:  +1 a +{JANELA_POS} pregões após data-com")
    print(f"{'='*80}")

    print(f"\n  {'Target':>8}  {'Bateu':>6}  {'%':>6}  {'Dia medio':>10}")
    for t in TARGETS:
        bateu = sum(1 for c in ciclos if c["targets"][t]["bateu"])
        pct = bateu / n * 100
        dias = [
            c["targets"][t]["primeiro_dia"]
            for c in ciclos
            if c["targets"][t]["bateu"] and c["targets"][t]["primeiro_dia"] is not None
        ]
        dia_med = f"{sum(dias)/len(dias):.1f}" if dias else "N/A"
        print(f"  {t*100:>7.2f}%  {bateu:>5}/{n}  {pct:>5.1f}%  dia +{dia_med:>7}")

    rets = [c["melhor_retorno"] for c in ciclos]
    print(f"\n  Melhor retorno na janela (media): {sum(rets)/len(rets)*100:.4f}%")
    print(f"  Melhor retorno na janela (min):   {min(rets)*100:.4f}%")
    print(f"  Melhor retorno na janela (max):   {max(rets)*100:.4f}%")

    dias_compra = [c["min_dia_rel"] for c in ciclos]
    freq = Counter(dias_compra).most_common(3)
    print(f"\n  Dia de compra mais freq (menor preço):")
    for dia, cnt in freq:
        print(f"    dia {dia:>3}: {cnt}x ({cnt/n*100:.0f}%)")

    print(f"\n  {'Data-com':>12}  {'Div':>6}  {'CompraAj':>9}  {'DiaC':>5}  "
          f"{'MelhorRet%':>10}  {'DiaV':>5}  ", end="")
    for t in TARGETS:
        print(f" {t*100:.2f}%", end="")
    print()

    for c in ciclos:
        print(f"  {str(c['data_com']):>12}  {c['dividendo']:>6.4f}  "
              f"{c['min_compra_aj']:>9.2f}  {c['min_dia_rel']:>5}  "
              f"{c['melhor_retorno']*100:>+10.4f}  {c['melhor_venda_dia']:>5}  ", end="")
        for t in TARGETS:
            ok = "S" if c["targets"][t]["bateu"] else "N"
            print(f"    {ok} ", end="")
        print()


def main() -> None:
    session = get_session()
    for ticker in TICKERS:
        ciclos_treino = analisar_janela_flexivel(
            ticker, session, TRAIN_START, TRAIN_END, JANELA_PRE, JANELA_POS, tuple(TARGETS))
        if ciclos_treino:
            imprimir_analise(ticker, ciclos_treino, f"Treino {TRAIN_START}-{TRAIN_END}")

        ciclos_teste = analisar_janela_flexivel(
            ticker, session, TEST_START, TEST_END, JANELA_PRE, JANELA_POS, tuple(TARGETS))
        if ciclos_teste:
            imprimir_analise(ticker, ciclos_teste, f"Teste {TEST_START}-{TEST_END}")
    session.close()


if __name__ == "__main__":
    main()
