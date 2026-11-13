import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta
from src.fii_analysis.decision.recommender import _derivar_acao, decidir_ticker
from src.fii_analysis.data.database import RelatorioMensal, Ticker

def test_derivar_acao_consensus():
    # 3/3 BUY -> COMPRAR, ALTA
    assert _derivar_acao(3, 0, 3) == ("COMPRAR", "ALTA")
    # 3/3 SELL -> VENDER, ALTA
    assert _derivar_acao(0, 3, 3) == ("VENDER", "ALTA")

    # 2/3 BUY -> COMPRAR, MEDIA
    assert _derivar_acao(2, 0, 3) == ("COMPRAR", "MEDIA")
    # 2/3 SELL -> VENDER, MEDIA
    assert _derivar_acao(0, 2, 3) == ("VENDER", "MEDIA")

    # 1/3 BUY -> AGUARDAR, BAIXA
    assert _derivar_acao(1, 0, 3) == ("AGUARDAR", "BAIXA")
    # 0/3 signals -> AGUARDAR, BAIXA
    assert _derivar_acao(0, 0, 3) == ("AGUARDAR", "BAIXA")


def test_derivar_acao_nao_tem_mais_veto_por_flag():
    # MUDANCA POR DECISAO (estudo em painel 2026-11-12): flag de destruicao de capital nao
    # veta mais (a flag virou alerta descritivo). _derivar_acao nem recebe mais a flag e
    # nunca devolve EVITAR/VETADA.
    import inspect
    assert "has_critical" not in inspect.signature(_derivar_acao).parameters
    for n_buy, n_sell in [(3, 0), (2, 0), (1, 0), (0, 3), (0, 2), (0, 0)]:
        assert _derivar_acao(n_buy, n_sell, 3)[0] != "EVITAR"

@patch('src.fii_analysis.decision.recommender.walk_forward_roll')
@patch('src.fii_analysis.decision.recommender.ThresholdOptimizerV2')
def test_decidir_ticker_veto_integration(MockOptimizer, mock_wf, db_session):
    # Mock walk_forward_roll to return a BUY signal today
    mock_wf.return_value = {
        "sinal_hoje": {"sinal": "BUY", "data_ultimo_sinal_oos": date(2025, 4, 1)},
        "n_steps": 10,
        # n_effective >= 30 e p_bh (BH sobre a familia do ticker) < 0.05 => WF tem suporte
        "summary": {"BUY": {"p_value": 0.01, "n_effective": 40, "mean": 0.02, "drift": 0.005}}
    }
    stats_otim = {  # otimizador com suporte: n=40 independentes, p do excesso 0.001
        "n_buy_thinned": 40, "n_sell_thinned": 40,
        "p_value_buy": 0.001, "p_value_sell": 0.5,
        "avg_return_buy_independent": 0.02, "deriva": 0.005, "excess_buy": 0.015,
    }
    
    # Mock optimizer signal
    mock_opt_instance = MagicMock()
    mock_opt_instance.get_signal_hoje.return_value = {"sinal": "BUY"}
    MockOptimizer.return_value = mock_opt_instance

    # Under healthy conditions, the recommendation should be COMPRAR
    # MOCK11 is healthy by default in our conftest.py
    decision_healthy = decidir_ticker(
        "MOCK11", db_session, optimizer_params={"some": "param"},
        pvp_pct_low=10.0, pvp_pct_high=90.0, optimizer_stats=stats_otim,
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
        pvp_pct_low=10.0, pvp_pct_high=90.0, optimizer_stats=stats_otim,
    )
    
    assert decision_unhealthy.flag_destruicao_capital is True
    # MUDANCA POR DECISAO: sem veto. O sinal COM suporte continua valendo (COMPRAR) e a flag
    # vira ALERTA descritivo no rationale; a acao nunca e EVITAR/VETADA.
    assert decision_unhealthy.acao == "COMPRAR"
    assert decision_unhealthy.nivel_concordancia != "VETADA"
    assert any("ALERTA (descritivo, nao veta)" in r for r in decision_unhealthy.rationale)
    # linha de evidencia legivel por maquina, escrita uma vez
    from src.fii_analysis.decision.evidencia import restaurar_evidencia
    ev = restaurar_evidencia(decision_unhealthy.rationale)
    assert ev["sobreviventes"] == 0 and ev["n_testes"] == 100
    assert sum(1 for r in decision_unhealthy.rationale if r.startswith("EVIDENCIA_JSON ")) == 1
