"""Testes de data/ifix.py — sem rede e sem tocar no CSV real do projeto."""

from datetime import date

import pytest
from sqlalchemy import select

import src.fii_analysis.data.ifix as ifix_mod
from src.fii_analysis.data.database import Universo


@pytest.fixture
def csv_tmp(tmp_path, monkeypatch):
    """Redireciona o CSV de fallback para um arquivo temporário."""
    csv_path = tmp_path / "ifix_composicao.csv"
    monkeypatch.setattr(ifix_mod, "IFIX_CSV_PATH", csv_path)
    return csv_path


def _bloquear_statusinvest(monkeypatch):
    """Qualquer chamada inesperada de rede falha o teste."""
    def _fail(*args, **kwargs):
        raise AssertionError("Teste não deve acessar a rede")
    return _fail


def test_ifix_composition_fallback_csv(db_session, csv_tmp, monkeypatch):
    """Com a B3 fora do ar, a composição vem do CSV e popula a tabela universo."""
    csv_tmp.write_text(
        "ticker,cnpj,peso_ifix\n"
        "MOCK11,11.111.111/0001-11,1.5\n"
        "MOCK13,33.333.333/0001-33,0.8\n",
        encoding="utf-8",
    )

    def fake_get(*args, **kwargs):
        raise ConnectionError("B3 indisponível (simulado)")

    monkeypatch.setattr(ifix_mod.requests, "get", fake_get)

    results = ifix_mod.get_ifix_composition(db_session)

    assert len(results) == 2
    tickers = {r["ticker"] for r in results}
    assert tickers == {"MOCK11", "MOCK13"}
    for item in results:
        assert item["cnpj"]
        assert item["peso_ifix"] >= 0

    rows = db_session.execute(select(Universo)).scalars().all()
    assert len(rows) == 2
    assert all(r.em_ifix for r in rows)
    assert all(r.data_referencia == date.today() for r in rows)
    assert all(r.fonte == "csv_fallback" for r in rows)


def test_ifix_composition_b3_api(db_session, csv_tmp, monkeypatch):
    """Resposta simulada da B3 + CNPJ resolvido pelo CSV; self-healing preserva mapeamentos."""
    csv_tmp.write_text(
        "ticker,cnpj,peso_ifix\n"
        "MOCK11,11.111.111/0001-11,1.5\n"
        "ANTIGO11,99.999.999/0001-99,0.2\n",
        encoding="utf-8",
    )

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"cod": "MOCK11", "part": "2,031"}]}

    def fake_get(url, *args, **kwargs):
        if "b3.com.br" in url:
            return FakeResponse()
        raise AssertionError(f"Chamada de rede inesperada: {url}")

    monkeypatch.setattr(ifix_mod.requests, "get", fake_get)

    results = ifix_mod.get_ifix_composition(db_session)

    assert len(results) == 1
    assert results[0]["ticker"] == "MOCK11"
    assert results[0]["peso_ifix"] == pytest.approx(2.031)

    row = db_session.execute(
        select(Universo).where(Universo.ticker == "MOCK11")
    ).scalar_one()
    assert row.fonte == "b3_api"

    # Self-healing: ANTIGO11 (não veio no pull) permanece no CSV como mapeamento
    conteudo = csv_tmp.read_text(encoding="utf-8")
    assert "ANTIGO11" in conteudo
    assert "MOCK11" in conteudo


def test_ifix_sem_fonte_alguma(db_session, csv_tmp, monkeypatch):
    """Sem B3 e sem CSV: retorna lista vazia sem explodir."""
    def fake_get(*args, **kwargs):
        raise ConnectionError("B3 indisponível (simulado)")

    monkeypatch.setattr(ifix_mod.requests, "get", fake_get)

    results = ifix_mod.get_ifix_composition(db_session)
    assert results == []
