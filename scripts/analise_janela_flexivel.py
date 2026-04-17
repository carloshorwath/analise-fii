"""
Análise de Janela Flexível para Dividend Capture
=================================================
Pergunta: Comprando no menor preço da janela pré-data-com,
em quantos ciclos existe pelo menos 1 dia pós-data-com
onde o retorno ajustado atinge um target mínimo?

Usa preço ajustado (fechamento_aj) para capturar dividendo.
"""

import sys
sys.path.insert(0, ".")

from datetime import date
from sqlalchemy import select
import pandas as pd

from src.fii_analysis.data.database import get_session, PrecoDiario, Dividendo
from src.fii_analysis.config import TICKERS, TRAIN_START, TRAIN_END, TEST_START, TEST_END

JANELA_PRE = 10   # pregões antes da data-com
JANELA_POS = 10   # pregões depois da data-com
TARGETS = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02]  # 0.25% a 2%


def analisar_janela_flexivel(ticker: str, session, start_date=None, end_date=None):
    """
    Para cada data-com:
    1. Acha o menor preço ajustado nos dias -JANELA_PRE a -1
    2. Nos dias +1 a +JANELA_POS, verifica se algum dia bateu cada target
    3. Retorna estatísticas por target
    """
    # Buscar dividendos
    q_div = select(Dividendo.data_com, Dividendo.valor_cota).where(
        Dividendo.ticker == ticker
    ).order_by(Dividendo.data_com.asc())
    dividendos = session.execute(q_div).all()
    if not dividendos:
        return None

    # Buscar preços
    q_preco = select(PrecoDiario.data, PrecoDiario.fechamento_aj, PrecoDiario.fechamento).where(
        PrecoDiario.ticker == ticker
    ).order_by(PrecoDiario.data.asc())
    precos = session.execute(q_preco).all()
    if not precos:
        return None

    datas = [p[0] for p in precos]
    fech_aj = {p[0]: float(p[1]) for p in precos if p[1] is not None}
    fech_raw = {p[0]: float(p[2]) for p in precos if p[2] is not None}
    datas_set = set(datas)

    ciclos = []

    for data_com, valor_cota in dividendos:
        if start_date and data_com < start_date:
            continue
        if end_date and data_com > end_date:
            continue

        # Achar índice da data-com nos pregões
        if data_com in datas_set:
            idx0 = datas.index(data_com)
        else:
            idx0 = None
            for i, d in enumerate(datas):
                if d > data_com:
                    break
                idx0 = i
            if idx0 is None:
                continue

        # Janela pré: dias -JANELA_PRE a -1
        idx_pre_start = max(0, idx0 - JANELA_PRE)
        idx_pre_end = idx0  # exclusive (não inclui dia 0)

        if idx_pre_start >= idx_pre_end:
            continue

        # Achar menor preço ajustado na janela pré
        min_preco_aj = None
        min_dia_rel = None
        min_data = None
        for i in range(idx_pre_start, idx_pre_end):
            d = datas[i]
            p = fech_aj.get(d)
            if p is not None:
                if min_preco_aj is None or p < min_preco_aj:
                    min_preco_aj = p
                    min_dia_rel = i - idx0  # negativo
                    min_data = d

        if min_preco_aj is None or min_preco_aj == 0:
            continue

        # Janela pós: dias +1 a +JANELA_POS
        idx_pos_start = idx0 + 1
        idx_pos_end = min(len(datas), idx0 + JANELA_POS + 1)

        if idx_pos_start >= idx_pos_end:
            continue

        # Para cada dia na janela pós, calcular retorno vs min_compra
        dias_pos = []
        for i in range(idx_pos_start, idx_pos_end):
            d = datas[i]
            p_aj = fech_aj.get(d)
            p_raw = fech_raw.get(d)
            if p_aj is not None:
                ret = p_aj / min_preco_aj - 1.0
                dias_pos.append({
                    "dia_rel": i - idx0,
                    "data": d,
                    "preco_aj": p_aj,
                    "retorno": ret,
                })

        if not dias_pos:
            continue

        # Melhor retorno na janela pós
        melhor = max(dias_pos, key=lambda x: x["retorno"])

        # Para cada target, verificar se algum dia bateu
        targets_atingidos = {}
        for t in TARGETS:
            bateu = any(dp["retorno"] >= t for dp in dias_pos)
            primeiro_dia = None
            if bateu:
                for dp in dias_pos:
                    if dp["retorno"] >= t:
                        primeiro_dia = dp["dia_rel"]
                        break
            targets_atingidos[t] = {"bateu": bateu, "primeiro_dia": primeiro_dia}

        ciclos.append({
            "data_com": data_com,
            "dividendo": float(valor_cota) if valor_cota else 0,
            "min_compra_aj": min_preco_aj,
            "min_dia_rel": min_dia_rel,
            "min_data": min_data,
            "melhor_venda_aj": melhor["preco_aj"],
            "melhor_venda_dia": melhor["dia_rel"],
            "melhor_retorno": melhor["retorno"],
            "targets": targets_atingidos,
        })

    return ciclos


def imprimir_analise(ticker: str, ciclos: list, periodo: str):
    n = len(ciclos)
    if n == 0:
        print(f"  {ticker}: sem ciclos no período {periodo}")
        return

    print(f"\n{'='*80}")
    print(f"  {ticker} — Janela Flexível — {periodo} ({n} ciclos)")
    print(f"  Janela compra: melhor preco em -{JANELA_PRE} a -1 pregoes")
    print(f"  Janela venda:  +1 a +{JANELA_POS} pregoes apos data-com")
    print(f"{'='*80}")

    # Estatísticas por target
    print(f"\n  {'Target':>8}  {'Bateu':>6}  {'%':>6}  {'Dia medio':>10}")
    for t in TARGETS:
        bateu = sum(1 for c in ciclos if c["targets"][t]["bateu"])
        pct = bateu / n * 100
        dias = [c["targets"][t]["primeiro_dia"] for c in ciclos
                if c["targets"][t]["bateu"] and c["targets"][t]["primeiro_dia"] is not None]
        dia_med = f"{sum(dias)/len(dias):.1f}" if dias else "N/A"
        print(f"  {t*100:>7.2f}%  {bateu:>5}/{n}  {pct:>5.1f}%  dia +{dia_med:>7}")

    # Melhor retorno médio
    rets = [c["melhor_retorno"] for c in ciclos]
    print(f"\n  Melhor retorno na janela (media): {sum(rets)/len(rets)*100:.4f}%")
    print(f"  Melhor retorno na janela (min):   {min(rets)*100:.4f}%")
    print(f"  Melhor retorno na janela (max):   {max(rets)*100:.4f}%")

    # Dia de compra mais frequente
    dias_compra = [c["min_dia_rel"] for c in ciclos]
    from collections import Counter
    freq = Counter(dias_compra).most_common(3)
    print(f"\n  Dia de compra mais freq (menor preco):")
    for dia, cnt in freq:
        print(f"    dia {dia:>3}: {cnt}x ({cnt/n*100:.0f}%)")

    # Detalhes por ciclo
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


def main():
    session = get_session()

    for ticker in TICKERS:
        # Treino
        ciclos_treino = analisar_janela_flexivel(ticker, session, TRAIN_START, TRAIN_END)
        if ciclos_treino:
            imprimir_analise(ticker, ciclos_treino, f"Treino {TRAIN_START}-{TRAIN_END}")

        # Teste
        ciclos_teste = analisar_janela_flexivel(ticker, session, TEST_START, TEST_END)
        if ciclos_teste:
            imprimir_analise(ticker, ciclos_teste, f"Teste {TEST_START}-{TEST_END}")

    session.close()


if __name__ == "__main__":
    main()
