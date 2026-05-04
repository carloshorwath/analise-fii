"""Módulo de sinais de momentum baseados em relatórios mensais e dados de CDI."""
from __future__ import annotations
import calendar
from datetime import date
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.fii_analysis.data.database import CdiDiario, RelatorioMensal, get_cnpj_by_ticker


def get_pl_trend(ticker: str, target_date: date, session: Session, months: int = 3) -> str:
    """Avalia tendencia do Patrimonio Liquido por cota nos ultimos N meses."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return 'ESTAVEL'

    stmt = (
        select(RelatorioMensal.patrimonio_liq, RelatorioMensal.cotas_emitidas)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.data_entrega <= target_date
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(months + 1)
    )
    rows = session.execute(stmt).all()

    if len(rows) < months + 1:
        return 'ESTAVEL'

    vpas = []
    for row in rows:
        pl, cotas = row
        if pl is None:
            return 'ESTAVEL'
        if cotas is not None and cotas > 0:
            vpas.append(float(pl) / float(cotas))
        else:
            vpas.append(float(pl))

    deltas = []
    for i in range(len(vpas) - 1):
        deltas.append(vpas[i] - vpas[i+1])

    if all(d > 0 for d in deltas):
        return 'CRESCENDO'
    elif all(d < 0 for d in deltas):
        return 'CAINDO'
    return 'ESTAVEL'


def get_rentab_divergencia(ticker: str, target_date: date, session: Session, meses: int = 6, tolerancia: float = 0.01) -> tuple[bool, float | None]:
    """Detecta divergencia sistematica entre rentabilidade efetiva e patrimonial."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return (False, None)

    stmt = (
        select(RelatorioMensal.rentab_efetiva, RelatorioMensal.rentab_patrim)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.data_entrega <= target_date
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(meses)
    )
    rows = session.execute(stmt).all()

    divergencias = []
    for row in rows:
        efetiva, patrim = row
        if efetiva is not None and patrim is not None:
            divergencias.append(float(efetiva) - float(patrim))

    if len(divergencias) < 3:
        return (False, None)

    media_divergencia = float(np.mean(divergencias))
    flag = media_divergencia > tolerancia

    return (flag, media_divergencia)


def get_dy_momentum(ticker: str, target_date: date, session: Session) -> float | None:
    """Retorna DY medio dos ultimos 3 meses menos DY medio dos ultimos 12 meses (em pontos percentuais)."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return None

    stmt = (
        select(RelatorioMensal.dy_mes_pct)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.data_entrega <= target_date
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(12)
    )
    rows = session.execute(stmt).all()

    if len(rows) < 12:
        return None

    dy_list = []
    for row in rows:
        dy = row[0]
        if dy is None:
            return None
        dy_list.append(float(dy))

    dy_3m = float(np.mean(dy_list[:3])) * 100
    dy_12m = float(np.mean(dy_list[:12])) * 100

    return round(dy_3m - dy_12m, 4)


def get_meses_dy_acima_cdi(ticker: str, target_date: date, session: Session, janela_meses: int = 12) -> int:
    """Conta quantos meses nos ultimos janela_meses o DY mensal do fundo superou o CDI mensal."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return 0

    stmt = (
        select(RelatorioMensal.data_referencia, RelatorioMensal.dy_mes_pct)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.data_entrega <= target_date
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(janela_meses)
    )
    rows = session.execute(stmt).all()

    if not rows:
        return 0

    count_superou = 0

    for row in rows:
        mes_ref, dy_mes = row
        if dy_mes is None:
            continue

        primeiro_dia = mes_ref.replace(day=1)
        _, last_day = calendar.monthrange(mes_ref.year, mes_ref.month)
        ultimo_dia = mes_ref.replace(day=last_day)

        cdi_stmt = (
            select(CdiDiario.taxa_diaria_pct)
            .where(
                CdiDiario.data >= primeiro_dia,
                CdiDiario.data <= ultimo_dia
            )
        )
        cdi_rows = session.execute(cdi_stmt).all()

        if not cdi_rows:
            continue

        cdi_mensal_factor = 1.0
        for cdi_row in cdi_rows:
            taxa_diaria = float(cdi_row[0])
            cdi_mensal_factor *= (1 + taxa_diaria / 100.0)

        cdi_mensal = cdi_mensal_factor - 1.0

        if float(dy_mes) > cdi_mensal:
            count_superou += 1

    return count_superou
