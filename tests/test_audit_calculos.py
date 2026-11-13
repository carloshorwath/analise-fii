"""Regressao dos 7 bugs de calculo achados na auditoria dos indicadores.

Cada teste usa dados sinteticos pequenos e o resultado esperado e calculado a mao
no proprio teste (comentarios mostram a conta).
"""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import delete, func, select

from src.fii_analysis.data.database import (
    BenchmarkDiario, CdiDiario, Dividendo, PrecoDiario, RelatorioMensal, Ticker,
)

_AGORA = datetime.now(timezone.utc)


def _weekdays(inicio: date, fim: date) -> list[date]:
    out, d = [], inicio
    while d <= fim:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _add_precos(session, ticker, datas, fechamento=100.0, fechamento_aj=None):
    for d in datas:
        f = fechamento(d) if callable(fechamento) else fechamento
        a = fechamento_aj(d) if callable(fechamento_aj) else (f if fechamento_aj is None else fechamento_aj)
        session.add(PrecoDiario(
            ticker=ticker, data=d, abertura=f, maxima=f, minima=f,
            fechamento=f, fechamento_aj=a, volume=1_000_000, fonte="teste", coletado_em=_AGORA,
        ))


def _add_divs(session, ticker, pares):
    for d, v in pares:
        session.add(Dividendo(ticker=ticker, data_com=d, valor_cota=v, fonte="teste"))


# ---------------------------------------------------------------------------
# 1. Percentil de DY Gap: dividendos desde data_min - 12m
# ---------------------------------------------------------------------------
def test_dy_gap_percentil_busca_dividendos_ate_12m_antes_da_data_mais_antiga(db_session):
    from src.fii_analysis.features.valuation import get_dy_gap_percentil

    # CDI = 0 em todos os dias => gap == DY 12m. Substitui o CDI do conftest.
    db_session.execute(delete(CdiDiario))
    for d in _weekdays(date(2022, 12, 1), date(2025, 12, 31)):
        db_session.add(CdiDiario(data=d, taxa_diaria_pct=0.0, coletado_em=_AGORA))

    ticker = "PCT11"
    _add_precos(db_session, ticker, _weekdays(date(2023, 1, 2), date(2025, 12, 31)), 100.0)
    # Pagamento no dia 15 de cada mes, jan/2023..dez/2025: 2.0 ate jun/2025, 1.0 de jul a dez/2025.
    pagtos = []
    for ano in (2023, 2024, 2025):
        for mes in range(1, 13):
            v = 2.0 if (ano, mes) <= (2025, 6) else 1.0
            pagtos.append((date(ano, mes, 15), v))
    _add_divs(db_session, ticker, pagtos)
    db_session.commit()

    t = date(2025, 12, 31)
    # DY 12m (gap, pois CDI=0) em t = (6*2.0 + 6*1.0)/100 = 0.18 (jan..dez/2025).
    # Janela = 252 pregoes anteriores a t (ate 2025-12-30). O gap de cada data d e a soma dos 12 ultimos
    # pagamentos / 100; fica == 0.18 somente de 15/dez a 30/dez (12 dias uteis: 15-19, 22-26, 29-30)
    # e e > 0.18 antes (ex.: 12/dez inclui o pagamento de 15/12/2024 => 0.19).
    # Percentil correto = 12 / 252 * 100 = 4.76.
    # Bug antigo: dividendos so desde (data_max - 12m) => DY das datas antigas
    # subestimado => quase todos os gaps historicos < 0.18 => percentil ~ topo.
    pct = get_dy_gap_percentil(ticker, t, 252, db_session)
    assert pct == pytest.approx(12 / 252 * 100)


# ---------------------------------------------------------------------------
# 2. DY n meses: janela semiaberta (nao conta 13 pagamentos)
# ---------------------------------------------------------------------------
def test_dy_12m_janela_semiaberta_e_dy_gap_herda(db_session):
    from src.fii_analysis.features.valuation import get_dy_gap, get_dy_n_meses

    ticker = "JAN11"
    t = date(2025, 6, 30)
    _add_precos(db_session, ticker, [t], 100.0)
    # 2024-06-30 esta EXATAMENTE em t-12m: fora da janela (2024-06-30, t).
    # MUDANCA POR DECISAO (convencao conservadora, estudo 2026-11-12): dividendo so entra
    # no DY a partir do pregao SEGUINTE a data-com (data-ex); data_com == t fica de fora.
    _add_divs(db_session, ticker, [
        (date(2024, 6, 30), 1.0),   # fora (borda inicial)
        (date(2024, 7, 30), 1.0),
        (date(2024, 12, 30), 1.0),
        (date(2025, 6, 30), 1.0),   # fora em t (data_com == t); entra em t+1
    ])
    db_session.commit()

    # soma correta em t = 2.0 / preco 100 = 0.02 (antes da decisao: 3.0/100 = 0.03)
    assert get_dy_n_meses(ticker, t, 12, db_session) == pytest.approx(0.02)
    # no pregao seguinte (t+1) o dividendo de t ja conta: janela (2024-07-01, 2025-07-01) = 3.0
    t1 = date(2025, 7, 1)
    _add_precos(db_session, ticker, [t1], 100.0)
    db_session.commit()
    assert get_dy_n_meses(ticker, t1, 12, db_session) == pytest.approx(0.03)

    # CDI do conftest: 0.04%/dia em dias uteis; registros em [2024-06-30, 2025-06-30]
    n = int(np.busday_count("2024-06-30", "2025-07-01"))
    cdi = 1.0004 ** n - 1.0
    assert get_dy_gap(ticker, t, db_session) == pytest.approx(0.02 - cdi)


# ---------------------------------------------------------------------------
# 3. retorno_total_12m: preco bruto + dividendos (aj ja embute dividendo)
# ---------------------------------------------------------------------------
def test_retorno_total_12m_usa_fechamento_bruto(db_session):
    from src.fii_analysis.features.risk_metrics import retorno_total_12m

    ticker = "RET11"
    datas = _weekdays(date(2025, 1, 1), date(2026, 1, 30))[-253:]
    assert len(datas) == 253
    # bruto sempre 100; ajustado = 90 no inicio (t-252) e 100 hoje.
    _add_precos(db_session, ticker, datas, fechamento=100.0,
                fechamento_aj=lambda d: 90.0 if d == datas[0] else 100.0)
    _add_divs(db_session, ticker, [(datas[100], 5.0)])  # dentro de (t-252, t]
    db_session.commit()

    # correto: (100 - 100 + 5) / 100 = 0.05   (bug antigo: (100 - 90 + 5)/90 = 0.1667)
    assert retorno_total_12m(ticker, db_session) == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 4. Sinal de hoje do otimizador usa a ultima linha com features (sem fwd_ret)
# ---------------------------------------------------------------------------
def test_sinal_hoje_usa_ultimo_pregao_e_ajuste_continua_exigindo_fwd_ret(db_session):
    from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2

    cnpj, ticker = "33.333.333/0001-33", "OPT11"
    db_session.add(Ticker(cnpj=cnpj, ticker=ticker, nome="Opt", segmento="Tijolo", mandato="Renda",
                          tipo_gestao="Ativa", codigo_isin="BROPT11", data_inicio=date(2024, 1, 1),
                          inativo_em=None))
    datas = _weekdays(date(2025, 1, 1), date(2025, 12, 31))[:100]
    _add_precos(db_session, ticker, datas, fechamento=lambda d: 100.0 + datas.index(d))
    db_session.add(RelatorioMensal(cnpj=cnpj, data_referencia=date(2024, 12, 31),
                                   data_entrega=date(2024, 12, 31), vp_por_cota=100.0,
                                   patrimonio_liq=1e8, cotas_emitidas=1_000_000,
                                   dy_mes_pct=0.01, rentab_efetiva=None, rentab_patrim=None))
    db_session.commit()

    opt = ThresholdOptimizerV2()
    params = {"pvp_percentil_buy": 20, "pvp_percentil_sell": 80,
              "meses_alerta_sell": 2, "dy_gap_pct_sell": 35}

    # Ajuste/validacao/teste: ultimas forward_days (20) linhas sem fwd_ret continuam fora.
    treino = opt._get_enriched_daily_data(ticker, db_session)
    assert treino["data"].max().date() == datas[-1 - 20]
    # Com a flag desligada a serie chega ao ultimo pregao (fwd_ret NaN nas ultimas 20).
    completo = opt._get_enriched_daily_data(ticker, db_session, exigir_fwd_ret=False)
    assert completo["data"].max().date() == datas[-1]
    assert completo["fwd_ret"].isna().sum() == 20

    sinal = opt.get_signal_hoje(ticker, db_session, params)
    assert sinal["indicators"]["data"] == datas[-1].strftime("%Y-%m-%d")
    # P/VP sobe todo dia (101..), e a maxima da janela => percentil 100 >= 80 => SELL
    assert sinal["sinal"] == "SELL"


# ---------------------------------------------------------------------------
# 5. Momentum relativo ao IFIX le benchmark_diario (XFIX11)
# ---------------------------------------------------------------------------
def test_momentum_relativo_ifix_le_benchmark_xfix11(db_session):
    from src.fii_analysis.features.momentum_signals import get_momentum_relativo_ifix

    t = db_session.execute(
        select(func.max(PrecoDiario.data)).where(PrecoDiario.ticker == "MOCK11")
    ).scalar_one()
    # conftest: MOCK11 plano em 100 (retorno 0); XFIX11 = 100 + i*0.01, i = 0..599.
    # Ultimo i = 599 -> 105.99 ; 21 pregoes antes i = 578 -> 105.78.
    ret_ifix = 105.99 / 105.78 - 1.0
    esperado = round((0.0 - ret_ifix) * 100, 4)   # ~ -0.1985
    assert get_momentum_relativo_ifix("MOCK11", t, db_session) == pytest.approx(esperado, abs=1e-3)

    # Falha explicita: sem benchmark => None (nao inventa valor)
    db_session.execute(delete(BenchmarkDiario))
    db_session.commit()
    assert get_momentum_relativo_ifix("MOCK11", t, db_session) is None


# ---------------------------------------------------------------------------
# 6. get_dy_medias: media anual e percentil com unidades coerentes
# ---------------------------------------------------------------------------
def test_get_dy_medias_media_anual_e_percentil_em_fracao(db_session):
    from src.fii_analysis.features.fundamentos import get_dy_medias

    cnpj, ticker = "44.444.444/0001-44", "MED11"
    db_session.add(Ticker(cnpj=cnpj, ticker=ticker, nome="Med", segmento="Tijolo", mandato="Renda",
                          tipo_gestao="Ativa", codigo_isin="BRMED11", data_inicio=date(2020, 1, 1),
                          inativo_em=None))
    _add_precos(db_session, ticker, [date(2025, 12, 31)], 100.0)
    # 60 pagamentos de 0.5 no dia 15, jan/2021..dez/2025
    _add_divs(db_session, ticker, [(date(a, m, 15), 0.5) for a in range(2021, 2026) for m in range(1, 13)])
    # dy_mes_pct em FRACAO; x12: 0.03, 0.048, 0.084, 0.108
    for i, dy in enumerate([0.0025, 0.004, 0.007, 0.009]):
        db_session.add(RelatorioMensal(cnpj=cnpj, data_referencia=date(2025, 1 + i, 1),
                                       data_entrega=date(2025, 1 + i, 20), vp_por_cota=100.0,
                                       patrimonio_liq=1e8, cotas_emitidas=1_000_000,
                                       dy_mes_pct=dy, rentab_efetiva=0.005, rentab_patrim=0.005))
    db_session.commit()

    r = get_dy_medias(ticker, session=db_session)
    assert r["dy_12m_atual"] == pytest.approx(0.06)           # 12 * 0.5 / 100
    assert r["media_dy_2anos"] == pytest.approx(0.06)         # (24 * 0.5 / 100) / 2 anos
    assert r["media_dy_5anos"] == pytest.approx(0.06)         # (60 * 0.5 / 100) / 5 anos
    # serie anualizada {0.03, 0.048, 0.084, 0.108}: <= 0.06 sao 2 de 4 => 50%
    # (bug antigo comparava com 6.0 => 100% sempre)
    assert r["percentil_na_serie_completa"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# 7. Radar: vistos == numero de criterios atendidos (sem +1)
# ---------------------------------------------------------------------------
def test_radar_vistos_conta_exatamente_os_criterios_atendidos(db_session, monkeypatch):
    import src.fii_analysis.features.radar as radar

    monkeypatch.setattr(radar, "get_pvp_percentil", lambda *a, **k: (10.0, 252))   # barato -> True
    monkeypatch.setattr(radar, "get_dy_gap_percentil", lambda *a, **k: 50.0)       # <= 70 -> False
    monkeypatch.setattr(radar, "flag_destruicao_capital",
                        lambda *a, **k: {"destruicao": False, "motivo": "ok"})   # saude -> True
    monkeypatch.setattr(radar, "volume_medio_21d", lambda *a, **k: 1e9)            # liquidez -> True

    df = radar.radar_matriz(["MOCK11"], db_session)
    row = df.iloc[0]
    assert (row.pvp_baixo, row.dy_gap_alto, row.saude_ok, row.liquidez_ok) == (True, False, True, True)
    # MUDANCA POR DECISAO: dy_gap_alto (indicador de regime) saiu de ``vistos``; sao 3 criterios
    # (pvp_baixo, saude_ok, liquidez_ok) e os 3 estao atendidos aqui -> vistos == 3 == RADAR_N_CRITERIOS.
    assert row.vistos == radar.RADAR_N_CRITERIOS == 3
