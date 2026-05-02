"""
CLI: Estratégia Spread-Recompra
================================
Investidor JÁ POSSUI o FII. A cada data-com:
1. Vende quando preço ajustado >= preco_compra * (1 + target)
2. Espera preço voltar a <= preco_compra
3. Recompra → lucro = target no bolso, mesma posição
"""

import sys
sys.path.insert(0, ".")

import numpy as np

from src.fii_analysis.config import TEST_END, TEST_START, TICKERS, TRAIN_END, TRAIN_START
from src.fii_analysis.data.database import get_session
from src.fii_analysis.models.div_capture import carregar_dados_ticker, simular_spread_recompra

TARGETS = [0.005, 0.0075, 0.01, 0.015]


def imprimir_resultados(ticker: str, target: float, ciclos_treino, ciclos_teste) -> None:
    print(f"\n{'='*90}")
    print(f"  {ticker} — Target: {target*100:.1f}%")
    print(f"{'='*90}")

    for periodo, ciclos in [("Treino", ciclos_treino), ("Teste", ciclos_teste)]:
        if not ciclos:
            continue

        n = len(ciclos)
        vendas = [c for c in ciclos if c["venda_feita"]]
        recompras = [c for c in vendas if c["recompra_feita"]]
        fora = [c for c in vendas if not c["recompra_feita"]]

        print(f"\n  --- {periodo} ({n} ciclos) ---")
        print(f"  Vendas realizadas:   {len(vendas):>3}/{n} ({len(vendas)/n*100:.0f}%)")
        if vendas:
            print(f"  Recompras ok:        {len(recompras):>3}/{len(vendas)} "
                  f"({len(recompras)/len(vendas)*100:.0f}%)")
        print(f"  Ficou fora (risco):  {len(fora):>3}")

        if recompras:
            dias = [c["dias_fora"] for c in recompras if c["dias_fora"]]
            lucros = [c["lucro"] for c in recompras if c["lucro"]]
            acum = 1.0
            for lc in lucros:
                acum *= (1 + lc)
            acum -= 1.0
            if dias:
                print(f"  Dias fora (média):   {np.mean(dias):.1f}")
            print(f"  Lucro médio/ciclo:   {np.mean(lucros)*100:.4f}%")
            print(f"  Lucro acumulado:     {acum*100:.4f}% ({len(recompras)} ciclos completos)")

        print(f"\n  {'Data-com':>12}  {'P.compra':>9}  "
              f"{'Vendeu?':>7}  {'P.venda':>8}  {'DiaV':>5}  "
              f"{'Recomprou?':>10}  {'DiasFora':>8}")
        for c in ciclos:
            vendeu = "SIM" if c["venda_feita"] else "---"
            if not c["posicao_inicio"]:
                vendeu = "S/POS"
            pv = f"{c['preco_venda']:.2f}" if c["preco_venda"] else "---"
            dv = f"+{c['dia_venda']}" if c["dia_venda"] else "---"
            recomp = "SIM" if c["recompra_feita"] else ("FORA" if c["venda_feita"] else "---")
            df = f"{c['dias_fora']}" if c["dias_fora"] else "---"
            print(f"  {str(c['data_com']):>12}  {c['preco_compra']:>9.2f}  "
                  f"{vendeu:>7}  {pv:>8}  {dv:>5}  "
                  f"{recomp:>10}  {df:>8}")


def main() -> None:
    session = get_session()

    for ticker in TICKERS:
        datas, fech_aj, _fech_raw, dividendos = carregar_dados_ticker(ticker, session)

        for target in TARGETS:
            ciclos_treino = simular_spread_recompra(
                datas, fech_aj, dividendos, target, TRAIN_START, TRAIN_END)
            ciclos_teste = simular_spread_recompra(
                datas, fech_aj, dividendos, target, TEST_START, TEST_END)
            imprimir_resultados(ticker, target, ciclos_treino, ciclos_teste)

    session.close()


if __name__ == "__main__":
    main()
