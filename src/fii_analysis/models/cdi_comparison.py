"""[PESQUISA — não operacional] Comparação diagnóstica: P/VP bruto vs resíduo CDI-ajustado.

EXPERIMENTO ENCERRADO (29/04/2026): veredito RESIDUO_PIORA. Não usar no fluxo operacional.

Fase 1 da V2 CDI. Constrói a série diária de resíduos CDI-ajustados com
regressão expanding (point-in-time) e compara com P/VP bruto.

Método:
  1. Série diária de P/VP (get_pvp_series)
  2. merge_asof(P/VP, CDI_diário, direction='backward') → cdi_12m por dia
  3. Expanding regression semanal (min 104 semanas):
     Para cada semana t, OLS(P/VP ~ CDI_12m) só com dados <= t
     → alpha_t, beta_t
  4. Forward-fill alpha_t, beta_t do semanal para o diário
  5. Resíduo diário = pvp_t - (alpha_t + beta_t * cdi_12m_t)
  6. Percentil rolling(504) do resíduo → residuo_pct
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select

from src.fii_analysis.data.database import CdiDiario
from src.fii_analysis.models.episodes import get_pvp_series


# Constantes
MIN_TRAIN_WEEKS = 104
MAX_LAGS = 4
ROLLING_WINDOW = 504


def _compute_cdi_12m_daily(session, data_min: date, data_max: date) -> pd.DataFrame:
    """Retorna DataFrame com data, cdi_12m para cada dia com CDI disponível.

    CDI 12m = produto acumulado das taxas diárias nos 12 meses anteriores.
    """
    inicio = date(data_min.year - 1, data_min.month, data_min.day)
    rows = session.execute(
        select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
        .where(CdiDiario.data >= inicio, CdiDiario.data <= data_max)
        .order_by(CdiDiario.data.asc())
    ).all()

    if not rows:
        return pd.DataFrame(columns=["data", "cdi_12m"])

    cdi_map = {r.data: float(r.taxa_diaria_pct) for r in rows}

    datas = sorted(cdi_map.keys())
    result = []
    for d in datas:
        d_inicio = (
            date(d.year - 1, d.month, d.day)
            if not (d.month == 2 and d.day == 29)
            else date(d.year - 1, 2, 28)
        )
        taxas = [v for dt, v in sorted(cdi_map.items()) if d_inicio <= dt <= d]
        if len(taxas) >= 200:
            cdi_12m = 1.0
            for t in taxas:
                cdi_12m *= (1.0 + t / 100.0)
            result.append({"data": d, "cdi_12m": cdi_12m - 1.0})

    return pd.DataFrame(result)


def build_daily_residual_series(
    ticker: str,
    session,
    t: date | None = None,
    rolling_window: int = ROLLING_WINDOW,
    min_train_weeks: int = MIN_TRAIN_WEEKS,
) -> pd.DataFrame:
    """Constrói série diária com P/VP bruto e resíduo CDI-ajustado.

    Retorna DataFrame com colunas:
      data, pvp, pvp_pct, residuo, residuo_pct, alpha_t, beta_t, cdi_12m,
      fechamento, fechamento_aj

    Sem leakage: regressão expanding usa apenas dados <= t.
    """
    if t is None:
        t = date.today()

    # 1. Série diária de P/VP
    df = get_pvp_series(ticker, session, rolling_window=rolling_window)
    if df.empty:
        return pd.DataFrame()

    df = df[df["data"] <= pd.Timestamp(t)].copy()
    df = df.sort_values("data").reset_index(drop=True)

    if len(df) < 252:
        return pd.DataFrame()

    # 2. CDI 12m diário via merge_asof
    data_min = df["data"].min().date() if hasattr(df["data"].min(), "date") else df["data"].min()
    data_max = df["data"].max().date() if hasattr(df["data"].max(), "date") else df["data"].max()

    cdi_df = _compute_cdi_12m_daily(session, data_min, data_max)
    if cdi_df.empty:
        return pd.DataFrame()

    cdi_df["data"] = pd.to_datetime(cdi_df["data"])

    df = pd.merge_asof(
        df.sort_values("data"),
        cdi_df[["data", "cdi_12m"]].sort_values("data"),
        on="data",
        direction="backward",
    )

    df = df.dropna(subset=["cdi_12m"]).reset_index(drop=True)
    if len(df) < 252:
        return pd.DataFrame()

    # Renomear pvp_pct para evitar conflito
    df = df.rename(columns={"pvp_pct": "pvp_pct"})

    # 3. Expanding regression semanal
    # Agrupar por semana ISO — última observação de cada semana
    df["_week"] = df["data"].dt.isocalendar().week.astype(int)
    df["_year"] = df["data"].dt.isocalendar().year.astype(int)
    idx_last = df.groupby(["_year", "_week"])["data"].idxmax()
    weekly = df.loc[idx_last, ["data", "pvp", "cdi_12m"]].sort_values("data").reset_index(drop=True)

    # Expanding OLS — para cada semana com >= min_train_weeks semanas anteriores
    try:
        from statsmodels.regression.linear_model import OLS
    except ImportError:
        return pd.DataFrame()

    coefs = []  # lista de (data_semana, alpha, beta)
    for i in range(min_train_weeks, len(weekly) + 1):
        w_train = weekly.iloc[:i]
        y = w_train["pvp"].values.astype(float)
        X = np.column_stack([np.ones(len(y)), w_train["cdi_12m"].values.astype(float)])

        try:
            model = OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": MAX_LAGS})
            alpha = float(model.params[0])
            beta = float(model.params[1])
        except Exception:
            alpha = coefs[-1][1] if coefs else 0.0
            beta = coefs[-1][2] if coefs else 0.0

        coefs.append((weekly.iloc[i - 1]["data"], alpha, beta))

    coefs_df = pd.DataFrame(coefs, columns=["data", "alpha_t", "beta_t"])

    # 4. Forward-fill coefs do semanal para o diário via merge_asof
    df = pd.merge_asof(
        df.sort_values("data"),
        coefs_df.sort_values("data"),
        on="data",
        direction="backward",
    )

    df = df.dropna(subset=["alpha_t", "beta_t"]).reset_index(drop=True)

    # 5. Resíduo diário
    df["residuo"] = df["pvp"] - (df["alpha_t"] + df["beta_t"] * df["cdi_12m"])

    # 6. Percentil rolling do resíduo
    min_periods = min(63, rolling_window)
    df["residuo_pct"] = (
        df["residuo"]
        .rolling(rolling_window, min_periods=min_periods)
        .rank(pct=True) * 100
    )

    # Limpar colunas auxiliares
    df = df.drop(columns=["_week", "_year"], errors="ignore")

    return df


# ─── Classificação de regime ───────────────────────────────────────

def _classify_regime(pct: float, low: float, high: float) -> str:
    """Classifica percentil em EXTREMO_LOW, NEUTRO ou EXTREMO_HIGH."""
    if pct <= low:
        return "EXTREMO_LOW"
    elif pct >= high:
        return "EXTREMO_HIGH"
    return "NEUTRO"


# ─── Diagnóstico ───────────────────────────────────────────────────

def compute_diagnostic(
    ticker: str,
    session,
    low_pct: float = 20.0,
    high_pct: float = 80.0,
    rolling_window: int = ROLLING_WINDOW,
    min_train_weeks: int = MIN_TRAIN_WEEKS,
) -> dict:
    """Computa diagnóstico comparativo P/VP bruto vs resíduo CDI-ajustado.

    Returns
    -------
    dict com:
      status: OK | DADOS_INSUFICIENTES | SEM_CDI
      corr: correlação Pearson entre pvp_pct e residuo_pct
      n_obs: número de observações diárias com ambos os percentis
      pct_discordancia: % de dias em que regimes divergem
      bruto_extremo_residuo_neutro: contagem
      bruto_neutro_residuo_extremo: contagem
      ambos_concordam: contagem
      exemplos_discordancia: lista de datas com maior divergência
      observacao: texto curto de plausibilidade
    """
    df = build_daily_residual_series(ticker, session, rolling_window=rolling_window,
                                     min_train_weeks=min_train_weeks)

    if df.empty:
        return {"status": "DADOS_INSUFICIENTES", "ticker": ticker}

    df = df.dropna(subset=["pvp_pct", "residuo_pct"]).copy()
    if len(df) < 63:
        return {"status": "DADOS_INSUFICIENTES", "ticker": ticker, "n_obs": len(df)}

    # Correlação
    corr = float(df["pvp_pct"].corr(df["residuo_pct"]))

    # Classificação de regime
    df["regime_bruto"] = df["pvp_pct"].apply(lambda x: _classify_regime(x, low_pct, high_pct))
    df["regime_residuo"] = df["residuo_pct"].apply(lambda x: _classify_regime(x, low_pct, high_pct))

    n_total = len(df)
    concordam = int((df["regime_bruto"] == df["regime_residuo"]).sum())
    discordam = n_total - concordam

    # Contagens cruzadas
    bruto_ext_residuo_neutro = int(
        ((df["regime_bruto"] != "NEUTRO") & (df["regime_residuo"] == "NEUTRO")).sum()
    )
    bruto_neutro_residuo_ext = int(
        ((df["regime_bruto"] == "NEUTRO") & (df["regime_residuo"] != "NEUTRO")).sum()
    )

    # Exemplos de discordância (maior diferença absoluta entre percentis)
    df["_diff"] = (df["pvp_pct"] - df["residuo_pct"]).abs()
    exemplos_df = df[df["regime_bruto"] != df["regime_residuo"]].nlargest(5, "_diff")
    exemplos = []
    for _, row in exemplos_df.iterrows():
        exemplos.append({
            "data": str(row["data"].date()) if hasattr(row["data"], "date") else str(row["data"]),
            "pvp_pct": round(float(row["pvp_pct"]), 1),
            "residuo_pct": round(float(row["residuo_pct"]), 1),
            "regime_bruto": row["regime_bruto"],
            "regime_residuo": row["regime_residuo"],
        })

    # Observação de plausibilidade
    if corr > 0.8:
        obs = "Alta correlação — resíduo pouco diferenciado do bruto"
    elif corr > 0.5:
        obs = "Correlação moderada — resíduo captura regime de juros"
    else:
        obs = "Baixa correlação — resíduo conta história diferente do bruto"

    return {
        "status": "OK",
        "ticker": ticker,
        "corr": round(corr, 4),
        "n_obs": n_total,
        "pct_discordancia": round(discordam / n_total * 100, 1),
        "bruto_extremo_residuo_neutro": bruto_ext_residuo_neutro,
        "bruto_neutro_residuo_extremo": bruto_neutro_residuo_ext,
        "ambos_concordam": concordam,
        "exemplos_discordancia": exemplos,
        "observacao": obs,
    }


def compute_diagnostic_batch(
    tickers: list[str],
    session,
    low_pct: float = 20.0,
    high_pct: float = 80.0,
) -> list[dict]:
    """Computa diagnóstico para múltiplos tickers."""
    results = []
    for ticker in tickers:
        try:
            results.append(compute_diagnostic(ticker, session, low_pct, high_pct))
        except Exception as e:
            results.append({"status": "ERRO", "ticker": ticker, "erro": str(e)})
    return results