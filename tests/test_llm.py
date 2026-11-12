import os
import pytest
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock
import requests

from src.fii_analysis.data.database import SnapshotRun, SnapshotTickerMetrics, SnapshotDecisions, LlmJournal
from src.fii_analysis.llm.context_builder import build_ticker_context, build_opportunity_context
from src.fii_analysis.llm.prompts import render_prompt, PROMPTS
from src.fii_analysis.llm.gateway import ask_llm, export_prompt_pack
from src.fii_analysis.llm.journal import registrar_resposta_llm, buscar_historico_llm


def _setup_snapshot_data(session):
    """Insere snapshot sintético no banco de testes."""
    run = SnapshotRun(
        data_referencia=date(2026, 6, 11),
        criado_em=datetime.now(timezone.utc),
        status="ready",
        universe_scope="curado"
    )
    session.add(run)
    session.commit()

    m1 = SnapshotTickerMetrics(
        run_id=run.id,
        ticker="MOCK11",
        preco=100.0,
        vp=100.0,
        pvp=1.0,
        pvp_percentil=90.0,
        dy_12m=0.10,
        dy_gap=0.01,
        dy_gap_percentil=60.0,
        volume_21d=1000000.0,
        score_total=80,
        score_valuation=70,
        score_risco=80,
        score_liquidez=90,
        score_historico=75
    )

    d1 = SnapshotDecisions(
        run_id=run.id,
        ticker="MOCK11",
        acao="COMPRAR",
        nivel_concordancia="ALTA",
        sinal_otimizador="BUY",
        sinal_episodio="BUY",
        sinal_walkforward="BUY",
        rationale_json='["Excelente valuation", "Saude forte"]',
        flag_destruicao_capital=False,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False
    )

    session.add_all([m1, d1])
    session.commit()
    return run.id


def test_build_ticker_context(db_session):
    _setup_snapshot_data(db_session)
    ctx = build_ticker_context("MOCK11", db_session)

    assert ctx["ticker"] == "MOCK11"
    assert ctx["score_total"] == 80
    assert ctx["indicadores"]["pvp_percentil"] == 90.0
    assert ctx["decisao"]["acao"] == "COMPRAR"
    assert "Excelente valuation" in ctx["decisao"]["rationale"]


def test_build_opportunity_context(db_session):
    _setup_snapshot_data(db_session)
    # Mock de MOCK13
    m3 = SnapshotTickerMetrics(
        run_id=1,
        ticker="MOCK13",
        preco=80.0,
        vp=100.0,
        pvp=0.8,
        pvp_percentil=20.0,
        dy_12m=0.12,
        dy_gap=0.03,
        dy_gap_percentil=80.0,
        volume_21d=800000.0,
        score_total=90,
        score_valuation=90,
        score_risco=85,
        score_liquidez=85,
        score_historico=80
    )
    db_session.add(m3)
    db_session.commit()

    ctx = build_opportunity_context("MOCK11", "MOCK13", db_session)
    assert ctx["vender_ticker"] == "MOCK11"
    assert ctx["comprar_ticker"] == "MOCK13"
    assert ctx["spread_pvp_percentil"] == 70.0  # 90.0 - 20.0
    assert ctx["spread_dy_gap_percentil"] == 20.0  # 80.0 - 60.0
    assert ctx["delta_score"] == 10  # 90 - 80


def test_render_prompt():
    ctx = {
        "ticker": "MOCK11",
        "data_contexto": "2026-06-11",
        "score_total": 80,
        "score_breakdown": {"valuation": 70, "risco": 80, "liquidez": 90, "historico": 75},
        "indicadores": {"pvp_percentil": 90.0},
        "decisao": {"acao": "COMPRAR", "nivel_concordancia": "ALTA"},
        "flags_risco": {},
        "historico_52w": {},
        "saude_financeira_6m": []
    }

    sys_p, user_p, ver = render_prompt("analise_ticker", ctx, "Pergunta teste")
    assert "MOCK11" in user_p
    assert "Pergunta teste" in user_p
    assert ver == PROMPTS["analise_ticker"]["version"]


@patch.dict(os.environ, {"N8N_FII_WEBHOOK_URL": "http://localhost/webhook", "N8N_FII_TOKEN": "secret"})
@patch("requests.post")
def test_ask_llm_success(mock_post):
    # Mock da resposta de sucesso (formato JSON)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "resposta_md": "Analise qualitativa Mock",
        "modelo": "gpt-4o"
    }
    mock_post.return_value = mock_resp

    context = {"ticker": "MOCK11", "data_contexto": "2026-06-11"}
    res = ask_llm("analise_ticker", context)

    assert res.status == "OK"
    assert res.resposta_md == "Analise qualitativa Mock"
    assert res.modelo == "gpt-4o"
    assert res.prompt_pack_path is None


@patch.dict(os.environ, {"N8N_FII_WEBHOOK_URL": "http://localhost/webhook"})
@patch("requests.post")
def test_ask_llm_timeout_fallback(mock_post):
    # Simula timeout de rede
    mock_post.side_effect = requests.Timeout("Timeout error")

    context = {"ticker": "MOCK11", "data_contexto": "2026-06-11"}
    res = ask_llm("analise_ticker", context)

    assert res.status == "TIMEOUT"
    assert res.prompt_pack_path is not None
    assert os.path.exists(res.prompt_pack_path)

    # Limpar arquivo
    if os.path.exists(res.prompt_pack_path):
        os.remove(res.prompt_pack_path)


@patch.dict(os.environ, {}, clear=True)
def test_ask_llm_no_config_fallback():
    # Sem variáveis de ambiente
    context = {"ticker": "MOCK11", "data_contexto": "2026-06-11"}
    res = ask_llm("analise_ticker", context)

    assert res.status == "SEM_CONFIG"
    assert res.prompt_pack_path is not None
    assert os.path.exists(res.prompt_pack_path)

    if os.path.exists(res.prompt_pack_path):
        os.remove(res.prompt_pack_path)


def test_llm_journal_operations(db_session):
    # Registrar resposta
    entry = registrar_resposta_llm(
        session=db_session,
        template="analise_ticker",
        prompt_version="1.0",
        ticker="MOCK11",
        snapshot_run_id=1,
        resposta_md="Conteudo MD",
        modelo="gpt-4o",
        latencia_ms=1500
    )
    db_session.commit()

    assert entry.id is not None

    # Buscar do histórico
    hist = buscar_historico_llm(db_session, "analise_ticker", "MOCK11")
    assert hist is not None
    assert hist.resposta_md == "Conteudo MD"
    assert hist.modelo == "gpt-4o"
