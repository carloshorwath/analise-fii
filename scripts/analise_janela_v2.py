"""
CLI: Janela Flexível v2 — Duas estratégias realistas
=====================================================
A) Compra no dia médio do mínimo (identificado no treino)
B) Recompra ao preço de compra anterior (vende acima, recompra no mesmo nível)
"""

import sys
sys.path.insert(0, ".")

import numpy as np

from src.fii_analysis.config import TEST_END, TEST_START, TICKERS, TRAIN_END, TRAIN_START
from src.fii_analysis.data.database import get_session
from src.fii_analysis.models.div_capture import (
    carregar_dados_ticker,
    estrategia_compra_fixa,
    estrategia_vende_recompra,
    identificar_dia_minimo_treino,
)

JANELA_POS = 10
TARGETS = [0.005, 0.0075, 0.01]


def imprimir_estrategia_a(ticker: str, ciclos: list, dia_compra: int, periodo: str) -> None:
    n = len(ciclos)
    if n == 0:
        return

    print(f"\n{'='*80}")
    print(f"  {ticker} — ESTRATEGIA A: compra fixa dia {dia_compra} — {periodo} ({n} ciclos)")
    print(f"{'='*80}")

    print(f"\n  {'Target':>8}  {'Bateu':>6}  {'%':>6}  {'Dia medio':>10}")
    for t in TARGETS:
        bateu = sum(1 for c in ciclos if c["targets"][t]["bateu"])
        pct = bateu / n * 100
        dias = [c["targets"][t]["dia"] for c in ciclos if c["targets"][t]["bateu"]]
        dia_med = f"{sum(dias)/len(dias):.1f}" if dias else "N/A"
        print(f"  {t*100:>7.2f}%  {bateu:>5}/{n}  {pct:>5.1f}%  dia +{dia_med:>7}")

    rets = [c["melhor_ret"] for c in ciclos if c["melhor_ret"] is not None]
    if rets:
        print(f"\n  Melhor ret na janela: media={np.mean(rets)*100:.2f}%  "
              f"min={min(rets)*100:.2f}%  max={max(rets)*100:.2f}%")


def imprimir_estrategia_b(ticker: str, ciclos: list, dia_compra: int, periodo: str) -> None:
    n = len(ciclos)
    if n == 0:
        return

    vendas = [c for c in ciclos if c.get("venda_feita")]
    recompras = [c for c in vendas if c.get("recompra_possivel")]

    print(f"\n{'='*80}")
    print(f"  {ticker} — ESTRATEGIA B: vende +0.5%, recompra ao preço — {periodo}")
    print(f"  Compra: dia {dia_compra} | Venda: +1 a +{JANELA_POS} quando >=0.5%")
    print(f"{'='*80}")

    print(f"\n  Ciclos totais:      {n}")
    print(f"  Vendas realizadas:  {len(vendas)}/{n} ({len(vendas)/n*100:.0f}%)")
    if vendas:
        print(f"  Recompras possíveis:{len(recompras)}/{len(vendas)} "
              f"({len(recompras)/len(vendas)*100:.0f}% das vendas)")

    if recompras:
        dias = [c["dias_ate_recompra"] for c in recompras if c["dias_ate_recompra"]]
        rets = [c["ret_venda"] for c in recompras]
        acum = 1.0
        for r in rets:
            acum *= (1 + r)
        acum -= 1.0
        print(f"  Dias até recompra (média): {np.mean(dias):.1f}" if dias else "")
        print(f"  Lucro médio por ciclo:     {np.mean(rets)*100:.4f}%")
        print(f"  Lucro acumulado ({len(recompras)} ciclos): {acum*100:.4f}%")

    print(f"\n  {'Data-com':>12}  {'CompraAj':>9}  {'VendaAj':>8}  {'Ret%':>7}  "
          f"{'DiaV':>5}  {'Recompra':>9}  {'DiasR':>6}")
    for c in ciclos:
        if not c.get("venda_feita"):
            print(f"  {str(c['data_com']):>12}  {c['preco_compra']:>9.2f}  "
                  f"{'---':>8}  {'---':>7}  {'---':>5}  {'SEM VENDA':>9}  {'---':>6}")
            continue
        recomp = "SIM" if c.get("recompra_possivel") else "NAO"
        dias_r = f"{c['dias_ate_recompra']}" if c.get("dias_ate_recompra") else "---"
        print(f"  {str(c['data_com']):>12}  {c['preco_compra']:>9.2f}  "
              f"{c['preco_venda']:>8.2f}  {c['ret_venda']*100:>+6.2f}%  "
              f"+{c['dia_venda']:>4}  {recomp:>9}  {dias_r:>6}")


def main() -> None:
    session = get_session()

    for ticker in TICKERS:
        datas, fech_aj, _fech_raw, dividendos = carregar_dados_ticker(ticker, session)

        resultado = identificar_dia_minimo_treino(
            datas, fech_aj, dividendos, TRAIN_START, TRAIN_END)

        dia_freq, dia_media, contagem = resultado

        print(f"\n{'#'*80}")
        print(f"  {ticker} — Dia do mínimo no treino")
        print(f"  Dia mais frequente: {dia_freq}")
        print(f"  Dia médio: {dia_media}")
        print(f"  Distribuição: ", end="")
        for dia in sorted(contagem.keys()):
            print(f"[{dia}]={contagem[dia]} ", end="")
        print()

        dia_compra = dia_freq

        # Estratégia A
        ciclos_a_treino = estrategia_compra_fixa(
            datas, fech_aj, dividendos, dia_compra, TRAIN_START, TRAIN_END,
            tuple(TARGETS), JANELA_POS)
        imprimir_estrategia_a(ticker, ciclos_a_treino, dia_compra, "Treino")

        ciclos_a_teste = estrategia_compra_fixa(
            datas, fech_aj, dividendos, dia_compra, TEST_START, TEST_END,
            tuple(TARGETS), JANELA_POS)
        imprimir_estrategia_a(ticker, ciclos_a_teste, dia_compra, "Teste")

        # Estratégia B
        ciclos_b_treino = estrategia_vende_recompra(
            datas, fech_aj, dividendos, dia_compra, TRAIN_START, TRAIN_END,
            target_venda=0.005, janela_pos=JANELA_POS)
        imprimir_estrategia_b(ticker, ciclos_b_treino, dia_compra, "Treino")

        ciclos_b_teste = estrategia_vende_recompra(
            datas, fech_aj, dividendos, dia_compra, TEST_START, TEST_END,
            target_venda=0.005, janela_pos=JANELA_POS)
        imprimir_estrategia_b(ticker, ciclos_b_teste, dia_compra, "Teste")

    session.close()


if __name__ == "__main__":
    main()
