import numpy as np
import pandas as pd


def portfolio_value(cash, shares, price, receivables):
    """Calcula o valor total da carteira (caixa + valor posicionado + recebíveis)."""
    return cash + (shares * price if price is not None else 0.0) + sum(receivables.values())


def _normalize_signal_actions(signal):
    """Converte um sinal em uma lista ordenada de acoes operacionais."""
    if signal == "SELL_BUY":
        return ["SELL", "BUY"]
    if signal == "BUY_SELL":
        return ["BUY", "SELL"]
    if signal in {"BUY", "SELL"}:
        return [signal]
    return []


def build_dividend_events(div_df, trading_dates):
    """Mapeia data-com para uma data de credito proxy no calendario de pregões.

    Como o banco nao armazena data_pagamento, usa-se o proximo pregao apos a
    data-com como proxy conservadora de disponibilidade de caixa. O direito ao
    dividendo nasce na data-com; o caixa so fica disponivel no dia seguinte.
    """
    if div_df.empty or not trading_dates:
        return {}

    trading_dates = [pd.Timestamp(d) for d in trading_dates]
    events = {}
    for _, row in div_df.iterrows():
        com_date = pd.Timestamp(row["data_com"])
        idx = np.searchsorted(trading_dates, com_date, side="right")
        credit_date = trading_dates[idx] if idx < len(trading_dates) else None
        events.setdefault(com_date, []).append({
            "valor_cota": float(row["valor_cota"]),
            "credit_date": credit_date,
        })
    return events


def simulate_trades(signals_df, signal_type, forward_days, cdi_df, div_df):
    """Simula estrategia BUY→SELL com preco bruto, dividendos explicitos e CDI.

    O capital fora do ativo rende CDI diario. Dividendos sao creditados como
    caixa separado usando a data-com para elegibilidade e o proximo pregao como
    proxy de disponibilidade, ja que nao ha data_pagamento no banco.
    """
    df = signals_df.sort_values("trade_idx").reset_index(drop=True)
    if df.empty:
        return {
            "dates": [],
            "entry_dates": [],
            "returns": [],
            "cumulative": [],
            "trades": [],
            "final": 0.0,
            "n_trades": 0,
            "open_position": False,
            "open_entry_date": None,
            "final_date": None,
            "cdi_idle_enabled": True,
            "dividend_proxy": "next_trading_day_after_data_com",
        }

    trading_dates = df["data"].tolist()
    dividend_events = build_dividend_events(div_df, trading_dates)
    cdi_map = {}
    if not cdi_df.empty:
        cdi_map = {
            pd.Timestamp(row["data"]): float(row["taxa_diaria_pct"]) / 100.0
            for _, row in cdi_df.iterrows()
        }

    trades = []
    in_position = False
    shares = 0.0
    cash = 1.0
    receivables = {}
    entry_price = None
    entry_date = None
    entry_pvp = None
    entry_trade_idx = None
    entry_capital = None
    dividends_trade = 0.0
    timeline_dates = []
    timeline_cumulative = []

    for current_pos, (_, row) in enumerate(df.iterrows()):
        current_date = pd.Timestamp(row["data"])
        signal = row["signal"]
        price = row.get("preco")
        if pd.isna(price):
            continue
        price = float(price)

        taxa = cdi_map.get(current_date)
        if taxa is not None and cash > 0:
            cash *= (1.0 + taxa)

        if current_date in receivables:
            cash += receivables.pop(current_date)

        if current_date in dividend_events and shares > 0:
            for event in dividend_events[current_date]:
                amount = shares * event["valor_cota"]
                dividends_trade += amount
                credit_date = event["credit_date"]
                if credit_date is None:
                    receivables[pd.Timestamp.max] = receivables.get(pd.Timestamp.max, 0.0) + amount
                else:
                    receivables[credit_date] = receivables.get(credit_date, 0.0) + amount

        for action in _normalize_signal_actions(signal):
            if action == "SELL" and in_position:
                cash += shares * price
                shares = 0.0
                total_after_exit = portfolio_value(cash, shares, price, receivables)
                trade_ret = (total_after_exit / entry_capital) - 1.0 if entry_capital else 0.0
                trade_ret_price = (price / entry_price) - 1.0 if entry_price else 0.0
                trades.append({
                    "data_entrada": entry_date,
                    "data_saida": row["data"],
                    "preco_entrada": entry_price,
                    "preco_saida": price,
                    "pvp_entrada": entry_pvp,
                    "pvp_saida": float(row["pvp"]) if not pd.isna(row.get("pvp")) else None,
                    "dias_uteis": int(row["trade_idx"] - entry_trade_idx),
                    "ret": trade_ret,
                    "ret_preco": trade_ret_price,
                    "dividendos_trade": dividends_trade,
                    "capital_apos_trade": total_after_exit,
                })
                in_position = False
                entry_price = None
                entry_date = None
                entry_pvp = None
                entry_trade_idx = None
                entry_capital = None
                dividends_trade = 0.0
                continue

            if action == signal_type and not in_position and cash > 0:
                entry_capital = portfolio_value(cash, shares, price, receivables)
                shares = cash / price
                cash = 0.0
                in_position = True
                entry_price = price
                entry_date = row["data"]
                entry_pvp = float(row["pvp"]) if not pd.isna(row.get("pvp")) else None
                entry_trade_idx = int(row["trade_idx"])
                dividends_trade = 0.0

        if trades and pd.Timestamp(trades[-1]["data_saida"]) == current_date:
            total_value = portfolio_value(cash, shares, price, receivables)
            timeline_dates.append(current_date)
            timeline_cumulative.append(total_value - 1.0)

    final_date = df["data"].iloc[-1] if not df.empty else None
    final_price = float(df["preco"].iloc[-1]) if not df.empty else None
    total_final = portfolio_value(cash, shares, final_price, receivables)
    if final_date is not None and (not timeline_dates or timeline_dates[-1] != final_date):
        timeline_dates.append(final_date)
        timeline_cumulative.append(total_final - 1.0)

    if not trades:
        return {
            "dates": timeline_dates,
            "entry_dates": [],
            "returns": [],
            "cumulative": timeline_cumulative,
            "trades": [],
            "final": total_final - 1.0,
            "n_trades": 0,
            "open_position": in_position,
            "open_entry_date": entry_date,
            "final_date": final_date,
            "cdi_idle_enabled": True,
            "dividend_proxy": "next_trading_day_after_data_com",
        }

    tdf = pd.DataFrame(trades)
    tdf["cum_ret"] = np.array(timeline_cumulative[:len(tdf)], dtype=float)
    return {
        "dates": timeline_dates,
        "entry_dates": tdf["data_entrada"].tolist(),
        "returns": tdf["ret"].tolist(),
        "cumulative": timeline_cumulative,
        "trades": tdf.to_dict("records"),
        "final": total_final - 1.0,
        "n_trades": len(tdf),
        "open_position": in_position,
        "open_entry_date": entry_date,
        "final_date": final_date,
        "cdi_idle_enabled": True,
        "dividend_proxy": "next_trading_day_after_data_com",
    }


def simulate_cdi_only(prices_df, cdi_df, valuation_dates=None, start_date=None):
    """Simula capital 100% em caixa remunerado a CDI."""
    if prices_df.empty:
        return {"dates": [], "cumulative": [], "final": 0.0, "n_trades": 0}

    df = prices_df.sort_values("data").copy()
    df["data"] = pd.to_datetime(df["data"])
    start_date = pd.Timestamp(start_date) if start_date is not None else pd.Timestamp(df["data"].iloc[0])

    cdi_map = {}
    if cdi_df is not None and not cdi_df.empty:
        cdi_map = {
            pd.Timestamp(row["data"]): float(row["taxa_diaria_pct"]) / 100.0
            for _, row in cdi_df.iterrows()
        }

    if valuation_dates is None:
        valuation_dates_set = set(pd.Timestamp(d) for d in df["data"] if pd.Timestamp(d) >= start_date)
    else:
        valuation_dates_set = set(pd.Timestamp(d) for d in valuation_dates if pd.Timestamp(d) >= start_date)

    cash = 1.0
    cumulative = []
    valid_dates = []

    for _, row in df.iterrows():
        current_date = pd.Timestamp(row["data"])
        if current_date < start_date:
            continue

        taxa = cdi_map.get(current_date)
        if taxa is not None and cash > 0:
            cash *= (1.0 + taxa)

        if current_date in valuation_dates_set:
            cumulative.append(cash - 1.0)
            valid_dates.append(current_date)

    if not valid_dates:
        return {"dates": [], "cumulative": [], "final": 0.0, "n_trades": 0}

    return {
        "dates": valid_dates,
        "cumulative": cumulative,
        "final": float(cumulative[-1]),
        "n_trades": 0,
        "cdi_idle_enabled": True,
    }


def simulate_buy_and_hold(signals_df, valuation_dates, start_date=None, cdi_df=None, div_df=None):
    """Baseline buy-and-hold com preco bruto, dividendos explicitos e CDI sobre caixa."""
    if not valuation_dates:
        return {"dates": [], "cumulative": [], "final": 0.0, "n_trades": 0}

    df = signals_df.sort_values("trade_idx").dropna(subset=["preco"]).copy()
    if df.empty:
        return {"dates": [], "cumulative": [], "final": 0.0, "n_trades": 0}

    start_date = start_date if start_date is not None else df["data"].iloc[0]
    trading_dates = df["data"].tolist()
    dividend_events = build_dividend_events(div_df if div_df is not None else pd.DataFrame(), trading_dates)
    cdi_map = {}
    if cdi_df is not None and not cdi_df.empty:
        cdi_map = {
            pd.Timestamp(row["data"]): float(row["taxa_diaria_pct"]) / 100.0
            for _, row in cdi_df.iterrows()
        }

    cash = 1.0
    shares = 0.0
    receivables = {}
    initialized = False
    valuation_dates_set = set(pd.Timestamp(d) for d in valuation_dates)
    cumulative = []
    valid_dates = []

    for _, row in df.iterrows():
        current_date = pd.Timestamp(row["data"])
        price = float(row["preco"])

        taxa = cdi_map.get(current_date)
        if taxa is not None and cash > 0:
            cash *= (1.0 + taxa)

        if current_date in receivables:
            cash += receivables.pop(current_date)

        if current_date in dividend_events and shares > 0:
            for event in dividend_events[current_date]:
                amount = shares * event["valor_cota"]
                credit_date = event["credit_date"]
                if credit_date is None:
                    receivables[pd.Timestamp.max] = receivables.get(pd.Timestamp.max, 0.0) + amount
                else:
                    receivables[credit_date] = receivables.get(credit_date, 0.0) + amount

        if not initialized and current_date == pd.Timestamp(start_date):
            shares = cash / price
            cash = 0.0
            initialized = True

        if current_date in valuation_dates_set and initialized:
            total_value = portfolio_value(cash, shares, price, receivables)
            cumulative.append(total_value - 1.0)
            valid_dates.append(current_date)

    if not valid_dates:
        return {"dates": [], "cumulative": [], "final": 0.0, "n_trades": 0}

    return {
        "dates": valid_dates,
        "cumulative": cumulative,
        "final": float(cumulative[-1]),
        "n_trades": len(valid_dates),
        "dividend_proxy": "next_trading_day_after_data_com",
    }
