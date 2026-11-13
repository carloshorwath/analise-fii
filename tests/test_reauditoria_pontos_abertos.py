"""Regressao dos pontos abertos da reauditoria (itens 1-9). Dado sintetico, resultado calculado a mao."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from src.fii_analysis.data.database import (
    AtivoPassivo, PrecoDiario, RelatorioMensal, Ticker,
)

CNPJ_SPLIT = "33.333.333/0001-33"


def _fii_com_informes(session, ticker, cnpj, informes):
    """informes: [(data_ref, vp, pl, cotas)], entrega = ref + 15 dias."""
    session.add(Ticker(cnpj=cnpj, ticker=ticker, nome=ticker, segmento="Tijolo"))
    for ref, vp, pl, cotas in informes:
        session.add(RelatorioMensal(
            cnpj=cnpj, data_referencia=ref, data_entrega=ref + timedelta(days=15),
            vp_por_cota=vp, patrimonio_liq=pl, cotas_emitidas=cotas,
            dy_mes_pct=0.007, rentab_efetiva=0.008, rentab_patrim=0.001,
        ))
    session.add(PrecoDiario(ticker=ticker, data=date(2024, 1, 2), fechamento=10.0, fechamento_aj=10.0,
                            volume=1000, fonte="t", coletado_em=datetime.now(timezone.utc)))
    session.commit()


def _fim_mes(ano, mes):
    return (pd.Timestamp(ano, mes, 1) + pd.offsets.MonthEnd(0)).date()


def _informes_split():
    """12 informes de 2024. Split 5:1 a partir do 7o informe (jul). PL 100 mi constante.
    Antes: 1.000.000 cotas, VP 100. Depois: 5.000.000 cotas, VP 20 (VP ajustado = 20 sempre)."""
    out = []
    for m in range(1, 13):
        ref = _fim_mes(2024, m)
        if m < 7:
            out.append((ref, 100.0, 100_000_000.0, 1_000_000))
        else:
            out.append((ref, 20.0, 100_000_000.0, 5_000_000))
    return out


# ---------------------------------------------------------------- item 1
def test_split_nao_vira_emissao_nem_queda_de_vp(db_session):
    from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital, tendencia_pl
    _fii_com_informes(db_session, "SPLT11", CNPJ_SPLIT, _informes_split())
    t = date(2025, 1, 31)
    assert emissoes_recentes("SPLT11", session=db_session, t=t) == []  # nominal daria +400%
    f = flag_destruicao_capital("SPLT11", db_session, t=t)
    assert f["n_emissoes_ruins"] == 0
    assert f["pct_3m"] == 0.0 and f["pct_6m"] == 0.0           # VP ajustado = 20 constante
    assert f["cond2_cotas_estaveis"] is True                   # cotas_aj constantes (5 mi)
    coef = tendencia_pl("SPLT11", session=db_session, t=t)[12]["coef_angular"]
    assert coef == pytest.approx(0.0, abs=1e-9)                # nominal daria ~ -8


def test_emissao_real_continua_detectada(db_session):
    """Controle: emissao de +10% das cotas com VP -5% (sem split) segue 'prejudicial'."""
    from src.fii_analysis.features.saude import emissoes_recentes
    inf = [(_fim_mes(2024, m), 100.0, 100_000_000.0, 1_000_000) for m in range(1, 6)]
    inf.append((_fim_mes(2024, 6), 95.0, 104_500_000.0, 1_100_000))  # +10% cotas, VP 100 -> 95
    _fii_com_informes(db_session, "EMIS11", "44.444.444/0001-44", inf)
    em = emissoes_recentes("EMIS11", session=db_session, t=date(2025, 1, 31))
    assert len(em) == 1
    assert em[0]["variacao_pct"] == pytest.approx(10.0)
    assert em[0]["impacto_vp_pct"] == pytest.approx(-5.0)
    assert em[0]["ruim"] is True


def test_pl_trend_usa_cotas_ajustadas(db_session):
    from src.fii_analysis.features.momentum_signals import get_pl_trend
    _fii_com_informes(db_session, "SPLT11", CNPJ_SPLIT, _informes_split())
    # janela de 2 informes (jun pre-split, jul pos-split) entregues ate 2024-08-20:
    # PL/cotas nominal = 100 -> 20 (CAINDO); ajustado = 20 -> 20 (ESTAVEL)
    assert get_pl_trend("SPLT11", date(2024, 8, 20), db_session, months=1) == "ESTAVEL"


def test_event_study_emissao_cotas_ignora_split(db_session):
    from src.fii_analysis.models.event_study_cvm import get_events
    _fii_com_informes(db_session, "SPLT11", CNPJ_SPLIT, _informes_split())
    bd = pd.Series(pd.bdate_range("2024-01-01", "2025-03-01").date)
    assert get_events("SPLT11", "emissao_cotas", db_session, 5, bd) == []


# ---------------------------------------------------------------- item 2
def _precos_volume(session, ticker, volumes, inicio=date(2025, 3, 3)):
    d, datas = inicio, []
    for v in volumes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        session.add(PrecoDiario(ticker=ticker, data=d, fechamento=50.0, fechamento_aj=50.0, volume=v,
                                fonte="t", coletado_em=datetime.now(timezone.utc)))
        datas.append(d)
        d += timedelta(days=1)
    session.commit()
    return datas


def test_bloqueia_compra_com_5_pregoes_seguidos_volume_zero(db_session):
    from src.fii_analysis.decision import elegibilidade as e
    datas = _precos_volume(db_session, "ZERO11", [500] * 7 + [0] * 5)
    motivo = e.motivo_bloqueio_compra("ZERO11", datas[-1], db_session)
    assert motivo is not None and "sem negocios ha 5 pregoes" in motivo
    assert e.pregoes_consecutivos_sem_volume("ZERO11", datas[-1], db_session) == 5


def test_4_zeros_seguidos_nao_bloqueia_mas_marca_intermitente(db_session):
    from src.fii_analysis.decision import elegibilidade as e
    datas = _precos_volume(db_session, "INTR11", [500] * 6 + [0] * 4)  # 4 de 10, 4 seguidos
    assert e.motivo_bloqueio_compra("INTR11", datas[-1], db_session) is None
    assert e.liquidez_intermitente("INTR11", datas[-1], db_session) == (4, 10)


def test_3_zeros_em_10_nao_marca_e_serie_curta_nao_marca(db_session):
    from src.fii_analysis.decision import elegibilidade as e
    datas = _precos_volume(db_session, "OKOK11", [500, 0, 500, 0, 500, 0, 500, 500, 500, 500])
    assert e.liquidez_intermitente("OKOK11", datas[-1], db_session) is None   # 3 de 10
    curta = _precos_volume(db_session, "NEW111", [0, 0, 0, 0], inicio=date(2025, 3, 3))
    assert e.liquidez_intermitente("NEW111", curta[-1], db_session) is None   # < 10 pregoes
    assert e.motivo_bloqueio_compra("NEW111", curta[-1], db_session) is None  # < 5 pregoes


def test_volume_nulo_nao_conta_como_zero(db_session):
    from src.fii_analysis.decision import elegibilidade as e
    datas = _precos_volume(db_session, "NULL11", [500] * 5 + [None] + [0] * 4)
    assert e.pregoes_consecutivos_sem_volume("NULL11", datas[-1], db_session) == 4


# ---------------------------------------------------------------- itens 3 e 4
def _ap(session, cnpj, **kw):
    base = dict(cnpj=cnpj, data_referencia=date(2025, 1, 31), data_entrega=date(2025, 2, 15))
    session.add(AtivoPassivo(**{**base, **kw}))
    session.commit()


def test_composicao_sociedades_tijolo_sem_dupla_contagem(db_session):
    from src.fii_analysis.features.composicao import classificar_fii, composicao_ativo
    # ativo 100: imoveis 40 + sociedades (10 acoes + 20 cotas) + outras cotas FII 20 (total_investido 90)
    # caixa: disp 5 DENTRO de necessidades_liquidez 5; receber: aluguel 3 DENTRO de valores_receber 5
    _ap(db_session, "11.111.111/0001-11", ativo_total=100.0, direitos_bens_imoveis=40.0,
        acoes_sociedades_fii=10.0, cotas_sociedades_fii=20.0, total_investido=90.0,
        disponibilidades=5.0, total_necessidades_liquidez=5.0,
        valores_receber=5.0, contas_receber_aluguel=3.0)
    c = composicao_ativo("MOCK11", db_session)
    assert c["pct_imoveis"] == pytest.approx(0.40)
    assert c["pct_sociedades_imobiliarias"] == pytest.approx(0.30)
    assert c["pct_imoveis_total"] == pytest.approx(0.70)
    assert c["pct_caixa"] == pytest.approx(0.05)              # antes: 0.10
    assert c["pct_valores_receber"] == pytest.approx(0.05)    # antes: 0.08
    assert c["pct_investimentos"] == pytest.approx(0.20)      # 90 - 40 - 30
    assert c["pct_outros"] == pytest.approx(0.0)
    soma = sum(c[k] for k in ("pct_imoveis", "pct_sociedades_imobiliarias", "pct_recebiveis", "pct_caixa",
                              "pct_investimentos", "pct_valores_receber", "pct_outros"))
    assert soma == pytest.approx(1.0)
    assert classificar_fii("MOCK11", db_session) == "Tijolo"  # so com imoveis diretos (40%) seria Hibrido


def test_fundo_de_fundos_nao_e_tijolo(db_session):
    from src.fii_analysis.features.composicao import classificar_fii
    _ap(db_session, "11.111.111/0001-11", ativo_total=100.0, direitos_bens_imoveis=0.0,
        acoes_sociedades_fii=0.0, cotas_sociedades_fii=0.0, total_investido=95.0,  # 95 em cotas de outros FIIs
        total_necessidades_liquidez=5.0)
    assert classificar_fii("MOCK11", db_session) == "Hibrido"


def test_composicao_banco_sem_colunas_de_sociedades_nao_quebra():
    from src.fii_analysis.features.composicao import _tem_colunas_sociedades
    eng = create_engine("sqlite://")
    with Session(eng) as s:
        s.execute(text("CREATE TABLE ativo_passivo (cnpj TEXT, data_referencia DATE)"))
        assert _tem_colunas_sociedades(s) is False


# ---------------------------------------------------------------- item 5
def test_cdi_12m_semiaberto(db_session):
    from src.fii_analysis.data.cdi import get_cdi_acumulado_12m
    t = date(2025, 6, 27)  # sexta; t-12m = 2024-06-27 (quinta, dia util) fica FORA
    n = int(np.busday_count("2024-06-28", "2025-06-28"))
    assert n == 261
    assert get_cdi_acumulado_12m(t, db_session) == pytest.approx(1.0004 ** n - 1.0, rel=1e-12)
    assert get_cdi_acumulado_12m(t, db_session) != pytest.approx(1.0004 ** (n + 1) - 1.0, rel=1e-9)


def test_janela_dy_gap_tem_exatamente_janela_pregoes_anteriores_a_t():
    from src.fii_analysis.features.valuation import _datas_janela
    datas = [date(2024, 1, 1) + timedelta(days=i) for i in range(400)]
    w = _datas_janela(datas, 252)
    assert len(w) == 252                      # antes: 251
    assert w[-1] == datas[-2] and w[0] == datas[-1 - 252]
    assert datas[-1] not in w                 # t excluido
    assert len(_datas_janela(datas[:100], 252)) == 99


# ---------------------------------------------------------------- item 6
def test_dy_mes_do_panorama_e_fracao(db_session):
    from src.fii_analysis.features.portfolio import carteira_panorama
    db_session.execute(text("UPDATE relatorios_mensais SET dy_mes_pct = 0.0064"))
    db_session.commit()
    df = carteira_panorama(["MOCK11"], db_session)
    assert df.loc[0, "dy_mes"] == pytest.approx(0.0064)   # antes: 0.000064 (exibido 0,01%)


# ---------------------------------------------------------------- item 8
def test_rotulo_desde_ontem_so_se_for_pregao_anterior():
    from src.fii_analysis.evaluation.daily_diff import rotulo_periodo_diff
    assert rotulo_periodo_diff(date(2026, 11, 11), date(2026, 11, 12)) == "desde ontem"
    assert rotulo_periodo_diff(date(2026, 11, 6), date(2026, 11, 9)) == "desde ontem"      # sex -> seg
    assert rotulo_periodo_diff(date(2026, 10, 30), date(2026, 11, 3)) == "desde ontem"     # 02/11 feriado
    assert rotulo_periodo_diff(date(2026, 6, 11), date(2026, 11, 12)) == "desde o snapshot anterior"
    assert rotulo_periodo_diff(date(2026, 11, 12), date(2026, 11, 12)) == "desde o snapshot anterior"


def test_markdown_do_diff_usa_rotulo_correto():
    from src.fii_analysis.evaluation.daily_diff import DailyDiff, render_diff_markdown
    md = render_diff_markdown(DailyDiff(data_atual=date(2026, 11, 12), data_anterior=date(2026, 6, 11)))
    assert "desde o snapshot anterior (11/06/2026" in md and "desde ontem" not in md


def test_rodape_update_prices_so_se_preco_defasado(db_session):
    from src.fii_analysis.evaluation.daily_diff import precos_desatualizados
    ultimo = db_session.execute(select(PrecoDiario.data).order_by(PrecoDiario.data.desc()).limit(1)).scalar_one()
    assert precos_desatualizados(db_session, hoje=ultimo) is False
    assert precos_desatualizados(db_session, hoje=ultimo + timedelta(days=7)) is True


# ---------------------------------------------------------------- item 9
def test_percentil_pvp_empate_numerico_nao_conta_como_abaixo(monkeypatch):
    import src.fii_analysis.features.valuation as val
    # janela: 40 obs = 1.0 - 1e-13 (empate numerico), 30 = 0.5 (abaixo), 30 = 2.0 (acima); t = 1.0
    pvps = [1.0 - 1e-13] * 40 + [0.5] * 30 + [2.0] * 30 + [1.0]
    datas = [date(2024, 1, 1) + timedelta(days=i) for i in range(len(pvps))]
    df = pd.DataFrame({"data": datas, "fechamento": pvps, "vp_por_cota": 1.0, "pvp": pvps})
    monkeypatch.setattr(val, "get_pvp_serie", lambda ticker, session: df)
    pct, n = val.get_pvp_percentil("X", datas[-1], 504, None)
    assert n == 100
    assert pct == pytest.approx(30.0)         # antes (comparacao crua): 70.0
