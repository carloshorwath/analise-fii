import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta
from src.fii_analysis.decision.recommender import _derivar_acao, decidir_ticker
from src.fii_analysis.data.database import RelatorioMensal, Ticker

def test_derivar_acao_consensus():
    # 3/3 BUY -> COMPRAR, ALTA
    assert _derivar_acao(3, 0, 3, False) == ("COMPRAR", "ALTA")
    # 3/3 SELL -> VENDER, ALTA
    assert _derivar_acao(0, 3, 3, False) == ("VENDER", "ALTA")
    
    # 2/3 BUY -> COMPRAR, MEDIA
    assert _derivar_acao(2, 0, 3, False) == ("COMPRAR", "MEDIA")
    # 2/3 SELL -> VENDER, MEDIA
    assert _derivar_acao(0, 2, 3, False) == ("VENDER", "MEDIA")
    
    # 1/3 BUY -> AGUARDAR, BAIXA
    assert _derivar_acao(1, 0, 3, False) == ("AGUARDAR", "BAIXA")
    # 0/3 signals -> AGUARDAR, BAIXA
    assert _derivar_acao(0, 0, 3, False) == ("AGUARDAR", "BAIXA")

def test_derivar_acao_veto():
    # BUY signal present, has critical flag -> EVITAR, VETADA
    assert _derivar_acao(3, 0, 3, True) == ("EVITAR", "VETADA")
    assert _derivar_acao(2, 0, 3, True) == ("EVITAR", "VETADA")
    assert _derivar_acao(1, 0, 3, True) == ("EVITAR", "VETADA")
    
    # SELL signal present, has critical flag -> VENDER (no veto on SELL)
    assert _derivar_acao(0, 3, 3, True) == ("VENDER", "ALTA")
    assert _derivar_acao(0, 2, 3, True) == ("VENDER", "MEDIA")

@patch('src.fii_analysis.decision.recommender.walk_forward_roll')
@patch('src.fii_analysis.decision.recommender.ThresholdOptimizerV2')
def test_decidir_ticker_veto_integration(MockOptimizer, mock_wf, db_session):
    # Mock walk_forward_roll to return a BUY signal today
    mock_wf.return_value = {
        "sinal_hoje": {"sinal": "BUY", "data_ultimo_sinal_oos": date(2025, 4, 1)},
        "n_steps": 10,
        "summary": {"BUY": {"p_value": 0.01}}
    }
    
    # Mock optimizer signal
    mock_opt_instance = MagicMock()
    mock_opt_instance.get_signal_hoje.return_value = {"sinal": "BUY"}
    MockOptimizer.return_value = mock_opt_instance

    # Under healthy conditions, the recommendation should be COMPRAR
    # MOCK11 is healthy by default in our conftest.py
    decision_healthy = decidir_ticker(
        "MOCK11", db_session, optimizer_params={"some": "param"},
        pvp_pct_low=10.0, pvp_pct_high=90.0
    )
    # Since walkforward (BUY) + optimizer (BUY) + episodes (which could be NEUTRO)
    # The total buy count will be >= 2 => COMPRAR
    assert decision_healthy.acao == "COMPRAR"
    assert decision_healthy.nivel_concordancia in ("ALTA", "MEDIA")
    assert decision_healthy.flag_destruicao_capital is False

    # Now, let's inject unhealthy reports for MOCK11 to trigger flag_destruicao_capital
    # We will add 4 consecutive reports with rentab_efetiva > rentab_patrim
    # Clean first existing monthly reports for MOCK11 to avoid mixing
    db_session.execute(RelatorioMensal.__table__.delete().where(RelatorioMensal.cnpj == "11.111.111/0001-11"))
    db_session.commit()

    # Insert 4 unhealthy monthly reports
    for i in range(4):
        ref_date = date(2025, 1 + i, 28)
        delivery_date = ref_date + timedelta(days=5)
        rep = RelatorioMensal(
            cnpj="11.111.111/0001-11",
            data_referencia=ref_date,
            data_entrega=delivery_date,
            vp_por_cota=100.0 - (i * 2.0),  # dropping PL (slope < -0.1)
            patrimonio_liq=90_000_000.0,
            cotas_emitidas=1_000_000,
            dy_mes_pct=1.5,
            rentab_efetiva=1.5,
            rentab_patrim=1.0  # rentab_efetiva > rentab_patrim => unhealthy!
        )
        db_session.add(rep)
    db_session.commit()

    # Query decidir_ticker again on a date after these reports are delivered
    decision_unhealthy = decidir_ticker(
        "MOCK11", db_session, optimizer_params={"some": "param"},
        pvp_pct_low=10.0, pvp_pct_high=90.0
    )
    
    assert decision_unhealthy.flag_destruicao_capital is True
    # The action must be EVITAR due to veto!
    assert decision_unhealthy.acao == "EVITAR"
    assert decision_unhealthy.nivel_concordancia == "VETADA"
