"""Regressao dos itens de backend (estudo em painel 2026-11-12 + QA de execucao).

Cada teste tem resultado calculado a mao (comentado). Ver relatorio para a lista de decisoes.
"""

import dataclasses
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, func, select, text

from src.fii_analysis.data.database import (
    Carteira, DecisaoLog, Dividendo, PrecoDiario, SnapshotDecisions, SnapshotRun,
)

_AGORA = datetime.now(timezone.utc)


def _dec(**kw):
    from src.fii_analysis.decision.recommender import _decisao_indisponivel
    base = _decisao_indisponivel("MOCK11", "x", date(2025, 1, 1))
    return dataclasses.replace(base, preco_referencia=100.0, **kw)


# ---------------------------------------------------------------- B1: janela 0 do percentil
def test_pvp_percentil_janela_zero_nao_levanta_e_e_nan():
    from src.fii_analysis.models.episodes import pvp_percentil_ate_t_menos_1
    out = pvp_percentil_ate_t_menos_1(pd.Series([1.0, 2.0, 3.0, 4.0]), 0, 0)
    assert out.isna().all()  # semantica anterior (rolling(0) -> NaN); antes: ValueError em w.max()
    # janela 2, minimo 2: so o 3o valor tem 2 anteriores; 3 >= max([1,2]) => 100
    out2 = pvp_percentil_ate_t_menos_1(pd.Series([1.0, 2.0, 3.0]), 2, 2)
    assert out2.iloc[:2].isna().all() and out2.iloc[2] == 100.0


def test_get_pvp_series_rolling_window_zero_funciona(db_session):
    from src.fii_analysis.models.episodes import get_pvp_series
    df = get_pvp_series("MOCK11", db_session, rolling_window=0)
    assert not df.empty and df["pvp"].notna().all() and df["pvp_pct"].isna().all()


def _cdi_df(n=150):
    x = np.linspace(0.05, 0.15, n)
    return pd.DataFrame({"data": pd.date_range("2020-01-05", periods=n, freq="7D").date,
                         "pvp": 1.0 - 2.0 * x + 0.01 * np.sin(np.arange(n)), "cdi_12m": x})


def test_cdi_sensitivity_ok_e_erro_de_codigo_distinto_de_nao_convergiu(db_session, monkeypatch):
    import src.fii_analysis.models.cdi_sensitivity as cs
    monkeypatch.setattr(cs, "_build_weekly_series", lambda *a, **k: _cdi_df())
    r = cs.compute_cdi_sensitivity("MOCK11", db_session)
    assert r.status == "OK" and r.beta == pytest.approx(-2.0, abs=0.1)   # pvp = 1 - 2*cdi (+ ruido)

    # erro de codigo (coluna ausente -> KeyError): ERRO_CODIGO, nao CONVERGENCIA_FALHOU
    monkeypatch.setattr(cs, "_build_weekly_series", lambda *a, **k: _cdi_df().drop(columns=["cdi_12m"]))
    assert cs.compute_cdi_sensitivity("MOCK11", db_session).status == "ERRO_CODIGO"

    # nao convergiu de fato (LinAlgError): CONVERGENCIA_FALHOU
    def _boom(*a, **k):
        raise np.linalg.LinAlgError("singular")
    import statsmodels.regression.linear_model as lm
    monkeypatch.setattr(cs, "_build_weekly_series", lambda *a, **k: _cdi_df())
    monkeypatch.setattr(lm.OLS, "fit", _boom)
    assert cs.compute_cdi_sensitivity("MOCK11", db_session).status == "CONVERGENCIA_FALHOU"


# ---------------------------------------------------------------- B3: numpy -> BLOB
def test_serialize_decisao_normaliza_numpy_e_persiste_integer(db_session):
    from src.fii_analysis.evaluation.daily_snapshots import serialize_ticker_decision
    d = _dec(pregoes_desde_ultimo_episodio=np.int64(7), episodio_eh_novo=np.bool_(True),
             pvp_atual=np.float32(0.5), pvp_percentil=float("nan"))
    row = serialize_ticker_decision(d, 1)
    assert type(row["pregoes_desde_ultimo_episodio"]) is int and row["pregoes_desde_ultimo_episodio"] == 7
    assert type(row["episodio_eh_novo"]) is bool
    assert type(row["pvp_atual"]) is float
    assert row["pvp_percentil"] is None   # NaN nao vai para o banco
    db_session.add(SnapshotRun(id=1, status="ready", universe_scope="curado", data_referencia=date(2025, 1, 1),
                               criado_em=_AGORA))
    db_session.add(SnapshotDecisions(**row))
    db_session.commit()
    tipo = db_session.execute(text("select typeof(pregoes_desde_ultimo_episodio) from snapshot_decisions")).scalar()
    assert tipo == "integer"


def test_migracao_blob_little_endian_para_integer():
    from src.fii_analysis.data.migrations import corrigir_pregoes_blob
    eng = create_engine("sqlite://")
    with eng.connect() as c:
        c.execute(text("create table snapshot_decisions (id integer primary key, pregoes_desde_ultimo_episodio)"))
        c.execute(text("insert into snapshot_decisions values (1, :b), (2, :b2), (3, NULL), (4, 5)"),
                  {"b": (1).to_bytes(8, "little"), "b2": (32).to_bytes(8, "little")})
        assert corrigir_pregoes_blob(c) == 2          # so os 2 BLOBs
        assert corrigir_pregoes_blob(c) == 0          # idempotente
        rows = c.execute(text("select id, pregoes_desde_ultimo_episodio, typeof(pregoes_desde_ultimo_episodio) "
                              "from snapshot_decisions order by id")).all()
    assert rows == [(1, 1, "integer"), (2, 32, "integer"), (3, None, "null"), (4, 5, "integer")]


# ---------------------------------------------------------------- B11: carteira a mercado
def test_posicoes_carteira_valor_de_mercado_e_herfindahl(db_session):
    from src.fii_analysis.features.portfolio import herfindahl, posicoes_carteira
    px = {t: float(db_session.execute(select(PrecoDiario.fechamento).where(PrecoDiario.ticker == t)
                                      .order_by(PrecoDiario.data.desc()).limit(1)).scalar_one())
          for t in ("MOCK11", "MOCK12")}
    hoje = date(2025, 1, 2)
    db_session.add_all([
        Carteira(ticker="MOCK11", quantidade=10, preco_medio=1.0, data_compra=hoje),
        Carteira(ticker="MOCK11", quantidade=5, preco_medio=1.0, data_compra=hoje),   # mesma acao: soma 15
        Carteira(ticker="MOCK12", quantidade=20, preco_medio=1.0, data_compra=hoje),
    ])
    db_session.commit()
    df = posicoes_carteira(db_session).set_index("ticker")
    assert df.loc["MOCK11", "quantidade"] == 15 and df.loc["MOCK12", "quantidade"] == 20
    v1, v2 = 15 * px["MOCK11"], 20 * px["MOCK12"]
    assert df.loc["MOCK11", "valor_mercado"] == pytest.approx(v1)
    assert df.loc["MOCK12", "valor_mercado"] == pytest.approx(v2)
    hh = herfindahl(df["valor_mercado"].tolist())
    p1, p2 = v1 / (v1 + v2), v2 / (v1 + v2)
    assert hh["hh"] == pytest.approx(p1 ** 2 + p2 ** 2) and hh["maior_peso"] == pytest.approx(max(p1, p2))


def test_resumo_defasagem_usa_maioria_e_nao_o_minimo():
    from src.fii_analysis.evaluation.panorama import resumo_defasagem
    u = {"A11": date(2026, 11, 12), "B11": date(2026, 11, 12), "C11": date(2026, 11, 12),
         "D11": date(2026, 11, 11), "HSRE11": date(2026, 6, 11)}
    maioria, defas = resumo_defasagem(u)
    assert maioria == date(2026, 11, 12)                      # 3 de 5; MIN seria 2026-06-11
    assert defas == {"D11": date(2026, 11, 11), "HSRE11": date(2026, 6, 11)}


# ---------------------------------------------------------------- B10: p None
def test_otimizador_p_none_quando_n_abaixo_do_minimo_e_suporte_trata_como_sem_suporte():
    from src.fii_analysis.decision.suporte import SEM_SUPORTE, aplicar_fdr, evidencia_otimizador, extrair_stats_otimizador
    from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2
    opt = ThresholdOptimizerV2()
    rng = np.random.default_rng(1)

    def base(n):
        return pd.DataFrame({"pvp_pct": [5.0] * n, "meses_alerta": [0] * n,
                             "fwd_ret": rng.normal(0.01, 0.02, n), "volume_drop_flag": [False] * n})

    params = {"pvp_percentil_buy": 10, "pvp_percentil_sell": 90, "meses_alerta_sell": 99, "dy_gap_pct_sell": 0}
    # 30 linhas, gap 20 => thinned = linhas 0 e 20 => n=2 < 4: nao calculavel
    r_pequeno = opt._evaluate(base(30), params)
    assert r_pequeno["n_buy_thinned"] == 2 and r_pequeno["p_value_buy"] is None
    assert r_pequeno["p_value_sell"] is None                 # sem eventos SELL
    # 100 linhas => thinned 0,20,40,60,80 => n=5 >= 4: p real em [0,1]
    r_grande = opt._evaluate(base(100), params)
    assert r_grande["n_buy_thinned"] == 5 and 0.0 <= r_grande["p_value_buy"] <= 1.0

    stats = extrair_stats_otimizador({"test_result": r_pequeno, "n_combinations": 1})
    ev = evidencia_otimizador("BUY", stats)
    assert ev["p_bruto"] is None
    forte = {"sinal": "BUY", "n": 40, "media": 0.02, "deriva": 0.0, "excesso": 0.02, "p_bruto": 0.001}
    julg = aplicar_fdr([ev, forte])
    assert julg[0]["status"] == SEM_SUPORTE and "indisponivel" in julg[0]["motivo"]
    # BH: p ausente entra como 1 na familia (m=2): p_bh do forte = 0.001*2/1 = 0.002 -> segue suportado
    assert julg[1]["status"] == "SUPORTADO" and julg[1]["p"] == pytest.approx(0.002) and julg[1]["m_familia"] == 2


def test_otimizador_expoe_deriva_e_excesso():
    from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2
    opt = ThresholdOptimizerV2()
    serie = np.linspace(-0.02, 0.04, 100)
    df = pd.DataFrame({"pvp_pct": [5.0] * 100, "meses_alerta": [0] * 100,
                       "fwd_ret": serie, "volume_drop_flag": [False] * 100})
    r = opt._evaluate(df, {"pvp_percentil_buy": 10, "pvp_percentil_sell": 90,
                           "meses_alerta_sell": 99, "dy_gap_pct_sell": 0})
    deriva = float(np.mean(serie))
    assert r["unconditional_mean"] == pytest.approx(deriva)
    # thinned = indices 0,20,40,60,80
    media_ind = float(np.mean(serie[[0, 20, 40, 60, 80]]))
    assert r["buy_excess_vs_market_independent"] == pytest.approx(media_ind - deriva)


# ---------------------------------------------------------------- B14: datas-com
def _divs(session, ticker, datas):
    for d in datas:
        session.add(Dividendo(ticker=ticker, data_com=d, valor_cota=1.0, fonte="teste"))
    session.commit()


def test_data_com_estimada_em_dia_util_e_nunca_no_passado(db_session):
    from src.fii_analysis.decision.abertos import detectar_janela_captura
    # intervalo mediano 29 dias; ultima 2025-05-31 + 29 = 2025-06-29 (DOMINGO) -> recua p/ sexta 2025-06-27
    _divs(db_session, "EST11", [date(2025, 4, 3), date(2025, 5, 2), date(2025, 5, 31)])
    r = detectar_janela_captura("EST11", db_session, hoje=date(2025, 6, 10))
    assert (date(2025, 6, 29).weekday(), r["proxima_data_com_estimada"]) == (6, date(2025, 6, 27))
    assert r["proxima_data_com_estimada"].weekday() < 5
    # estimativa (27/06) ja passou em 10/07: None, nunca uma data anterior a referencia
    r2 = detectar_janela_captura("EST11", db_session, hoje=date(2025, 7, 10))
    assert r2["proxima_data_com_estimada"] is None and r2["dias_corridos_ate"] is None and r2["aberta"] is False


def test_diff_so_lista_o_que_mudou_e_alinha_datas_com_a_watchlist(db_session):
    from src.fii_analysis.evaluation.daily_diff import DailyDiff, calcular_diff_diario, render_diff_markdown
    # render: badge igual nao aparece
    dd = DailyDiff(data_atual=date(2024, 1, 3), data_anterior=date(2024, 1, 2),
                   mudacoes_acao=[{"ticker": "AAA11", "acao_ant": "AGUARDAR", "acao_nv": "COMPRAR",
                                   "badge_ant": "HOLD", "badge_nv": "HOLD"}])
    md = render_diff_markdown(dd)
    assert "Ação: `AGUARDAR` ➔ `COMPRAR`" in md and "Badge:" not in md

    # fonte unica: estimativa de snapshot_decisions (a da watchlist) aparece nas proximas datas-com
    for rid, d in ((1, date(2024, 1, 2)), (2, date(2024, 1, 3))):
        db_session.add(SnapshotRun(id=rid, status="ready", universe_scope="curado", data_referencia=d,
                                   criado_em=_AGORA, finalizado_em=_AGORA))
    db_session.add(SnapshotDecisions(run_id=1, ticker="MOCK11", acao="AGUARDAR"))
    db_session.add(SnapshotDecisions(run_id=2, ticker="MOCK11", acao="AGUARDAR",
                                     proxima_data_com_estimada=date(2024, 1, 5)))   # sexta, 2 pregoes a frente
    db_session.add(SnapshotDecisions(run_id=2, ticker="MOCK12", acao="AGUARDAR",
                                     proxima_data_com_estimada=date(2024, 2, 5)))   # fora dos 5 pregoes
    db_session.commit()
    diff = calcular_diff_diario(db_session, run_id_atual=2, run_id_anterior=1)
    assert [(x["ticker"], x["data_com"], x["estimada"]) for x in diff.proximas_datas_com] == \
        [("MOCK11", date(2024, 1, 5), True)]
    assert "ESTIMADA" in render_diff_markdown(diff) and "Nenhuma data-com" not in render_diff_markdown(diff)


# ---------------------------------------------------------------- validacao de posicao + journal
def test_validar_posicao():
    from src.fii_analysis.decision.carteira_validacao import validar_posicao
    ok = {"MOCK11", "XPML11"}
    assert validar_posicao("xpml11", 10, 99.5, ok) == []
    assert validar_posicao("XPML11", 10.0, 1, ok) == []                    # float integral vale
    assert validar_posicao("XPML11", np.int64(3), 1, ok) == []
    assert len(validar_posicao("ZZZZ11", 10, 1, ok)) == 1                  # ticker inexistente
    assert len(validar_posicao("XPML11", 0, 1, ok)) == 1                   # qtd 0
    assert len(validar_posicao("XPML11", -5, 1, ok)) == 1
    assert len(validar_posicao("XPML11", 2.5, 1, ok)) == 1                 # nao inteira
    assert len(validar_posicao("XPML11", True, 1, ok)) == 1                # bool nao e quantidade
    assert len(validar_posicao("XPML11", 10, 0, ok)) == 1                  # preco 0
    assert len(validar_posicao("XPML11", 10, float("nan"), ok)) == 1
    assert len(validar_posicao("XPML11", 10, "abc", ok)) == 1
    assert len(validar_posicao("", 0, -1, ok)) == 3                        # ticker, qtd e preco: 3 erros


def test_registrar_decisao_recusa_ticker_inexistente_e_duplicata(db_session):
    from src.fii_analysis.decision.decision_journal import registrar_decisao
    d0 = date(2024, 6, 1)
    dec, av = registrar_decisao(db_session, "ROTACAO", "ZZZZ11", "MOCK11", 1, 1.0, 7, "x", d0)
    assert dec is None and len(av) == 1 and "ZZZZ11" in av[0]
    assert db_session.execute(select(func.count()).select_from(DecisaoLog)).scalar_one() == 0

    dec, av = registrar_decisao(db_session, "ROTACAO", "MOCK12", "MOCK11", 1, 1.0, 7, "x", d0)
    assert dec is not None and av == []
    dec2, av2 = registrar_decisao(db_session, "ROTACAO", "MOCK12", "MOCK11", 1, 1.0, 7, "x", d0)  # mesmo dia
    assert dec2 is None and len(av2) == 1 and "duplicata" in av2[0]
    dec3, av3 = registrar_decisao(db_session, "ROTACAO", "MOCK12", "MOCK11", 1, 1.0, 7, "x", d0 + timedelta(days=1))
    assert dec3 is not None and av3 == []                                  # outro dia: ok
    assert db_session.execute(select(func.count()).select_from(DecisaoLog)).scalar_one() == 2


# ---------------------------------------------------------------- advisor: so fato, nunca previsao
def test_flag_destruicao_vira_alerta_hold_nunca_sair_nem_evitar():
    from src.fii_analysis.decision.portfolio_advisor import aconselhar_carteira
    motivo = "[ALERTA] VP/cota em queda (-0.59% ao mes). 3 meses consecutivos de queda do VP/cota."
    holdings = [{"ticker": "MOCK11", "quantidade": 100, "preco_medio": 90.0},   # ~99% da carteira
                {"ticker": "A11", "quantidade": 1, "preco_medio": 90.0}]
    precos = {"MOCK11": 100.0, "A11": 100.0}
    for acao, nivel in (("AGUARDAR", "BAIXA"), ("EVITAR", "VETADA")):        # EVITAR = snapshot legado
        adv = aconselhar_carteira([_dec(flag_destruicao_capital=True, motivo_destruicao=motivo,
                                        acao=acao, nivel_concordancia=nivel)],
                                  holdings, precos_atuais=precos)
        a = next(x for x in adv if x.ticker == "MOCK11")
        assert a.badge == "HOLD" and a.badge not in ("SAIR", "EVITAR_NOVOS_APORTES")
        assert "ALERTA DE RISCO (descritivo)" in a.racional and "-0.59% ao mes" in a.racional
        assert "[ALERTA]" in a.racional and "Sem evidencia" in a.racional
        assert "destr.capital" in a.flags_resumo and a.prioridade == "MEDIA"
    # sinal COM suporte continua funcionando (nao e flag): VENDER -> REDUZIR, alerta anexado
    adv = aconselhar_carteira([_dec(acao="VENDER", nivel_concordancia="ALTA", flag_destruicao_capital=True,
                                    motivo_destruicao=motivo)], holdings, precos_atuais=precos)
    a = next(x for x in adv if x.ticker == "MOCK11")
    assert a.badge == "REDUZIR" and "ALERTA DE RISCO" in a.racional


# ---------------------------------------------------------------- radar
def test_radar_dy_gap_alto_fora_de_vistos(db_session, monkeypatch):
    import src.fii_analysis.features.radar as radar
    assert radar.RADAR_N_CRITERIOS == 3
    monkeypatch.setattr(radar, "get_pvp_percentil", lambda *a, **k: (50.0, 252))     # pvp_baixo False
    monkeypatch.setattr(radar, "get_dy_gap_percentil", lambda *a, **k: 95.0)         # dy_gap_alto True
    monkeypatch.setattr(radar, "flag_destruicao_capital", lambda *a, **k: {"destruicao": False, "motivo": "ok"})
    monkeypatch.setattr(radar, "volume_medio_21d", lambda *a, **k: 1e9)
    row = radar.radar_matriz(["MOCK11"], db_session).iloc[0]
    assert (row.pvp_baixo, row.dy_gap_alto, row.saude_ok, row.liquidez_ok) == (False, True, True, True)
    assert row.vistos == 2                      # so saude_ok + liquidez_ok; dy_gap_alto e gravado mas nao conta


# ---------------------------------------------------------------- evidencia
def test_evidencia_linha_estavel_e_restauravel():
    from src.fii_analysis.decision.evidencia import EVIDENCIA, linha_evidencia, restaurar_evidencia
    from src.fii_analysis.decision.suporte import rationale_legivel
    linha = linha_evidencia()
    assert linha.startswith("EVIDENCIA_JSON ") and linha == linha_evidencia()
    assert restaurar_evidencia(["x", linha]) == EVIDENCIA
    assert restaurar_evidencia(["x"]) is None
    assert EVIDENCIA["sobreviventes"] == 0 and EVIDENCIA["n_testes"] == 100 and EVIDENCIA["data"] == "2026-11-12"
    assert rationale_legivel(["a", linha]) == ["a"]


# ---------------------------------------------------------------- janela do retorno total
def test_primeiro_mes_com_cobertura_exige_sequencia_final_e_ignora_ultimo_mes():
    from src.fii_analysis.data.corporate_actions import primeiro_mes_com_cobertura
    precos = {"2017-10": 2, "2022-02": 69, "2022-03": 70, "2022-04": 70, "2022-05": 70, "2022-06": 70}
    divs = {"2017-10": 1, "2022-02": 9, "2022-03": 43, "2022-04": 69, "2022-05": 67, "2022-06": 3}
    # 2017-10: 1/2=50% (isolado, seria falso positivo); 02: 13%; 03: 61%; 04: 99%; 05: 96%;
    # 06 e o ultimo mes (incompleto, 4%) e e ignorado => sequencia final = 03..05 => 2022-03
    assert primeiro_mes_com_cobertura(precos, divs) == "2022-03"
    assert primeiro_mes_com_cobertura({"2022-01": 10}, {}) is None


def test_get_inicio_retorno_total_do_dado(db_session):
    from src.fii_analysis.data.corporate_actions import get_inicio_retorno_total
    db_session.execute(text("delete from dividendos"))
    db_session.execute(text("delete from precos_diarios"))
    for t in ("A11", "B11"):
        db_session.add_all([
            PrecoDiario(ticker=t, data=date(2022, m, 15), abertura=1, maxima=1, minima=1, fechamento=1,
                        fechamento_aj=1, volume=1, fonte="t", coletado_em=_AGORA) for m in (1, 2, 3, 4, 5)
        ])
    for m in (1, 2, 3, 4, 5):
        db_session.add(Dividendo(ticker="A11", data_com=date(2022, m, 10), valor_cota=1, fonte="t"))
    for m in (4, 5):
        db_session.add(Dividendo(ticker="B11", data_com=date(2022, m, 10), valor_cota=1, fonte="t"))
    db_session.commit()
    # meses 01..04 (maio e o ultimo, ignorado): 01-03 = 1/2 = 50% (>= 0,5), 04 = 2/2 => sequencia desde 2022-01
    assert get_inicio_retorno_total(db_session) == date(2022, 1, 1)


def test_identify_episodes_ignora_retorno_pre_inicio_retorno_total():
    from src.fii_analysis.models.episodes import identify_episodes
    n = 100
    df = pd.DataFrame({
        "data": pd.bdate_range("2023-01-02", periods=n), "fechamento": 100.0,
        "fechamento_aj": 100.0 * 1.001 ** np.arange(n), "x": 1.0, "pct": 5.0,   # BUY todo dia
    })
    kw = dict(pvp_pct_low=10, pvp_pct_high=90, forward_days=5, value_col="x", pct_col="pct")
    sem = identify_episodes(df, **kw)
    # fwd_ret definido para i <= 94; thinning gap 5 => 0,5,...,90 => 19 episodios
    assert sem["summary"]["buy"]["n"] == 19
    df2 = df.assign(ret_total_ok=np.arange(n) >= 50)       # retorno total so valido de i=50 em diante
    com = identify_episodes(df2, **kw)
    assert com["summary"]["buy"]["n"] == 9                  # 50,55,...,90
    assert com["params"]["n_dias_fora_janela_retorno_total"] == 50   # dias 0..49 tinham fwd_ret definido e foram zerados
    assert "INICIO_RETORNO_TOTAL" in com["params"]["aviso_janela"]
    assert min(com["buy"]["data"]) == df["data"].iloc[50]
