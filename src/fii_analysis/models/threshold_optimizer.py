import itertools
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import select

from src.fii_analysis.data.database import PrecoDiario, RelatorioMensal, get_cnpj_by_ticker
from src.fii_analysis.features.fundamentos import get_efetiva_vs_patrimonial_resumo


class ThresholdOptimizer:
    def __init__(self):
        # Grids simplificados para dados diários
        self.pvp_percentil_buy_grid = [15, 20, 25, 30, 35]
        self.pvp_percentil_sell_grid = [65, 70, 75, 80, 85]
        self.meses_alerta_sell_grid = [1, 2, 3]
        self.forward_days = 20

    def _get_enriched_daily_data(self, ticker, session):
        cnpj = get_cnpj_by_ticker(ticker, session)
        if not cnpj:
            return pd.DataFrame()

        # 1. Buscar precos_diarios
        prices_db = session.execute(
            select(PrecoDiario.data, PrecoDiario.fechamento, PrecoDiario.fechamento_aj)
            .where(PrecoDiario.ticker == ticker)
            .order_by(PrecoDiario.data.asc())
        ).all()
        if not prices_db:
            return pd.DataFrame()
        
        prices_df = pd.DataFrame([
            {"data": p.data, "fechamento": float(p.fechamento), "fechamento_aj": float(p.fechamento_aj)} 
            for p in prices_db if p.fechamento is not None and p.fechamento_aj is not None
        ])
        prices_df["data"] = pd.to_datetime(prices_df["data"])

        # 2. Buscar relatórios CVM
        reports_db = session.execute(
            select(
                RelatorioMensal.data_referencia,
                RelatorioMensal.data_entrega,
                RelatorioMensal.vp_por_cota,
                RelatorioMensal.rentab_efetiva,
                RelatorioMensal.rentab_patrim
            )
            .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega.isnot(None))
            .order_by(RelatorioMensal.data_referencia.asc())
        ).all()
        if not reports_db:
            return pd.DataFrame()

        reports_df = pd.DataFrame([
            {
                "data_ref": r.data_referencia,
                "data_entrega": r.data_entrega,
                "vp_por_cota": float(r.vp_por_cota) if r.vp_por_cota else None,
                "rentab_efetiva": float(r.rentab_efetiva) if r.rentab_efetiva else None,
                "rentab_patrim": float(r.rentab_patrim) if r.rentab_patrim else None
            } for r in reports_db
        ])
        reports_df["data_entrega"] = pd.to_datetime(reports_df["data_entrega"])
        reports_df = reports_df.sort_values("data_entrega")

        # 3. Calcular meses_alerta nos relatórios
        consec = 0
        meses_alerta_list = []
        for _, r in reports_df.iterrows():
            ef = r["rentab_efetiva"]
            pa = r["rentab_patrim"]
            # Consideramos None como saudável para não disparar alerta falso por falta de dados? 
            # Originalmente r.rentab_efetiva.isnot(None) na query.
            if ef is not None and pa is not None:
                saudavel = (pa >= 0 and ef >= pa)
                if not saudavel:
                    consec += 1
                else:
                    consec = 0
            meses_alerta_list.append(consec)
        reports_df["meses_alerta"] = meses_alerta_list

        # 4. Merge asof para alinhar VP e meses_alerta com preços diários
        # Garante que VP em t é o último entregue até t
        df = pd.merge_asof(
            prices_df, 
            reports_df[["data_entrega", "vp_por_cota", "meses_alerta"]],
            left_on="data",
            right_on="data_entrega",
            direction="backward"
        )

        # 5. Calcular Indicadores em Bulk
        df["pvp"] = df["fechamento"] / df["vp_por_cota"]
        # Rolling percentile: pvp.rolling(504).rank(pct=True)
        # O prompt pede 504 pregões anteriores.
        df["pvp_pct"] = df["pvp"].rolling(504, min_periods=63).rank(pct=True) * 100
        
        # 6. Calcular Retorno Futuro (20 pregões)
        # fwd_ret = (P_{t+20} / P_t) - 1
        df["fwd_ret"] = (df["fechamento_aj"].shift(-self.forward_days) / df["fechamento_aj"]) - 1.0

        return df.dropna(subset=["pvp_pct", "meses_alerta", "fwd_ret"])

    def _make_splits(self, df):
        n = len(df)
        if n < 200: # Mínimo arbitrário para ter splits razoáveis
            return None
        
        n_train = int(n * 0.6)
        n_val = int(n * 0.2)
        
        # Split com gaps de 10 pregões
        gap = 10
        
        train_df = df.iloc[:n_train]
        val_df = df.iloc[n_train + gap : n_train + gap + n_val]
        test_df = df.iloc[n_train + gap + n_val + gap :]
        
        return {
            "train": train_df,
            "val": val_df,
            "test": test_df
        }

    def optimize(self, ticker, session):
        df_enriched = self._get_enriched_daily_data(ticker, session)
        
        if df_enriched.empty:
            return {"error": "Dados insuficientes ou ticker não encontrado"}

        splits = self._make_splits(df_enriched)
        if not splits or len(splits["val"]) == 0 or len(splits["test"]) == 0:
            return {"error": f"Dados insuficientes para splits (Total: {len(df_enriched)})"}

        best_params = None
        best_val_score = -999.0
        results_grid = []
        
        # Grid Search Simplificado
        combinations = list(itertools.product(
            self.pvp_percentil_buy_grid, 
            self.pvp_percentil_sell_grid, 
            self.meses_alerta_sell_grid
        ))
        
        for pvp_b, pvp_s, al_s in combinations:
            params = {
                "pvp_percentil_buy": pvp_b,
                "pvp_percentil_sell": pvp_s,
                "meses_alerta_sell": al_s,
                "forward_days": self.forward_days
            }
            
            train_metrics = self._evaluate(splits["train"], params)
            val_metrics = self._evaluate(splits["val"], params)
            
            # Score: Retorno Médio Buy - Retorno Médio Sell (em % para ser mais legível)
            score = val_metrics["avg_return_buy"] - val_metrics["avg_return_sell"]
            
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
            return {"error": "Nenhuma combinação válida encontrada no grid"}

        # Avaliação final no Teste
        test_result = self._evaluate(splits["test"], best_params)
        placebo = self._run_placebo(splits["test"], best_params, df_enriched)
        
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
            # Para o gráfico histórico, amostramos para não sobrecarregar
            "indicator_history": df_enriched.iloc[::5].to_dict("records"),
            "grid_results": results_grid
        }

    def _evaluate(self, df, params):
        # Para evitar overtrading no cálculo de retorno médio,
        # só pegamos sinais que ocorrem com um distanciamento de forward_days
        buy_returns = []
        sell_returns = []
        
        last_buy_idx = -999
        last_sell_idx = -999
        
        # Usando índices para garantir distanciamento de pregões
        for i, (idx, row) in enumerate(df.iterrows()):
            is_buy = (row["pvp_pct"] <= params["pvp_percentil_buy"])
            
            is_sell = (row["pvp_pct"] >= params["pvp_percentil_sell"] or 
                       row["meses_alerta"] >= params["meses_alerta_sell"])
            
            if is_buy and (i - last_buy_idx) >= self.forward_days:
                buy_returns.append(row["fwd_ret"])
                last_buy_idx = i
                
            if is_sell and (i - last_sell_idx) >= self.forward_days:
                sell_returns.append(row["fwd_ret"])
                last_sell_idx = i
                
        avg_buy = np.mean(buy_returns) if buy_returns else 0.0
        avg_sell = np.mean(sell_returns) if sell_returns else 0.0
        
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

    def _run_placebo(self, test_df, params, full_df, n_shuffles=200):
        if len(test_df) == 0:
            return {"p_value_buy": 1.0, "p_value_sell": 1.0}
            
        real_metrics = self._evaluate(test_df, params)
        all_possible_returns = full_df["fwd_ret"].dropna().tolist()
        
        shuffled_buys = []
        shuffled_sells = []
        rng = np.random.default_rng(42)
        
        for _ in range(n_shuffles):
            if real_metrics["n_buy"] > 0:
                sim_buys = rng.choice(all_possible_returns, size=real_metrics["n_buy"], replace=False)
                shuffled_buys.append(np.mean(sim_buys))
            else:
                shuffled_buys.append(0.0)
                
            if real_metrics["n_sell"] > 0:
                sim_sells = rng.choice(all_possible_returns, size=real_metrics["n_sell"], replace=False)
                shuffled_sells.append(np.mean(sim_sells))
            else:
                shuffled_sells.append(0.0)
            
        p_buy = np.mean([abs(b) >= abs(real_metrics["avg_return_buy"]) for b in shuffled_buys])
        p_sell = np.mean([abs(s) >= abs(real_metrics["avg_return_sell"]) for s in shuffled_sells])
        
        return {
            "p_value_buy": float(p_buy),
            "p_value_sell": float(p_sell),
            "avg_placebo_buy": float(np.mean(shuffled_buys)),
            "avg_placebo_sell": float(np.mean(shuffled_sells))
        }

    def get_signal_hoje(self, ticker, session, params):
        # Para o sinal de hoje, calculamos o enriquecimento e pegamos a última linha
        df = self._get_enriched_daily_data(ticker, session)
        if df.empty:
            return {"sinal": "NEUTRO", "details": "Dados insuficientes"}
        
        row = df.iloc[-1]
        
        is_buy = (row["pvp_pct"] <= params["pvp_percentil_buy"])
        is_sell = (row["pvp_pct"] >= params["pvp_percentil_sell"] or 
                   row["meses_alerta"] >= params["meses_alerta_sell"])
        
        sinal = "NEUTRO"
        if is_buy: sinal = "BUY"
        elif is_sell: sinal = "SELL"
        
        return {
            "sinal": sinal,
            "indicators": {
                "pvp_pct": float(row["pvp_pct"]),
                "meses_alerta": int(row["meses_alerta"]),
                "data": row["data"].strftime("%Y-%m-%d")
            }
        }
