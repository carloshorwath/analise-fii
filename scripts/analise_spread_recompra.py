"""
Estrategia Spread-Recompra
===========================
Investidor JA POSSUI o FII. A cada data-com:
1. Vende quando preco ajustado >= preco_compra * (1 + target)
2. Espera preco voltar a <= preco_compra
3. Recompra -> lucro = target no bolso, mesma posicao

Pergunta: com que frequencia o preco volta a P apos subir a P+target?
"""

import sys
sys.path.insert(0, ".")

from sqlalchemy import select
import numpy as np

from src.fii_analysis.data.database import get_session, PrecoDiario, Dividendo
from src.fii_analysis.config import TICKERS, TRAIN_START, TRAIN_END, TEST_START, TEST_END

JANELA_VENDA = 10    # pregoes apos data-com para vender
TARGETS = [0.005, 0.0075, 0.01, 0.015]  # 0.5% a 1.5%


def carregar_dados(ticker, session):
    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
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
    return datas, fech_aj, dividendos


def simular_spread(ticker, datas, fech_aj, dividendos, target, start, end):
    """
    Simula a estrategia de spread-recompra para um target especifico.
    
    O investidor comeca com posicao comprada no primeiro preco disponivel.
    A cada data-com:
      - Se tem posicao: tenta vender a preco_compra * (1+target) nos +1..+10
      - Se vendeu: espera preco voltar a <= preco_compra ate a proxima data-com
      - Se recomprou: lucro = spread, posicao restaurada
    """
    datas_set = set(datas)
    
    # Filtrar dividendos no periodo
    divs = [(dc, float(vc) if vc else 0) for dc, vc in dividendos
            if start <= dc <= end]
    
    if not divs:
        return None
    
    # Preco inicial: primeiro preco antes da primeira data-com
    primeira_dc = divs[0][0]
    preco_compra = None
    for d in datas:
        if d >= primeira_dc:
            break
        p = fech_aj.get(d)
        if p:
            preco_compra = p
    
    if preco_compra is None:
        return None
    
    ciclos = []
    posicao = True  # comeca comprado
    
    for idx_div, (data_com, dividendo) in enumerate(divs):
        # Achar indice do pregao da data-com
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
        
        # Proxima data-com (para limitar janela de recompra)
        if idx_div + 1 < len(divs):
            prox_dc = divs[idx_div + 1][0]
            idx_prox = None
            for i, d in enumerate(datas):
                if d >= prox_dc:
                    idx_prox = i
                    break
            if idx_prox is None:
                idx_prox = len(datas)
        else:
            idx_prox = len(datas)
        
        ciclo = {
            "data_com": data_com,
            "dividendo": dividendo,
            "preco_compra": preco_compra,
            "posicao_inicio": posicao,
            "venda_feita": False,
            "recompra_feita": False,
            "preco_venda": None,
            "dia_venda": None,
            "preco_recompra": None,
            "dia_recompra": None,
            "dias_fora": None,
            "lucro": None,
        }
        
        if not posicao:
            # Nao tem posicao, procura recompra antes da data-com
            for i in range(max(0, idx0 - 20), idx0 + 1):
                p = fech_aj.get(datas[i])
                if p is not None and p <= preco_compra:
                    posicao = True
                    preco_compra = p  # recomprou
                    ciclo["recompra_feita"] = True
                    ciclo["preco_recompra"] = p
                    ciclo["dia_recompra"] = datas[i]
                    break
            
            if not posicao:
                ciclo["posicao_inicio"] = False
                ciclos.append(ciclo)
                continue
        
        # Tem posicao - tenta vender apos data-com
        preco_alvo_venda = preco_compra * (1 + target)
        
        for i in range(idx0 + 1, min(len(datas), idx0 + JANELA_VENDA + 1)):
            p = fech_aj.get(datas[i])
            if p is not None and p >= preco_alvo_venda:
                ciclo["venda_feita"] = True
                ciclo["preco_venda"] = p
                ciclo["dia_venda"] = i - idx0
                
                # Agora procura recompra: preco <= preco_compra
                # entre a venda e a proxima data-com
                for j in range(i + 1, idx_prox):
                    pj = fech_aj.get(datas[j])
                    if pj is not None and pj <= preco_compra:
                        ciclo["recompra_feita"] = True
                        ciclo["preco_recompra"] = pj
                        ciclo["dia_recompra"] = datas[j]
                        ciclo["dias_fora"] = j - i
                        ciclo["lucro"] = p / preco_compra - 1.0
                        posicao = True
                        # preco_compra permanece o mesmo (recomprou ao mesmo nivel)
                        break
                
                if not ciclo["recompra_feita"]:
                    posicao = False  # ficou fora
                    ciclo["lucro"] = None
                
                break
        
        ciclos.append(ciclo)
    
    return ciclos


def imprimir_resultados(ticker, target, ciclos_treino, ciclos_teste):
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
        print(f"  Recompras ok:        {len(recompras):>3}/{len(vendas) if vendas else 1} "
              f"({len(recompras)/len(vendas)*100:.0f}%)" if vendas else "")
        print(f"  Ficou fora (risco):  {len(fora):>3}")
        
        if recompras:
            dias = [c["dias_fora"] for c in recompras if c["dias_fora"]]
            lucros = [c["lucro"] for c in recompras if c["lucro"]]
            acum = 1.0
            for l in lucros:
                acum *= (1 + l)
            acum -= 1.0
            print(f"  Dias fora (media):   {np.mean(dias):.1f}" if dias else "")
            print(f"  Lucro medio/ciclo:   {np.mean(lucros)*100:.4f}%")
            print(f"  Lucro acumulado:     {acum*100:.4f}% ({len(recompras)} ciclos completos)")
        
        # Detalhes
        print(f"\n  {'Data-com':>12}  {'P.compra':>9}  "
              f"{'Vendeu?':>7}  {'P.venda':>8}  {'DiaV':>5}  "
              f"{'Recomprou?':>10}  {'DiasFora':>8}")
        for c in ciclos:
            vendeu = "SIM" if c["venda_feita"] else "---"
            pv = f"{c['preco_venda']:.2f}" if c["preco_venda"] else "---"
            dv = f"+{c['dia_venda']}" if c["dia_venda"] else "---"
            recomp = "SIM" if c["recompra_feita"] else ("FORA" if c["venda_feita"] else "---")
            df = f"{c['dias_fora']}" if c["dias_fora"] else "---"
            
            if not c["posicao_inicio"]:
                vendeu = "S/POS"
            
            print(f"  {str(c['data_com']):>12}  {c['preco_compra']:>9.2f}  "
                  f"{vendeu:>7}  {pv:>8}  {dv:>5}  "
                  f"{recomp:>10}  {df:>8}")


def main():
    session = get_session()
    
    for ticker in TICKERS:
        datas, fech_aj, dividendos = carregar_dados(ticker, session)
        
        for target in TARGETS:
            ciclos_treino = simular_spread(
                ticker, datas, fech_aj, dividendos, target, TRAIN_START, TRAIN_END)
            ciclos_teste = simular_spread(
                ticker, datas, fech_aj, dividendos, target, TEST_START, TEST_END)
            
            imprimir_resultados(ticker, target, ciclos_treino, ciclos_teste)
    
    session.close()


if __name__ == "__main__":
    main()
