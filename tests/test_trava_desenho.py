"""Regressao do desenho da trava de significancia.

Cobre: (1) teste do EXCESSO sobre a deriva (nao contra zero), (2) familia BH,
(3) p de holdout do otimizador sem multiplicar pelo grid, (4) percentis da
decisao iguais aos da metrica. Dados sinteticos com resultado calculado a mao
quando possivel; os casos estocasticos usam semente fixa.
"""

import re
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.fii_analysis.decision import recommender as rec
from src.fii_analysis.decision.suporte import (
    ajustar_bh,
    aplicar_fdr,
    evidencia,
    evidencia_episodio,
    extrair_stats_otimizador,
)
from src.fii_analysis.features.valuation import get_dy_gap_percentil, get_pvp_percentil
from src.fii_analysis.models.episodes import (
    get_pvp_series,
    identify_episodes,
    pvp_percentil_ate_t_menos_1,
)
from src.fii_analysis.models.teste_excesso import excesso_vs_deriva
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2


# ============================================================================
# 1. Excesso sobre a deriva (calculo a mao)
# ============================================================================


def test_excesso_calculado_a_mao():
    # deriva 1%; eventos = deriva + [2,3,1,2,2]% => excesso medio 2%
    # desvios do excesso em torno de 2%: 0,+1,-1,0,0 (em %) => var = 2e-4/4 = 5e-5
    # se = sqrt(5e-5)/sqrt(5) = 0.0031623 ; t = 0.02/0.0031623 = 6.3246 ; g.l. = 4
    ev = [0.03, 0.04, 0.02, 0.03, 0.03]
    r = excesso_vs_deriva(ev, 0.01, "BUY")
    assert r["n"] == 5
    assert r["media_bruta"] == pytest.approx(0.03)
    assert r["deriva"] == pytest.approx(0.01)
    assert r["excesso"] == pytest.approx(0.02)
    assert r["t_stat"] == pytest.approx(6.3246, abs=1e-3)
    assert r["p_value"] < 0.005                       # unicaudal direita, t=6.32, 4 g.l.
    # SELL com o mesmo dado (excesso positivo) nao tem evidencia na direcao do sinal
    assert excesso_vs_deriva(ev, 0.01, "SELL")["p_value"] > 0.995


def test_retorno_positivo_so_por_deriva_nao_e_evidencia():
    # Eventos todos positivos (media 1%, desvio pequeno): contra ZERO seria
    # "altamente significativo"; contra a deriva de 1% o excesso e 0 => p = 0,5.
    ev = [0.012, 0.008, 0.011, 0.010, 0.009]          # media exata 0,010
    contra_zero = excesso_vs_deriva(ev, 0.0, "BUY")["p_value"]
    contra_deriva = excesso_vs_deriva(ev, 0.010, "BUY")
    assert contra_zero < 0.001
    assert contra_deriva["excesso"] == pytest.approx(0.0, abs=1e-12)
    assert contra_deriva["p_value"] == pytest.approx(0.5, abs=1e-6)


def test_excesso_sell_unicaudal_esquerda():
    ev = [-0.01, 0.0, -0.02, -0.01, -0.01]            # media -1%, deriva 0,5%
    r = excesso_vs_deriva(ev, 0.005, "SELL")
    assert r["excesso"] == pytest.approx(-0.015)
    assert r["p_value"] < 0.01
    assert excesso_vs_deriva(ev, 0.005, "BUY")["p_value"] > 0.99


def test_excesso_n_pequeno_ou_sem_variancia_nao_gera_p():
    assert excesso_vs_deriva([0.01, 0.02, 0.03], 0.0, "BUY")["p_value"] is None   # n<5
    assert excesso_vs_deriva([0.02] * 8, 0.01, "BUY")["p_value"] is None          # SE=0


def _serie_sintetica(n=3000, seed=11, bump=0.0, drift=0.0005, vol=0.003):
    """Preco com deriva positiva; P/VP aleatorio independente do retorno.

    bump > 0: retorno do dia seguinte a um dia de P/VP extremamente baixo
    (percentil ate t-1 <= 10) recebe +bump => sinal BUY com poder preditivo.
    """
    rng = np.random.default_rng(seed)
    pvp = 1.0 + 0.1 * rng.standard_normal(n)
    pct = pvp_percentil_ate_t_menos_1(pd.Series(pvp), 504, 63).to_numpy()
    ret = drift + vol * rng.standard_normal(n)
    if bump:
        for i in range(n - 1):
            if not np.isnan(pct[i]) and pct[i] <= 10:
                ret[i + 1] += bump
    preco = 100.0 * np.cumprod(1.0 + ret)
    return pd.DataFrame({
        "data": pd.bdate_range("2012-01-02", periods=n),
        "fechamento": preco, "fechamento_aj": preco, "pvp": pvp,
    })


def test_ativo_com_deriva_e_sinal_sem_poder_preditivo_nao_sai_suportado():
    df = _serie_sintetica(bump=0.0)
    res = identify_episodes(df, 10, 90, forward_days=20, min_gap=20)
    buy = res["summary"]["buy"]
    # deriva positiva: a media bruta do BUY e positiva e "passaria" contra zero ...
    p_zero = excesso_vs_deriva(res["buy"]["fwd_ret"].values, 0.0, "BUY")["p_value"]
    assert buy["mean"] > 0.005 and p_zero < 0.01
    # ... deriva = media de TODOS os fwd_ret elegiveis (conferida de forma independente)
    fwd = (df["fechamento_aj"].shift(-20) / df["fechamento_aj"] - 1.0)
    pct = pvp_percentil_ate_t_menos_1(df["pvp"], 504, 63)
    elegiveis = fwd[pct.notna() & fwd.notna()]
    assert buy["drift"] == pytest.approx(float(elegiveis.mean()))
    assert buy["excess"] == pytest.approx(buy["mean"] - buy["drift"])
    # ... mas o p do EXCESSO nao rejeita H0
    assert buy["p_value"] > 0.05
    # e, mesmo com n suficiente e familia unitaria, a trava nao da suporte
    ev = evidencia_episodio("BUY", {"buy": {**buy, "n": max(buy["n"], 30)}})
    assert aplicar_fdr([ev])[0]["status"] == "SEM_SUPORTE"


def test_ativo_com_excesso_real_sai_suportado():
    df = _serie_sintetica(bump=0.01)
    res = identify_episodes(df, 10, 90, forward_days=20, min_gap=20)
    buy = res["summary"]["buy"]
    assert buy["n"] >= 30
    assert buy["excess"] > 0.005
    assert buy["p_value"] < 0.001
    ev = evidencia_episodio("BUY", {"buy": buy})
    j = aplicar_fdr([ev])[0]
    assert j["status"] == "SUPORTADO"
    assert j["media"] == pytest.approx(buy["mean"]) and j["deriva"] == pytest.approx(buy["drift"])


# ============================================================================
# 2. Benjamini-Hochberg
# ============================================================================


def test_bh_exemplo_numerico_6_pvalores():
    # m=6. Ordenados: .005 .01 .03 .04 .2 .5 ; p*m/rank = .03 .03 .06 .048 .24 .5
    # step-up de baixo p/ cima (min acumulado): .03 .03 .06 .06 .24 .5
    p = [0.01, 0.04, 0.03, 0.005, 0.2, 0.5]
    esperado = [0.03, 0.06, 0.06, 0.03, 0.24, 0.5]
    assert ajustar_bh(p) == pytest.approx(esperado)


def test_bh_exemplo_numerico_5_pvalores():
    # m=5: .001*5=.005 ; .008*5/2=.02 ; .039*5/3=.065 ; .041*5/4=.05125 ; .6
    # min acumulado de baixo p/ cima: .6, .05125, .05125, .02, .005
    p = [0.001, 0.008, 0.039, 0.041, 0.6]
    assert ajustar_bh(p) == pytest.approx([0.005, 0.02, 0.05125, 0.05125, 0.6])
    assert ajustar_bh([]) == []
    assert ajustar_bh([0.7]) == [0.7]
    assert ajustar_bh([0.4, 0.9]) == pytest.approx([0.8, 0.9])


def test_trava_usa_p_bh_da_familia_e_nao_o_bruto():
    # 5 sinais ativos com n=40 e excesso na direcao; p bruto .001 .008 .039 .041 .6
    # => p_bh .005 .02 .05125 .05125 .6 ; com q=0,05 passam so os dois primeiros
    # (os p brutos .039 e .041 passariam sozinhos: a familia os reprova).
    ps = [0.001, 0.008, 0.039, 0.041, 0.6]
    evs = [evidencia("BUY", 40, 0.02, 0.005, p) for p in ps]
    r = aplicar_fdr(evs)
    assert [x["status"] for x in r] == ["SUPORTADO", "SUPORTADO", "SEM_SUPORTE", "SEM_SUPORTE", "SEM_SUPORTE"]
    assert [x["p"] for x in r] == pytest.approx([0.005, 0.02, 0.05125, 0.05125, 0.6], abs=1e-6)
    assert all(x["m_familia"] == 5 for x in r)
    # sozinhos (familia de 1) os .039/.041 passariam => a correcao e o que os barra
    assert aplicar_fdr([evs[2]])[0]["status"] == "SUPORTADO"


def test_familia_conta_ativos_e_trata_p_ausente_como_1():
    evs = [
        evidencia("BUY", 40, 0.02, 0.005, 0.01),
        evidencia("NEUTRO", None, None, None, None),     # nao ativo: fora da familia
        evidencia("SELL", 3, -0.01, 0.0, None),          # ativo sem p: entra com p=1
    ]
    r = aplicar_fdr(evs)
    assert r[0]["m_familia"] == 2 and r[2]["m_familia"] == 2
    assert r[0]["p"] == pytest.approx(0.02)              # .01*2/1
    assert r[1]["status"] == "NAO_APLICA"
    assert r[2]["status"] == "SEM_SUPORTE"


def test_bh_em_nivel_de_rodada_no_decidir_universo(db_session):
    """MOCK11 (p .04) sozinho passa; na rodada com MOCK12 (p .06) o BH o reprova."""
    wf = {"sinal_hoje": {"sinal": "NEUTRO"}, "n_steps": 3, "summary": {}}

    def _st(p):
        return {"n_buy_thinned": 40, "p_value_buy": p, "avg_return_buy_independent": 0.02,
                "deriva": 0.0, "excess_buy": 0.02, "n_sell_thinned": 0, "p_value_sell": 1.0}

    with patch.object(rec, "walk_forward_roll", return_value=wf),             patch.object(rec, "_sinal_episodio_atual", return_value="NEUTRO"),             patch.object(rec, "ThresholdOptimizerV2") as MockOpt:
        MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "BUY"}
        sozinho = rec.decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1}, optimizer_stats=_st(0.04))
        rodada = rec.decidir_universo(
            db_session, ["MOCK11", "MOCK12"],
            optimizer_params_por_ticker={"MOCK11": {"x": 1}, "MOCK12": {"x": 1}},
            optimizer_stats_por_ticker={"MOCK11": _st(0.04), "MOCK12": _st(0.06)},
        )
    s1 = sozinho.suporte_sinais["otimizador"]
    assert s1["m_familia"] == 1 and s1["status"] == "SUPORTADO" and s1["p"] == pytest.approx(0.04)
    assert sozinho.n_concordam_buy == 1
    r11, r12 = (d.suporte_sinais["otimizador"] for d in rodada)
    assert r11["m_familia"] == r12["m_familia"] == 2
    # BH: ordenados .04 .06 => .04*2/1=.08 ; .06*2/2=.06 ; min acumulado: .06 e .06
    assert r11["p"] == pytest.approx(0.06) and r12["p"] == pytest.approx(0.06)
    assert r11["p_bruto"] == pytest.approx(0.04)
    assert r11["status"] == "SEM_SUPORTE" and r12["status"] == "SEM_SUPORTE"
    assert all(d.n_concordam_buy == 0 for d in rodada)
    assert [d.sinal_otimizador for d in rodada] == ["BUY", "BUY"]     # sinal continua gravado


# ============================================================================
# 3. Otimizador: p de holdout sem multiplicar pelo grid
# ============================================================================


def _df_otimizador(n=1500, seed=5):
    rng = np.random.default_rng(seed)
    pvp_pct = rng.uniform(0, 100, n)
    fwd = 0.004 + 0.01 * rng.standard_normal(n) + np.where(pvp_pct <= 15, 0.02, 0.0)
    return pd.DataFrame({
        "data": pd.bdate_range("2015-01-01", periods=n),
        "fechamento": 100.0, "fechamento_aj": 100.0, "pvp": 1.0,
        "pvp_pct": pvp_pct, "meses_alerta": 0, "fwd_ret": fwd,
        "volume_drop_flag": False,
    })


def test_p_holdout_do_otimizador_nao_e_multiplicado_pelo_grid(db_session):
    df = _df_otimizador()
    opt = ThresholdOptimizerV2()
    with patch.object(ThresholdOptimizerV2, "_get_enriched_daily_data", return_value=df), \
            patch("src.fii_analysis.models.threshold_optimizer_v2.get_cnpj_by_ticker", return_value="x"):
        res = opt.optimize("MOCK11", db_session)
    tr = res["test_result"]
    assert "p_value_buy_bonferroni" not in tr and "p_value_sell_bonferroni" not in tr
    assert res["n_combinations"] > 100                      # grid grande (256 combinacoes brutas)

    # recalculo independente do p de holdout: thinning guloso (gap >= 20) sobre o
    # split de teste, excesso sobre a media de TODOS os dias do split, t unicaudal
    splits = opt._make_splits(df)
    test = splits["test"].reset_index(drop=True)
    bp = res["best_params"]
    mask = (test["pvp_pct"] <= bp["pvp_percentil_buy"]).to_numpy()
    kept, last = [], -9999
    for i, ok in enumerate(mask):
        if ok and i - last >= 20:
            kept.append(test["fwd_ret"].iloc[i])
            last = i
    deriva = float(test["fwd_ret"].mean())
    esperado = excesso_vs_deriva(kept, deriva, "BUY", n_min=4)
    assert tr["n_buy_thinned"] == len(kept) == esperado["n"]
    assert tr["unconditional_mean"] == pytest.approx(deriva)
    assert tr["buy_excess_vs_market_independent"] == pytest.approx(esperado["excesso"])
    assert tr["p_value_buy"] == pytest.approx(esperado["p_value"])
    # p entregue ao recommender = p bruto do holdout (nao p * n_combinations)
    st = extrair_stats_otimizador(res)
    assert st["p_value_buy"] == pytest.approx(tr["p_value_buy"])
    assert st["deriva"] == pytest.approx(deriva)
    assert 0.0 < tr["p_value_buy"] < 1.0 / res["n_combinations"]  # o desenho antigo daria min(1, p*grid)


# ============================================================================
# 4. Percentis da decisao = percentis da metrica
# ============================================================================


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_percentis_da_decisao_iguais_aos_da_metrica(MockOpt, mock_wf, db_session):
    mock_wf.return_value = {"error": "x"}
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "NEUTRO"}
    d = rec.decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1})
    pvp_m, _ = get_pvp_percentil("MOCK11", d.data_referencia, 504, db_session)
    dy_m = get_dy_gap_percentil("MOCK11", d.data_referencia, 252, db_session)
    assert pvp_m is not None                                # 600 pregoes sinteticos
    assert d.pvp_percentil == pvp_m
    assert d.dy_gap_percentil == dy_m
    assert d.flag_pvp_caro == (pvp_m > 95)
    assert d.flag_dy_gap_baixo == (dy_m is not None and dy_m < 5)


@patch("src.fii_analysis.decision.recommender.walk_forward_roll")
@patch("src.fii_analysis.decision.recommender.ThresholdOptimizerV2")
def test_decisao_chama_metricas_com_as_janelas_do_snapshot(MockOpt, mock_wf, db_session):
    mock_wf.return_value = {"error": "x"}
    MockOpt.return_value.get_signal_hoje.return_value = {"sinal": "NEUTRO"}
    chamadas = {}

    def _dy(ticker, t, janela=None, session=None):
        chamadas["dy"] = janela
        return 3.0                                          # < 5 => flag

    def _pvp(ticker, t, janela=None, session=None):
        chamadas["pvp"] = janela
        return 97.0, 504                                    # > 95 => flag

    with patch.object(rec, "get_dy_gap_percentil", _dy), patch.object(rec, "get_pvp_percentil", _pvp):
        d = rec.decidir_ticker("MOCK11", db_session, optimizer_params={"x": 1})
    assert (d.pvp_percentil, d.dy_gap_percentil) == (97.0, 3.0)
    assert d.flag_pvp_caro and d.flag_dy_gap_baixo          # flags usam o numero exibido
    # guarda contra deriva: mesmas janelas que build_snapshot_ticker_metrics
    src = (Path(__file__).resolve().parents[1] / "src/fii_analysis/evaluation/daily_snapshots.py").read_text(encoding="utf-8")
    assert chamadas["pvp"] == int(re.search(r"get_pvp_percentil\(ticker, data_ref, (\d+), session\)", src).group(1))
    assert chamadas["dy"] == int(re.search(r"get_dy_gap_percentil\(ticker, data_ref, (\d+), session\)", src).group(1))


def test_percentil_interno_dos_episodios_ate_t_menos_1_e_igual_ao_da_metrica(db_session):
    df = get_pvp_series("MOCK11", db_session)
    ult = df.iloc[-1]
    pvp_m, _ = get_pvp_percentil("MOCK11", ult["data"].date(), 504, db_session)
    assert float(ult["pvp_pct"]) == pytest.approx(pvp_m)


def test_percentil_ate_t_menos_1_nao_inclui_o_dia_atual():
    # 63 valores anteriores 1..63 e depois um novo minimo: contra os ANTERIORES = 0
    # (com o dia atual na janela, o rank-pct seria 1/64 = 1,56%).
    v = list(range(1, 64)) + [0.5, 100.0, 30.5]
    out = pvp_percentil_ate_t_menos_1(pd.Series(v, dtype=float), 504, 63)
    assert out.iloc[:63].isna().all()
    assert out.iloc[63] == 0.0                              # novo minimo
    assert out.iloc[64] == 100.0                            # novo maximo
    # 30.5: janela = 1..63, 0.5, 100 (65 valores); estritamente abaixo: 30 + 1 (0.5) = 31
    assert out.iloc[65] == pytest.approx(31 / 65 * 100)
