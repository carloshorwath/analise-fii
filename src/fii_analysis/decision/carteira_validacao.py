"""Validacao de posicao de carteira (logica pura; a UI/CLI decide o que fazer com os erros)."""

from __future__ import annotations

import math
from typing import Iterable

from sqlalchemy import select


def validar_posicao(
    ticker: str | None,
    quantidade,
    preco,
    tickers_validos: Iterable[str],
) -> list[str]:
    """Erros legiveis de uma posicao (lista vazia = valida).

    Regras: quantidade inteira > 0 (float so se integral, ex.: 10.0; bool nao vale),
    preco finito > 0, ticker existente em ``tickers_validos`` (use ``tickers_conhecidos``).
    """
    erros: list[str] = []

    t = (ticker or "").strip().upper()
    if not t:
        erros.append("Ticker nao informado.")
    elif t not in {x.upper() for x in tickers_validos}:
        erros.append(f"Ticker {t} nao existe na base (tickers/universo).")

    q_ok = (
        not isinstance(quantidade, bool)
        and isinstance(quantidade, (int, float))
        and math.isfinite(quantidade)
        and float(quantidade).is_integer()
    ) or (hasattr(quantidade, "item") and _numpy_inteiro(quantidade))
    if not q_ok:
        erros.append(f"Quantidade deve ser um numero inteiro (recebido: {quantidade!r}).")
    elif float(quantidade) <= 0:
        erros.append(f"Quantidade deve ser maior que zero (recebido: {quantidade}).")

    try:
        p = float(preco)
        p_ok = math.isfinite(p)
    except (TypeError, ValueError):
        p_ok = False
    if not p_ok:
        erros.append(f"Preco invalido (recebido: {preco!r}).")
    elif p <= 0:
        erros.append(f"Preco deve ser maior que zero (recebido: {preco}).")

    return erros


def _numpy_inteiro(valor) -> bool:
    try:
        v = valor.item()
    except Exception:
        return False
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and float(v).is_integer()


def tickers_conhecidos(session) -> set[str]:
    """Tickers existentes: tabela ``tickers`` UNIAO ``universo`` (qualquer data)."""
    from src.fii_analysis.data.database import Ticker, Universo

    a = session.execute(select(Ticker.ticker)).scalars().all()
    b = session.execute(select(Universo.ticker)).scalars().all()
    return {x.upper() for x in [*a, *b] if x}
