from __future__ import annotations

from datetime import date
from typing import Optional
from sqlalchemy import select

from src.fii_analysis.data.database import LlmJournal


def registrar_resposta_llm(
    session,
    template: str,
    prompt_version: str,
    ticker: str,
    snapshot_run_id: Optional[int],
    resposta_md: str,
    modelo: Optional[str] = None,
    latencia_ms: Optional[int] = None
) -> LlmJournal:
    """Registra uma interação bem-sucedida do LLM no banco de dados."""
    entry = LlmJournal(
        data=date.today(),
        template=template,
        prompt_version=prompt_version,
        modelo=modelo,
        ticker=ticker,
        snapshot_run_id=snapshot_run_id,
        resposta_md=resposta_md,
        latencia_ms=latencia_ms
    )
    session.add(entry)
    session.flush()
    return entry


def buscar_historico_llm(
    session,
    template: str,
    ticker: str
) -> Optional[LlmJournal]:
    """Recupera a análise mais recente gravada para um dado ticker e template."""
    return session.execute(
        select(LlmJournal)
        .where(LlmJournal.template == template, LlmJournal.ticker == ticker)
        .order_by(LlmJournal.data.desc(), LlmJournal.id.desc())
        .limit(1)
    ).scalar_one_or_none()
