import pytest
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import select

from src.fii_analysis.data.database import Ticker, PrecoDiario, RelatorioMensal, Carteira, Universo, SnapshotRun, SnapshotOpportunities
from src.fii_analysis.decision.recommender import TickerDecision
from src.fii_analysis.decision.opportunities import detectar_oportunidades


def _setup_mock_fiis(session, hoje: date):
    """Auxiliar para configurar MOCK11 e MOCK13 no mesmo segmento (Tijolo) e gerar histórico."""
    from src.fii_analysis.decision.opportunities import obter_ultimos_pregoes
    from src.fii_analysis.data.database import SnapshotTickerMetrics, SnapshotRun

    # Adicionar MOCK13 (Tijolo) que não está na fixture padrão conftest.py
    t3 = Ticker(
        cnpj="33.333.333/0001-33",
        ticker="MOCK13",
        nome="Mock Fund 13",
        segmento="Tijolo",
        mandato="Renda",
        tipo_gestao="Ativa",
        codigo_isin="BRMOCK13",
        data_inicio=date(2023, 1, 1),
        inativo_em=None
    )
    session.add(t3)
    session.commit()

    # Adicionar MOCK11 na carteira
    c1 = Carteira(ticker="MOCK11", quantidade=100, preco_medio=95.0, data_compra=date(2024, 1, 1))
    session.add(c1)
    session.commit()

    # Adicionar MOCK13 no IFIX (Universo)
    now = datetime.now(timezone.utc)
    u3 = Universo(
        ticker="MOCK13",
        cnpj="33.333.333/0001-33",
        em_ifix=True,
        peso_ifix=1.5,
        data_referencia=hoje,
        fonte="test",
        atualizado_em=now
    )
    u1 = Universo(
        ticker="MOCK11",
        cnpj="11.111.111/0001-11",
        em_ifix=True,
        peso_ifix=1.0,
        data_referencia=hoje,
        fonte="test",
        atualizado_em=now
    )
    session.add_all([u1, u3])
    session.commit()

    # Adicionar preços históricos para MOCK13
    # MOCK13 tem fechamento de 80.0
    precos = session.execute(select(PrecoDiario.data).where(PrecoDiario.ticker == "MOCK11")).scalars().all()
    for d in precos:
        p3 = PrecoDiario(
            ticker="MOCK13",
            data=d,
            abertura=80.0,
            maxima=81.0,
            minima=79.0,
            fechamento=80.0,
            fechamento_aj=80.0,
            volume=600000,
            fonte="test",
            coletado_em=now
        )
        session.add(p3)
        
    # Relatórios CVM para MOCK13
    months = session.execute(select(RelatorioMensal.data_referencia).where(RelatorioMensal.cnpj == "11.111.111/0001-11")).scalars().all()
    for d in months:
        r3 = RelatorioMensal(
            cnpj="33.333.333/0001-33",
            data_referencia=d,
            data_entrega=d + timedelta(days=10),
            vp_por_cota=100.0,
            patrimonio_liq=100_000_000.0,
            cotas_emitidas=1_000_000,
            dy_mes_pct=1.0,
            rentab_efetiva=0.8,
            rentab_patrim=0.9
        )
        session.add(r3)
        
    session.commit()

    # Registrar snapshots históricos para as datas que serão checadas pela persistência
    dates_to_check = obter_ultimos_pregoes(session, hoje, 3)
    for d in dates_to_check:
        if d == hoje:
            continue
        
        # verificar se ja existe run para d
        existing_run = session.execute(
            select(SnapshotRun).where(SnapshotRun.data_referencia == d)
        ).scalar_one_or_none()
        
        if existing_run:
            run = existing_run
        else:
            run = SnapshotRun(
                data_referencia=d,
                criado_em=datetime.now(timezone.utc),
                status="ready",
                universe_scope="curado"
            )
            session.add(run)
            session.commit()
            
        m1 = SnapshotTickerMetrics(
            run_id=run.id,
            ticker="MOCK11",
            pvp_percentil=90.0,
            score_total=40
        )
        m3 = SnapshotTickerMetrics(
            run_id=run.id,
            ticker="MOCK13",
            pvp_percentil=20.0,
            score_total=75
        )
        session.add_all([m1, m3])
        
    session.commit()


def test_rotation_opportunities_basic(db_session):
    hoje = datetime.now(timezone.utc).date()
    _setup_mock_fiis(db_session, hoje)

    # Mockar decisões
    d_vender = TickerDecision(
        ticker="MOCK11",
        data_referencia=hoje,
        classificacao="Tijolo",
        sinal_otimizador="NEUTRO",
        sinal_episodio="SELL",
        sinal_walkforward="NEUTRO",
        flag_destruicao_capital=False,
        motivo_destruicao=None,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="AGUARDAR",
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=1.05,
        pvp_percentil=90.0,  # elevado, candidato a vender
        dy_gap_percentil=50.0,
        preco_referencia=105.0,
        score_total=40,
    )

    d_comprar = TickerDecision(
        ticker="MOCK13",
        data_referencia=hoje,
        classificacao="Tijolo",
        sinal_otimizador="NEUTRO",
        sinal_episodio="BUY",
        sinal_walkforward="NEUTRO",
        flag_destruicao_capital=False,
        motivo_destruicao=None,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="COMPRAR",
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=0.80,
        pvp_percentil=20.0,  # barato, candidato a comprar
        dy_gap_percentil=80.0,
        preco_referencia=80.0,
        score_total=75,
    )

    universo_decisoes = {"MOCK11": d_vender, "MOCK13": d_comprar}

    # Executar
    opps = detectar_oportunidades(db_session, hoje, universo_decisoes=universo_decisoes)

    assert len(opps) > 0
    opp = opps[0]
    assert opp.vender == "MOCK11"
    assert opp.comprar == "MOCK13"
    assert opp.segmento == "Tijolo"
    assert opp.spread_pvp_pct == 70.0
    assert opp.spread_liquido_pct > 25.0
    assert not opp.flags_veto


def test_rotation_opportunities_veto_saude(db_session):
    hoje = datetime.now(timezone.utc).date()
    _setup_mock_fiis(db_session, hoje)

    d_vender = TickerDecision(
        ticker="MOCK11",
        data_referencia=hoje,
        classificacao="Tijolo",
        sinal_otimizador="NEUTRO",
        sinal_episodio="NEUTRO",
        sinal_walkforward="NEUTRO",
        flag_destruicao_capital=False,
        motivo_destruicao=None,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="AGUARDAR",
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=1.05,
        pvp_percentil=95.0,
        dy_gap_percentil=50.0,
        preco_referencia=105.0,
        score_total=40,
    )

    # comprar com flag_destruicao_capital = True (VETO)
    d_comprar = TickerDecision(
        ticker="MOCK13",
        data_referencia=hoje,
        classificacao="Tijolo",
        sinal_otimizador="NEUTRO",
        sinal_episodio="NEUTRO",
        sinal_walkforward="NEUTRO",
        flag_destruicao_capital=True,  # Veto
        motivo_destruicao="Destruicao ativa",
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="EVITAR",
        nivel_concordancia="VETADA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=0.75,
        pvp_percentil=15.0,
        dy_gap_percentil=80.0,
        preco_referencia=75.0,
        score_total=75,
    )

    universo_decisoes = {"MOCK11": d_vender, "MOCK13": d_comprar}
    opps = detectar_oportunidades(db_session, hoje, universo_decisoes=universo_decisoes)
    
    # Deve ser suprimida devido ao veto
    assert len(opps) == 0


def test_rotation_opportunities_cooldown(db_session):
    hoje = datetime.now(timezone.utc).date()
    _setup_mock_fiis(db_session, hoje)

    # Adicionar um snapshot anterior e registrar a oportunidade no log para ativar o cooldown
    run = SnapshotRun(
        data_referencia=hoje - timedelta(days=2),
        criado_em=datetime.now(timezone.utc),
        status="ready",
        universe_scope="curado"
    )
    db_session.add(run)
    db_session.commit()

    opp_hist = SnapshotOpportunities(
        run_id=run.id,
        data_referencia=hoje - timedelta(days=2),
        vender="MOCK11",
        comprar="MOCK13",
        segmento="Tijolo",
        spread_pvp_pct=50.0,
        spread_dy_gap=0.0,
        delta_score=10.0,
        custo_estimado_pct=0.06,
        spread_liquido_pct=49.94,
        dias_persistencia=3,
        racional_json="[]",
        vetos_json="[]",
        critic_veredicto="APROVADO"
    )
    db_session.add(opp_hist)
    db_session.commit()

    d_vender = TickerDecision(
        ticker="MOCK11",
        data_referencia=hoje,
        classificacao="Tijolo",
        sinal_otimizador="NEUTRO",
        sinal_episodio="SELL",
        sinal_walkforward="NEUTRO",
        flag_destruicao_capital=False,
        motivo_destruicao=None,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="AGUARDAR",
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=1.05,
        pvp_percentil=90.0,
        dy_gap_percentil=50.0,
        preco_referencia=105.0,
        score_total=40,
    )

    d_comprar = TickerDecision(
        ticker="MOCK13",
        data_referencia=hoje,
        classificacao="Tijolo",
        sinal_otimizador="NEUTRO",
        sinal_episodio="BUY",
        sinal_walkforward="NEUTRO",
        flag_destruicao_capital=False,
        motivo_destruicao=None,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="COMPRAR",
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=0.80,
        pvp_percentil=20.0,
        dy_gap_percentil=80.0,
        preco_referencia=80.0,
        score_total=75,
    )

    universo_decisoes = {"MOCK11": d_vender, "MOCK13": d_comprar}
    opps = detectar_oportunidades(db_session, hoje, universo_decisoes=universo_decisoes)
    
    # Supressão por cooldown ativa
    assert len(opps) == 0
