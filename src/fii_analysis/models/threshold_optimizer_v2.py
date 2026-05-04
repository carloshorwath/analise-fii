"""Otimizador de Thresholds — versao consolidada (V2).

Grid search + thinning independente + placebo fundidos com extensoes de robustez:
- Metricas de risco ajustado: Sharpe, Sortino, max drawdown, win rate
- Diagnostico de overfitting (degradacao treino->validacao->teste)
- Modelagem de custos de transacao (emolumentos B3)
- Intervalos de confianca via bootstrap i.i.d. em amostra independente
- Analise de sensibilidade 2D (heatmap)
- Analise por regime de mercado (ex-ante via nivel P/VP)

Domain boundary: sinais BUY/SELL baseados em P/VP percentil, meses alerta,
DY Gap percentil. Forward return em janela fixa de 20 pregoes.
NAO e recomendacao de investimento — modelo experimental com poucos eventos.
"""

import itertools
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.config import CUSTO_POR_TRADE
from src.fii_analysis.data.database import (
    CdiDiario, Dividendo, PrecoDiario, RelatorioMensal, get_cnpj_by_ticker,
)
from src.fii_analysis.models.trade_simulator import simulate_trades, simulate_buy_and_hold
from src.fii_analysis.models.walk_forward_rolling import _load_cdi_series, _load_dividend_series


class ThresholdOptimizerV2:
    """Otimizador de thresholds com robustez estatistica.

    Classe unica: inclui toda a logica de grid search, splits temporais,
    inferencia com thinning independente e placebo, mais as extensoes de
    risco, overfitting, bootstrap CI, sensibilidade 2D e analise de regime.
    """

    def __init__(self):
        self.pvp_percentil_buy_grid = [15, 20, 25, 30, 35, 40, 45, 50]
        self.pvp_percentil_sell_grid = [55, 60, 65, 70, 75, 80, 85, 90]
        self.meses_alerta_sell_grid = [1, 2]
        self.dy_gap_pct_sell_grid = [25, 35]
        self.forward_days = 20

    # =========================================================================
    # DATA
    # =========================================================================

    def _get_enriched_daily_data(self, ticker, session):
        cnpj = get_cnpj_by_ticker(ticker, session)
        if not cnpj:
            return pd.DataFrame()

        prices_db = session.execute(
            select(PrecoDiario.data, PrecoDiario.fechamento, PrecoDiario.fechamento_aj, PrecoDiario.volume)
            .where(PrecoDiario.ticker == ticker)
            .order_by(PrecoDiario.data.asc())
        ).all()
        if not prices_db:
            return pd.DataFrame()

        prices_df = pd.DataFrame([
            {"data": p.data, "fechamento": float(p.fechamento), "fechamento_aj": float(p.fechamento_aj), "volume": int(p.volume) if p.volume is not None else None}
            for p in prices_db if p.fechamento is not None and p.fechamento_aj is not None
        ])
        prices_df["data"] = pd.to_datetime(prices_df["data"])

        reports_db = session.execute(
            select(
                RelatorioMensal.data_referencia,
                RelatorioMensal.data_entrega,
                RelatorioMensal.vp_por_cota,
                RelatorioMensal.rentab_efetiva,
                RelatorioMensal.rentab_patrim,
            )
            .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega.isnot(None))
            .order_by(RelatorioMensal.data_referencia.asc())
        ).all()
        if not reports_db:
            return pd.DataFrame()

        reports_df = pd.DataFrame([
            {
                "data_entrega": r.data_entrega,
                "vp_por_cota": float(r.vp_por_cota) if r.vp_por_cota else None,
                "rentab_efetiva": float(r.rentab_efetiva) if r.rentab_efetiva else None,
                "rentab_patrim": float(r.rentab_patrim) if r.rentab_patrim else None,
            }
            for r in reports_db
        ])
        reports_df["data_entrega"] = pd.to_datetime(reports_df["data_entrega"])
        reports_df = reports_df.sort_values("data_entrega")

        consec = 0
        meses_alerta_list = []
        for _, r in reports_df.iterrows():
            ef, pa = r["rentab_efetiva"], r["rentab_patrim"]
            if ef is not None and pa is not None:
                consec = 0 if (pa >= 0 and ef >= pa) else consec + 1
            meses_alerta_list.append(consec)
        reports_df["meses_alerta"] = meses_alerta_list

        df = pd.merge_asof(
            prices_df,
            reports_df[["data_entrega", "vp_por_cota", "meses_alerta"]],
            left_on="data",
            right_on="data_entrega",
            direction="backward",
        )

        df["pvp"] = df["fechamento"] / df["vp_por_cota"]
        df["pvp_pct"] = df["pvp"].rolling(504, min_periods=63).rank(pct=True) * 100

        df = self._add_dy_gap_pct(df, ticker, session)

        df["fwd_ret"] = (df["fechamento_aj"].shift(-self.forward_days) / df["fechamento_aj"]) - 1.0

        return df.dropna(subset=["pvp_pct", "meses_alerta", "fwd_ret"])

    def _add_dy_gap_pct(self, df, ticker, session):
        """DY Gap percentil rolling para todos os dias em batch."""
        if df.empty:
            df["dy_gap_pct"] = np.nan
            return df

        data_min = (df["data"].min() - pd.DateOffset(months=13)).date()
        data_max = df["data"].max().date()

        divs = session.execute(
            select(Dividendo.data_com, Dividendo.valor_cota)
            .where(
                Dividendo.ticker == ticker,
                Dividendo.data_com >= data_min,
                Dividendo.data_com <= data_max,
                Dividendo.valor_cota.isnot(None),
            )
            .order_by(Dividendo.data_com.asc())
        ).all()

        if not divs:
            df = df.copy()
            df["dy_gap_pct"] = np.nan
            return df

        div_dates = pd.to_datetime([d.data_com for d in divs])
        div_vals = np.array([float(d.valor_cota) for d in divs])

        cdi_rows = session.execute(
            select(CdiDiario.data, CdiDiario.taxa_diaria_pct)
            .where(CdiDiario.data >= data_min, CdiDiario.data <= data_max)
            .order_by(CdiDiario.data.asc())
        ).all()
        cdi_dates = pd.to_datetime([c.data for c in cdi_rows])
        cdi_vals = np.array([float(c.taxa_diaria_pct) for c in cdi_rows])

        price_dates_arr = df["data"].values
        price_vals_arr = df["fechamento"].values

        gaps = np.full(len(df), np.nan)

        for i, d in enumerate(df["data"]):
            inicio_12m = d - pd.DateOffset(months=12)

            div_mask = (div_dates > inicio_12m) & (div_dates <= d)
            soma = div_vals[div_mask].sum()
            if soma == 0:
                continue

            pidx = np.searchsorted(price_dates_arr, d.to_datetime64(), side="right") - 1
            if pidx < 0:
                continue
            p = price_vals_arr[pidx]
            if p == 0:
                continue

            cdi_mask = (cdi_dates >= inicio_12m) & (cdi_dates <= d)
            taxas = cdi_vals[cdi_mask]
            if len(taxas) < 200:
                continue

            cdi_12m = np.prod(1.0 + taxas / 100.0) - 1.0
            gaps[i] = (soma / p) - cdi_12m

        df = df.copy()
        df["dy_gap"] = gaps
        df["dy_gap_pct"] = pd.Series(gaps, index=df.index).rolling(252, min_periods=50).rank(pct=True) * 100
        return df

    # =========================================================================
    # SPLITS
    # =========================================================================

    def _make_splits(self, df):
        n = len(df)
        if n < 200:
            return None
        n_train = int(n * 0.6)
        n_val = int(n * 0.2)
        # Gap >= forward_days para evitar vazamento de labels entre splits.
        gap = self.forward_days
        return {
            "train": df.iloc[:n_train],
            "val": df.iloc[n_train + gap: n_train + gap + n_val],
            "test": df.iloc[n_train + gap + n_val + gap:],
        }

    # =========================================================================
    # INFERENCIA ESTATISTICA
    # =========================================================================

    @staticmethod
    def _is_degenerate(returns):
        """Detecta serie degenerada: variancia zero, quase-constante, ou poucos valores unicos.

        Guard relativo+estrutural: evita que bootstrap ou t-test receba serie
        sem variacao real e produza p-valor espurio (ex: p=0 para retornos constantes).
        n_unique <= 2: com apenas 2 valores distintos o bootstrap circular colapsa
        num reticulado discreto pequeno e o p-valor fica descalibrado.
        """
        a = np.asarray(returns, dtype=float)
        if len(a) < 2:
            return True
        std = float(np.std(a))
        mean = float(np.mean(a))
        if std < 1e-8 + 1e-4 * max(abs(mean), 1e-6):
            return True
        if float(np.ptp(a)) < 1e-10:
            return True
        if len(np.unique(np.round(a, 8))) <= 2:
            return True
        return False

    def _thin_returns(self, df, mask):
        """Retorna apenas os retornos forward independentes."""
        thinned_df = self._thin_df(df, mask)
        return thinned_df["fwd_ret"].astype(float).tolist()

    def _thin_df(self, df, mask):
        """Seleciona observacoes independentes com gap minimo de forward_days."""
        valid_mask = (mask & df["fwd_ret"].notna()).to_numpy()
        kept_positions = []
        last_pos = -9999
        for pos, is_valid in enumerate(valid_mask):
            if is_valid and pos - last_pos >= self.forward_days:
                kept_positions.append(pos)
                last_pos = pos

        if not kept_positions:
            return df.iloc[0:0].copy()
        return df.iloc[kept_positions].copy()

    def _build_signal_masks(self, df, params):
        """Constroi mascaras BUY/SELL de forma centralizada."""
        has_dy_gap = "dy_gap_pct" in df.columns
        buy_mask = df["pvp_pct"] <= params["pvp_percentil_buy"]

        if has_dy_gap:
            dg = df["dy_gap_pct"].fillna(999.0)
            dy_gap_sell_mask = dg < params.get("dy_gap_pct_sell", 35)
        else:
            dy_gap_sell_mask = pd.Series(False, index=df.index)

        sell_mask = (
            (df["pvp_pct"] >= params["pvp_percentil_sell"])
            | (df["meses_alerta"] >= params["meses_alerta_sell"])
            | dy_gap_sell_mask
        )
        return buy_mask, sell_mask

    # =========================================================================
    # AVALIACAO
    # =========================================================================

    def _evaluate(self, df, params):
        """Avalia um conjunto de parametros em um split.

        BUY: H0 mean=0 bicaudal, ttest_1samp sobre retornos thinned.
        SELL: H0 E[r_sell - r_mkt] >= 0, H1 < 0, unicaudal esquerda, thinned.

        Thinning (forward_days gap entre observacoes) garante independencia
        serial diretamente na amostra inferencial, evitando tratar uma serie
        filtrada irregular como se tivesse espacamento temporal uniforme.

        Justificativa SELL unicaudal (pre-especificado, nao post-hoc):
          pvp_pct alto  → fundo precificado acima do VP historico (caro)
          meses_alerta  → rentabilidade efetiva < patrimonial (distribuindo capital)
          dy_gap_pct baixo → DY caiu abaixo do CDI (spread negativo)
        Essas condicoes precedem subperformance por mecanismo economico. A direcao
        H1 < 0 foi fixada antes do grid search.
        """
        buy_mask, sell_mask = self._build_signal_masks(df, params)

        # Medias descritivas (retornos brutos, todos os sinais)
        buy_returns_all = df.loc[buy_mask, "fwd_ret"].dropna().tolist()
        sell_returns_all = df.loc[sell_mask, "fwd_ret"].dropna().tolist()
        avg_buy = float(np.mean(buy_returns_all)) if buy_returns_all else 0.0
        avg_sell = float(np.mean(sell_returns_all)) if sell_returns_all else 0.0
        unconditional_mean = float(df["fwd_ret"].mean()) if len(df) > 0 else 0.0

        # Thinned para inferencia (independencia garantida)
        buy_thinned = self._thin_returns(df, buy_mask)
        sell_thinned = self._thin_returns(df, sell_mask)
        avg_buy_indep = float(np.mean(buy_thinned)) if buy_thinned else 0.0
        avg_sell_indep = float(np.mean(sell_thinned)) if sell_thinned else 0.0
        sell_excess_thinned = [r - unconditional_mean for r in sell_thinned]

        # BUY: t-test bicaudal H0: mean=0
        buy_degenerate = self._is_degenerate(buy_thinned) if len(buy_thinned) >= 2 else True
        if len(buy_thinned) >= 4 and not buy_degenerate:
            _, p_buy = stats.ttest_1samp(buy_thinned, 0.0)
            p_buy = float(p_buy)
        else:
            p_buy = 1.0

        # SELL: t-test unicaudal esquerda H0: E[excess] >= 0
        sell_degenerate = self._is_degenerate(sell_excess_thinned) if len(sell_excess_thinned) >= 2 else True
        if len(sell_excess_thinned) >= 4 and not sell_degenerate:
            _, p_sell = stats.ttest_1samp(sell_excess_thinned, 0.0, alternative="less")
            p_sell = float(p_sell)
        else:
            p_sell = 1.0

        return {
            "n_buy": len(buy_returns_all),
            "n_buy_thinned": len(buy_thinned),
            "avg_return_buy": avg_buy,
            "avg_return_buy_independent": avg_buy_indep,
            "p_value_buy": p_buy,
            "buy_se_degenerate": buy_degenerate,
            "n_sell": len(sell_returns_all),
            "n_sell_thinned": len(sell_thinned),
            "avg_return_sell": avg_sell,
            "avg_return_sell_independent": avg_sell_indep,
            "sell_excess_vs_market": avg_sell - unconditional_mean,
            "sell_excess_vs_market_independent": avg_sell_indep - unconditional_mean,
            "p_value_sell": p_sell,
            "sell_se_degenerate": sell_degenerate,
            "unconditional_mean": unconditional_mean,
        }

    def _run_placebo(self, test_df, params, full_df, n_shuffles=500):
        if len(test_df) == 0:
            return {"p_value_buy": 1.0, "p_value_sell": 1.0, "avg_placebo_buy": 0.0, "avg_placebo_sell": 0.0}

        real = self._evaluate(test_df, params)
        pool = test_df["fwd_ret"].dropna().to_numpy()
        rng = np.random.default_rng(42)
        block = self.forward_days
        n_pool = len(pool)

        def _block_sample_mean(size):
            n_blocks = max(1, size // block)
            starts = rng.integers(0, n_pool, size=n_blocks)
            sample = np.concatenate([
                np.take(pool, np.arange(s, s + block) % n_pool) for s in starts
            ])[:size]
            return float(np.mean(sample))

        shuffled_buys, shuffled_sells = [], []
        for _ in range(n_shuffles):
            shuffled_buys.append(
                _block_sample_mean(max(1, real["n_buy_thinned"])) if real["n_buy_thinned"] > 0 else 0.0
            )
            shuffled_sells.append(
                _block_sample_mean(max(1, real["n_sell_thinned"])) if real["n_sell_thinned"] > 0 else 0.0
            )

        p_buy = float(np.mean(np.abs(shuffled_buys) >= abs(real["avg_return_buy_independent"])))

        real_excess = real.get(
            "sell_excess_vs_market_independent",
            real.get("sell_excess_vs_market", real["avg_return_sell"]),
        )
        shuffled_excesses = np.array(shuffled_sells) - float(test_df["fwd_ret"].mean())
        p_sell = float(np.mean(shuffled_excesses <= real_excess))

        return {
            "p_value_buy": p_buy,
            "p_value_sell": p_sell,
            "avg_placebo_buy": float(np.mean(shuffled_buys)),
            "avg_placebo_sell": float(np.mean(shuffled_sells)),
            "sell_excess_vs_market": real_excess,
        }

    # =========================================================================
    # OTIMIZACAO
    # =========================================================================

    def optimize(self, ticker, session):
        df = self._get_enriched_daily_data(ticker, session)
        if df.empty:
            return {"error": "Dados insuficientes ou ticker nao encontrado"}

        splits = self._make_splits(df)
        if not splits or len(splits["val"]) == 0 or len(splits["test"]) == 0:
            return {"error": f"Dados insuficientes para splits (Total: {len(df)})"}

        combinations = list(itertools.product(
            self.pvp_percentil_buy_grid,
            self.pvp_percentil_sell_grid,
            self.meses_alerta_sell_grid,
            self.dy_gap_pct_sell_grid,
        ))
        n_combinations = len(combinations)

        best_params = None
        best_val_score = -999.0
        results_grid = []

        for pvp_b, pvp_s, al_s, dy_s in combinations:
            if pvp_s - pvp_b < 15:
                continue
            params = {
                "pvp_percentil_buy": pvp_b,
                "pvp_percentil_sell": pvp_s,
                "meses_alerta_sell": al_s,
                "dy_gap_pct_sell": dy_s,
                "forward_days": self.forward_days,
            }
            train_m = self._evaluate(splits["train"], params)
            val_m = self._evaluate(splits["val"], params)
            score = val_m["avg_return_buy"] - val_m["avg_return_sell"]

            if val_m["n_buy"] > 0 or val_m["n_sell"] > 0:
                if score > best_val_score:
                    best_val_score = score
                    best_params = params
                results_grid.append({"params": params, "train": train_m, "val": val_m, "score": score})

        if not best_params:
            return {"error": "Nenhuma combinacao valida encontrada no grid"}

        test_result = self._evaluate(splits["test"], best_params)
        test_result["p_value_buy_bonferroni"] = min(1.0, test_result["p_value_buy"] * n_combinations)
        test_result["p_value_sell_bonferroni"] = min(1.0, test_result["p_value_sell"] * n_combinations)

        placebo = self._run_placebo(splits["test"], best_params, df)
        train_score = next(r["train"] for r in results_grid if r["params"] == best_params)
        val_score = next(r["val"] for r in results_grid if r["params"] == best_params)

        return {
            "best_params": best_params,
            "train_score": train_score,
            "val_score": val_score,
            "test_result": test_result,
            "placebo": placebo,
            "n_splits": {
                "train": len(splits["train"]),
                "val": len(splits["val"]),
                "test": len(splits["test"]),
            },
            "n_combinations": n_combinations,
            "indicator_history": df.iloc[::5].to_dict("records"),
            "grid_results": results_grid,
        }

    def get_signal_hoje(self, ticker, session, params):
        df = self._get_enriched_daily_data(ticker, session)
        if df.empty:
            return {"sinal": "NEUTRO", "details": "Dados insuficientes"}

        row = df.iloc[-1]
        has_dy_gap = "dy_gap_pct" in df.columns

        dy_gap_sell = False
        if has_dy_gap:
            dg = row.get("dy_gap_pct", np.nan)
            if not (isinstance(dg, float) and np.isnan(dg)):
                dy_gap_sell = dg < params.get("dy_gap_pct_sell", 35)

        is_buy = row["pvp_pct"] <= params["pvp_percentil_buy"]
        is_sell = (
            row["pvp_pct"] >= params["pvp_percentil_sell"]
            or row["meses_alerta"] >= params["meses_alerta_sell"]
            or dy_gap_sell
        )

        sinal = "BUY" if is_buy else ("SELL" if is_sell else "NEUTRO")

        indicators = {
            "pvp_pct": float(row["pvp_pct"]),
            "meses_alerta": int(row["meses_alerta"]),
            "data": row["data"].strftime("%Y-%m-%d"),
        }
        if has_dy_gap:
            dg = row.get("dy_gap_pct", np.nan)
            if not (isinstance(dg, float) and np.isnan(dg)):
                indicators["dy_gap_pct"] = float(dg)

        return {"sinal": sinal, "indicators": indicators}

    # =========================================================================
    # EXTENSOES V2: ROBUSTEZ
    # =========================================================================

    def optimize_v2(self, ticker, session):
        """Otimizacao com metricas estendidas de robustez."""
        base = self.optimize(ticker, session)
        if "error" in base:
            return base

        df = self._get_enriched_daily_data(ticker, session)
        splits = self._make_splits(df)
        best_params = base["best_params"]
        test_result = base["test_result"]

        buy_mask, sell_mask = self._build_signal_masks(splits["test"], best_params)

        test_buy_returns = splits["test"].loc[buy_mask, "fwd_ret"].dropna().tolist()
        test_sell_returns = splits["test"].loc[sell_mask, "fwd_ret"].dropna().tolist()
        test_buy_returns_indep = self._thin_returns(splits["test"], buy_mask)
        test_sell_returns_indep = self._thin_returns(splits["test"], sell_mask)

        buy_risk = self.compute_risk_metrics(test_buy_returns, independent_returns=test_buy_returns_indep)
        sell_risk = self.compute_risk_metrics(test_sell_returns, independent_returns=test_sell_returns_indep)
        buy_risk_adj = self.compute_risk_metrics(
            test_buy_returns,
            independent_returns=test_buy_returns_indep,
            cost_per_trade=CUSTO_POR_TRADE,
        )

        overfit = self.compute_overfitting_score(base["train_score"], base["val_score"], test_result)
        buy_ci = self.compute_bootstrap_ci(test_buy_returns_indep)
        sell_ci = self.compute_bootstrap_ci(test_sell_returns_indep)
        sensitivity_df = self.compute_sensitivity_2d(splits, best_params)
        # Mediana do P/VP congelada no treino — evita look-ahead no teste
        train_pvp_median = float(splits["train"]["pvp_pct"].median())
        regime = self._analyze_regime(
            splits["test"], test_buy_returns, test_sell_returns,
            best_params, train_pvp_median=train_pvp_median,
        )

        # Simulation on Test Set
        test_df = splits["test"].copy()
        
        signals = []
        for i, (idx, row) in enumerate(test_df.iterrows()):
            if buy_mask.loc[idx]:
                signal = "BUY"
            elif sell_mask.loc[idx]:
                signal = "SELL"
            else:
                signal = "NEUTRO"
                
            signals.append({
                "data": row["data"],
                "trade_idx": i,
                "pvp": row["pvp"],
                "preco": float(row["fechamento"]),
                "preco_aj": float(row["fechamento_aj"]),
                "signal": signal,
            })
            
        signals_df = pd.DataFrame(signals)
        
        cdi_df = _load_cdi_series(session, signals_df["data"].min(), signals_df["data"].max())
        div_df = _load_dividend_series(ticker, session, signals_df["data"].min(), signals_df["data"].max())

        cum_buy = simulate_trades(signals_df, "BUY", best_params["forward_days"], cdi_df, div_df)
        cum_hold = simulate_buy_and_hold(
            signals_df,
            valuation_dates=cum_buy.get("dates", []),
            start_date=signals_df["data"].iloc[0],
            cdi_df=cdi_df,
            div_df=div_df,
        )

        base["v2"] = {
            "buy_risk": buy_risk,
            "sell_risk": sell_risk,
            "buy_risk_after_cost": buy_risk_adj,
            "overfit": overfit,
            "buy_ci": buy_ci,
            "sell_ci": sell_ci,
            "sensitivity_2d": sensitivity_df,
            "regime": regime,
            "simulation": {
                "follow_buy": cum_buy,
                "hold": cum_hold,
            },
            "cost_per_trade": CUSTO_POR_TRADE,
            "n_test_buy": len(test_buy_returns),
            "n_test_sell": len(test_sell_returns),
            "n_test_buy_independent": len(test_buy_returns_indep),
            "n_test_sell_independent": len(test_sell_returns_indep),
            "n_effective_buy": buy_risk["n_effective"],
            "n_effective_sell": sell_risk["n_effective"],
        }

        return base

    def compute_risk_metrics(
        self,
        returns,
        independent_returns=None,
        benchmark_returns=None,
        cost_per_trade=CUSTO_POR_TRADE,
    ):
        """Metricas de risco ajustado sobre retornos forward (sobrepostos).

        AVISO: Sharpe, Sortino e Max Drawdown calculados sobre retornos sobrepostos
        sao exploratorios. A anulizacao por sqrt(252/h) pressupoe independencia
        serial que nao e plenamente valida aqui [Lo 2002].
        """
        r = np.array(returns, dtype=float)
        r_indep = np.array(independent_returns if independent_returns is not None else returns, dtype=float)
        n = len(r)
        n_eff = len(r_indep)

        if n == 0:
            return {
                "n": 0,
                "n_effective": 0,
                "mean": 0.0,
                "mean_raw": 0.0,
                "mean_independent": None,
                "std": 0.0,
                "std_raw": 0.0,
                "std_independent": None,
                "median": 0.0,
                "median_raw": 0.0,
                "median_independent": None,
                "sharpe": None,
                "sortino": None,
                "max_drawdown": None,
                "win_rate": None,
                "win_rate_independent": None,
                "profit_factor": None,
                "mean_after_cost": None,
                "skewness": None,
                "kurtosis": None,
            }

        mean_r = float(np.mean(r))
        std_r = float(np.std(r, ddof=1)) if n >= 2 else 0.0
        mean_r_indep = float(np.mean(r_indep)) if n_eff > 0 else None
        std_r_indep = float(np.std(r_indep, ddof=1)) if n_eff >= 2 else None

        ann_factor = np.sqrt(252 / self.forward_days)
        sharpe = (mean_r / std_r) * ann_factor if std_r > 0 else None

        downside = r[r < 0]
        if len(downside) >= 2:
            downside_std = float(np.std(downside, ddof=1))
            sortino = (mean_r / downside_std) * ann_factor if downside_std > 0 else None
        else:
            sortino = None

        cum = np.cumprod(1 + r)
        running_max = np.maximum.accumulate(cum)
        drawdowns = (cum - running_max) / running_max
        max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else None

        wins = int(np.sum(r > 0))
        win_rate = wins / n

        if np.any(r < 0):
            gross_profit = float(np.sum(r[r > 0]))
            gross_loss = float(np.abs(np.sum(r[r < 0])))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
        else:
            profit_factor = None

        mean_after_cost = float(np.mean(r - cost_per_trade))
        win_rate_indep = float(np.mean(r_indep > 0)) if n_eff > 0 else None

        skew = float(stats.skew(r)) if n >= 3 else None
        kurt = float(stats.kurtosis(r)) if n >= 4 else None

        return {
            "n": n,
            "n_effective": n_eff,
            "mean": mean_r,
            "mean_raw": mean_r,
            "mean_independent": mean_r_indep,
            "std": std_r,
            "std_raw": std_r,
            "std_independent": std_r_indep,
            "median": float(np.median(r)),
            "median_raw": float(np.median(r)),
            "median_independent": float(np.median(r_indep)) if n_eff > 0 else None,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "win_rate_independent": win_rate_indep,
            "profit_factor": profit_factor,
            "mean_after_cost": mean_after_cost,
            "skewness": skew,
            "kurtosis": kurt,
        }

    def compute_overfitting_score(self, train_result, val_result, test_result):
        """Diagnostica overfitting comparando treino->validacao->teste.

        Retorna SEM_SINAL quando train_buy ~ 0 ou n_eff < 1 (degenerescencia):
        classificar como ROBUSTO nesses casos seria falso negativo perigoso.
        """
        train_buy = train_result.get("avg_return_buy", 0.0)
        val_buy = val_result.get("avg_return_buy", 0.0)
        test_buy = test_result.get("avg_return_buy", 0.0)

        n_eff_train = train_result.get("n_buy_thinned", 0)
        if abs(train_buy) < 1e-8 or n_eff_train < 1:
            return {
                "train_buy": train_buy,
                "val_buy": val_buy,
                "test_buy": test_buy,
                "val_degradation": None,
                "test_degradation": None,
                "is_overfit": False,
                "is_severe": False,
                "classification": "SEM_SINAL",
                "rank_consistent": False,
            }

        val_degrad = (train_buy - val_buy) / abs(train_buy)
        test_degrad = (train_buy - test_buy) / abs(train_buy)

        is_overfit = val_degrad > 0.5 or test_degrad > 0.5
        is_severe = val_degrad > 0.8 or test_degrad > 0.8
        has_negative_degradation = val_degrad < 0 or test_degrad < 0

        if is_severe:
            classification = "SEVERO"
        elif is_overfit:
            classification = "SUSPEITO"
        elif has_negative_degradation:
            classification = "SUSPEITO"
        elif val_degrad < 0.2 and test_degrad < 0.3:
            classification = "ROBUSTO"
        else:
            classification = "MODERADO"

        ranks = [
            r.get("avg_return_buy", 0.0) > r.get("avg_return_sell", 0.0)
            for r in [train_result, val_result, test_result]
        ]
        rank_consistent = all(ranks)

        return {
            "train_buy": train_buy,
            "val_buy": val_buy,
            "test_buy": test_buy,
            "val_degradation": val_degrad,
            "test_degradation": test_degrad,
            "is_overfit": is_overfit,
            "classification": classification,
            "rank_consistent": rank_consistent,
        }

    def compute_bootstrap_ci(self, returns, n_boot=2000, ci=0.95):
        """IC bootstrap i.i.d. sobre retornos ja thinned/independentes."""
        r = np.array(returns, dtype=float)
        n = len(r)
        if n < 4:
            return {"lower": None, "upper": None, "mean": float(np.mean(r)) if n > 0 else None,
                     "width": None, "warning": "Menos de 4 observacoes"}

        if self._is_degenerate(r):
            return {"lower": None, "upper": None, "mean": float(np.mean(r)),
                     "width": None, "warning": "Serie degenerada — bootstrap invalido"}

        rng = np.random.default_rng(42)
        boot_means = []
        for _ in range(n_boot):
            sample = rng.choice(r, size=n, replace=True)
            boot_means.append(float(np.mean(sample)))

        boot_means = np.array(boot_means)
        alpha = (1 - ci) / 2
        return {
            "lower": float(np.percentile(boot_means, alpha * 100)),
            "upper": float(np.percentile(boot_means, (1 - alpha) * 100)),
            "mean": float(np.mean(boot_means)),
            "width": float(np.percentile(boot_means, (1 - alpha) * 100) - np.percentile(boot_means, alpha * 100)),
            "ci_level": ci,
        }

    def compute_sensitivity_2d(self, splits, best_params, dim_x="pvp_percentil_buy", dim_y="pvp_percentil_sell"):
        """Heatmap de sensibilidade 2D: varia dim_x e dim_y fixando os demais."""
        grid_x = self.pvp_percentil_buy_grid if dim_x == "pvp_percentil_buy" else self.pvp_percentil_sell_grid
        grid_y = self.pvp_percentil_sell_grid if dim_y == "pvp_percentil_sell" else self.pvp_percentil_buy_grid

        results = []
        for x_val in grid_x:
            for y_val in grid_y:
                params = dict(best_params)
                params[dim_x] = x_val
                params[dim_y] = y_val
                test_m = self._evaluate(splits["test"], params)
                val_m = self._evaluate(splits["val"], params)
                results.append({
                    dim_x: x_val,
                    dim_y: y_val,
                    "test_buy_return": test_m["avg_return_buy"],
                    "test_sell_return": test_m["avg_return_sell"],
                    "test_n_buy": test_m["n_buy"],
                    "val_spread": val_m["avg_return_buy"] - val_m["avg_return_sell"],
                })

        return pd.DataFrame(results)

    def _analyze_regime(self, test_df, buy_returns, sell_returns, best_params=None,
                        train_pvp_median=None):
        """Performance por regime definido ex-ante pelo nivel de P/VP.

        Premio (pvp_pct > mediana) vs Desconto (pvp_pct <= mediana).
        Mediana congelada do treino quando disponivel — elimina look-ahead residual.
        Fallback para mediana do proprio teste se train_pvp_median nao for fornecido.
        """
        if test_df.empty or len(test_df) < 50:
            return {"classification": "INSUFICIENTE", "detail": "Poucos dados"}
        if "pvp_pct" not in test_df.columns:
            return {"classification": "INSUFICIENTE", "detail": "pvp_pct ausente"}

        buy_thr = best_params["pvp_percentil_buy"] if best_params else 25

        if train_pvp_median is not None:
            pvp_median = float(train_pvp_median)
            median_source = "treino"
        else:
            pvp_median = float(test_df["pvp_pct"].median())
            median_source = "teste"
        premium_mask = test_df["pvp_pct"] > pvp_median
        discount_mask = test_df["pvp_pct"] <= pvp_median

        n_premium = int(premium_mask.sum())
        n_discount = int(discount_mask.sum())

        premium_buy_mean = float(test_df.loc[premium_mask & (test_df["pvp_pct"] <= buy_thr), "fwd_ret"].mean()) if n_premium > 0 else None
        discount_buy_mean = float(test_df.loc[discount_mask & (test_df["pvp_pct"] <= buy_thr), "fwd_ret"].mean()) if n_discount > 0 else None

        premium_uncond = float(test_df.loc[premium_mask, "fwd_ret"].mean()) if n_premium > 0 else 0.0
        discount_uncond = float(test_df.loc[discount_mask, "fwd_ret"].mean()) if n_discount > 0 else 0.0

        return {
            "classification": "OK",
            "regime_variable": "pvp_pct",
            "pvp_median_threshold": pvp_median,
            "pvp_median_source": median_source,
            "n_premium": n_premium,
            "n_discount": n_discount,
            "premium_unconditional": premium_uncond,
            "discount_unconditional": discount_uncond,
            "premium_excess": (premium_buy_mean - premium_uncond) if premium_buy_mean is not None else None,
            "discount_excess": (discount_buy_mean - discount_uncond) if discount_buy_mean is not None else None,
        }
