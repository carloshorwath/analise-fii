import pytest
from datetime import date
from sqlalchemy import select

from src.fii_analysis.data.database import RelatorioMensal, Ticker
from src.fii_analysis.features.saude import flag_destruicao_capital

def test_falso_positivo_lucro_extraordinario(db_session):
    """Testa se um mês com lucro extraordinário (VP não cai) é ignorado no streak."""
    # Criar um ticker de teste
    t = Ticker(ticker="TEST11", cnpj="00.000.000/0001-01")
    db_session.add(t)
    
    # 6 meses normais (mediana rentab_efetiva ~ 1%)
    for i in range(1, 7):
        db_session.add(RelatorioMensal(
            cnpj="00.000.000/0001-01",
            data_referencia=date(2024, i, 1),
            data_entrega=date(2024, i, 15),
            vp_por_cota=100.0,
            cotas_emitidas=1000000,
            rentab_efetiva=1.0,
            rentab_patrim=1.0,
        ))
        
    # Mês 7: Lucro extraordinário (rentab_efetiva = 5.0, rentab_patrim = 4.0)
    # A rent_patrim foi menor (4.0 < 5.0), logo a distribuição foi "prejudicial" pela regra ingênua
    # Porém, 5.0 > 3 * mediana(1.0), então deve ser ignorado.
    db_session.add(RelatorioMensal(
        cnpj="00.000.000/0001-01",
        data_referencia=date(2024, 7, 1),
        data_entrega=date(2024, 7, 15),
        vp_por_cota=100.0,
        cotas_emitidas=1000000,
        rentab_efetiva=5.0,
        rentab_patrim=4.0,
    ))
    
    # Mês 8: Mês ruim normal (rentab_efetiva = 1.0, rentab_patrim = 0.5)
    db_session.add(RelatorioMensal(
        cnpj="00.000.000/0001-01",
        data_referencia=date(2024, 8, 1),
        data_entrega=date(2024, 8, 15),
        vp_por_cota=99.9,
        cotas_emitidas=1000000,
        rentab_efetiva=1.0,
        rentab_patrim=0.9,
    ))
    
    db_session.commit()
    
    # Avaliando no mês 8
    res = flag_destruicao_capital("TEST11", session=db_session, t=date(2024, 8, 20))
    
    # current_consec agora mede meses consecutivos de QUEDA do VP/cota (> 0,1%/mês);
    # o critério antigo (efetiva > patrimonial) era identicamente dy_mes > 0.
    # Aqui o VP caiu 0,1% no último mês (não excede o limiar) -> streak 0, fundo saudável.
    assert res["current_consec"] == 0
    assert res["destruicao"] is False
    assert res["gravidade"] in ("saudavel", "em_recuperacao")


def test_destruicao_verdadeira(db_session):
    """Testa um fundo de papel que consistentemente distribui amortização de capital."""
    t = Ticker(ticker="BAD11", cnpj="00.000.000/0002-02")
    db_session.add(t)
    
    vp_atual = 100.0
    for i in range(1, 9):
        # VP caindo constantemente, rentab_efetiva sempre > rentab_patrimonial
        # Rentab efetiva em torno de 1.2%
        vp_atual -= 1.0
        db_session.add(RelatorioMensal(
            cnpj="00.000.000/0002-02",
            data_referencia=date(2024, i, 1),
            data_entrega=date(2024, i, 15),
            vp_por_cota=vp_atual,
            cotas_emitidas=1000000,
            rentab_efetiva=1.2,
            rentab_patrim=0.2, # menor que efetiva
        ))
        
    db_session.commit()
    
    res = flag_destruicao_capital("BAD11", session=db_session, t=date(2024, 8, 20))
    
    # VP caindo 1% ao mês -> slope negativo
    # 8 meses consecutivos de distribuição > gerado
    assert res["current_consec"] >= 4
    assert res["destruicao"] is True
    assert res["gravidade"] in ("alerta", "critica")
    assert res["score_saude"] < 50
