"""Elegibilidade de COMPRA: fundo encerrado/em liquidacao e preco desatualizado.

Duas condicoes impedem qualquer recomendacao de compra (acao COMPRAR, badge
AUMENTAR, candidato de rotacao). A posicao ja existente continua aparecendo
normalmente — o bloqueio e so do lado COMPRAR.

    1. Evento de liquidacao/encerramento vigente na data de referencia
       (tabela eventos_corporativos, ``data <= data_ref``).
    2. Ultimo preco do ticker com atraso > N pregoes em relacao a data de
       referencia (config.yaml: decisao.preco_defasado_dias_uteis, default 5).
       Atraso = numero de pregoes do mercado (datas distintas em precos_diarios)
       apos o ultimo preco do ticker, ate a data de referencia.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, select

from src.fii_analysis.config_yaml import get_decisao_param
from src.fii_analysis.data.database import EventoCorporativo, PrecoDiario

# Substrings (minusculas, sem acento) do campo eventos_corporativos.tipo
_TIPOS_ENCERRAMENTO = ("liquid", "encerr")


def limite_dias_preco_defasado() -> int:
    return int(get_decisao_param("preco_defasado_dias_uteis", 5))


def data_referencia_mercado(session) -> Optional[date]:
    """Ultima data com preco no banco (referencia de mercado)."""
    return session.execute(select(func.max(PrecoDiario.data))).scalar_one_or_none()


def evento_encerramento_vigente(ticker: str, data_ref: date, session) -> Optional[tuple[date, str]]:
    """(data, tipo) do evento de liquidacao/encerramento mais antigo com data <= data_ref."""
    rows = session.execute(
        select(EventoCorporativo.data, EventoCorporativo.tipo)
        .where(EventoCorporativo.ticker == ticker, EventoCorporativo.data <= data_ref)
        .order_by(EventoCorporativo.data.asc())
    ).all()
    for data_evt, tipo in rows:
        if any(k in (tipo or "").lower() for k in _TIPOS_ENCERRAMENTO):
            return data_evt, tipo
    return None


def atraso_preco_pregoes(ticker: str, data_ref: date, session) -> Optional[tuple[date, int]]:
    """(ultimo_preco, pregoes_de_atraso) ou None se o ticker nao tem preco ate data_ref."""
    ultimo = session.execute(
        select(func.max(PrecoDiario.data)).where(
            PrecoDiario.ticker == ticker, PrecoDiario.data <= data_ref
        )
    ).scalar_one_or_none()
    if ultimo is None:
        return None
    atraso = session.execute(
        select(func.count(func.distinct(PrecoDiario.data))).where(
            PrecoDiario.data > ultimo, PrecoDiario.data <= data_ref
        )
    ).scalar_one()
    return ultimo, int(atraso or 0)


def motivo_bloqueio_compra(
    ticker: str, data_ref: Optional[date], session, *, limite_pregoes: Optional[int] = None
) -> Optional[str]:
    """Texto do motivo se o ticker nao pode receber compra em ``data_ref``; senao None."""
    if data_ref is None:
        data_ref = data_referencia_mercado(session)
        if data_ref is None:
            return None
    evento = evento_encerramento_vigente(ticker, data_ref, session)
    if evento is not None:
        data_evt, tipo = evento
        rotulo = "em liquidacao" if "liquid" in (tipo or "").lower() else "encerrado"
        return f"fundo {rotulo} desde {data_evt.isoformat()}"

    limite = limite_dias_preco_defasado() if limite_pregoes is None else limite_pregoes
    atraso = atraso_preco_pregoes(ticker, data_ref, session)
    if atraso is not None and atraso[1] > limite:
        ultimo, n = atraso
        return (
            f"preco desatualizado: ultimo preco em {ultimo.isoformat()} "
            f"({n} pregoes de atraso vs {data_ref.isoformat()}; limite {limite})"
        )
    return None
