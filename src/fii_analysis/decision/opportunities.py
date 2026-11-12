"""Motor de Oportunidades de Rotação (vender X da carteira → comprar Y do IFIX).

Desenho (universo dual, ADR-23):
  - Lado VENDER: decisões completas da carteira (recommender + portfolio_advisor).
  - Lado COMPRAR: métricas + radar do snapshot (universo IFIX é observação,
    não recebe os 3 motores de decisão — eles só são validados para a lista curada).

O resultado é DESCRITIVO: pares candidatos com filtros de valuation relativo,
saúde, liquidez e custos — sem validação estatística de retorno futuro.
O spread líquido é uma margem de segurança heurística (percentil P/VP menos
um haircut de custos em %), não uma previsão de retorno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy import select, func

from src.fii_analysis.config_yaml import get_oportunidades_param, get_threshold, get_piso_liquidez
from src.fii_analysis.data.database import (
    Carteira,
    SnapshotRun,
    SnapshotTickerMetrics,
    SnapshotRadar,
    SnapshotOpportunities,
    PrecoDiario,
    Universo,
)
from src.fii_analysis.decision.elegibilidade import motivo_bloqueio_compra
from src.fii_analysis.decision.recommender import TickerDecision, decidir_universo
from src.fii_analysis.decision.portfolio_advisor import aconselhar_carteira
from src.fii_analysis.features.valuation import get_pvp_percentil
from src.fii_analysis.features.risk_metrics import liquidez_media_21d
from src.fii_analysis.features.composicao import classificar_fii
from src.fii_analysis.features.saude import get_ltv_flag


@dataclass
class RotationOpportunity:
    vender: str               # ticker da carteira
    comprar: str              # candidato do universo IFIX
    segmento: str             # rotação intra-segmento (Tijolo/Papel/Híbrido)
    spread_pvp_pct: float     # pvp_percentil(vender) - pvp_percentil(comprar)
    spread_dy_gap: float      # dy_gap_percentil(comprar) - dy_gap_percentil(vender)
    delta_score: float        # score(comprar) - score(vender)
    custo_estimado_pct: float # corretagem B3 + IR 20% sobre ganho da venda (% do valor)
    spread_liquido_pct: float # spread bruto - haircut de custos (heurístico)
    dias_persistencia: int    # nº de pregões em que o par ficou acima do limiar
    turnaround: bool = False  # candidato a comprar está "em recuperação" (compra na baixa)
    racional: list[str] = field(default_factory=list)
    flags_veto: list[str] = field(default_factory=list)


@dataclass
class _BuyCandidate:
    """Fatos mínimos do lado COMPRAR, independente da fonte (snapshot ou decisões)."""
    ticker: str
    classe: str                       # Tijolo / Papel / Híbrido
    pvp_percentil: float
    dy_gap_percentil: Optional[float]
    score_total: Optional[int]
    turnaround: bool = False
    flag_ltv_alto: bool = False
    ltv_atual: Optional[float] = None
    dividend_safety_flag: bool = False
    payout_vs_caixa: Optional[float] = None


def _obter_pvp_percentil_historico(ticker: str, d: date, session) -> Optional[float]:
    """Lê o percentil P/VP de um snapshot existente; fallback para cálculo point-in-time."""
    run = session.execute(
        select(SnapshotRun.id)
        .where(SnapshotRun.data_referencia == d, SnapshotRun.status == "ready")
        .order_by(SnapshotRun.criado_em.desc())
        .limit(1)
    ).scalar_one_or_none()

    if run is not None:
        val = session.execute(
            select(SnapshotTickerMetrics.pvp_percentil)
            .where(SnapshotTickerMetrics.run_id == run, SnapshotTickerMetrics.ticker == ticker)
        ).scalar_one_or_none()
        if val is not None:
            return float(val)

    try:
        pvp_pct, _ = get_pvp_percentil(ticker, d, 504, session)
        return float(pvp_pct) if pvp_pct is not None else None
    except Exception:
        return None


def obter_ultimos_pregoes(session, data_ref: date, n: int) -> list[date]:
    """Retorna os últimos n pregões (datas distintas com preço) até data_ref, inclusive."""
    rows = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.data <= data_ref)
        .order_by(PrecoDiario.data.desc())
        .distinct()
        .limit(n)
    ).scalars().all()
    return sorted(rows)


def _tickers_ifix(session) -> list[str]:
    """Tickers em IFIX na composição mais recente da tabela universo."""
    latest = session.execute(select(func.max(Universo.data_referencia))).scalar_one_or_none()
    if not latest:
        return []
    return session.execute(
        select(Universo.ticker)
        .where(Universo.em_ifix == True, Universo.data_referencia == latest)  # noqa: E712
    ).scalars().all()


def _bloqueio_candidato(session, ticker: str, data_ref: Optional[date]) -> Optional[str]:
    """Motivo pelo qual o ticker nao pode ser candidato de compra (liquidacao, preco defasado)."""
    try:
        motivo = motivo_bloqueio_compra(ticker, data_ref, session)
    except Exception as exc:  # elegibilidade nao pode derrubar o motor de rotacao
        logger.warning("{}: falha ao checar elegibilidade de compra: {}", ticker, exc)
        return None
    if motivo:
        logger.info("{}: excluido como candidato de compra — {}", ticker, motivo)
    return motivo


def _candidatos_comprar_de_snapshot(
    session, run_id: int, tickers_universo: set[str], tickers_carteira: set[str],
    data_ref: Optional[date] = None,
) -> list[_BuyCandidate]:
    """Lado COMPRAR a partir de snapshot_ticker_metrics + snapshot_radar do run.

    Filtros (PROJETO.md §5.4): saúde OK e liquidez OK obrigatórios, P/VP barato,
    radar >= 3/4 vistos, CVM não defasada. "Em recuperação" não é vetado — vira
    candidato TURNAROUND com rótulo explícito (o mercado pode já ter precificado).
    """
    pvp_barato = get_threshold("pvp_percentil_barato", 30)

    rows = session.execute(
        select(SnapshotTickerMetrics, SnapshotRadar)
        .join(
            SnapshotRadar,
            (SnapshotRadar.run_id == SnapshotTickerMetrics.run_id)
            & (SnapshotRadar.ticker == SnapshotTickerMetrics.ticker),
        )
        .where(SnapshotTickerMetrics.run_id == run_id)
    ).all()

    candidatos: list[_BuyCandidate] = []
    for met, rad in rows:
        t = met.ticker
        if t in tickers_carteira or t not in tickers_universo:
            continue
        if not rad.saude_ok or not rad.liquidez_ok:
            continue
        if met.cvm_defasada:
            continue
        if met.pvp_percentil is None or float(met.pvp_percentil) > pvp_barato:
            continue
        if (rad.vistos or 0) < 3:
            continue
        if _bloqueio_candidato(session, t, data_ref):
            continue

        classe = classificar_fii(t, session=session)
        if not classe or classe == "Indefinido":
            continue

        turnaround = bool(rad.saude_motivo and "RECUPERA" in rad.saude_motivo.upper())

        candidatos.append(_BuyCandidate(
            ticker=t,
            classe=classe,
            pvp_percentil=float(met.pvp_percentil),
            dy_gap_percentil=float(met.dy_gap_percentil) if met.dy_gap_percentil is not None else None,
            score_total=int(met.score_total) if met.score_total is not None else None,
            turnaround=turnaround,
        ))
    return candidatos


def _candidatos_comprar_de_decisoes(
    session,
    universo_decisoes: dict[str, TickerDecision],
    tickers_universo: set[str],
    tickers_carteira: set[str],
    data_ref: Optional[date] = None,
) -> list[_BuyCandidate]:
    """Lado COMPRAR a partir de TickerDecision (caminho legado / testes)."""
    pvp_barato = get_threshold("pvp_percentil_barato", 30)
    dy_caro = get_threshold("dy_gap_percentil_caro", 70)
    piso = get_piso_liquidez()

    candidatos: list[_BuyCandidate] = []
    for t in tickers_universo:
        if t in tickers_carteira:
            continue
        decisao = universo_decisoes.get(t)
        if not decisao:
            continue
        if decisao.bloqueio_compra or _bloqueio_candidato(session, t, data_ref):
            continue

        saude_ok = not decisao.flag_destruicao_capital
        vol = liquidez_media_21d(t, session)
        liquidez_ok = vol is not None and vol >= piso
        pvp_pct = decisao.pvp_percentil
        cvm_ok = not getattr(decisao, "cvm_defasada", False)

        pvp_baixo = pvp_pct is not None and pvp_pct < pvp_barato
        dy_gap_pct = decisao.dy_gap_percentil
        dy_gap_alto = dy_gap_pct is not None and dy_gap_pct > dy_caro
        vistos = sum([pvp_baixo, dy_gap_alto, saude_ok, liquidez_ok])

        if not (saude_ok and liquidez_ok and cvm_ok and pvp_pct is not None
                and pvp_pct <= pvp_barato and vistos >= 3):
            continue

        classe = decisao.classificacao
        if not classe or classe == "Indefinido":
            continue

        motivo = (decisao.motivo_destruicao or "").upper()
        candidatos.append(_BuyCandidate(
            ticker=t,
            classe=classe,
            pvp_percentil=float(pvp_pct),
            dy_gap_percentil=float(dy_gap_pct) if dy_gap_pct is not None else None,
            score_total=decisao.score_total,
            turnaround="RECUPERA" in motivo,
            flag_ltv_alto=bool(getattr(decisao, "flag_ltv_alto", False)),
            ltv_atual=getattr(decisao, "ltv_atual", None),
            dividend_safety_flag=bool(getattr(decisao, "dividend_safety_flag", False)),
            payout_vs_caixa=getattr(decisao, "payout_vs_caixa", None),
        ))
    return candidatos


def detectar_oportunidades(
    session,
    data_ref: date,
    universo_decisoes: Optional[dict[str, TickerDecision]] = None,
    run_id: Optional[int] = None,
) -> list[RotationOpportunity]:
    """Identifica trocas intra-segmento: posição cara da carteira → candidato barato do IFIX.

    Fontes do lado COMPRAR (em ordem de preferência):
      1. ``run_id`` — métricas/radar do snapshot em construção (caminho de produção);
      2. ``universo_decisoes`` — TickerDecision por ticker (caminho legado/testes).
    """
    logger.info("Executando motor de rotação para {}", data_ref)

    # 1. Carteira
    carteira_rows = session.execute(select(Carteira)).scalars().all()
    if not carteira_rows:
        logger.info("Carteira vazia. Nenhuma oportunidade de rotação aplicável.")
        return []

    holdings = [
        {
            "ticker": c.ticker,
            "quantidade": c.quantidade,
            "preco_medio": float(c.preco_medio),
            "data_compra": c.data_compra,
        }
        for c in carteira_rows
    ]
    holdings_dict = {h["ticker"]: h for h in holdings}
    tickers_carteira = set(holdings_dict.keys())

    tickers_universo = set(_tickers_ifix(session))

    # 2. Decisões da carteira (lado VENDER)
    if universo_decisoes is None:
        decisoes_list = decidir_universo(session, sorted(tickers_carteira))
        universo_decisoes = {d.ticker: d for d in decisoes_list}

    decisoes_carteira = [universo_decisoes[t] for t in tickers_carteira if t in universo_decisoes]
    advices = aconselhar_carteira(decisoes_carteira, holdings)
    advices_dict = {a.ticker: a for a in advices}

    # 3. Candidatos a VENDER: P/VP rico no próprio histórico OU badge REDUZIR/SAIR
    candidatos_vender: list[TickerDecision] = []
    for ticker in tickers_carteira:
        decisao = universo_decisoes.get(ticker)
        if not decisao:
            continue
        pvp_pct = decisao.pvp_percentil
        advice = advices_dict.get(ticker)
        badge = advice.badge if advice else "HOLD"
        if (pvp_pct is not None and pvp_pct >= 80) or badge in ("REDUZIR", "SAIR"):
            if pvp_pct is None:
                logger.debug("{}: candidato a vender sem pvp_percentil — par não computável", ticker)
                continue
            candidatos_vender.append(decisao)

    if not candidatos_vender:
        logger.info("Nenhum candidato a VENDER identificado na carteira.")
        return []

    # 4. Candidatos a COMPRAR
    if run_id is not None:
        candidatos_comprar = _candidatos_comprar_de_snapshot(
            session, run_id, tickers_universo, tickers_carteira, data_ref
        )
    else:
        candidatos_comprar = _candidatos_comprar_de_decisoes(
            session, universo_decisoes, tickers_universo, tickers_carteira, data_ref
        )

    if not candidatos_comprar:
        logger.info("Nenhum candidato a COMPRAR identificado no universo IFIX.")
        return []

    # 5. Cooldown: pares já exibidos nos últimos N pregões ficam em silêncio
    cooldown_dias = get_oportunidades_param("cooldown_dias", 21)
    recent_dates = session.execute(
        select(SnapshotOpportunities.data_referencia)
        .where(SnapshotOpportunities.data_referencia < data_ref)
        .order_by(SnapshotOpportunities.data_referencia.desc())
        .distinct()
        .limit(cooldown_dias)
    ).scalars().all()

    cooldown_set: set[tuple[str, str]] = set()
    if recent_dates:
        min_date = min(recent_dates)
        cooldown_pairs = session.execute(
            select(SnapshotOpportunities.vender, SnapshotOpportunities.comprar)
            .where(
                SnapshotOpportunities.data_referencia >= min_date,
                SnapshotOpportunities.data_referencia < data_ref,
            )
        ).all()
        cooldown_set = {(row[0], row[1]) for row in cooldown_pairs}

    # 6. Cruzar pares intra-segmento e avaliar
    spread_pvp_min = get_oportunidades_param("spread_pvp_percentil_min", 25)
    persistencia_dias = get_oportunidades_param("persistencia_dias", 3)
    oportunidades_validas: list[RotationOpportunity] = []

    for vender in candidatos_vender:
        seg_vender = vender.classificacao
        if not seg_vender or seg_vender == "Indefinido":
            # Decisões reconstruídas do snapshot não carregam classificacao —
            # recalcula sob demanda (consulta barata em ativo_passivo).
            try:
                seg_vender = classificar_fii(vender.ticker, session=session)
            except Exception:
                seg_vender = None
        if not seg_vender or seg_vender == "Indefinido":
            continue

        for comprar in candidatos_comprar:
            if seg_vender != comprar.classe:
                continue
            if (vender.ticker, comprar.ticker) in cooldown_set:
                continue

            spread_pvp = float(vender.pvp_percentil) - comprar.pvp_percentil
            if spread_pvp < spread_pvp_min:
                continue

            dy_gap_vender = vender.dy_gap_percentil if vender.dy_gap_percentil is not None else 0.0
            dy_gap_comprar = comprar.dy_gap_percentil if comprar.dy_gap_percentil is not None else 0.0
            spread_dy = dy_gap_comprar - dy_gap_vender
            score_v = vender.score_total if vender.score_total is not None else 0
            score_c = comprar.score_total if comprar.score_total is not None else 0
            delta_score = float(score_c - score_v)

            # Custos: emolumentos B3 (0.03% venda + 0.03% compra) + IR 20% sobre ganho
            custo_b3_pct = 0.06
            preco_vender = vender.preco_referencia or 0.0
            h = holdings_dict.get(vender.ticker)
            preco_medio = h["preco_medio"] if h else 0.0
            ir_pct = 0.0
            if preco_vender > preco_medio > 0:
                ir_pct = (0.20 * (preco_vender - preco_medio) / preco_vender) * 100.0
            custo_estimado = custo_b3_pct + ir_pct
            spread_liquido = spread_pvp - custo_estimado

            # Persistência: spread acima do limiar nos últimos N pregões
            dates_to_check = obter_ultimos_pregoes(session, data_ref, persistencia_dias)
            is_persistente = True
            for d in dates_to_check:
                if d == data_ref:
                    continue  # já verificado acima
                pvp_v = _obter_pvp_percentil_historico(vender.ticker, d, session)
                pvp_c = _obter_pvp_percentil_historico(comprar.ticker, d, session)
                if pvp_v is None or pvp_c is None or (pvp_v - pvp_c) < spread_pvp_min:
                    is_persistente = False
                    break
            if not is_persistente:
                continue

            # Vetos absolutos (lado comprar) — calculados sob demanda no caminho snapshot
            flag_ltv = comprar.flag_ltv_alto
            ltv_atual = comprar.ltv_atual
            if run_id is not None and not flag_ltv:
                try:
                    flag_ltv, ltv_atual = get_ltv_flag(comprar.ticker, data_ref, session)
                except Exception:
                    flag_ltv, ltv_atual = False, None

            vetos: list[str] = []
            # Anti value-trap: rotação deve melhorar (ou manter) a qualidade
            # composta — barato com score pior que a posição atual não é troca,
            # é downgrade. Threshold em config.yaml (oportunidades.delta_score_min).
            delta_score_min = get_oportunidades_param("delta_score_min", 0)
            if comprar.score_total is not None and vender.score_total is not None \
                    and delta_score < delta_score_min:
                vetos.append(
                    f"Score de {comprar.ticker} ({comprar.score_total}) é inferior ao de "
                    f"{vender.ticker} ({vender.score_total}) — possível value trap"
                )
            if flag_ltv and ltv_atual is not None:
                vetos.append(f"LTV alto ({ltv_atual:.1%}) em {comprar.ticker}")
            if comprar.dividend_safety_flag:
                payout_str = f"{comprar.payout_vs_caixa:.0%}" if comprar.payout_vs_caixa is not None else "n/d"
                vetos.append(f"Dividendo insustentável (payout {payout_str}) em {comprar.ticker}")
            if custo_estimado > spread_pvp:
                vetos.append(
                    f"Custos estimados ({custo_estimado:.2f}%) excedem spread bruto ({spread_pvp:.2f} pp)"
                )
            if spread_liquido < spread_pvp_min:
                vetos.append(
                    f"Spread líquido ({spread_liquido:.2f} pp) abaixo do mínimo de {spread_pvp_min} pp"
                )

            racionais = [
                f"P/VP percentil de {vender.ticker} ({vender.pvp_percentil:.0f}) está elevado, "
                f"enquanto {comprar.ticker} ({comprar.pvp_percentil:.0f}) está barato no mesmo "
                f"segmento {seg_vender}.",
            ]
            if comprar.score_total is not None and vender.score_total is not None:
                racionais.append(
                    f"Score de {comprar.ticker} ({comprar.score_total}) vs {vender.ticker} "
                    f"({vender.score_total}): {delta_score:+.0f} pontos."
                )
            if spread_dy > 0:
                racionais.append(
                    f"DY Gap percentil de {comprar.ticker} ({dy_gap_comprar:.0f}) é superior ao de "
                    f"{vender.ticker} ({dy_gap_vender:.0f})."
                )
            if comprar.turnaround:
                racionais.append(
                    f"TURNAROUND: {comprar.ticker} teve destruição de capital no passado, mas o VP/cota "
                    f"está em recuperação — o desconto atual pode já refletir o pior. Risco acima da média; "
                    f"confira o último relatório gerencial antes de agir."
                )

            opp = RotationOpportunity(
                vender=vender.ticker,
                comprar=comprar.ticker,
                segmento=seg_vender,
                spread_pvp_pct=float(spread_pvp),
                spread_dy_gap=float(spread_dy),
                delta_score=delta_score,
                custo_estimado_pct=float(custo_estimado),
                spread_liquido_pct=float(spread_liquido),
                dias_persistencia=persistencia_dias,
                turnaround=comprar.turnaround,
                racional=racionais,
                flags_veto=vetos,
            )

            if not vetos:
                oportunidades_validas.append(opp)

    # 7. Ordenar por spread líquido e limitar
    oportunidades_validas.sort(key=lambda o: o.spread_liquido_pct, reverse=True)
    max_opps = get_oportunidades_param("max_oportunidades_dia", 3)
    return oportunidades_validas[:max_opps]
