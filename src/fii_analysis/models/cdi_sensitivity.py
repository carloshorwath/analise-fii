"""Sensibilidade do P/VP ao CDI — regressão diagnóstica por ticker.

Regressão OLS semanal: P/VP_t = α + β * CDI_12m_t + ε_t

- P/VP: última observação disponível da semana (point-in-time, sem média).
- CDI: acumulado 12m na mesma data.
- Erros padrão HAC/Newey-West com maxlags=4.
- min_obs=104 semanas (~2 anos).

Esta é uma feature diagnóstica (V1): entra como campo informativo no
TickerDecision sem alterar a ação final. O objetivo é validar se o
resíduo CDI-ajustado separa melhor BUY/SELL em OOS antes de promover
a camada de ajuste.

Status possíveis:
    OK                    — regressão convergiu com >= 104 semanas.
    DADOS_INSUFICIENTES   — menos de 104 semanas com P/VP + CDI pareados.
    SEM_CDI               — sem dados de CDI na tabela cdi_diario.
    CONVERGENCIA_FALHOU   — OLS falhou (ex: matriz singular).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from src.fii_analysis.data.cdi import get_cdi_acumulado_12m
from src.fii_analysis.data.database import CdiDiario
from src.fii_analysis.models.episodes import get_pvp_series


# Constantes
MIN_OBS = 104  # semanas (~2 anos)
MAX_LAGS = 4   # Newey-West


@dataclass
class CdiSensitivityResult:
    """Resultado da regressão CDI sensitivity para um ticker."""

    status: str  # OK | DADOS_INSUFICIENTES | SEM_CDI | CONVERGENCIA_FALHOU
    beta: float | None = None
    r_squared: float | None = None
    p_value: float | None = None
    residuo_atual: float | None = None
    residuo_percentil: float | None = None
    n_obs: int = 0


def _build_weekly_series(
    ticker: str,
    session,
    t: date | None = None,
) -> pd.DataFrame:
    """Constrói série semanal (último P/VP da semana + CDI 12m).

    Retorna DataFrame com colunas: data, pvp, cdi_12m.
    Uma linha por semana, usando o último dia com P/VP disponível.
    """
    if t is None:
        t = date.today()

    # 1. Obter série diária de P/VP
    df_pvp = get_pvp_series(ticker, session, rolling_window=0)  # sem rolling
    if df_pvp.empty:
        return pd.DataFrame(columns=["data", "pvp", "cdi_12m"])

    # Filtrar apenas dados <= t
    df_pvp = df_pvp[df_pvp["data"] <= pd.Timestamp(t)].copy()
    if df_pvp.empty:
        return pd.DataFrame(columns=["data", "pvp", "cdi_12m"])

    # Garantir tipos
    df_pvp["data"] = pd.to_datetime(df_pvp["data"]).dt.date
    df_pvp = df_pvp.dropna(subset=["pvp"])
    if df_pvp.empty:
        return pd.DataFrame(columns=["data", "pvp", "cdi_12m"])

    # 2. Agrupar por semana ISO — pegar a última observação de cada semana
    df_pvp["semana"] = pd.to_datetime(df_pvp["data"]).dt.isocalendar().week.astype(int)
    df_pvp["ano_semana"] = pd.to_datetime(df_pvp["data"]).dt.isocalendar().year.astype(int)

    # Último P/VP por (ano, semana)
    idx_last = df_pvp.groupby(["ano_semana", "semana"])["data"].idxmax()
    df_weekly = df_pvp.loc[idx_last, ["data", "pvp"]].copy()
    df_weekly = df_weekly.sort_values("data").reset_index(drop=True)

    # 3. Batch query CDI para todas as datas semanais
    datas = df_weekly["data"].tolist()
    if not datas:
        return pd.DataFrame(columns=["data", "pvp", "cdi_12m"])

    data_min = min(datas)
    # CDI 12m precisa de 1 ano antes da data mínima
    data_inicio_cdi = date(data_min.year - 1, data_min.month, data_min.day)

    cdi_rows = session.execute(
        select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
        .where(CdiDiario.data >= data_inicio_cdi, CdiDiario.data <= t)
        .order_by(CdiDiario.data.asc())
    ).all()
    cdi_map = {c.data: float(c.taxa_diaria_pct) for c in cdi_rows}

    if not cdi_map:
        return pd.DataFrame(columns=["data", "pvp", "cdi_12m"])

    # 4. Calcular CDI acumulado 12m para cada data semanal
    from math import prod as math_prod

    cdi_12m_list: list[float | None] = []
    for d in datas:
        inicio = (
            date(d.year - 1, d.month, d.day)
            if not (d.month == 2 and d.day == 29)
            else date(d.year - 1, 2, 28)
        )
        taxas = [v for dt, v in sorted(cdi_map.items()) if inicio <= dt <= d]
        if len(taxas) < 200:
            cdi_12m_list.append(None)
        else:
            cdi_12m_list.append(math_prod(1.0 + v / 100.0 for v in taxas) - 1.0)

    df_weekly["cdi_12m"] = cdi_12m_list

    # Remover linhas sem CDI
    df_weekly = df_weekly.dropna(subset=["cdi_12m"]).reset_index(drop=True)

    return df_weekly


def compute_cdi_sensitivity(
    ticker: str,
    session,
    t: date | None = None,
) -> CdiSensitivityResult:
    """Calcula sensibilidade do P/VP ao CDI para um ticker.

    Regressão: P/VP_t = α + β * CDI_12m_t (nível, sem log).
    Erros padrão HAC/Newey-West com maxlags=4.
    Mínimo de 104 observações semanais.

    Parameters
    ----------
    ticker : str
    session : SQLAlchemy session
    t : date, optional
        Data de referência (default: hoje). Só usa dados <= t.

    Returns
    -------
    CdiSensitivityResult
    """
    # Verificar se há CDI no banco
    has_cdi = session.execute(
        select(CdiDiario.data).limit(1)
    ).scalar_one_or_none()
    if has_cdi is None:
        return CdiSensitivityResult(status="SEM_CDI")

    # Construir série semanal
    df = _build_weekly_series(ticker, session, t)

    if len(df) < MIN_OBS:
        return CdiSensitivityResult(status="DADOS_INSUFICIENTES", n_obs=len(df))

    # Regressão OLS com HAC
    try:
        from statsmodels.regression.linear_model import OLS
        import statsmodels.stats.sandwich_covariance as sw

        y = df["pvp"].values.astype(float)
        X = np.column_stack([
            np.ones(len(y)),
            df["cdi_12m"].values.astype(float),
        ])

        model = OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": MAX_LAGS})

        beta = float(model.params[1])
        r_squared = float(model.rsquared)
        p_value = float(model.pvalues[1])
        n_obs = int(model.nobs)

        # Resíduo atual (última observação)
        y_pred_last = float(model.predict(X[-1:])[0])
        residuo = float(y[-1]) - y_pred_last

        # Percentil do resíduo atual na amostra de resíduos
        residuos = model.resid
        residuo_pct = float(np.searchsorted(np.sort(residuos), residuo) / len(residuos) * 100)

        return CdiSensitivityResult(
            status="OK",
            beta=beta,
            r_squared=r_squared,
            p_value=p_value,
            residuo_atual=residuo,
            residuo_percentil=residuo_pct,
            n_obs=n_obs,
        )

    except Exception:
        return CdiSensitivityResult(status="CONVERGENCIA_FALHOU", n_obs=len(df))


def compute_cdi_sensitivity_batch(
    tickers: list[str],
    session,
    t: date | None = None,
) -> dict[str, CdiSensitivityResult]:
    """Calcula sensibilidade CDI para múltiplos tickers.

    Returns
    -------
    dict[ticker, CdiSensitivityResult]
    """
    results: dict[str, CdiSensitivityResult] = {}
    for ticker in tickers:
        try:
            results[ticker] = compute_cdi_sensitivity(ticker, session, t)
        except Exception:
            results[ticker] = CdiSensitivityResult(status="CONVERGENCIA_FALHOU")
    return results


def cdi_sensitivity_to_dict(result: CdiSensitivityResult) -> dict:
    """Converte CdiSensitivityResult para dict (serialização em snapshot)."""
    return {
        "cdi_status": result.status,
        "cdi_beta": result.beta,
        "cdi_r_squared": result.r_squared,
        "cdi_p_value": result.p_value,
        "cdi_residuo_atual": result.residuo_atual,
        "cdi_residuo_percentil": result.residuo_percentil,
    }