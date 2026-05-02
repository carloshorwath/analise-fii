"""[PESQUISA — não operacional] Avaliação OOS: baseline P/VP bruto vs experimental resíduo CDI-ajustado.

EXPERIMENTO ENCERRADO (29/04/2026): veredito RESIDUO_PIORA. Não usar no fluxo operacional.

Fase 2 da V2 CDI. Compara os dois sinais nos motores de episódios e
walk-forward rolling, coletando métricas OOS idênticas para ambos.

Baseline:     value_col='pvp',  pct_col='pvp_pct'
Experimental: value_col='residuo', pct_col='residuo_pct'

Regras:
- Não alterar _derivar_acao() nem promover resíduo a sinal oficial.
- Zero leakage: resíduo vem de regressão expanding (point-in-time).
- Se dados insuficientes, retorna status explícito.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from src.fii_analysis.models.cdi_comparison import build_daily_residual_series
from src.fii_analysis.models.episodes import identify_episodes, get_pvp_series
from src.fii_analysis.models.walk_forward_rolling import walk_forward_roll


# ─── Helpers de extração de métricas ───────────────────────────────

def _extract_episodes_metrics(result: dict) -> dict:
    """Extrai métricas comparáveis de resultado de identify_episodes."""
    summary = result.get("summary", {})
    buy = summary.get("buy", {})
    sell = summary.get("sell", {})
    comp = summary.get("comparison", {})

    return {
        "n_buy": buy.get("n", 0),
        "n_sell": sell.get("n", 0),
        "win_rate_buy": buy.get("win_rate"),
        "mean_buy": buy.get("mean"),
        "ci_lower_buy": buy.get("ci_lower"),
        "ci_upper_buy": buy.get("ci_upper"),
        "p_value_buy": buy.get("p_value"),
        "win_rate_sell": sell.get("win_rate"),
        "mean_sell": sell.get("mean"),
        "p_value_sell": sell.get("p_value"),
        "mw_pvalue": comp.get("mw_pvalue") if comp else None,
        "spread": comp.get("buy_minus_sell") if comp else None,
    }


def _extract_wf_metrics(result: dict) -> dict:
    """Extrai métricas comparáveis de resultado de walk_forward_roll."""
    if "error" in result:
        return {"error": result["error"]}

    summary = result.get("summary", {})
    buy = summary.get("BUY", {})
    sell = summary.get("SELL", {})
    comp = result.get("comparison", {})

    return {
        "n_buy": buy.get("n", 0),
        "n_effective_buy": buy.get("n_effective", 0),
        "win_rate_buy": buy.get("win_rate"),
        "mean_buy": buy.get("mean"),
        "p_value_buy": buy.get("p_value"),
        "ci_lower_buy": buy.get("ci_lower"),
        "ci_upper_buy": buy.get("ci_upper"),
        "n_sell": sell.get("n", 0),
        "n_effective_sell": sell.get("n_effective", 0),
        "win_rate_sell": sell.get("win_rate"),
        "mean_sell": sell.get("mean"),
        "p_value_sell": sell.get("p_value"),
        "mw_pvalue": comp.get("mw_pvalue") if comp else None,
        "spread": comp.get("spread") if comp else None,
        "n_steps": result.get("n_steps", 0),
    }


# ─── Comparação por motor ─────────────────────────────────────────

def compare_episodes_oos(
    ticker: str,
    session,
    pvp_pct_low: float = 10.0,
    pvp_pct_high: float = 90.0,
    forward_days: int = 30,
) -> dict:
    """Compara baseline (P/VP bruto) vs experimental (resíduo CDI) em episódios.

    Returns
    -------
    dict com:
      ticker, status, baseline, experimental, diff
    """
    # Construir série com resíduo
    df = build_daily_residual_series(ticker, session)
    if df.empty:
        return {"ticker": ticker, "status": "DADOS_INSUFICIENTES"}

    if "residuo_pct" not in df.columns or df["residuo_pct"].dropna().empty:
        return {"ticker": ticker, "status": "SEM_RESIDUO"}

    # Baseline: P/VP bruto
    try:
        res_baseline = identify_episodes(
            df, pvp_pct_low=pvp_pct_low, pvp_pct_high=pvp_pct_high,
            forward_days=forward_days, value_col="pvp", pct_col="pvp_pct",
        )
        metrics_baseline = _extract_episodes_metrics(res_baseline)
    except Exception as e:
        metrics_baseline = {"error": str(e)}

    # Experimental: resíduo CDI
    try:
        res_experimental = identify_episodes(
            df, pvp_pct_low=pvp_pct_low, pvp_pct_high=pvp_pct_high,
            forward_days=forward_days, value_col="residuo", pct_col="residuo_pct",
        )
        metrics_experimental = _extract_episodes_metrics(res_experimental)
    except Exception as e:
        metrics_experimental = {"error": str(e)}

    return {
        "ticker": ticker,
        "status": "OK",
        "baseline": metrics_baseline,
        "experimental": metrics_experimental,
    }


def compare_wf_oos(
    ticker: str,
    session,
    train_months: int = 18,
    predict_months: int = 1,
    pvp_pct_buy: float = 15.0,
    pvp_pct_sell: float = 85.0,
    forward_days: int = 20,
) -> dict:
    """Compara baseline vs experimental em walk-forward rolling.

    Returns
    -------
    dict com:
      ticker, status, baseline, experimental
    """
    # Construir série com resíduo
    df = build_daily_residual_series(ticker, session)
    if df.empty:
        return {"ticker": ticker, "status": "DADOS_INSUFICIENTES"}

    if "residuo_pct" not in df.columns or df["residuo_pct"].dropna().empty:
        return {"ticker": ticker, "status": "SEM_RESIDUO"}

    # Baseline: P/VP bruto (sem alt_df — usa get_pvp_series internamente)
    try:
        res_baseline = walk_forward_roll(
            ticker, session,
            train_months=train_months, predict_months=predict_months,
            pvp_pct_buy=pvp_pct_buy, pvp_pct_sell=pvp_pct_sell,
            forward_days=forward_days,
            value_col="pvp", pct_col="pvp_pct",
        )
        metrics_baseline = _extract_wf_metrics(res_baseline)
    except Exception as e:
        metrics_baseline = {"error": str(e)}

    # Experimental: resíduo CDI (com alt_df)
    try:
        res_experimental = walk_forward_roll(
            ticker, session,
            train_months=train_months, predict_months=predict_months,
            pvp_pct_buy=pvp_pct_buy, pvp_pct_sell=pvp_pct_sell,
            forward_days=forward_days,
            alt_df=df, value_col="residuo", pct_col="residuo_pct",
        )
        metrics_experimental = _extract_wf_metrics(res_experimental)
    except Exception as e:
        metrics_experimental = {"error": str(e)}

    return {
        "ticker": ticker,
        "status": "OK",
        "baseline": metrics_baseline,
        "experimental": metrics_experimental,
    }


# ─── Batch e veredito ──────────────────────────────────────────────

def compare_oos_batch(
    tickers: list[str],
    session,
    **kwargs,
) -> dict:
    """Roda comparação OOS completa (episódios + walk-forward) para múltiplos tickers.

    Returns
    -------
    dict com:
      episodes: list de resultados por ticker
      walk_forward: list de resultados por ticker
    """
    episodes_results = []
    wf_results = []

    for ticker in tickers:
        try:
            episodes_results.append(
                compare_episodes_oos(ticker, session, **kwargs)
            )
        except Exception as e:
            episodes_results.append({"ticker": ticker, "status": "ERRO", "erro": str(e)})

        try:
            wf_results.append(
                compare_wf_oos(ticker, session)
            )
        except Exception as e:
            wf_results.append({"ticker": ticker, "status": "ERRO", "erro": str(e)})

    return {
        "episodes": episodes_results,
        "walk_forward": wf_results,
    }


def _safe_get(d: dict, key: str, default=None):
    """Get seguro para métricas que podem ser dict com error."""
    if isinstance(d, dict) and "error" in d:
        return default
    return d.get(key, default)


def verdict(batch_results: dict) -> dict:
    """Classifica resultado final da comparação OOS.

    Returns
    -------
    dict com:
      classificacao: RESIDUO_MELHORA | RESIDUO_EMPATA | RESIDUO_PIORA | INCONCLUSIVO
      detalhe: texto explicativo
      n_melhora: quantos tickers/motores o resíduo melhorou
      n_empata: idem
      n_piora: idem
      n_inconclusivo: idem
    """
    contagens = {"melhora": 0, "empata": 0, "piora": 0, "inconclusivo": 0}
    detalhes = []

    for motor_label, results_key in [("Episodios", "episodes"), ("Walk-Forward", "walk_forward")]:
        for r in batch_results.get(results_key, []):
            ticker = r.get("ticker", "?")
            status = r.get("status", "")
            if status != "OK":
                contagens["inconclusivo"] += 1
                detalhes.append(f"  {ticker} ({motor_label}): {status}")
                continue

            bl = r.get("baseline", {})
            ex = r.get("experimental", {})

            # Se algum tem erro, inconclusivo
            if isinstance(bl, dict) and "error" in bl:
                contagens["inconclusivo"] += 1
                detalhes.append(f"  {ticker} ({motor_label}): baseline erro")
                continue
            if isinstance(ex, dict) and "error" in ex:
                contagens["inconclusivo"] += 1
                detalhes.append(f"  {ticker} ({motor_label}): experimental erro")
                continue

            # Comparar win_rate BUY e mean BUY
            wr_bl = _safe_get(bl, "win_rate_buy")
            wr_ex = _safe_get(ex, "win_rate_buy")
            mean_bl = _safe_get(bl, "mean_buy")
            mean_ex = _safe_get(ex, "mean_buy")

            # Lógica de classificação
            if wr_bl is None or wr_ex is None or mean_bl is None or mean_ex is None:
                contagens["inconclusivo"] += 1
                detalhes.append(f"  {ticker} ({motor_label}): métricas insuficientes")
                continue

            wr_diff = wr_ex - wr_bl
            mean_diff = mean_ex - mean_bl

            # Melhora: win_rate >= +5pp OU retorno médio >= +2pp, sem piorar o outro
            wr_melhora = wr_diff >= 0.05
            mean_melhora = mean_diff >= 0.02
            wr_piora = wr_diff <= -0.05
            mean_piora = mean_diff <= -0.02

            if (wr_melhora or mean_melhora) and not (wr_piora or mean_piora):
                contagens["melhora"] += 1
                detalhes.append(
                    f"  {ticker} ({motor_label}): MELHORA "
                    f"WR {wr_bl:.1%}→{wr_ex:.1%} | Ret {mean_bl:.2%}→{mean_ex:.2%}"
                )
            elif (wr_piora or mean_piora) and not (wr_melhora or mean_melhora):
                contagens["piora"] += 1
                detalhes.append(
                    f"  {ticker} ({motor_label}): PIORA "
                    f"WR {wr_bl:.1%}→{wr_ex:.1%} | Ret {mean_bl:.2%}→{mean_ex:.2%}"
                )
            else:
                contagens["empata"] += 1
                detalhes.append(
                    f"  {ticker} ({motor_label}): EMPATA "
                    f"WR {wr_bl:.1%}→{wr_ex:.1%} | Ret {mean_bl:.2%}→{mean_ex:.2%}"
                )

    # Classificação final
    total = sum(contagens.values())
    if total == 0:
        classificacao = "INCONCLUSIVO"
    elif contagens["melhora"] > contagens["piora"]:
        classificacao = "RESIDUO_MELHORA"
    elif contagens["piora"] > contagens["melhora"]:
        classificacao = "RESIDUO_PIORA"
    elif contagens["melhora"] == contagens["piora"] and contagens["melhora"] > 0:
        classificacao = "INCONCLUSIVO"
    else:
        classificacao = "RESIDUO_EMPATA"

    return {
        "classificacao": classificacao,
        "detalhes": detalhes,
        "n_melhora": contagens["melhora"],
        "n_empata": contagens["empata"],
        "n_piora": contagens["piora"],
        "n_inconclusivo": contagens["inconclusivo"],
    }