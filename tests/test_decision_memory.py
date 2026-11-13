from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import (
    SnapshotRun,
    SnapshotDecisions,
    SnapshotTickerMetrics,
    SnapshotPortfolioAdvices,
    SnapshotRadar,
    SnapshotOpportunities,
    SnapshotStructuralAlerts,
    DecisaoLog,
    PrecoDiario,
    BenchmarkDiario,
)
from src.fii_analysis.evaluation.daily_diff import calcular_diff_diario, render_diff_markdown
from src.fii_analysis.decision.decision_journal import registrar_decisao, calcular_retornos_ex_post


def test_daily_diff(db_session: Session):
    # 1. Inserir runs
    dt_ant = date(2024, 1, 2)  # pregoes consecutivos reais (01/01 e feriado)
    dt_act = date(2024, 1, 3)
    
    run_ant = SnapshotRun(
        id=1,
        status="ready",
        universe_scope="curado",
        data_referencia=dt_ant,
        criado_em=datetime.now(timezone.utc),
        finalizado_em=datetime.now(timezone.utc),
    )
    run_act = SnapshotRun(
        id=2,
        status="ready",
        universe_scope="curado",
        data_referencia=dt_act,
        criado_em=datetime.now(timezone.utc),
        finalizado_em=datetime.now(timezone.utc),
    )
    db_session.add_all([run_ant, run_act])
    db_session.commit()

    # 2. Inserir Decisions (mudança de Ação/Badge para MOCK11)
    dec_ant1 = SnapshotDecisions(run_id=1, ticker="MOCK11", acao="AGUARDAR")
    dec_act1 = SnapshotDecisions(run_id=2, ticker="MOCK11", acao="COMPRAR")
    dec_ant2 = SnapshotDecisions(run_id=1, ticker="MOCK12", acao="AGUARDAR")
    dec_act2 = SnapshotDecisions(run_id=2, ticker="MOCK12", acao="AGUARDAR")
    db_session.add_all([dec_ant1, dec_act1, dec_ant2, dec_act2])

    # 3. Inserir Advices
    adv_ant1 = SnapshotPortfolioAdvices(run_id=1, ticker="MOCK11", badge="HOLD", racional="x", prioridade="MEDIA", valida_ate=dt_ant)
    adv_act1 = SnapshotPortfolioAdvices(run_id=2, ticker="MOCK11", badge="AUMENTAR", racional="y", prioridade="ALTA", valida_ate=dt_act)
    db_session.add_all([adv_ant1, adv_act1])

    # 4. Inserir Radar (mudança de pvp_baixo para MOCK12)
    rad_ant1 = SnapshotRadar(run_id=1, ticker="MOCK12", pvp_baixo=False, dy_gap_alto=False, saude_ok=True, liquidez_ok=True)
    rad_act1 = SnapshotRadar(run_id=2, ticker="MOCK12", pvp_baixo=True, dy_gap_alto=False, saude_ok=True, liquidez_ok=True)
    db_session.add_all([rad_ant1, rad_act1])

    # 5. Inserir Ticker Metrics (mudança de score >= 5 para MOCK11)
    met_ant1 = SnapshotTickerMetrics(run_id=1, ticker="MOCK11", score_total=70)
    met_act1 = SnapshotTickerMetrics(run_id=2, ticker="MOCK11", score_total=76)
    db_session.add_all([met_ant1, met_act1])

    # 6. Nova Oportunidade
    opp1 = SnapshotOpportunities(
        run_id=2,
        data_referencia=dt_act,
        vender="MOCK12",
        comprar="MOCK11",
        segmento="Misto",
        spread_pvp_pct=5.0,
        spread_dy_gap=1.0,
        delta_score=6.0,
        custo_estimado_pct=0.3,
        spread_liquido_pct=4.7,
        dias_persistencia=1,
        racional_json="{}",
        vetos_json="{}",
        critic_veredicto="APROVADO",
    )
    db_session.add(opp1)

    # 7. Novo alerta
    alert1 = SnapshotStructuralAlerts(
        run_id=2,
        carteira_hash="dummy_hash",
        tipo="Concentração de Segmento",
        severidade="atencao",
        descricao="Segmento Tijolo acima de 40%",
        valor=42.0,
    )
    db_session.add(alert1)
    db_session.commit()

    # Calcular diff
    diff = calcular_diff_diario(db_session, run_id_atual=2, run_id_anterior=1)
    
    assert diff.data_atual == dt_act
    assert diff.data_anterior == dt_ant
    assert len(diff.mudacoes_acao) == 1
    assert diff.mudacoes_acao[0]["ticker"] == "MOCK11"
    assert diff.mudacoes_acao[0]["acao_ant"] == "AGUARDAR"
    assert diff.mudacoes_acao[0]["acao_nv"] == "COMPRAR"
    assert diff.mudacoes_acao[0]["badge_ant"] == "HOLD"
    assert diff.mudacoes_acao[0]["badge_nv"] == "AUMENTAR"

    assert len(diff.mudacoes_radar) == 1
    assert diff.mudacoes_radar[0]["ticker"] == "MOCK12"
    assert diff.mudacoes_radar[0]["filtro"] == "pvp_baixo"
    assert diff.mudacoes_radar[0]["ant"] is False
    assert diff.mudacoes_radar[0]["nv"] is True

    assert len(diff.mudacoes_score) == 1
    assert diff.mudacoes_score[0]["ticker"] == "MOCK11"
    assert diff.mudacoes_score[0]["score_ant"] == 70
    assert diff.mudacoes_score[0]["score_nv"] == 76
    assert diff.mudacoes_score[0]["delta"] == 6

    assert len(diff.oportunidades_novas) == 1
    assert diff.oportunidades_novas[0]["vender"] == "MOCK12"
    assert diff.oportunidades_novas[0]["comprar"] == "MOCK11"

    assert len(diff.alertas_novos) == 1
    assert diff.alertas_novos[0]["tipo"] == "Concentração de Segmento"

    # Renderizar md
    md = render_diff_markdown(diff)
    assert "O que mudou desde ontem" in md
    assert "MOCK11" in md
    assert "MOCK12" in md


def test_decision_journal_registration(db_session: Session):
    t_date = date(2024, 6, 1)
    dec, avisos = registrar_decisao(
        session=db_session,
        tipo="ROTACAO",
        ticker_vendido="MOCK12",
        ticker_comprado="MOCK11",
        quantidade=100,
        preco=98.5,
        opportunity_id=42,
        racional_usuario="Racional de teste",
        data=t_date,
    )

    assert avisos == []
    assert dec.id is not None
    
    # Buscar da base
    db_dec = db_session.execute(select(DecisaoLog).where(DecisaoLog.id == dec.id)).scalar_one()
    assert db_dec.tipo == "ROTACAO"
    assert db_dec.ticker_vendido == "MOCK12"
    assert db_dec.ticker_comprado == "MOCK11"
    assert db_dec.quantidade == 100
    assert db_dec.preco == 98.5
    assert db_dec.opportunity_id == 42
    assert db_dec.racional_usuario == "Racional de teste"
    assert db_dec.data == t_date


def test_calcular_retornos_ex_post(db_session: Session):
    # Limpar qualquer oportunidade antiga da conftest
    db_session.query(SnapshotOpportunities).delete()
    db_session.query(DecisaoLog).delete()
    db_session.commit()

    t_start = date(2024, 1, 10)
    t_end = t_start + timedelta(days=90)

    # Inserir preços conhecidos para MOCK11 (comprar) e MOCK12 (vender)
    # Primeiro remover preços dessas datas se existirem para evitar duplicidade na pk
    db_session.query(PrecoDiario).filter(PrecoDiario.ticker.in_(["MOCK11", "MOCK12"]), PrecoDiario.data.in_([t_start, t_end])).delete()
    db_session.query(BenchmarkDiario).filter(BenchmarkDiario.ticker == "XFIX11", BenchmarkDiario.data.in_([t_start, t_end])).delete()
    db_session.commit()

    # Preços no início (T_start)
    db_session.add(PrecoDiario(ticker="MOCK11", data=t_start, fechamento=100.0, fechamento_aj=100.0, coletado_em=datetime.now(timezone.utc)))
    db_session.add(PrecoDiario(ticker="MOCK12", data=t_start, fechamento=50.0, fechamento_aj=50.0, coletado_em=datetime.now(timezone.utc)))
    
    # Preços no fim (T_end)
    db_session.add(PrecoDiario(ticker="MOCK11", data=t_end, fechamento=110.0, fechamento_aj=110.0, coletado_em=datetime.now(timezone.utc)))  # +10%
    db_session.add(PrecoDiario(ticker="MOCK12", data=t_end, fechamento=48.0, fechamento_aj=48.0, coletado_em=datetime.now(timezone.utc)))     # -4%

    # Benchmark XFIX11
    db_session.add(BenchmarkDiario(ticker="XFIX11", data=t_start, fechamento=1000.0, coletado_em=datetime.now(timezone.utc)))
    db_session.add(BenchmarkDiario(ticker="XFIX11", data=t_end, fechamento=1020.0, coletado_em=datetime.now(timezone.utc)))  # +2%
    db_session.commit()

    # Inserir Oportunidade antiga
    opp = SnapshotOpportunities(
        id=99,
        run_id=5,
        data_referencia=t_start,
        vender="MOCK12",
        comprar="MOCK11",
        segmento="Misto",
        spread_pvp_pct=5.0,
        spread_dy_gap=1.0,
        delta_score=6.0,
        custo_estimado_pct=0.3,
        spread_liquido_pct=4.7,
        dias_persistencia=1,
        racional_json="{}",
        vetos_json="{}",
        critic_veredicto="APROVADO",
    )
    db_session.add(opp)
    db_session.commit()

    # Registrar decisão como realizada
    registrar_decisao(
        session=db_session,
        tipo="ROTACAO",
        ticker_vendido="MOCK12",
        ticker_comprado="MOCK11",
        opportunity_id=99,
        data=t_start,
    )

    # Calcular retorno ex-post com horizonte 90 dias
    res = calcular_retornos_ex_post(db_session, dias_horizonte=90, data_base=t_end)

    assert len(res) == 1
    r = res[0]
    assert r["opportunity_id"] == 99
    assert r["vender"] == "MOCK12"
    assert r["comprar"] == "MOCK11"
    
    # MOCK11: 110 / 100 - 1 = +10%
    assert abs(r["retorno_comprar"] - 0.10) < 1e-5
    
    # MOCK12: 48 / 50 - 1 = -4%
    assert abs(r["retorno_vender"] - (-0.04)) < 1e-5
    
    # Par: +10% - (-4%) = +14%
    assert abs(r["retorno_par"] - 0.14) < 1e-5
    
    # Benchmark: 1020 / 1000 - 1 = +2%
    assert abs(r["retorno_xfix11"] - 0.02) < 1e-5
    
    assert r["bateu_xfix11"] is True
    assert r["realizada"] is True
