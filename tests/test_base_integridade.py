"""Regressao: integridade da base (dividendos duplicados, splits x VP, fechamento_aj proprio)."""
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.fii_analysis.data import ingestion as ing
from src.fii_analysis.data.corporate_actions import (
    ajustar_relatorios,
    calcular_retorno_total,
    deduplicar_proximos,
    detectar_splits,
)
from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal, Ticker
from src.fii_analysis.features.indicators import get_pvp, get_pvp_serie, get_vp_cotas_pit


# --------------------------------------------------------------------------- dividendos
def test_dedup_mesmo_valor_ate_7_dias_mantem_preferida():
    # SNFF11: ex-date (16/04) gravada como data-com ao lado da data-com correta (15/04)
    linhas = [(date(2025, 4, 15), 0.72), (date(2025, 4, 16), 0.72), (date(2025, 5, 15), 0.72)]
    assert deduplicar_proximos(linhas) == [date(2025, 4, 16)]  # sem preferida: mantem a mais antiga
    assert deduplicar_proximos(linhas, preferidas={date(2025, 4, 16)}) == [date(2025, 4, 15)]


def test_dedup_conservador_valores_diferentes_ou_mais_de_7_dias_ficam():
    assert deduplicar_proximos([(date(2025, 6, 16), 1.06), (date(2025, 6, 17), 0.92)]) == []
    assert deduplicar_proximos([(date(2025, 6, 1), 0.5), (date(2025, 6, 9), 0.5)]) == []  # 8 dias


def test_limpar_dividendos_duplicados_no_banco_e_dy_12m(db_session):
    db_session.add(Ticker(cnpj="33.333.333/0001-33", ticker="DUPL11"))
    # 12 meses de 1,00 + 12 duplicatas (1 dia depois) = DY dobrado
    for m in range(1, 13):
        db_session.add(Dividendo(ticker="DUPL11", data_com=date(2025, m, 10), valor_cota=1.0, fonte="x"))
        db_session.add(Dividendo(ticker="DUPL11", data_com=date(2025, m, 11), valor_cota=1.0, fonte="x"))
    db_session.commit()
    assert ing.limpar_dividendos_duplicados("DUPL11", db_session) == 12
    soma = sum(float(d.valor_cota) for d in db_session.query(Dividendo).filter_by(ticker="DUPL11"))
    assert soma == pytest.approx(12.0)  # antes: 24,0 (DY 25% em vez de 12,5% com P=100)


def test_reconciliar_base_split_so_regrava_multiplo_de_split():
    d = Dividendo(ticker="X", data_com=date(2023, 1, 1), valor_cota=1.1)
    assert ing._reconciliar_base_split(d, 0.11) is True and d.valor_cota == pytest.approx(0.11)
    d2 = Dividendo(ticker="X", data_com=date(2023, 1, 1), valor_cota=0.10)
    assert ing._reconciliar_base_split(d2, 0.0957) is False and d2.valor_cota == pytest.approx(0.10)  # 1,045x: preserva


# --------------------------------------------------------------------------- splits x VP
def _rel_split():
    # 6 informes; split 1:10 no 4o (jan/2024): cotas x10, VP /10, PL estavel
    ref = pd.to_datetime(["2023-10-01", "2023-11-01", "2023-12-01", "2024-01-01", "2024-02-01", "2024-03-01"])
    return pd.DataFrame({
        "data_referencia": ref,
        "vp_por_cota": [100.0, 101.0, 102.0, 10.3, 10.4, 10.5],
        "patrimonio_liq": [1.00e8, 1.01e8, 1.02e8, 1.03e8, 1.04e8, 1.05e8],
        "cotas_emitidas": [1_000_000] * 3 + [10_000_000] * 3,
    })


def test_detectar_splits_e_ajustar_vp():
    ev, amb = detectar_splits(_rel_split())
    assert len(ev) == 1 and ev[0].fator == 10.0 and ev[0].primeiro_informe_pos == date(2024, 1, 1) and not amb
    aj = ajustar_relatorios(_rel_split(), ev)
    assert aj.vp_aj.round(4).tolist() == [10.0, 10.1, 10.2, 10.3, 10.4, 10.5]  # sem degrau 10x
    assert aj.cotas_aj.tolist() == [10_000_000] * 6


def test_emissao_nao_e_split():
    r = _rel_split()
    r["cotas_emitidas"] = [1_000_000] * 3 + [2_000_000] * 3
    r["vp_por_cota"] = [100.0, 101, 102, 101, 102, 103]
    r["patrimonio_liq"] = r.vp_por_cota * r.cotas_emitidas  # PL dobrou: captacao
    assert detectar_splits(r)[0] == []


def test_grupamento_fator_inverso():
    r = pd.DataFrame({
        "data_referencia": pd.to_datetime(["2023-01-01", "2023-02-01"]),
        "vp_por_cota": [1.0, 10.0], "patrimonio_liq": [1e8, 1e8], "cotas_emitidas": [1e8, 1e7],
    })
    ev, _ = detectar_splits(r)
    assert ev[0].fator == pytest.approx(0.1)
    assert ajustar_relatorios(r, ev).vp_aj.tolist() == pytest.approx([10.0, 10.0])


def _setup_fundo_split(db_session):
    """Preco ja split-ajustado (10 ate 20/jan; 10,3 depois). Split no preco em 15/jan/2024;
    1o informe pos-split (ref jan) so e entregue em 12/fev."""
    db_session.add(Ticker(cnpj="44.444.444/0001-44", ticker="SPLT11"))
    rels = [("2023-11-01", "2023-12-12", 100.0, 1_000_000), ("2023-12-01", "2024-01-12", 100.0, 1_000_000),
            ("2024-01-01", "2024-02-12", 10.0, 10_000_000), ("2024-02-01", "2024-03-12", 10.0, 10_000_000)]
    for ref, ent, vp, cotas in rels:
        db_session.add(RelatorioMensal(cnpj="44.444.444/0001-44", data_referencia=date.fromisoformat(ref),
                                       data_entrega=date.fromisoformat(ent), vp_por_cota=vp,
                                       patrimonio_liq=vp * cotas, cotas_emitidas=cotas))
    d = date(2024, 1, 2)
    while d < date(2024, 3, 1):
        if d.weekday() < 5:
            db_session.add(PrecoDiario(ticker="SPLT11", data=d, fechamento=10.0, fechamento_aj=10.0))
        d += timedelta(days=1)
    db_session.commit()


def test_vp_pit_entre_split_e_primeiro_informe_pos_usa_vp_antigo_na_base_nova(db_session):
    _setup_fundo_split(db_session)
    # 2024-01-31: split ja ocorreu no preco, mas o ultimo informe entregue e o de dez (VP 100 nominal)
    vp, cotas = get_vp_cotas_pit("SPLT11", date(2024, 1, 31), db_session)
    assert vp == pytest.approx(10.0) and cotas == pytest.approx(10_000_000)
    assert get_pvp("SPLT11", date(2024, 1, 31), db_session) == pytest.approx(1.0)  # 10/10 (antes: 0,1)
    # depois do 1o informe pos-split o VP nominal ja e o novo (fator 1)
    vp2, _ = get_vp_cotas_pit("SPLT11", date(2024, 2, 20), db_session)
    assert vp2 == pytest.approx(10.0)
    serie = get_pvp_serie("SPLT11", db_session)
    assert serie.pvp.round(6).unique().tolist() == [1.0]  # serie sem degrau


def test_pvp_fundo_sem_split_identico_ao_nominal(db_session):
    # MOCK11 (conftest): preco 100, VP 100 -> P/VP 1,0 exato; VP ajustado == nominal
    vp, cotas = get_vp_cotas_pit("MOCK11", date(2025, 6, 1), db_session)
    assert vp == pytest.approx(100.0) and cotas == pytest.approx(1_000_000)
    assert get_pvp("MOCK11", date(2025, 6, 1), db_session) == pytest.approx(1.0)


# --------------------------------------------------------------------------- retorno total
def test_retorno_total_reinveste_na_data_ex_e_ultimo_dia_fator_1():
    # sex 05/jan data-com; ex = seg 08/jan. P: 100,100,100(ex: cai p/ 99 com div 1)...
    idx = pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"])
    p = pd.Series([100.0, 100.0, 99.0, 99.0], index=idx)
    tr = calcular_retorno_total(p, [(date(2024, 1, 5), 1.0)])
    # ex 08/jan: TR = TR_ant * (99+1)/100 = sem degrau (retorno aj = 0, retorno preco = -1%)
    assert tr.iloc[-1] == pytest.approx(99.0)               # ultimo dia: fator 1
    assert tr.iloc[2] / tr.iloc[1] - 1 == pytest.approx(0.0)  # data-ex: aj nao cai
    assert p.iloc[2] / p.iloc[1] - 1 == pytest.approx(-0.01)
    assert tr.iloc[0] == pytest.approx(99.0)                # 100 * 0,99... = historico escalado para tras
    # sem dividendo, aj == fechamento
    assert calcular_retorno_total(p, []).tolist() == p.tolist()


def test_retorno_total_12m_calculado_a_mao():
    # 253 pregoes, P0=100 -> P_t=110, dividendo 1,0 em duas datas-ex com precos 105 e 108
    idx = pd.bdate_range("2024-01-01", periods=253)
    p = pd.Series(np.linspace(100, 110, 253), index=idx)
    i1, i2 = 100, 200
    divs = [(idx[i1 - 1].date(), 1.0), (idx[i2 - 1].date(), 1.0)]
    tr = calcular_retorno_total(p, divs)
    mao = (p.iloc[-1] / p.iloc[0]) * ((p.iloc[i1] + 1) / p.iloc[i1]) * ((p.iloc[i2] + 1) / p.iloc[i2]) - 1
    assert tr.iloc[-1] / tr.iloc[0] - 1 == pytest.approx(mao)


def test_retorno_total_ignora_dividendo_sem_ex_na_serie_e_linhas_nulas():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    p = pd.Series([10.0, np.nan, 10.0, 10.0], index=idx)  # glitch invalidado = NaN
    tr = calcular_retorno_total(p, [(date(2024, 1, 5), 1.0)])  # ex futura (apos ultimo preco)
    assert np.isnan(tr.iloc[1]) and tr.dropna().tolist() == [10.0, 10.0, 10.0]


def test_recalcular_fechamento_aj_por_inteiro_e_idempotente(db_session):
    db_session.add(Ticker(cnpj="55.555.555/0001-55", ticker="TRET11"))
    for i, (d, p) in enumerate([(date(2024, 3, 4), 100.0), (date(2024, 3, 5), 100.0),
                                (date(2024, 3, 6), 99.0), (date(2024, 3, 7), 99.0)]):
        db_session.add(PrecoDiario(ticker="TRET11", data=d, fechamento=p, fechamento_aj=12345.0))  # lixo do Yahoo
    db_session.add(Dividendo(ticker="TRET11", data_com=date(2024, 3, 5), valor_cota=1.0, fonte="x"))
    db_session.commit()
    assert ing.recalcular_fechamento_aj("TRET11", db_session) == 4
    aj = [float(r.fechamento_aj) for r in db_session.query(PrecoDiario).filter_by(ticker="TRET11").order_by(PrecoDiario.data)]
    assert aj == pytest.approx([99.0, 99.0, 99.0, 99.0])  # sem degrau na data-ex (06/mar)
    assert ing.recalcular_fechamento_aj("TRET11", db_session) == 0  # idempotente


# --------------------------------------------------------------------------- carga: linhas vazias
def test_linha_precisa_revisao_vazia_ou_provisoria_mas_nao_invalida():
    vazia = PrecoDiario(ticker="A", data=date(2026, 5, 7), abertura=0, maxima=0, minima=0, fechamento=10.0,
                        volume=0, coletado_em=datetime(2026, 5, 20), fonte="yfinance")
    assert ing._linha_precisa_revisao(vazia)
    ok = PrecoDiario(ticker="A", data=date(2026, 5, 7), abertura=1, maxima=1, minima=1, fechamento=1.0,
                     volume=5, coletado_em=datetime(2026, 5, 20), fonte="yfinance")
    assert not ing._linha_precisa_revisao(ok)
    prov = PrecoDiario(ticker="A", data=date(2026, 5, 7), abertura=1, maxima=1, minima=1, fechamento=1.0,
                       volume=5, coletado_em=datetime(2026, 5, 7, 14), fonte="yfinance")
    assert ing._linha_precisa_revisao(prov)
    vazia.fonte = ing.FONTE_INVALIDA
    assert not ing._linha_precisa_revisao(vazia)
