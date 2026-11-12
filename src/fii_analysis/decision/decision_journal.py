from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import (
    DecisaoLog,
    SnapshotOpportunities,
    PrecoDiario,
    BenchmarkDiario,
)


def registrar_decisao(
    session: Session,
    tipo: str,
    ticker_vendido: str | None = None,
    ticker_comprado: str | None = None,
    quantidade: int | None = None,
    preco: float | None = None,
    opportunity_id: int | None = None,
    racional_usuario: str | None = None,
    data: date | None = None,
) -> DecisaoLog:
    """Registra uma decisão real tomada pelo investidor na base de dados."""
    if data is None:
        data = date.today()

    tipo_upper = tipo.upper()
    if tipo_upper not in ["COMPRA", "VENDA", "ROTACAO", "IGNORADA"]:
        logger.warning(f"Tipo de decisão incomum: {tipo_upper}")

    decisao = DecisaoLog(
        data=data,
        tipo=tipo_upper,
        ticker_vendido=ticker_vendido,
        ticker_comprado=ticker_comprado,
        quantidade=quantidade,
        preco=preco,
        opportunity_id=opportunity_id,
        racional_usuario=racional_usuario,
    )
    session.add(decisao)
    session.commit()
    logger.info(
        f"Decisão registrada: {tipo_upper} | Vendido: {ticker_vendido} | Comprado: {ticker_comprado} | Qtd: {quantidade} | Preço: {preco}"
    )
    return decisao


def get_fechamento_on_or_before(session: Session, ticker: str, dt: date) -> float | None:
    """Busca o preço de fechamento (ajustado se disponível, senão regular) na data ou imediatamente antes."""
    row = session.execute(
        select(PrecoDiario.fechamento_aj, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= dt)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).first()
    if not row:
        return None
    val = row[0] if row[0] is not None else row[1]
    return float(val) if val is not None else None


def get_benchmark_on_or_before(session: Session, ticker: str, dt: date) -> float | None:
    """Busca o fechamento do benchmark na data ou imediatamente antes."""
    val = session.execute(
        select(BenchmarkDiario.fechamento)
        .where(BenchmarkDiario.ticker == ticker, BenchmarkDiario.data <= dt)
        .order_by(BenchmarkDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(val) if val is not None else None


def calcular_retornos_ex_post(
    session: Session,
    dias_horizonte: int = 90,
    data_base: date | None = None,
) -> list[dict[str, Any]]:
    """Calcula o retorno acumulado das rotações recomendadas em snapshot_opportunities

    no período [T, T + dias_horizonte] comparado ao XFIX11.
    """
    if data_base is None:
        # Pega a maior data de preço no banco para servir de referência (evita problemas com banco defasado em testes/offline)
        max_db_date = session.execute(select(func.max(PrecoDiario.data))).scalar()
        data_base = max_db_date if max_db_date is not None else date.today()

    max_reco_date = data_base - timedelta(days=dias_horizonte)

    # Busca todas as oportunidades cujo horizonte já passou
    opps = session.execute(
        select(SnapshotOpportunities)
        .where(SnapshotOpportunities.data_referencia <= max_reco_date)
        .order_by(SnapshotOpportunities.data_referencia.desc())
    ).scalars().all()

    resultados = []
    vistos: set[tuple] = set()  # dedup: regenerações --force criam linhas repetidas no mesmo dia
    for opp in opps:
        chave = (opp.data_referencia, opp.vender, opp.comprar)
        if chave in vistos:
            continue
        vistos.add(chave)
        t_start = opp.data_referencia
        t_end = t_start + timedelta(days=dias_horizonte)

        p_v_start = get_fechamento_on_or_before(session, opp.vender, t_start)
        p_v_end = get_fechamento_on_or_before(session, opp.vender, t_end)

        p_c_start = get_fechamento_on_or_before(session, opp.comprar, t_start)
        p_c_end = get_fechamento_on_or_before(session, opp.comprar, t_end)

        p_b_start = get_benchmark_on_or_before(session, "XFIX11", t_start)
        p_b_end = get_benchmark_on_or_before(session, "XFIX11", t_end)

        if None in (p_v_start, p_v_end, p_c_start, p_c_end):
            # Se faltam preços do par, pula
            continue

        r_vender = (p_v_end / p_v_start) - 1.0
        r_comprar = (p_c_end / p_c_start) - 1.0
        r_par = r_comprar - r_vender

        if p_b_start is not None and p_b_end is not None and p_b_start > 0:
            r_bench = (p_b_end / p_b_start) - 1.0
        else:
            r_bench = 0.0

        # Verifica se o investidor realizou essa rotação específica
        # (busca na base por matching de opportunity_id ou ticker/tipo/data aproximada)
        decisao_row = session.execute(
            select(DecisaoLog)
            .where(
                (DecisaoLog.opportunity_id == opp.id) |
                (
                    (DecisaoLog.ticker_vendido == opp.vender) &
                    (DecisaoLog.ticker_comprado == opp.comprar) &
                    (DecisaoLog.tipo == "ROTACAO") &
                    (DecisaoLog.data >= t_start - timedelta(days=2)) &
                    (DecisaoLog.data <= t_start + timedelta(days=2))
                )
            )
        ).scalars().first()

        realizada = False
        racional_usuario = None
        if decisao_row:
            if decisao_row.tipo == "ROTACAO":
                realizada = True
            racional_usuario = decisao_row.racional_usuario

        resultados.append({
            "opportunity_id": opp.id,
            "data_recomendacao": t_start,
            "vender": opp.vender,
            "comprar": opp.comprar,
            "segmento": opp.segmento,
            "spread_liquido_pct": float(opp.spread_liquido_pct),
            "delta_score": float(opp.delta_score),
            "retorno_vender": r_vender,
            "retorno_comprar": r_comprar,
            "retorno_par": r_par,
            "retorno_xfix11": r_bench,
            "bateu_xfix11": r_par > r_bench,
            "realizada": realizada,
            "racional_usuario": racional_usuario,
        })

    return resultados
