"""Cálculos de CDI — desacoplados do módulo de ingestão.

Este módulo contém apenas leitura da tabela cdi_diario (SQLAlchemy puro).
Zero import de yfinance, requests ou qualquer cliente externo.

Motivo: ingestion.py importa yfinance no topo, o que cria regressão de import
em caminhos puramente analíticos (valuation, models, decision).
"""

from __future__ import annotations

from datetime import date
from math import prod

from sqlalchemy import select

from src.fii_analysis.data.database import CdiDiario


def get_cdi_acumulado_12m(t: date, session) -> float | None:
    """Retorna CDI acumulado nos 12 meses anteriores a t (como fração, ex: 0.105).

    Usa registros point-in-time da tabela cdi_diario.
    Retorna None se houver dados insuficientes (< 200 dias úteis).
    """
    inicio = (
        date(t.year - 1, t.month, t.day)
        if not (t.month == 2 and t.day == 29)
        else date(t.year - 1, 2, 28)
    )
    registros = (
        session.execute(
            select(CdiDiario.taxa_diaria_pct)
            .where(CdiDiario.data >= inicio, CdiDiario.data <= t)
            .order_by(CdiDiario.data.asc())
        )
        .scalars()
        .all()
    )

    if len(registros) < 200:
        return None

    # acumula: (1 + taxa_diaria/100) para cada dia
    acumulado = prod(1.0 + float(r) / 100.0 for r in registros) - 1.0
    return acumulado


def get_cdi_acumulado_semana(t: date, session) -> float | None:
    """CDI acumulado 12m até a data t (atalho semântico para uso semanal)."""
    return get_cdi_acumulado_12m(t, session)