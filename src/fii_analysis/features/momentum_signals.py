"""Módulo de sinais de momentum baseados em relatórios mensais e dados de CDI."""
from __future__ import annotations
import calendar
from datetime import date
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.fii_analysis.data.database import BenchmarkDiario, CdiDiario, PrecoDiario, RelatorioMensal, get_cnpj_by_ticker
from src.fii_analysis.features.indicators import get_relatorios_ajustados


def get_pl_trend(ticker: str, target_date: date, session: Session, months: int = 3) -> str:
    """Avalia tendencia do Patrimonio Liquido por cota nos ultimos N meses."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return 'ESTAVEL'

    # Cotas na base ajustada a splits: PL/cotas nominal criaria um degrau falso no split.
    df = get_relatorios_ajustados(ticker, session)
    df = df[pd.to_datetime(df["data_entrega"]) <= pd.Timestamp(target_date)]
    df = df.sort_values("data_referencia", ascending=False).head(months + 1)
    rows = [(r.patrimonio_liq, r.cotas_aj) for r in df.itertuples(index=False)]

    if len(rows) < months + 1:
        return 'ESTAVEL'

    vpas = []
    for row in rows:
        pl, cotas = row
        if pd.isna(pl):
            return 'ESTAVEL'
        if pd.notna(cotas) and cotas > 0:
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
    """Media (efetiva - patrimonial) dos ultimos meses; flag se > tolerancia.

    ATENCAO: efetiva - patrimonial == dy_mes_pct (identidade exata nos dados da
    CVM). Esta funcao mede, portanto, o rendimento distribuido medio do mes (p.p.),
    NAO se o fundo distribui mais do que gera. A flag fica True para qualquer
    fundo que pague rendimento > tolerancia/mes.
    """
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


def get_momentum_relativo_ifix(
    ticker: str, target_date: date, session: Session, window: int = 21
) -> float | None:
    """
    Retorna retorno_fii_21d - retorno_ifix_21d em percentual.
    Positivo = FII superou o mercado. Negativo = fraqueza idiossincratica.
    O IFIX vem de benchmark_diario (ticker XFIX11), alinhado nas MESMAS datas da janela
    do FII (ultimo fechamento do benchmark <= cada data). Retorna None se o benchmark
    nao estiver no banco ou dados insuficientes.
    """
    try:
        stmt_fii = (
            select(PrecoDiario.fechamento_aj, PrecoDiario.data)
            .where(
                PrecoDiario.ticker == ticker,
                PrecoDiario.data <= target_date
            )
            .order_by(PrecoDiario.data.desc())
            .limit(window + 1)
        )
        rows_fii = session.execute(stmt_fii).all()

        if len(rows_fii) < window + 1 or any(r[0] is None for r in rows_fii):
            return None

        def _ifix_em(d: date) -> float | None:
            return session.execute(
                select(BenchmarkDiario.fechamento)
                .where(BenchmarkDiario.ticker == "XFIX11", BenchmarkDiario.data <= d,
                       BenchmarkDiario.fechamento.isnot(None))
                .order_by(BenchmarkDiario.data.desc())
                .limit(1)
            ).scalar_one_or_none()

        ifix_fim = _ifix_em(rows_fii[0][1])
        ifix_ini = _ifix_em(rows_fii[window][1])
        if ifix_fim is None or ifix_ini is None or float(ifix_ini) == 0:
            return None

        retorno_fii = (float(rows_fii[0][0]) / float(rows_fii[window][0])) - 1
        retorno_ifix = (float(ifix_fim) / float(ifix_ini)) - 1

        return round((retorno_fii - retorno_ifix) * 100, 4)
    except Exception:
        return None


def get_dividend_safety(
    ticker: str, target_date: date, session: Session, meses: int = 6
) -> dict:
    """
    Avalia sustentabilidade do dividendo.
    Retorna dict com: payout_vs_caixa (float|None), cortes_24m (int), flag_insustentavel (bool)
    """
    result = {'payout_vs_caixa': None, 'cortes_24m': 0, 'flag_insustentavel': False}

    try:
        cnpj = get_cnpj_by_ticker(ticker, session)
        if not cnpj:
            return result

        stmt = (
            select(RelatorioMensal.dy_mes_pct, RelatorioMensal.rentab_efetiva)
            .where(
                RelatorioMensal.cnpj == cnpj,
                RelatorioMensal.data_entrega <= target_date
            )
            .order_by(RelatorioMensal.data_referencia.desc())
            .limit(24)
        )
        rows = session.execute(stmt).all()

        if not rows:
            return result

        # 1. Calcular cortes_24m
        # Rows ja estao em ordem decrescente de data_referencia (mais recente no indice 0)
        # DY caiu em relacao ao mes anterior significa: dy_mes_pct[i] < dy_mes_pct[i+1]
        cortes = 0
        for i in range(len(rows) - 1):
            dy_atual = rows[i][0]
            dy_anterior = rows[i+1][0]
            if dy_atual is not None and dy_anterior is not None:
                if float(dy_atual) < float(dy_anterior):
                    cortes += 1
        result['cortes_24m'] = cortes

        # 2. Calcular payout_vs_caixa pros ultimos `meses`
        rows_recentes = rows[:meses]
        payouts = []
        for row in rows_recentes:
            dy_pct = row[0]
            rentab = row[1]
            if dy_pct is not None and rentab is not None and float(rentab) > 0.0001:
                payouts.append(float(dy_pct) / float(rentab))

        if len(payouts) >= 3:
            avg_payout = float(np.mean(payouts))
            result['payout_vs_caixa'] = avg_payout
            if avg_payout > 1.10:
                result['flag_insustentavel'] = True

        return result
    except Exception:
        return result
