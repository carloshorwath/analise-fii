"""Walk-Forward Rolling — Validacao out-of-sample genuina.

Treina em janela rolante de train_months meses, prediz os proximos
predict_months meses, avanca. Produz serie de sinais e retornos
out-of-sample sem selecao de parametros viciada.

Cada step:
1. Calcula P/VP percentil rolling na janela de treino
2. Define threshold BUY/SELL baseado no treino (percentil extremo)
3. Aplica threshold no periodo de predicao (out-of-sample)
4. Registra sinal e retorno real
"""

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.data.database import CdiDiario, Dividendo
from src.fii_analysis.models.episodes import get_pvp_series
from src.fii_analysis.models.trade_simulator import simulate_trades, simulate_buy_and_hold


def walk_forward_roll(ticker, session, train_months=18, predict_months=1,
                      pvp_pct_buy=15, pvp_pct_sell=85, forward_days=20,
                      alt_df=None, value_col="pvp", pct_col="pvp_pct"):
    """Executa walk-forward rolling com janela de treino deslizante.

    Parameters
    ----------
    ticker : str
    session : SQLAlchemy session
    train_months : int
        Meses da janela de treino (default 18).
    predict_months : int
        Meses do periodo de predicao out-of-sample (default 1).
    pvp_pct_buy : float
        Percentil P/VP para BUY (default 15).
    pvp_pct_sell : float
        Percentil P/VP para SELL (default 85).
    forward_days : int
        Pregoes do retorno forward (default 20).
    alt_df : DataFrame, optional
        DataFrame alternativo com colunas data, fechamento, fechamento_aj,
        value_col, pct_col. Se None, usa get_pvp_series().
    value_col : str
        Coluna com o valor bruto do sinal (default 'pvp').
    pct_col : str
        Coluna com o percentil rolling do sinal (default 'pvp_pct').

    Returns
    -------
    dict com signals (DataFrame), cumulative, summary.
    """
    if alt_df is not None:
        df = alt_df.copy()
    else:
        df = get_pvp_series(ticker, session)
    if df.empty:
        return {"error": "Dados insuficientes"}

    df = df.dropna(subset=[pct_col]).copy()
    df = df.sort_values("data").reset_index(drop=True)
    # Mapa data → posicao de pregao (indice iloc no df completo de pregoes)
    date_to_idx = {row["data"]: i for i, row in df.iterrows()}

    # Forward return
    df["fwd_ret"] = df["fechamento_aj"].shift(-forward_days) / df["fechamento_aj"] - 1.0

    # Split em janelas
    train_days = train_months * 21  # ~21 uteis/mes
    predict_days = predict_months * 21
    step_days = predict_days  # avanca predict_days de cada vez

    if len(df) < train_days + predict_days + forward_days:
        return {"error": f"Dados insuficientes: {len(df)} pregoes, precisa ~{train_days + predict_days + forward_days}"}

    signals = []
    start = train_days

    while start + predict_days <= len(df) - forward_days:
        train_df = df.iloc[start - train_days:start]
        test_df = df.iloc[start:start + predict_days]

        if train_df.empty or test_df.empty:
            start += step_days
            continue

        # Calcula percentis DO TREINO para definir o que e "extremo"
        # P/VP percentil ja e rolling(504), mas restringimos ao treino
        train_vals = train_df[value_col].dropna()
        if len(train_vals) < 63:
            start += step_days
            continue

        buy_threshold = float(np.percentile(train_vals, pvp_pct_buy))
        sell_threshold = float(np.percentile(train_vals, pvp_pct_sell))

        # Para cada dia de teste, classifica o sinal
        for _, row in test_df.iterrows():
            if pd.isna(row.get("fwd_ret")):
                continue

            val = row[value_col]
            if pd.isna(val):
                continue

            if val <= buy_threshold:
                signal = "BUY"
            elif val >= sell_threshold:
                signal = "SELL"
            else:
                signal = "NEUTRO"

            signals.append({
                "data": row["data"],
                "trade_idx": int(date_to_idx[row["data"]]),
                "pvp": val,
                "preco": float(row["fechamento"]),
                "preco_aj": float(row["fechamento_aj"]),
                "pvp_buy_thr": buy_threshold,
                "pvp_sell_thr": sell_threshold,
                "signal": signal,
                "fwd_ret": row["fwd_ret"],
            })

        start += step_days

    if not signals:
        return {"error": "Nenhum sinal gerado — janelas insuficientes"}

    signals_df = pd.DataFrame(signals)
    cdi_df = _load_cdi_series(session, signals_df["data"].min(), signals_df["data"].max())
    div_df = _load_dividend_series(ticker, session, signals_df["data"].min(), signals_df["data"].max())

    # Summary por tipo de sinal — thinning REAL para independencia
    summary = {}
    for sig in ["BUY", "SELL", "NEUTRO"]:
        subset = signals_df[signals_df["signal"] == sig]
        if subset.empty:
            summary[sig] = {"n": 0}
            continue

        rets = subset["fwd_ret"].dropna().values
        n_raw = len(rets)

        # THINNING por distancia real em pregoes, nao por contagem de sinais.
        thinned_subset = _thin_by_gap(subset.dropna(subset=["fwd_ret"]), forward_days)
        thinned_rets = thinned_subset["fwd_ret"].astype(float).values
        n_eff = len(thinned_rets)
        mean_r = float(np.mean(thinned_rets)) if n_eff > 0 else None

        # CI bootstrap sobre observacoes independentes (thinned)
        ci_lower, ci_upper = None, None
        if n_eff >= 5:
            rng = np.random.default_rng(42)
            boot = []
            for _ in range(2000):
                boot.append(float(np.mean(rng.choice(thinned_rets, size=n_eff, replace=True))))
            boot = np.array(boot)
            ci_lower = float(np.percentile(boot, 2.5))
            ci_upper = float(np.percentile(boot, 97.5))

        # t-test sobre observacoes independentes
        t_stat, p_value = None, None
        if n_eff >= 5:
            t_stat, p_value = float(stats.ttest_1samp(thinned_rets, 0.0)[0]), float(stats.ttest_1samp(thinned_rets, 0.0)[1])

        summary[sig] = {
            "n": n_raw,
            "n_effective": n_eff,
            "mean": mean_r,
            "mean_raw": float(np.mean(rets)),
            "median": float(np.median(thinned_rets)) if n_eff > 0 else None,
            "std": float(np.std(thinned_rets, ddof=1)) if n_eff >= 2 else None,
            "win_rate": float(np.mean(thinned_rets > 0)) if n_eff > 0 else None,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "t_stat": t_stat,
            "p_value": p_value,
        }

    # BUY vs SELL comparison — thinning GLOBAL para independencia cruzada.
    # Relógios separados por grupo (acima) servem para estatísticas univariadas.
    # Para Mann-Whitney, garantir que nenhum par BUY/SELL tenha janelas sobrepostas.
    global_thinned = _thin_global_signals(signals_df, forward_days, date_to_idx)
    buy_global = global_thinned[global_thinned["signal"] == "BUY"]["fwd_ret"].dropna().values
    sell_global = global_thinned[global_thinned["signal"] == "SELL"]["fwd_ret"].dropna().values

    comparison = None
    if len(buy_global) >= 5 and len(sell_global) >= 5:
        mw_stat, mw_p = stats.mannwhitneyu(buy_global, sell_global, alternative="greater")
        comparison = {
            "buy_mean": float(np.mean(buy_global)),
            "sell_mean": float(np.mean(sell_global)),
            "spread": float(np.mean(buy_global) - np.mean(sell_global)),
            "mw_stat": float(mw_stat),
            "mw_pvalue": float(mw_p),
            "n_buy_eff": len(buy_global),
            "n_sell_eff": len(sell_global),
        }

    # Simulacao com motor de trades reais nao sobrepostos
    cum_buy = simulate_trades(signals_df, "BUY", forward_days, cdi_df, div_df)
    cum_hold = simulate_buy_and_hold(
        signals_df,
        valuation_dates=cum_buy.get("dates", []),
        start_date=signals_df["data"].iloc[0],
        cdi_df=cdi_df,
        div_df=div_df,
    )

    return {
        "signals": signals_df,
        "summary": summary,
        "comparison": comparison,
        "cumulative": {
            "follow_buy": cum_buy,
            "hold": cum_hold,
        },
        "params": {
            "train_months": train_months,
            "predict_months": predict_months,
            "pvp_pct_buy": pvp_pct_buy,
            "pvp_pct_sell": pvp_pct_sell,
            "forward_days": forward_days,
        },
        "n_steps": len(signals_df["data"].dt.to_period("M").unique()),
    }


def _thin_global_signals(signals_df, forward_days, date_to_idx):
    """Thinning cronologico global sobre BUY+SELL combinados.

    Usa date_to_idx (data → posicao no df original de pregoes) para medir o
    gap em pregoes exatos — evita aproximacoes de calendario.
    Usado APENAS para comparacao Mann-Whitney BUY vs SELL.
    Estatisticas univariadas de cada grupo usam thinning proprio (relogios separados).
    """
    df = signals_df[signals_df["signal"].isin(["BUY", "SELL"])].sort_values("data").reset_index(drop=True)
    if df.empty:
        return df

    if "trade_idx" in df.columns:
        return _thin_by_gap(df, forward_days)

    kept = []
    last_idx = -9999

    for _, row in df.iterrows():
        ep_idx = date_to_idx.get(row["data"], -9999)
        if ep_idx - last_idx >= forward_days:
            kept.append(row)
            last_idx = ep_idx

    return pd.DataFrame(kept) if kept else df.iloc[:0]


def _thin_by_gap(df, forward_days, idx_col="trade_idx"):
    """Aplica thinning guloso usando a distancia real em pregoes."""
    if df.empty:
        return df

    df = df.sort_values(idx_col).reset_index(drop=True)
    kept = []
    last_idx = -9999
    for _, row in df.iterrows():
        current_idx = int(row[idx_col])
        if current_idx - last_idx >= forward_days:
            kept.append(row)
            last_idx = current_idx

    return pd.DataFrame(kept) if kept else df.iloc[:0]


def _load_cdi_series(session, data_inicio, data_fim):
    """Carrega CDI diario para o intervalo usado no walk-forward."""
    rows = session.execute(
        select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
        .where(CdiDiario.data >= data_inicio.date(), CdiDiario.data <= data_fim.date())
        .order_by(CdiDiario.data.asc())
    ).all()
    if not rows:
        return pd.DataFrame(columns=["data", "taxa_diaria_pct"])
    return pd.DataFrame(
        [{"data": pd.Timestamp(r.data), "taxa_diaria_pct": float(r.taxa_diaria_pct)} for r in rows]
    )


def _load_dividend_series(ticker, session, data_inicio, data_fim):
    """Carrega dividendos por data-com no intervalo do walk-forward."""
    rows = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(
            Dividendo.ticker == ticker,
            Dividendo.data_com >= data_inicio.date(),
            Dividendo.data_com <= data_fim.date(),
            Dividendo.valor_cota.isnot(None),
        )
        .order_by(Dividendo.data_com.asc())
    ).all()
    if not rows:
        return pd.DataFrame(columns=["data_com", "valor_cota"])
    return pd.DataFrame(
        [{"data_com": pd.Timestamp(r.data_com), "valor_cota": float(r.valor_cota)} for r in rows]
    )


