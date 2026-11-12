"""Regressao dos 3 achados de METODO da auditoria.

A. Saude em % do VP/cota (nao em R$ absolutos) + criterio efetiva>patrimonial removido
   + point-in-time (t) em flag_destruicao_capital / emissoes_recentes.
B. Trava de significancia no voto (n >= 30 independentes e p corrigido < 0.05).
C. Fundo em liquidacao / preco desatualizado nunca recebe compra.

Todos os numeros esperados sao calculados a mao nos comentarios.
"""

import dataclasses
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, func, select

from src.fii_analysis.data.database import EventoCorporativo, PrecoDiario, RelatorioMensal, Ticker
from src.fii_analysis.decision import elegibilidade
from src.fii_analysis.decision.opportunities import _candidatos_comprar_de_decisoes
from src.fii_analysis.decision.portfolio_advisor import aconselhar_carteira
from src.fii_analysis.decision.recommender import _decisao_indisponivel, decidir_ticker
from src.fii_analysis.decision.suporte import (
    avaliar_suporte,
    restaurar_de_rationale,
    rotulo_sinal,
    suporte_episodio,
    suporte_walkforward,
)
from src.fii_analysis.features.saude import (
    _score_destruicao_pct,
    emissoes_recentes,
    flag_destruicao_capital,
)
from src.fii_analysis.models.threshold_optimizer_v2 import (
    load_optimizer_cache_stats,
    save_optimizer_cache,
)

STATS_OTIM_OK = {
    "n_buy_thinned": 40, "n_sell_thinned": 40,
    "p_value_buy_bonferroni": 0.001, "p_value_sell_bonferroni": 0.001,
    "avg_return_buy_independent": 0.02,
}
WF_BUY_OK = {"sinal_hoje": {"sinal": "BUY"}, "n_steps": 10,
             "summary": {"BUY": {"p_value": 0.01, "n_effective": 40, "mean": 0.02}}}


def _add_fundo(session, ticker, cnpj, vps, inicio=date(2024, 1, 1)):
    """Fundo com um relatorio por mes, VP/cota dado; efetiva > patrim (dy > 0) sempre."""
    session.add(Ticker(ticker=ticker, cnpj=cnpj))
    for i, vp in enumerate(vps):
        ref = date(inicio.year, inicio.month + i, 1)
        session.add(RelatorioMensal(
            cnpj=cnpj, data_referencia=ref, data_entrega=ref + timedelta(days=10),
            vp_por_cota=vp, cotas_emitidas=1_000_000, rentab_efetiva=1.0, rentab_patrim=0.0,
        ))
    session.commit()


# ============================================================================
# A. Saude em % do VP
# ============================================================================


def test_saude_cota_cara_e_barata_mesma_queda_percentual_mesmo_resultado(db_session):
    # Fundo A: VP 100 -> 97,5 (queda linear de 0,5/mes). Fundo B = A/10 (cota de R$ ~10).
    # 3m: slope -0,5, media 98 -> -0,5102%/mes <= -0,5 => score_vp_3m = 100
    # 6m: slope -0,5, media 98,75 -> -0,5063%/mes       => score_vp_6m = 100
    # 5 quedas seguidas de 0,5% (> 0,1%): streak 5 -> 5/6*100 = 83,33
    # destruicao = round(0,6*100 + 0,3*100 + 0,1*83,33) = round(98,33) = 98 => saude 2 => critica
    vps_a = [100.0, 99.5, 99.0, 98.5, 98.0, 97.5]
    _add_fundo(db_session, "CARA11", "01.000.000/0001-01", vps_a)
    _add_fundo(db_session, "BARA11", "02.000.000/0001-02", [v / 10 for v in vps_a])
    t = date(2024, 12, 31)
    a = flag_destruicao_capital("CARA11", db_session, t=t)
    b = flag_destruicao_capital("BARA11", db_session, t=t)
    assert a["score_vp_3m"] == b["score_vp_3m"] == 100.0
    assert a["score_vp_6m"] == b["score_vp_6m"] == 100.0
    assert a["current_consec"] == b["current_consec"] == 5
    assert a["score_saude"] == b["score_saude"] == 2
    assert a["gravidade"] == b["gravidade"] == "critica"
    assert a["pct_3m"] == pytest.approx(-0.5102, abs=1e-4)
    # Em R$ absolutos (regra antiga) B teria slope -0,05 > -0,1 e NAO seria severo.
    assert b["slope_3m"] == pytest.approx(-0.05, abs=1e-4)


@pytest.mark.parametrize("pct,esperado", [
    (0.2, 0.0),      # acima de +0,1%/mes
    (0.05, 5.0),     # (0,1-0,05)/0,1*10
    (0.0, 10.0),     # neutro
    (-0.25, 55.0),   # 10 + (0,25/0,5)*90
    (-0.5, 100.0),   # limiar severo
    (-1.0, 100.0),
])
def test_score_destruicao_faixas_em_pct(pct, esperado):
    assert _score_destruicao_pct(pct, 0.1, -0.5) == pytest.approx(esperado)


def test_streak_nao_conta_mes_com_distribuicao_positiva_se_vp_nao_cai(db_session):
    # efetiva (1.0) > patrimonial (0.0) em TODOS os meses (dy = 1.0 > 0), mas VP sobe 0,5%/mes.
    # Criterio antigo contaria 6 meses consecutivos; o novo mede queda do VP => 0.
    _add_fundo(db_session, "SOBE11", "03.000.000/0001-03",
               [100.0, 100.5, 101.0, 101.5, 102.0, 102.5])
    r = flag_destruicao_capital("SOBE11", db_session, t=date(2024, 12, 31))
    assert r["current_consec"] == 0 and r["max_consec_historico"] == 0
    assert r["gravidade"] == "saudavel" and r["destruicao"] is False
    assert r["score_saude"] == 100


def test_emissoes_recentes_respeita_data_entrega(db_session):
    # Cotas 1.000.000 -> 1.100.000 (+10%) no relatorio de 2024-03, entregue em 2024-03-11.
    session = db_session
    session.add(Ticker(ticker="EMI11", cnpj="04.000.000/0001-04"))
    for i, cotas in enumerate([1_000_000, 1_000_000, 1_100_000]):
        ref = date(2024, 1 + i, 1)
        session.add(RelatorioMensal(
            cnpj="04.000.000/0001-04", data_referencia=ref, data_entrega=ref + timedelta(days=10),
            vp_por_cota=100.0, cotas_emitidas=cotas, rentab_efetiva=1.0, rentab_patrim=0.0))
    session.commit()
    assert emissoes_recentes("EMI11", session=session, t=date(2024, 3, 10)) == []
    r = emissoes_recentes("EMI11", session=session, t=date(2024, 3, 11))
    assert len(r) == 1 and r[0]["variacao_pct"] == pytest.approx(10.0)


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_recommender_passa_data_de_referencia_para_saude(MockOpt, mock_wf, db_session):
    mock_wf.return_value = {"error": "x"}
    capturado = {}

    def fake_flag(ticker, session, t=None):
        capturado["flag_t"] = t
        return {"destruicao": False}

    def fake_emiss(ticker, session=None, t=None, **kw):
        capturado["emiss_t"] = t
        return []

    with patch("src.fii_analysis.decision.recommender.flag_destruicao_capital", fake_flag), \
         patch("src.fii_analysis.decision.recommender.emissoes_recentes", fake_emiss):
        d = decidir_ticker("MOCK11", db_session)
    ultimo = db_session.execute(
        select(PrecoDiario.data).where(PrecoDiario.ticker == "MOCK11").order_by(PrecoDiario.data.desc())
    ).scalars().first()
    assert capturado["flag_t"] == capturado["emiss_t"] == d.data_referencia == ultimo
    assert capturado["flag_t"] != date.today()


# ============================================================================
# B. Trava de significancia
# ============================================================================


def test_avaliar_suporte_fronteiras():
    assert avaliar_suporte("BUY", 30, 0.049)["status"] == "SUPORTADO"
    assert avaliar_suporte("BUY", 29, 0.001)["status"] == "SEM_SUPORTE"      # n < 30
    assert avaliar_suporte("BUY", 30, 0.05)["status"] == "SEM_SUPORTE"       # p precisa ser < 0.05
    assert avaliar_suporte("BUY", 100, 1.0)["status"] == "SEM_SUPORTE"
    assert avaliar_suporte("SELL", None, 0.01)["status"] == "SEM_SUPORTE"    # sem n
    assert avaliar_suporte("SELL", 50, None)["status"] == "SEM_SUPORTE"      # sem p
    assert avaliar_suporte("BUY", 50, 0.01, direcao_ok=False)["status"] == "SEM_SUPORTE"
    assert avaliar_suporte("NEUTRO", 50, 0.01)["status"] == "NAO_APLICA"
    assert avaliar_suporte("INDISPONIVEL", None, None)["status"] == "NAO_APLICA"


def test_suporte_episodio_aplica_bonferroni_m2():
    # p bruto 0,02 * 2 testes = 0,04 < 0,05 => suportado; 0,03 * 2 = 0,06 => nao.
    ok = suporte_episodio("BUY", {"buy": {"n": 40, "p_value": 0.02, "mean": 0.03}})
    assert ok["status"] == "SUPORTADO" and ok["p"] == pytest.approx(0.04)
    ruim = suporte_episodio("BUY", {"buy": {"n": 40, "p_value": 0.03, "mean": 0.03}})
    assert ruim["status"] == "SEM_SUPORTE" and ruim["p"] == pytest.approx(0.06)
    # p baixo mas media negativa num sinal BUY nao e suporte
    assert suporte_episodio("BUY", {"buy": {"n": 40, "p_value": 0.001, "mean": -0.03}})["status"] == "SEM_SUPORTE"
    # SELL exige media < 0
    assert suporte_episodio("SELL", {"sell": {"n": 40, "p_value": 0.001, "mean": -0.03}})["status"] == "SUPORTADO"
    assert suporte_episodio("BUY", None)["status"] == "SEM_SUPORTE"


def test_suporte_walkforward_usa_n_effective_nao_n_bruto():
    s = {"BUY": {"n": 500, "n_effective": 12, "p_value": 0.0001, "mean": 0.02}}
    r = suporte_walkforward("BUY", s)
    assert r["status"] == "SEM_SUPORTE" and r["n"] == 12


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_sinais_sem_suporte_nao_votam_mas_ficam_gravados(MockOpt, mock_wf, db_session):
    mock_wf.return_value = {"sinal_hoje": {"sinal": "BUY"}, "n_steps": 10,
                            "summary": {"BUY": {"p_value": 0.0001, "n_effective": 3, "mean": 0.05}}}
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "BUY"}
    stats_fracas = {"n_buy_thinned": 4, "p_value_buy_bonferroni": 1.0,
                    "avg_return_buy_independent": 0.02}
    d = decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1}, optimizer_stats=stats_fracas)
    assert d.sinal_otimizador == "BUY" and d.sinal_walkforward == "BUY"   # gravados
    assert d.suporte_sinais["otimizador"]["status"] == "SEM_SUPORTE"
    assert d.suporte_sinais["walkforward"]["status"] == "SEM_SUPORTE"
    assert d.n_concordam_buy == 0 and d.acao == "AGUARDAR"
    assert rotulo_sinal("BUY", d.suporte_sinais["otimizador"]) == "BUY (info)"
    # status viaja no rationale_json e e restauravel sem mudar o schema
    suporte, bloqueio = restaurar_de_rationale(d.rationale)
    assert suporte == d.suporte_sinais and bloqueio is None


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_dois_sinais_com_suporte_votam_comprar_media(MockOpt, mock_wf, db_session):
    mock_wf.return_value = WF_BUY_OK
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "BUY"}
    d = decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1}, optimizer_stats=STATS_OTIM_OK)
    assert d.n_concordam_buy == 2 and d.acao == "COMPRAR" and d.nivel_concordancia == "MEDIA"
    assert d.suporte_sinais["otimizador"]["status"] == "SUPORTADO"


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_otimizador_sem_stats_no_cache_e_sem_suporte(MockOpt, mock_wf, db_session):
    mock_wf.return_value = {"error": "x"}
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "SELL"}
    d = decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1})   # cache de teste vazio
    assert d.sinal_otimizador == "SELL"
    assert d.suporte_sinais["otimizador"]["status"] == "SEM_SUPORTE"
    assert d.n_concordam_sell == 0


def test_cache_do_otimizador_guarda_stats_e_so_casa_com_mesmos_params(tmp_path):
    params = {"pvp_percentil_buy": 15}
    save_optimizer_cache("ZZZ11", params, cache_dir=tmp_path, test_stats=STATS_OTIM_OK)
    assert load_optimizer_cache_stats("ZZZ11", params, cache_dir=tmp_path) == STATS_OTIM_OK
    assert load_optimizer_cache_stats("ZZZ11", {"pvp_percentil_buy": 20}, cache_dir=tmp_path) is None
    save_optimizer_cache("YYY11", params, cache_dir=tmp_path)             # cache antigo, sem stats
    assert load_optimizer_cache_stats("YYY11", params, cache_dir=tmp_path) is None


# ============================================================================
# C. Liquidacao / preco desatualizado
# ============================================================================


def _ultimo_preco(session, ticker="MOCK11"):
    return session.execute(
        select(func.max(PrecoDiario.data)).where(PrecoDiario.ticker == ticker)
    ).scalar_one()


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_fundo_em_liquidacao_nunca_comprar(MockOpt, mock_wf, db_session):
    mock_wf.return_value = WF_BUY_OK
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "BUY"}
    kw = dict(optimizer_params={"x": 1}, optimizer_stats=STATS_OTIM_OK)
    assert decidir_ticker("MOCK11", db_session, **kw).acao == "COMPRAR"     # controle

    ult = _ultimo_preco(db_session)
    db_session.add(EventoCorporativo(ticker="MOCK11", cnpj="11.111.111/0001-11",
                                     data=ult - timedelta(days=30), tipo="liquidacao"))
    db_session.commit()
    d = decidir_ticker("MOCK11", db_session, **kw)
    assert d.acao == "AGUARDAR" and d.nivel_concordancia == "BAIXA"
    assert d.bloqueio_compra == f"fundo em liquidacao desde {(ult - timedelta(days=30)).isoformat()}"
    assert restaurar_de_rationale(d.rationale)[1] == d.bloqueio_compra


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_liquidacao_futura_ainda_nao_vigente_nao_bloqueia(MockOpt, mock_wf, db_session):
    mock_wf.return_value = WF_BUY_OK
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "BUY"}
    ult = _ultimo_preco(db_session)
    db_session.add(EventoCorporativo(ticker="MOCK11", data=ult + timedelta(days=1), tipo="liquidacao"))
    db_session.commit()
    d = decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1}, optimizer_stats=STATS_OTIM_OK)
    assert d.bloqueio_compra is None and d.acao == "COMPRAR"


def test_preco_desatualizado_limite_de_5_pregoes(db_session):
    datas = db_session.execute(
        select(PrecoDiario.data).where(PrecoDiario.ticker == "MOCK12").order_by(PrecoDiario.data)
    ).scalars().all()
    ref = datas[-1]
    # remove os ultimos 5 pregoes de MOCK12: atraso = 5 => NAO bloqueia (so > 5)
    db_session.execute(delete(PrecoDiario).where(PrecoDiario.ticker == "MOCK12",
                                                 PrecoDiario.data.in_(datas[-5:])))
    db_session.commit()
    assert elegibilidade.atraso_preco_pregoes("MOCK12", ref, db_session) == (datas[-6], 5)
    assert elegibilidade.motivo_bloqueio_compra("MOCK12", ref, db_session) is None
    # mais um pregao removido: atraso = 6 => bloqueia
    db_session.execute(delete(PrecoDiario).where(PrecoDiario.ticker == "MOCK12",
                                                 PrecoDiario.data == datas[-6]))
    db_session.commit()
    motivo = elegibilidade.motivo_bloqueio_compra("MOCK12", ref, db_session)
    assert motivo is not None and motivo.startswith(f"preco desatualizado: ultimo preco em {datas[-7].isoformat()}")
    assert "6 pregoes de atraso" in motivo
    # MOCK11 (em dia) nao e afetado
    assert elegibilidade.motivo_bloqueio_compra("MOCK11", ref, db_session) is None


def _decisao_comprar(**kw):
    base = _decisao_indisponivel("MOCK11", "x", date(2025, 1, 1))
    return dataclasses.replace(base, acao="COMPRAR", nivel_concordancia="ALTA",
                               preco_referencia=100.0, **kw)


def test_advisor_nunca_aumenta_fundo_bloqueado_e_posicao_continua_listada():
    # 4 posicoes de mesmo valor (10 x R$100) => peso 25% < 30% (limite de concentracao)
    holdings = [{"ticker": t, "quantidade": 10, "preco_medio": 90.0}
                for t in ("MOCK11", "A11", "B11", "C11")]
    precos = {t: 100.0 for t in ("MOCK11", "A11", "B11", "C11")}
    livre = aconselhar_carteira([_decisao_comprar()], holdings, precos_atuais=precos)
    livre = [a for a in livre if a.ticker == "MOCK11"]
    assert livre[0].badge == "AUMENTAR"                                        # controle
    bloq = aconselhar_carteira(
        [_decisao_comprar(bloqueio_compra="fundo em liquidacao desde 2026-04-16")], holdings,
        precos_atuais=precos)
    bloq = [a for a in bloq if a.ticker == "MOCK11"]
    assert len(bloq) == 1                                                       # posicao aparece
    assert bloq[0].badge == "HOLD" and bloq[0].badge != "AUMENTAR"
    assert "fundo em liquidacao desde 2026-04-16" in bloq[0].racional


def test_candidato_de_rotacao_exclui_fundo_em_liquidacao(db_session):
    dec = dataclasses.replace(
        _decisao_indisponivel("MOCK11", "x", date(2025, 1, 1)),
        pvp_percentil=10.0, dy_gap_percentil=80.0, classificacao="Tijolo")
    ref = _ultimo_preco(db_session)
    universo = {"MOCK11": dec}
    cands = _candidatos_comprar_de_decisoes(db_session, universo, {"MOCK11"}, set(), ref)
    assert [c.ticker for c in cands] == ["MOCK11"]                             # controle
    db_session.add(EventoCorporativo(ticker="MOCK11", data=ref - timedelta(days=10), tipo="liquidacao"))
    db_session.commit()
    assert _candidatos_comprar_de_decisoes(db_session, universo, {"MOCK11"}, set(), ref) == []
