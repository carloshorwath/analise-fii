"""
Estratégias de Dividend Capture para FIIs.
Lógica de negócio pura — sem dependências de UI ou impressão.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import Dividendo, PrecoDiario


# ─── helpers internos ────────────────────────────────────────────────────────

def _carregar_dados(ticker: str, session: Session) -> tuple:
    """Retorna (datas, fech_aj, fech_raw, dividendos)."""
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


def _idx_data_com(data_com: date, datas: list, datas_set: set) -> Optional[int]:
    """Índice do pregão da data-com (ou mais próximo anterior)."""
    if data_com in datas_set:
        return datas.index(data_com)
    idx = None
    for i, d in enumerate(datas):
        if d > data_com:
            break
        idx = i
    return idx


# ─── API pública ─────────────────────────────────────────────────────────────

def carregar_dados_ticker(ticker: str, session: Session) -> tuple:
    """
    Carrega preços e dividendos do DB para um ticker.
    Retorna (datas, fech_aj, fech_raw, dividendos).
    """
    return _carregar_dados(ticker, session)


def analisar_janela_flexivel(
    ticker: str,
    session: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    janela_pre: int = 10,
    janela_pos: int = 10,
    targets: tuple[float, ...] = (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02),
) -> list[dict]:
    """
    Para cada data-com, identifica o menor preço na janela pré e verifica se
    algum dia pós atinge cada target de retorno ajustado.
    Retorna lista de ciclos com resultados por target.
    """
    datas, fech_aj, _fech_raw, dividendos = _carregar_dados(ticker, session)
    if not dividendos or not datas:
        return []

    datas_set = set(datas)
    ciclos = []

    for data_com, valor_cota in dividendos:
        if start_date and data_com < start_date:
            continue
        if end_date and data_com > end_date:
            continue

        idx0 = _idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue

        idx_pre_start = max(0, idx0 - janela_pre)
        if idx_pre_start >= idx0:
            continue

        min_preco_aj, min_dia_rel, min_data = None, None, None
        for i in range(idx_pre_start, idx0):
            d = datas[i]
            p = fech_aj.get(d)
            if p is not None and (min_preco_aj is None or p < min_preco_aj):
                min_preco_aj = p
                min_dia_rel = i - idx0
                min_data = d

        if min_preco_aj is None:
            continue

        dias_pos = []
        for i in range(idx0 + 1, min(len(datas), idx0 + janela_pos + 1)):
            d = datas[i]
            p = fech_aj.get(d)
            if p is not None:
                dias_pos.append({
                    "dia_rel": i - idx0,
                    "data": d,
                    "preco_aj": p,
                    "retorno": p / min_preco_aj - 1.0,
                })

        if not dias_pos:
            continue

        melhor = max(dias_pos, key=lambda x: x["retorno"])
        targets_atingidos = {
            t: {
                "bateu": any(dp["retorno"] >= t for dp in dias_pos),
                "primeiro_dia": next((dp["dia_rel"] for dp in dias_pos if dp["retorno"] >= t), None),
            }
            for t in targets
        }

        ciclos.append({
            "data_com": data_com,
            "dividendo": float(valor_cota) if valor_cota else 0.0,
            "min_compra_aj": min_preco_aj,
            "min_dia_rel": min_dia_rel,
            "min_data": min_data,
            "melhor_venda_aj": melhor["preco_aj"],
            "melhor_venda_dia": melhor["dia_rel"],
            "melhor_retorno": melhor["retorno"],
            "targets": targets_atingidos,
        })

    return ciclos


def identificar_dia_minimo_treino(
    datas: list,
    fech_aj: dict,
    dividendos: list,
    start: date,
    end: date,
    janela_pre: int = 10,
) -> tuple[int, float, Counter]:
    """
    No treino, identifica qual dia relativo (-janela_pre a -1) mais frequentemente
    tem o menor preço ajustado.
    Retorna (dia_mais_freq, media_ponderada, contagem).
    """
    datas_set = set(datas)
    contagem: Counter = Counter()

    for data_com, _ in dividendos:
        if data_com < start or data_com > end:
            continue
        idx0 = _idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue

        min_p, min_rel = None, None
        for i in range(max(0, idx0 - janela_pre), idx0):
            p = fech_aj.get(datas[i])
            if p is not None and (min_p is None or p < min_p):
                min_p = p
                min_rel = i - idx0
        if min_rel is not None:
            contagem[min_rel] += 1

    if not contagem:
        return -5, -5.0, contagem

    dia_mais_freq = contagem.most_common(1)[0][0]
    total = sum(contagem.values())
    media = sum(dia * cnt for dia, cnt in contagem.items()) / total
    return dia_mais_freq, round(media, 1), contagem


def estrategia_compra_fixa(
    datas: list,
    fech_aj: dict,
    dividendos: list,
    dia_compra: int,
    start: date,
    end: date,
    targets: tuple[float, ...] = (0.005, 0.0075, 0.01),
    janela_pos: int = 10,
) -> list[dict]:
    """
    Compra no dia relativo fixo (ex: -5) identificado no treino.
    Vende no primeiro dia pós que atinge cada target de retorno.
    Retorna lista de ciclos.
    """
    datas_set = set(datas)
    ciclos = []

    for data_com, valor_cota in dividendos:
        if data_com < start or data_com > end:
            continue
        idx0 = _idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue

        idx_compra = idx0 + dia_compra  # dia_compra é negativo
        if idx_compra < 0 or idx_compra >= len(datas):
            continue
        preco_compra = fech_aj.get(datas[idx_compra])
        if preco_compra is None:
            continue

        melhor_ret, melhor_dia = None, None
        targets_hit = {t: {"bateu": False, "dia": None, "ret": None} for t in targets}

        for i in range(idx0 + 1, min(len(datas), idx0 + janela_pos + 1)):
            p = fech_aj.get(datas[i])
            if p is None:
                continue
            ret = p / preco_compra - 1.0
            dia_rel = i - idx0

            if melhor_ret is None or ret > melhor_ret:
                melhor_ret, melhor_dia = ret, dia_rel

            for t in targets:
                if not targets_hit[t]["bateu"] and ret >= t:
                    targets_hit[t] = {"bateu": True, "dia": dia_rel, "ret": ret}

        ciclos.append({
            "data_com": data_com,
            "dividendo": float(valor_cota) if valor_cota else 0.0,
            "preco_compra": preco_compra,
            "dia_compra": dia_compra,
            "melhor_ret": melhor_ret,
            "melhor_dia": melhor_dia,
            "targets": targets_hit,
        })

    return ciclos


def estrategia_vende_recompra(
    datas: list,
    fech_aj: dict,
    dividendos: list,
    dia_compra: int,
    start: date,
    end: date,
    target_venda: float = 0.005,
    janela_pos: int = 10,
) -> list[dict]:
    """
    Compra no dia fixo, vende quando retorno >= target_venda,
    depois tenta recomprar ao preço de compra antes da próxima data-com.
    Retorna lista de ciclos com resultado de cada operação.
    """
    datas_set = set(datas)
    divs_periodo = [(dc, vc) for dc, vc in dividendos if start <= dc <= end]
    ciclos = []

    for idx_div, (data_com, valor_cota) in enumerate(divs_periodo):
        idx0 = _idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue

        idx_compra = idx0 + dia_compra
        if idx_compra < 0 or idx_compra >= len(datas):
            continue
        preco_compra = fech_aj.get(datas[idx_compra])
        if preco_compra is None:
            continue

        idx_prox = (
            _idx_data_com(divs_periodo[idx_div + 1][0], datas, datas_set)
            if idx_div + 1 < len(divs_periodo)
            else min(len(datas) - 1, idx0 + 30)
        )

        venda_feita = False
        preco_venda, dia_venda, ret_venda = None, None, None

        for i in range(idx0 + 1, min(len(datas), idx0 + janela_pos + 1)):
            p = fech_aj.get(datas[i])
            if p is None:
                continue
            if p / preco_compra - 1.0 >= target_venda:
                venda_feita = True
                preco_venda = p
                dia_venda = i - idx0
                ret_venda = p / preco_compra - 1.0
                break

        if not venda_feita:
            ciclos.append({
                "data_com": data_com,
                "dividendo": float(valor_cota) if valor_cota else 0.0,
                "preco_compra": preco_compra,
                "venda_feita": False,
                "recompra_possivel": False,
            })
            continue

        recompra_possivel = False
        preco_recompra, dia_recompra, dias_ate_recompra = None, None, None
        idx_inicio = idx0 + dia_venda + 1
        idx_fim = (idx_prox + dia_compra) if idx_prox is not None else len(datas)

        for i in range(idx_inicio, min(len(datas), idx_fim)):
            p = fech_aj.get(datas[i])
            if p is not None and p <= preco_compra:
                recompra_possivel = True
                preco_recompra = p
                dia_recompra = datas[i]
                dias_ate_recompra = i - (idx0 + dia_venda)
                break

        ciclos.append({
            "data_com": data_com,
            "dividendo": float(valor_cota) if valor_cota else 0.0,
            "preco_compra": preco_compra,
            "venda_feita": True,
            "preco_venda": preco_venda,
            "dia_venda": dia_venda,
            "ret_venda": ret_venda,
            "recompra_possivel": recompra_possivel,
            "preco_recompra": preco_recompra,
            "dia_recompra": dia_recompra,
            "dias_ate_recompra": dias_ate_recompra,
            "lucro_ciclo": ret_venda if recompra_possivel else None,
        })

    return ciclos


def simular_spread_recompra(
    datas: list,
    fech_aj: dict,
    dividendos: list,
    target: float,
    start: date,
    end: date,
    janela_venda: int = 10,
) -> Optional[list[dict]]:
    """
    Investidor JÁ POSSUI o FII.
    Vende quando preço >= preco_compra * (1 + target), aguarda o preço voltar.
    Retorna lista de ciclos ou None se sem dados.
    """
    datas_set = set(datas)
    divs = [(dc, float(vc) if vc else 0.0) for dc, vc in dividendos if start <= dc <= end]
    if not divs:
        return None

    # Preço inicial: último fechamento antes da primeira data-com
    primeira_dc = divs[0][0]
    preco_compra = None
    for d in datas:
        if d >= primeira_dc:
            break
        p = fech_aj.get(d)
        if p is not None:
            preco_compra = p

    if preco_compra is None:
        return None

    ciclos = []
    posicao = True

    for idx_div, (data_com, dividendo) in enumerate(divs):
        idx0 = _idx_data_com(data_com, datas, datas_set)
        if idx0 is None:
            continue

        idx_prox = len(datas)
        if idx_div + 1 < len(divs):
            for i, d in enumerate(datas):
                if d >= divs[idx_div + 1][0]:
                    idx_prox = i
                    break

        ciclo: dict = {
            "data_com": data_com, "dividendo": dividendo,
            "preco_compra": preco_compra, "posicao_inicio": posicao,
            "venda_feita": False, "recompra_feita": False,
            "preco_venda": None, "dia_venda": None,
            "preco_recompra": None, "dia_recompra": None,
            "dias_fora": None, "lucro": None,
        }

        if not posicao:
            for i in range(max(0, idx0 - 20), idx0 + 1):
                p = fech_aj.get(datas[i])
                if p is not None and p <= preco_compra:
                    posicao = True
                    preco_compra = p
                    ciclo.update({"recompra_feita": True, "preco_recompra": p, "dia_recompra": datas[i]})
                    break
            if not posicao:
                ciclos.append(ciclo)
                continue

        preco_alvo = preco_compra * (1 + target)
        for i in range(idx0 + 1, min(len(datas), idx0 + janela_venda + 1)):
            p = fech_aj.get(datas[i])
            if p is not None and p >= preco_alvo:
                ciclo.update({"venda_feita": True, "preco_venda": p, "dia_venda": i - idx0})
                for j in range(i + 1, idx_prox):
                    pj = fech_aj.get(datas[j])
                    if pj is not None and pj <= preco_compra:
                        ciclo.update({
                            "recompra_feita": True, "preco_recompra": pj,
                            "dia_recompra": datas[j], "dias_fora": j - i,
                            "lucro": p / preco_compra - 1.0,
                        })
                        posicao = True
                        break
                if not ciclo["recompra_feita"]:
                    posicao = False
                break

        ciclos.append(ciclo)

    return ciclos
