"""Episodios Discretos — Extremos de P/VP.

Identifica momentos em que o P/VP entrou em territorio extremo
(percentil rolling < p_low ou > p_high) e rastreia o retorno forward.

Principios:
- Cada episodio e INDEPENDENTE: thin by forward_days apos a entrada
- Nao usa OR de multiplas condicoes — so P/VP percentil
- Nao usa retornos sobrepostos — cada observacao representa um periodo distinto
- Thresholds sao percentis rolling, nao numeros magicos
"""

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.data.database import (
    PrecoDiario,
    RelatorioMensal,
    get_cnpj_by_ticker,
)


def get_pvp_series(ticker, session, rolling_window=504):
    """Retorna DataFrame com data, preco, vp_por_cota, pvp, pvp_percentil."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return pd.DataFrame()

    prices_db = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()

    if not prices_db:
        return pd.DataFrame()

    prices = pd.DataFrame([
        {"data": pd.Timestamp(p.data), "fechamento": float(p.fechamento),
         "fechamento_aj": float(p.fechamento_aj)}
        for p in prices_db if p.fechamento is not None and p.fechamento_aj is not None
    ])

    reports_db = session.execute(
        select(RelatorioMensal.data_entrega, RelatorioMensal.vp_por_cota)
        .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega.isnot(None))
        .order_by(RelatorioMensal.data_entrega.asc())
    ).all()

    if not reports_db:
        return pd.DataFrame()

    reports = pd.DataFrame([
        {"data_entrega": pd.Timestamp(r.data_entrega), "vp_por_cota": float(r.vp_por_cota) if r.vp_por_cota else None}
        for r in reports_db
    ]).dropna(subset=["vp_por_cota"]).sort_values("data_entrega")

    df = pd.merge_asof(
        prices,
        reports[["data_entrega", "vp_por_cota"]],
        left_on="data", right_on="data_entrega", direction="backward",
    )

    df = df.dropna(subset=["vp_por_cota"])
    df = df[df["vp_por_cota"] > 0].copy()

    df["pvp"] = df["fechamento"] / df["vp_por_cota"]
    min_periods = min(63, rolling_window)
    df["pvp_pct"] = df["pvp"].rolling(rolling_window, min_periods=min_periods).rank(pct=True) * 100

    return df


def identify_episodes(df, pvp_pct_low=10, pvp_pct_high=90, forward_days=30,
                      min_hold_days=None, rolling_window=504,
                      value_col="pvp", pct_col="pvp_pct"):
    """Identifica episodios de P/VP extremo com thinning para independencia.

    Parameters
    ----------
    df : DataFrame com colunas data, fechamento_aj e as colunas de sinal
    pvp_pct_low : percentil abaixo do qual = BUY
    pvp_pct_high : percentil acima do qual = SELL
    forward_days : janela de retorno forward
    min_hold_days : intervalo minimo entre episodios em DIAS UTEIS.
        Deve ser >= forward_days para garantir que retornos nao se sobreponham
        e o bootstrap i.i.d. seja valido. Default = forward_days (sincronizado
        automaticamente).
    rolling_window : janela para calculo do percentil
    value_col : coluna com o valor bruto do sinal (default 'pvp')
    pct_col : coluna com o percentil rolling do sinal (default 'pvp_pct')

    Returns
    -------
    dict com episodes_buy, episodes_sell, summary
    """
    if min_hold_days is None:
        min_hold_days = forward_days

    if min_hold_days < forward_days:
        raise ValueError(
            f"min_hold_days={min_hold_days} < forward_days={forward_days}. "
            "Episodios com retornos forward sobrepostos violam a hipotese de "
            "independencia do bootstrap i.i.d. e do t-test. "
            "Use min_hold_days >= forward_days."
        )

    df = df.copy()

    # Recalcular percentil rolling APENAS se pct_col='pvp_pct' e não existir
    if pct_col not in df.columns or (pct_col == "pvp_pct" and value_col == "pvp"):
        min_periods = min(63, rolling_window)
        df["pvp_pct"] = df["pvp"].rolling(rolling_window, min_periods=min_periods).rank(pct=True) * 100
        pct_col = "pvp_pct"

    df = df.dropna(subset=[pct_col]).copy()
    df = df.sort_values("data").reset_index(drop=True)

    # Forward return
    df["fwd_ret"] = df["fechamento_aj"].shift(-forward_days) / df["fechamento_aj"] - 1.0

    # Build index of trading days for gap calculation
    date_to_idx = {d: i for i, d in enumerate(df["data"])}

    episodes_buy = []
    episodes_sell = []
    last_buy_idx = -9999
    last_sell_idx = -9999

    for idx, row in df.iterrows():
        if pd.isna(row["fwd_ret"]):
            continue

        # Gap em DIAS UTEIS (indice do DataFrame = pregões consecutivos)
        current_idx = idx

        pct_val = row[pct_col]

        # BUY episode: percentil <= pvp_pct_low
        if pct_val <= pvp_pct_low:
            if current_idx - last_buy_idx >= min_hold_days:
                episodes_buy.append({
                    "data": row["data"],
                    "pvp": row[value_col],
                    "pvp_pct": pct_val,
                    "preco": row["fechamento"],
                    "fwd_ret": row["fwd_ret"],
                })
                last_buy_idx = current_idx

        # SELL episode: percentil >= pvp_pct_high
        if pct_val >= pvp_pct_high:
            if current_idx - last_sell_idx >= min_hold_days:
                episodes_sell.append({
                    "data": row["data"],
                    "pvp": row[value_col],
                    "pvp_pct": pct_val,
                    "preco": row["fechamento"],
                    "fwd_ret": row["fwd_ret"],
                })
                last_sell_idx = current_idx

    buy_df = pd.DataFrame(episodes_buy) if episodes_buy else pd.DataFrame()
    sell_df = pd.DataFrame(episodes_sell) if episodes_sell else pd.DataFrame()

    summary = _compute_summary(buy_df, sell_df, forward_days, date_to_idx)

    return {
        "buy": buy_df,
        "sell": sell_df,
        "summary": summary,
        "params": {
            "pvp_pct_low": pvp_pct_low,
            "pvp_pct_high": pvp_pct_high,
            "forward_days": forward_days,
            "min_hold_days": min_hold_days,
            "rolling_window": rolling_window,
        },
    }


def _thin_global(buy_df, sell_df, forward_days, date_to_idx):
    """Thinning cronologico global sobre BUY+SELL combinados.

    Para garantir independencia na comparacao BUY vs SELL, combina os dois
    grupos, ordena por data e aplica thinning guloso: mantem um episodio so
    se seu indice de pregao estiver >= forward_days apos o ultimo mantido,
    independente do tipo. Usado APENAS para Mann-Whitney; estatisticas
    univariadas de cada grupo usam thinning proprio (relogios separados).
    """
    combined = []
    for _, row in buy_df.iterrows():
        combined.append({"data": row["data"], "tipo": "buy", "fwd_ret": row["fwd_ret"]})
    for _, row in sell_df.iterrows():
        combined.append({"data": row["data"], "tipo": "sell", "fwd_ret": row["fwd_ret"]})

    combined.sort(key=lambda x: x["data"])

    kept = []
    last_idx = -9999
    for ep in combined:
        ep_idx = date_to_idx.get(ep["data"], -9999)
        if ep_idx - last_idx >= forward_days:
            kept.append(ep)
            last_idx = ep_idx

    buy_g = pd.DataFrame([e for e in kept if e["tipo"] == "buy"])
    sell_g = pd.DataFrame([e for e in kept if e["tipo"] == "sell"])
    return buy_g, sell_g


def _compute_summary(buy_df, sell_df, forward_days, date_to_idx=None):
    """Calcula estatisticas descritivas dos episodios."""
    result = {"buy": {}, "sell": {}}

    for label, df in [("buy", buy_df), ("sell", sell_df)]:
        if df.empty:
            result[label] = {"n": 0, "mean": None, "median": None, "std": None,
                             "win_rate": None, "ci_lower": None, "ci_upper": None,
                             "min": None, "max": None}
            continue

        rets = df["fwd_ret"].values
        n = len(rets)
        mean_r = float(np.mean(rets))
        median_r = float(np.median(rets))
        std_r = float(np.std(rets, ddof=1)) if n >= 2 else 0.0
        win_rate = float(np.mean(rets > 0))

        # Bootstrap CI (observacoes sao independentes — thinning ja aplicado)
        ci_lower, ci_upper = None, None
        if n >= 5:
            rng = np.random.default_rng(42)
            boot_means = []
            for _ in range(2000):
                sample = rng.choice(rets, size=n, replace=True)
                boot_means.append(float(np.mean(sample)))
            boot_means = np.array(boot_means)
            ci_lower = float(np.percentile(boot_means, 2.5))
            ci_upper = float(np.percentile(boot_means, 97.5))

        # t-test (valido pq observacoes sao independentes)
        t_stat, p_value = None, None
        if n >= 5:
            t_stat, p_value = float(stats.ttest_1samp(rets, 0.0)[0]), float(stats.ttest_1samp(rets, 0.0)[1])

        result[label] = {
            "n": n,
            "mean": mean_r,
            "median": median_r,
            "std": std_r,
            "win_rate": win_rate,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "t_stat": t_stat,
            "p_value": p_value,
            "min": float(np.min(rets)),
            "max": float(np.max(rets)),
        }

    # Comparacao BUY vs SELL — thinning GLOBAL para independencia cruzada.
    # Estatisticas univariadas acima usam thinning proprio de cada grupo.
    # Aqui o Mann-Whitney exige que nenhum par BUY/SELL compartilhe janela forward.
    if not buy_df.empty and not sell_df.empty:
        if date_to_idx is not None:
            buy_cmp, sell_cmp = _thin_global(buy_df, sell_df, forward_days, date_to_idx)
        else:
            buy_cmp, sell_cmp = buy_df, sell_df

        buy_rets = buy_cmp["fwd_ret"].values if not buy_cmp.empty else np.array([])
        sell_rets = sell_cmp["fwd_ret"].values if not sell_cmp.empty else np.array([])
        buy_minus_sell = (
            float(np.mean(buy_rets) - np.mean(sell_rets))
            if len(buy_rets) > 0 and len(sell_rets) > 0 else None
        )

        if len(buy_rets) >= 5 and len(sell_rets) >= 5:
            mw_stat, mw_p = stats.mannwhitneyu(buy_rets, sell_rets, alternative="greater")
            result["comparison"] = {
                "mw_stat": float(mw_stat),
                "mw_pvalue": float(mw_p),
                "buy_minus_sell": buy_minus_sell,
                "n_buy_global": len(buy_rets),
                "n_sell_global": len(sell_rets),
            }
        else:
            result["comparison"] = {
                "mw_stat": None, "mw_pvalue": None,
                "buy_minus_sell": buy_minus_sell,
                "n_buy_global": len(buy_rets),
                "n_sell_global": len(sell_rets),
            }
    else:
        result["comparison"] = None

    return result
