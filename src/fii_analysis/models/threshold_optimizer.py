import itertools
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.data.database import PrecoDiario, RelatorioMensal, get_cnpj_by_ticker
from src.fii_analysis.features.fundamentos import get_efetiva_vs_patrimonial_resumo
from src.fii_analysis.features.valuation import get_dy_gap_percentil, get_pvp_percentil


class ThresholdOptimizer:
    def __init__(self):
        self.pvp_buy_grid = [15, 20, 25, 30, 35, 40]
        self.pvp_sell_grid = [60, 65, 70, 75, 80]
        self.dy_buy_grid = [55, 65, 70, 75]
        self.dy_sell_grid = [25, 30, 35, 45]
        self.alerta_sell_grid = [1, 2, 3]
        self.forward_days = 20

    def _get_point_in_time_fundamentos(self, ticker, t, session):
        cnpj = get_cnpj_by_ticker(ticker, session)
        if not cnpj:
            return 0

        rows = session.execute(
            select(
                RelatorioMensal.rentab_efetiva,
                RelatorioMensal.rentab_patrim,
            )
            .where(
                RelatorioMensal.cnpj == cnpj,
                RelatorioMensal.data_entrega <= t,
                RelatorioMensal.rentab_efetiva.isnot(None),
                RelatorioMensal.rentab_patrim.isnot(None),
            )
            .order_by(RelatorioMensal.data_referencia.desc())
            .limit(6)
        ).all()

        if not rows:
            return 0

        consec = 0
        for r in rows:
            ef = float(r.rentab_efetiva)
            pa = float(r.rentab_patrim)
            saudavel = pa >= 0 and ef >= pa
            if not saudavel:
                consec += 1
            else:
                break
        return consec

    def _get_forward_return(self, ticker, start_date, forward_days, prices_df):
        # prices_df must be sorted by data
        subset = prices_df[prices_df["data"] >= start_date].head(forward_days + 1)
        if len(subset) < forward_days + 1:
            return None
        
        p0 = subset.iloc[0]["fechamento_aj"]
        p1 = subset.iloc[forward_days]["fechamento_aj"]
        
        if p0 is None or p1 is None or p0 == 0:
            return None
        
        return (float(p1) / float(p0)) - 1.0

    def _make_splits(self, reports):
        if len(reports) < 10:
            return None
        
        n = len(reports)
        n_train = int(n * 0.6)
        n_val = int(n * 0.2)
        
        train_reports = reports.iloc[:n_train]
        val_reports = reports.iloc[n_train : n_train + n_val]
        test_reports = reports.iloc[n_train + n_val :]
        
        # Gap logic: exclude reports within 14 calendar days after train/val end
        train_end = train_reports["data_entrega"].max()
        val_start_limit = train_end + timedelta(days=14)
        val_reports = val_reports[val_reports["data_entrega"] > val_start_limit].copy()
        
        if len(val_reports) > 0:
            val_end = val_reports["data_entrega"].max()
            test_start_limit = val_end + timedelta(days=14)
            test_reports = test_reports[test_reports["data_entrega"] > test_start_limit].copy()
        else:
            test_reports = test_reports.iloc[0:0].copy()
        
        return {
            "train": train_reports,
            "val": val_reports,
            "test": test_reports
        }

    def optimize(self, ticker, session):
        cnpj = get_cnpj_by_ticker(ticker, session)
        if not cnpj:
            return {"error": "Ticker não encontrado"}

        # Load reports
        reports_db = session.execute(
            select(RelatorioMensal.data_referencia, RelatorioMensal.data_entrega)
            .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega.isnot(None))
            .order_by(RelatorioMensal.data_entrega.asc())
        ).all()
        
        if not reports_db:
            return {"error": "Relatórios não encontrados"}
            
        reports = pd.DataFrame([{"data_ref": r.data_referencia, "data_entrega": r.data_entrega} for r in reports_db])
        
        # Load prices for return calculation
        prices_db = session.execute(
            select(PrecoDiario.data, PrecoDiario.fechamento_aj)
            .where(PrecoDiario.ticker == ticker)
            .order_by(PrecoDiario.data.asc())
        ).all()
        prices_df = pd.DataFrame([{"data": p.data, "fechamento_aj": p.fechamento_aj} for p in prices_db])
        
        if prices_df.empty:
            return {"error": "Preços não encontrados"}

        # Pre-calculate indicators point-in-time
        indicator_cache = []
        for _, row in reports.iterrows():
            t = row["data_entrega"]
            pvp_pct, _ = get_pvp_percentil(ticker, t, session=session)
            dy_gap_pct = get_dy_gap_percentil(ticker, t, session=session)
            meses_alerta = self._get_point_in_time_fundamentos(ticker, t, session)
            fwd_ret = self._get_forward_return(ticker, t, self.forward_days, prices_df)
            
            indicator_cache.append({
                "data_entrega": t,
                "pvp_pct": pvp_pct,
                "dy_gap_pct": dy_gap_pct,
                "meses_alerta": meses_alerta,
                "fwd_ret": fwd_ret
            })
            
        reports_enriched = pd.DataFrame(indicator_cache).dropna(subset=["pvp_pct", "dy_gap_pct", "fwd_ret"])
        
        splits = self._make_splits(reports_enriched)
        if not splits or len(splits["val"]) == 0:
            return {"error": f"Dados insuficientes para splits (Treino: {len(splits['train']) if splits else 0}, Val: {len(splits['val']) if splits else 0})"}

        best_params = None
        best_val_score = -999.0
        
        results_grid = []
        
        # Grid Search
        combinations = list(itertools.product(
            self.pvp_buy_grid, self.pvp_sell_grid, 
            self.dy_buy_grid, self.dy_sell_grid, 
            self.alerta_sell_grid
        ))
        
        for pvp_b, pvp_s, dy_b, dy_s, al_s in combinations:
            params = {
                "pvp_percentil_buy": pvp_b,
                "pvp_percentil_sell": pvp_s,
                "dy_gap_percentil_buy": dy_b,
                "dy_gap_percentil_sell": dy_s,
                "meses_alerta_sell": al_s,
                "forward_days": 20
            }
            
            train_metrics = self._evaluate(splits["train"], params)
            val_metrics = self._evaluate(splits["val"], params)
            
            score = val_metrics["avg_return_buy"] - val_metrics["avg_return_sell"]
            
            # Constraint: prioritize buy > 0 and sell < 0
            if val_metrics["n_buy"] > 0 or val_metrics["n_sell"] > 0:
                if score > best_val_score:
                    best_val_score = score
                    best_params = params
                    
                results_grid.append({
                    "params": params,
                    "train": train_metrics,
                    "val": val_metrics,
                    "score": score
                })

        if not best_params:
            return {"error": "Nenhuma combinação válida encontrada"}

        # Final Test
        test_result = self._evaluate(splits["test"], best_params)
        
        # Placebo test on Test Set
        placebo = self._run_placebo(splits["test"], best_params, prices_df)
        
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
                "test": len(splits["test"])
            },
            "indicator_history": reports_enriched.to_dict("records"),
            "grid_results": results_grid
        }

    def _evaluate(self, df, params):
        buy_returns = []
        sell_returns = []
        
        last_buy_date = date(1900, 1, 1)
        last_sell_date = date(1900, 1, 1)
        
        for _, row in df.iterrows():
            # Signal Logic
            is_buy = (row["pvp_pct"] <= params["pvp_percentil_buy"] and 
                      row["dy_gap_pct"] >= params["dy_gap_percentil_buy"])
            
            is_sell = (row["pvp_pct"] >= params["pvp_percentil_sell"] or 
                       row["dy_gap_pct"] <= params["dy_gap_percentil_sell"] or 
                       row["meses_alerta"] >= params["meses_alerta_sell"])
            
            # Greedy overlap filter (gap >= 20 days)
            if is_buy and (row["data_entrega"] - last_buy_date).days >= 20:
                buy_returns.append(row["fwd_ret"])
                last_buy_date = row["data_entrega"]
                
            if is_sell and (row["data_entrega"] - last_sell_date).days >= 20:
                sell_returns.append(row["fwd_ret"])
                last_sell_date = row["data_entrega"]
                
        avg_buy = np.mean(buy_returns) if buy_returns else 0.0
        avg_sell = np.mean(sell_returns) if sell_returns else 0.0
        
        # Statistical significance (very basic p-value against 0)
        p_buy = stats.ttest_1samp(buy_returns, 0.0).pvalue if len(buy_returns) > 1 else 1.0
        p_sell = stats.ttest_1samp(sell_returns, 0.0).pvalue if len(sell_returns) > 1 else 1.0

        return {
            "n_buy": len(buy_returns),
            "avg_return_buy": float(avg_buy),
            "p_value_buy": float(p_buy),
            "n_sell": len(sell_returns),
            "avg_return_sell": float(avg_sell),
            "p_value_sell": float(p_sell)
        }

    def _run_placebo(self, test_df, params, prices_df, n_shuffles=200):
        if len(test_df) == 0:
            return {"p_value_buy": 1.0, "p_value_sell": 1.0}
            
        real_metrics = self._evaluate(test_df, params)
        
        # Shuffle dates to get placebo distribution
        all_possible_dates = prices_df["data"].tolist()
        
        shuffled_buys = []
        shuffled_sells = []
        
        rng = np.random.default_rng(42)
        
        for _ in range(n_shuffles):
            n_b = real_metrics["n_buy"]
            n_s = real_metrics["n_sell"]
            
            sim_buys = []
            if n_b > 0:
                random_dates = rng.choice(all_possible_dates, size=n_b, replace=False)
                for d in random_dates:
                    ret = self._get_forward_return("", d, self.forward_days, prices_df)
                    if ret is not None: sim_buys.append(ret)
            shuffled_buys.append(np.mean(sim_buys) if sim_buys else 0.0)
            
            sim_sells = []
            if n_s > 0:
                random_dates = rng.choice(all_possible_dates, size=n_s, replace=False)
                for d in random_dates:
                    ret = self._get_forward_return("", d, self.forward_days, prices_df)
                    if ret is not None: sim_sells.append(ret)
            shuffled_sells.append(np.mean(sim_sells) if sim_sells else 0.0)
            
        p_buy = np.mean([abs(b) >= abs(real_metrics["avg_return_buy"]) for b in shuffled_buys])
        p_sell = np.mean([abs(s) >= abs(real_metrics["avg_return_sell"]) for s in shuffled_sells])
        
        return {
            "p_value_buy": float(p_buy),
            "p_value_sell": float(p_sell),
            "avg_placebo_buy": float(np.mean(shuffled_buys)),
            "avg_placebo_sell": float(np.mean(shuffled_sells))
        }

    def get_signal_hoje(self, ticker, session, params):
        ultimo_preco_date = session.execute(
            select(PrecoDiario.data).where(PrecoDiario.ticker == ticker).order_by(PrecoDiario.data.desc()).limit(1)
        ).scalar_one_or_none()
        
        if not ultimo_preco_date:
            return {"sinal": "NEUTRO", "details": "Sem dados de preço"}
            
        pvp_pct, _ = get_pvp_percentil(ticker, ultimo_preco_date, session=session)
        dy_gap_pct = get_dy_gap_percentil(ticker, ultimo_preco_date, session=session)
        resumo_fund = get_efetiva_vs_patrimonial_resumo(ticker, session=session)
        meses_alerta = resumo_fund["meses_consecutivos_alerta"]
        
        if pvp_pct is None or dy_gap_pct is None:
             return {"sinal": "NEUTRO", "details": "Indicadores incompletos"}

        is_buy = (pvp_pct <= params["pvp_percentil_buy"] and 
                  dy_gap_pct >= params["dy_gap_percentil_buy"])
        
        is_sell = (pvp_pct >= params["pvp_percentil_sell"] or 
                   dy_gap_pct <= params["dy_gap_percentil_sell"] or 
                   meses_alerta >= params["meses_alerta_sell"])
        
        sinal = "NEUTRO"
        if is_buy: sinal = "BUY"
        elif is_sell: sinal = "SELL"
        
        return {
            "sinal": sinal,
            "indicators": {
                "pvp_pct": pvp_pct,
                "dy_gap_pct": dy_gap_pct,
                "meses_alerta": meses_alerta
            }
        }
