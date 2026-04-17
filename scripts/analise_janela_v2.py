"""
Janela Flexível v2 — Duas estratégias realistas
================================================
A) Compra no dia médio do mínimo (identificado no treino)
B) Recompra ao preço de compra anterior (vende acima, recompra no mesmo nível)

Ambas usam preço ajustado e venda flexível com target.
"""

import sys
sys.path.insert(0, ".")

from datetime import date
from collections import Counter
from sqlalchemy import select
import pandas as pd
import numpy as np

from src.fii_analysis.data.database import get_session, PrecoDiario, Dividendo
from src.fii_analysis.config import TICKERS, TRAIN_START, TRAIN_END, TEST_START, TEST_END

JANELA_PRE = 10
JANELA_POS = 10
TARGETS = [0.005, 0.0075, 0.01]  # 0.5%, 0.75%, 1%


def carregar_dados(ticker, session):
    """Carrega preços e dividendos do DB."""
    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    dividendos = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker)
        .order_by(Dividendo.data_com.asc())
    ).all()
    datas = [p[0] for p in precos]
    fech_aj = {p[0]: float(p[1]) for p in precos if p[1] is not None}
    fech_raw = {p[0]: float(p[2]) for p in precos if p[2] is not None}
    return datas, fech_aj, fech_raw, dividendos


def achar_idx_data_com(data_com, datas, datas_set):
    """Retorna o índice do pregão da data-com (ou mais próximo anterior)."""
    if data_com in datas_set:
        return datas.index(data_com)
    idx = None
    for i, d in enumerate(datas):
        if d > data_com:
            break
        idx = i
    return idx


def identificar_dia_minimo_treino(ticker, datas, fech_aj, dividendos, start, end):
    """
    No período de treino, identifica qual dia relativo (-10 a -1) 
    mais frequentemente tem o menor preço ajustado.
    """
    datas_set = set(datas)
    contagem_min = Counter()
    
    for data_com, _ in dividendos:
        if data_com < start or data_com > end:
            continue
        idx0 = achar_idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue
        
        idx_pre_start = max(0, idx0 - JANELA_PRE)
        min_p = None
        min_rel = None
        for i in range(idx_pre_start, idx0):
            d = datas[i]
            p = fech_aj.get(d)
            if p is not None and (min_p is None or p < min_p):
                min_p = p
                min_rel = i - idx0
        if min_rel is not None:
            contagem_min[min_rel] += 1
    
    if not contagem_min:
        return -5  # fallback
    
    # Dia mais frequente
    dia_mais_freq = contagem_min.most_common(1)[0][0]
    
    # Média ponderada dos dias
    total = sum(contagem_min.values())
    media = sum(dia * cnt for dia, cnt in contagem_min.items()) / total
    
    return dia_mais_freq, round(media, 1), contagem_min


# ═══════════════════════════════════════════════════════════════════════
# ESTRATÉGIA A: Compra no dia fixo (identificado no treino como mínimo)
# ═══════════════════════════════════════════════════════════════════════

def estrategia_a(ticker, datas, fech_aj, dividendos, dia_compra, start, end):
    """
    Compra no dia relativo fixo (ex: -5).
    Vende no primeiro dia +1..+10 que atinge cada target.
    """
    datas_set = set(datas)
    ciclos = []
    
    for data_com, valor_cota in dividendos:
        if data_com < start or data_com > end:
            continue
        idx0 = achar_idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue
        
        # Compra no dia fixo
        idx_compra = idx0 + dia_compra  # dia_compra é negativo
        if idx_compra < 0 or idx_compra >= len(datas):
            continue
        preco_compra = fech_aj.get(datas[idx_compra])
        if preco_compra is None or preco_compra == 0:
            continue
        
        # Janela de venda: +1 a +JANELA_POS
        melhor_ret = None
        melhor_dia = None
        targets_hit = {}
        
        for t in TARGETS:
            targets_hit[t] = {"bateu": False, "dia": None, "ret": None}
        
        for i in range(idx0 + 1, min(len(datas), idx0 + JANELA_POS + 1)):
            d = datas[i]
            p = fech_aj.get(d)
            if p is None:
                continue
            ret = p / preco_compra - 1.0
            dia_rel = i - idx0
            
            if melhor_ret is None or ret > melhor_ret:
                melhor_ret = ret
                melhor_dia = dia_rel
            
            for t in TARGETS:
                if not targets_hit[t]["bateu"] and ret >= t:
                    targets_hit[t] = {"bateu": True, "dia": dia_rel, "ret": ret}
        
        ciclos.append({
            "data_com": data_com,
            "dividendo": float(valor_cota) if valor_cota else 0,
            "preco_compra": preco_compra,
            "dia_compra": dia_compra,
            "melhor_ret": melhor_ret,
            "melhor_dia": melhor_dia,
            "targets": targets_hit,
        })
    
    return ciclos


# ═══════════════════════════════════════════════════════════════════════
# ESTRATÉGIA B: Vende acima, recompra ao mesmo preço
# ═══════════════════════════════════════════════════════════════════════

def estrategia_b(ticker, datas, fech_aj, dividendos, dia_compra, start, end):
    """
    1. Compra no dia fixo (dia_compra)
    2. Vende no primeiro dia +1..+10 que retorno >= target
    3. Após vender, busca recompra: preço volta a <= preço de compra 
       nos dias restantes até a próxima data-com
    """
    datas_set = set(datas)
    
    # Filtrar dividendos no período
    divs_periodo = [(dc, vc) for dc, vc in dividendos if start <= dc <= end]
    
    ciclos = []
    
    for idx_div, (data_com, valor_cota) in enumerate(divs_periodo):
        idx0 = achar_idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue
        
        # Compra
        idx_compra = idx0 + dia_compra
        if idx_compra < 0 or idx_compra >= len(datas):
            continue
        preco_compra = fech_aj.get(datas[idx_compra])
        if preco_compra is None or preco_compra == 0:
            continue
        
        # Próxima data-com (para limitar janela de recompra)
        if idx_div + 1 < len(divs_periodo):
            prox_data_com = divs_periodo[idx_div + 1][0]
            idx_prox = achar_idx_data_com(prox_data_com, datas, datas_set)
        else:
            idx_prox = min(len(datas) - 1, idx0 + 30)  # fallback
        
        # Venda: primeiro dia +1..+10 com retorno >= 0.5% (target conservador)
        target_venda = 0.005  # 0.5%
        venda_feita = False
        preco_venda = None
        dia_venda = None
        ret_venda = None
        
        for i in range(idx0 + 1, min(len(datas), idx0 + JANELA_POS + 1)):
            p = fech_aj.get(datas[i])
            if p is None:
                continue
            ret = p / preco_compra - 1.0
            if ret >= target_venda:
                venda_feita = True
                preco_venda = p
                dia_venda = i - idx0
                ret_venda = ret
                break
        
        if not venda_feita:
            ciclos.append({
                "data_com": data_com,
                "dividendo": float(valor_cota) if valor_cota else 0,
                "preco_compra": preco_compra,
                "venda_feita": False,
                "recompra_possivel": False,
            })
            continue
        
        # Recompra: procurar dia onde preço <= preço_compra
        # entre a venda e a próxima data-com - dia_compra (para recomprar a tempo)
        idx_inicio_recompra = idx0 + dia_venda + 1
        idx_fim_recompra = idx_prox + dia_compra if idx_prox else len(datas)
        
        recompra_possivel = False
        preco_recompra = None
        dia_recompra = None
        dias_ate_recompra = None
        
        for i in range(idx_inicio_recompra, min(len(datas), idx_fim_recompra)):
            p = fech_aj.get(datas[i])
            if p is None:
                continue
            if p <= preco_compra:
                recompra_possivel = True
                preco_recompra = p
                dia_recompra = datas[i]
                dias_ate_recompra = i - (idx0 + dia_venda)
                break
        
        ciclos.append({
            "data_com": data_com,
            "dividendo": float(valor_cota) if valor_cota else 0,
            "preco_compra": preco_compra,
            "venda_feita": True,
            "preco_venda": preco_venda,
            "dia_venda": dia_venda,
            "ret_venda": ret_venda,
            "recompra_possivel": recompra_possivel,
            "preco_recompra": preco_recompra,
            "dia_recompra": dia_recompra,
            "dias_ate_recompra": dias_ate_recompra,
            "lucro_ciclo": (ret_venda if recompra_possivel else None),
        })
    
    return ciclos


# ═══════════════════════════════════════════════════════════════════════
# IMPRESSÃO
# ═══════════════════════════════════════════════════════════════════════

def imprimir_estrategia_a(ticker, ciclos, dia_compra, periodo):
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


def imprimir_estrategia_b(ticker, ciclos, dia_compra, periodo):
    n = len(ciclos)
    if n == 0:
        return
    
    vendas = [c for c in ciclos if c.get("venda_feita")]
    recompras = [c for c in vendas if c.get("recompra_possivel")]
    
    print(f"\n{'='*80}")
    print(f"  {ticker} — ESTRATEGIA B: vende +0.5%, recompra ao preco — {periodo}")
    print(f"  Compra: dia {dia_compra} | Venda: +1 a +{JANELA_POS} quando >=0.5%")
    print(f"{'='*80}")
    
    print(f"\n  Ciclos totais:      {n}")
    print(f"  Vendas realizadas:  {len(vendas)}/{n} ({len(vendas)/n*100:.0f}%)")
    print(f"  Recompras possiveis:{len(recompras)}/{len(vendas)} "
          f"({len(recompras)/len(vendas)*100:.0f}% das vendas)" if vendas else "")
    
    if recompras:
        dias = [c["dias_ate_recompra"] for c in recompras if c["dias_ate_recompra"]]
        rets = [c["ret_venda"] for c in recompras]
        print(f"  Dias ate recompra (media): {np.mean(dias):.1f}")
        print(f"  Lucro medio por ciclo:     {np.mean(rets)*100:.4f}%")
        
        # Lucro acumulado dos ciclos completos
        acum = 1.0
        for c in recompras:
            acum *= (1 + c["ret_venda"])
        acum -= 1.0
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


def main():
    session = get_session()
    
    for ticker in TICKERS:
        datas, fech_aj, fech_raw, dividendos = carregar_dados(ticker, session)
        
        # Identificar dia do mínimo no treino
        resultado = identificar_dia_minimo_treino(
            ticker, datas, fech_aj, dividendos, TRAIN_START, TRAIN_END)
        
        if resultado is None:
            print(f"{ticker}: sem dados suficientes")
            continue
        
        dia_freq, dia_media, contagem = resultado
        
        print(f"\n{'#'*80}")
        print(f"  {ticker} — Dia do minimo no treino")
        print(f"  Dia mais frequente: {dia_freq}")
        print(f"  Dia medio: {dia_media}")
        print(f"  Distribuicao: ", end="")
        for dia in sorted(contagem.keys()):
            print(f"[{dia}]={contagem[dia]} ", end="")
        print()
        
        # Usar dia mais frequente como dia de compra
        dia_compra = dia_freq
        
        # ── Estratégia A ──
        ciclos_a_treino = estrategia_a(
            ticker, datas, fech_aj, dividendos, dia_compra, TRAIN_START, TRAIN_END)
        imprimir_estrategia_a(ticker, ciclos_a_treino, dia_compra, "Treino")
        
        ciclos_a_teste = estrategia_a(
            ticker, datas, fech_aj, dividendos, dia_compra, TEST_START, TEST_END)
        imprimir_estrategia_a(ticker, ciclos_a_teste, dia_compra, "Teste")
        
        # ── Estratégia B ──
        ciclos_b_treino = estrategia_b(
            ticker, datas, fech_aj, dividendos, dia_compra, TRAIN_START, TRAIN_END)
        imprimir_estrategia_b(ticker, ciclos_b_treino, dia_compra, "Treino")
        
        ciclos_b_teste = estrategia_b(
            ticker, datas, fech_aj, dividendos, dia_compra, TEST_START, TEST_END)
        imprimir_estrategia_b(ticker, ciclos_b_teste, dia_compra, "Teste")
    
    session.close()


if __name__ == "__main__":
    main()
