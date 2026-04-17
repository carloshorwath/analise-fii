from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from src.fii_analysis.data.database import Dividendo, PrecoDiario


def simulate_strategy(
    ticker: str,
    dias_antes: int,
    dias_depois: int,
    session,
    start_date: date | None = None,
    end_date: date | None = None,
    custo_por_trade: float = 0.0,
    ir_ganho_capital: float = 0.20,
) -> pd.DataFrame:
    """
    Simula a estratégia usando fechamento_aj (preço ajustado por dividendos).

    Com preços ajustados:
    - O efeito mecânico do ex-dividend está removido da série de preços.
    - O retorno (preco_venda_aj / preco_compra_aj - 1) já inclui o dividendo
      proporcional ao período de holding, sem necessidade de somar manualmente.
    - Não há distinção entre dias_depois=0 e dias_depois>=1 para o dividendo:
      o ajuste retroativo da série cuida disso automaticamente.
    """
    if dias_antes < 1:
        raise ValueError("dias_antes deve ser >= 1 (nao comprar na data-com)")
    if dias_depois < 1:
        raise ValueError("dias_depois deve ser >= 1 (nao vender na data-com)")

    pregoes = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not pregoes:
        return pd.DataFrame(
            columns=["data_com", "dividendo", "preco_compra", "data_compra", "preco_venda", "data_venda",
                     "retorno", "retorno_liquido", "ret_preco", "ret_dividendo", "preco_compra_raw", "preco_venda_raw"]
        )

    datas = [p.data for p in pregoes]
    fech_map     = {p.data: float(p.fechamento_aj) for p in pregoes if p.fechamento_aj is not None}
    fech_raw_map = {p.data: float(p.fechamento)    for p in pregoes if p.fechamento    is not None}
    datas_set = set(datas)

    q = select(Dividendo.data_com, Dividendo.valor_cota).where(Dividendo.ticker == ticker).order_by(Dividendo.data_com.asc())
    if start_date:
        q = q.where(Dividendo.data_com >= start_date)
    if end_date:
        q = q.where(Dividendo.data_com <= end_date)
    dividendos = session.execute(q).all()

    rows = []
    for data_com, valor_cota in dividendos:
        if data_com in datas_set:
            idx0 = datas.index(data_com)
        else:
            idx0 = None
            for i, d in enumerate(datas):
                if d > data_com:
                    break
                idx0 = i
            if idx0 is None:
                continue

        idx_compra = idx0 - dias_antes
        idx_venda = idx0 + dias_depois

        if idx_compra < 0 or idx_venda >= len(datas):
            continue

        preco_compra = fech_map.get(datas[idx_compra])
        preco_venda  = fech_map.get(datas[idx_venda])
        div = float(valor_cota) if valor_cota is not None else 0.0

        if preco_compra is None or preco_venda is None or preco_compra == 0:
            continue

        # Retorno total via preços ajustados (inclui dividendo implicitamente)
        ret = preco_venda / preco_compra - 1.0

        # Decomposição: preço bruto vs dividendo
        pc_raw = fech_raw_map.get(datas[idx_compra])
        pv_raw = fech_raw_map.get(datas[idx_venda])
        if pc_raw and pv_raw and pc_raw != 0:
            ret_preco = pv_raw / pc_raw - 1.0          # só movimento de preço (ganho de capital)
            ret_div   = div / pc_raw                    # contribuição do dividendo
        else:
            ret_preco = None
            ret_div   = None

        # Retorno líquido = retorno total (preço ajustado, inclui dividendo) - emolumentos B3
        # IR é calculado separadamente sobre ret_preco (ganho de capital bruto)
        # no report final. Dividendo de FII é isento de IR para PF.
        ret_liq = ret - custo_por_trade

        rows.append({
            "data_com": data_com,
            "dividendo": div,
            "preco_compra": preco_compra,
            "data_compra": datas[idx_compra],
            "preco_venda": preco_venda,
            "data_venda": datas[idx_venda],
            "retorno": ret,
            "retorno_liquido": ret_liq,
            "ret_preco": ret_preco,
            "ret_dividendo": ret_div,
            "preco_compra_raw": pc_raw,
            "preco_venda_raw": pv_raw,
        })

    return pd.DataFrame(rows)


def compute_risk_metrics(returns: pd.Series) -> dict:
    """
    Calcula métricas de risco a partir de uma série de retornos por trade.

    Returns:
        dict com max_drawdown, sharpe, sortino, max_consecutive_losses
    """
    if len(returns) < 2:
        return {
            "max_drawdown": None,
            "sharpe": None,
            "sortino": None,
            "max_consecutive_losses": None,
        }

    # Max drawdown: maior queda acumulada pico-a-vale
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdowns = (cumulative - running_max) / running_max
    max_dd = float(drawdowns.min())

    # Sharpe (anualizado: ~12 trades/ano para FIIs mensais)
    trades_por_ano = 12
    mean_ret = float(returns.mean())
    std_ret = float(returns.std())
    sharpe = (mean_ret / std_ret * np.sqrt(trades_por_ano)) if std_ret > 0 else None

    # Sortino (só penaliza downside)
    downside = returns[returns < 0]
    downside_std = float(downside.std()) if len(downside) > 1 else 0.0
    sortino = (mean_ret / downside_std * np.sqrt(trades_por_ano)) if downside_std > 0 else None

    # Max perdas consecutivas
    is_loss = (returns < 0).astype(int)
    max_consec = 0
    current = 0
    for loss in is_loss:
        if loss:
            current += 1
            max_consec = max(max_consec, current)
        else:
            current = 0

    return {
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_consecutive_losses": max_consec,
    }


def optimize_strategy(
    ticker: str,
    session,
    train_end_date: date,
    train_start_date: date | None = None,
    dias_antes_range=range(1, 11),
    dias_depois_range=range(1, 11),
    custo_por_trade: float = 0.0,
    ir_ganho_capital: float = 0.20,
) -> dict:
    grid_rows = []
    best = None

    for da in dias_antes_range:
        for dd in dias_depois_range:
            sim = simulate_strategy(ticker, da, dd, session,
                                    start_date=train_start_date, end_date=train_end_date,
                                    custo_por_trade=custo_por_trade,
                                    ir_ganho_capital=ir_ganho_capital)
            n = len(sim)
            if n == 0:
                grid_rows.append({"dias_antes": da, "dias_depois": dd, "taxa_acerto": None,
                                  "retorno_medio_bruto": None, "retorno_medio_liq": None, "n_eventos": 0})
                continue

            taxa = float((sim["retorno_liquido"] > 0).mean())
            ret_bruto = float(sim["retorno"].mean())
            ret_liq = float(sim["retorno_liquido"].mean())
            grid_rows.append({"dias_antes": da, "dias_depois": dd, "taxa_acerto": taxa,
                              "retorno_medio_bruto": ret_bruto, "retorno_medio_liq": ret_liq, "n_eventos": n})

            # Otimiza pelo retorno líquido — evita selecionar pares que só funcionam brutos
            if best is None or ret_liq > best["retorno_medio_liq"]:
                best = {"dias_antes": da, "dias_depois": dd, "taxa_acerto": taxa,
                        "retorno_medio_bruto": ret_bruto, "retorno_medio_liq": ret_liq, "n_eventos": n}

    grid_df = pd.DataFrame(grid_rows)

    if best is None:
        return {"dias_antes": None, "dias_depois": None, "taxa_acerto": None,
                "retorno_medio_bruto": None, "retorno_medio_liq": None, "n_eventos": 0, "grid": grid_df}

    return {**best, "grid": grid_df}


def buy_and_hold_return(
    ticker: str,
    session,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Retorno buy-and-hold usando fechamento_aj.

    fechamento_aj é o preço ajustado retroativamente por todos os dividendos.
    O retorno (p_fim_aj / p_ini_aj - 1) é o retorno total (preço + dividendos)
    sem precisar somar dividendos manualmente — eles já estão na série ajustada.
    """
    preco_ini = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data >= start_date)
        .order_by(PrecoDiario.data.asc())
        .limit(1)
    ).first()

    preco_fim = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= end_date)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).first()

    if not preco_ini or not preco_fim:
        return {"preco_inicial": None, "data_inicial": None, "preco_final": None, "data_final": None, "dividendos_recebidos": None, "retorno_total": None, "n_dividendos": 0}

    p_ini = float(preco_ini[1])
    p_fim = float(preco_fim[1])

    n_div = session.execute(
        select(func.count()).select_from(Dividendo).where(
            Dividendo.ticker == ticker,
            Dividendo.data_com >= preco_ini[0],
            Dividendo.data_com <= preco_fim[0],
        )
    ).scalar_one()

    ret = p_fim / p_ini - 1.0

    return {
        "preco_inicial": p_ini,
        "data_inicial": preco_ini[0],
        "preco_final": p_fim,
        "data_final": preco_fim[0],
        "dividendos_recebidos": None,
        "retorno_total": ret,
        "n_dividendos": n_div,
    }


def print_strategy_report(ticker: str, session) -> None:
    """Legacy report function — prefer run_strategy.py for full analysis."""
    hoje = date.today()
    train_end = hoje - timedelta(days=365)

    print("=" * 70)
    print(f"  ESTRATEGIA DIVIDEND-CAPTURE — {ticker}")
    print("=" * 70)

    print(f"\n  Treino: ate {train_end}")
    print(f"  Teste:  {train_end} a {hoje}")

    print("\n--- Otimizacao (treino) ---")
    opt = optimize_strategy(ticker, session, train_end)

    if opt["dias_antes"] is None:
        print("  Nenhum par valido encontrado no treino.")
        print("=" * 70)
        return

    print(f"  Melhor par: dias_antes={opt['dias_antes']}, dias_depois={opt['dias_depois']}")
    print(f"  Taxa acerto treino: {opt['taxa_acerto'] * 100:.1f}%")
    print(f"  Retorno medio bruto: {opt['retorno_medio_bruto'] * 100:.4f}%")
    print(f"  Retorno medio liq:   {opt['retorno_medio_liq'] * 100:.4f}%")
    print(f"  Eventos treino: {opt['n_eventos']}")

    grid = opt["grid"]
    valid_grid = grid.dropna(subset=["retorno_medio_liq"]).sort_values("retorno_medio_liq", ascending=False)
    print(f"\n  Top 5 pares (treino):")
    print(f"  {'Antes':>6} {'Depois':>7} {'Acerto%':>9} {'RetLiq%':>10} {'N':>4}")
    for _, r in valid_grid.head(5).iterrows():
        acerto = f"{r['taxa_acerto'] * 100:.1f}" if r["taxa_acerto"] is not None else "N/A"
        ret = f"{r['retorno_medio_liq'] * 100:.4f}" if r["retorno_medio_liq"] is not None else "N/A"
        print(f"  {int(r['dias_antes']):>6} {int(r['dias_depois']):>7} {acerto:>9} {ret:>10} {int(r['n_eventos']):>4}")

    print(f"\n--- Teste (fora da amostra) ---")
    sim_teste = simulate_strategy(ticker, opt["dias_antes"], opt["dias_depois"], session, start_date=train_end)

    if sim_teste.empty:
        print("  Nenhum evento no periodo de teste.")
        print("=" * 70)
        return

    taxa_teste = float((sim_teste["retorno_liquido"] > 0).mean())
    ret_medio_teste = float(sim_teste["retorno_liquido"].mean())
    ret_acumulado = float((1 + sim_teste["retorno_liquido"]).prod() - 1)

    print(f"  Parametros: antes={opt['dias_antes']}, depois={opt['dias_depois']}")
    print(f"  Eventos teste:     {len(sim_teste)}")
    print(f"  Taxa acerto (liq): {taxa_teste * 100:.1f}%")
    print(f"  Retorno medio liq: {ret_medio_teste * 100:.4f}%")
    print(f"  Acumulado liq:     {ret_acumulado * 100:.4f}%")

    print(f"\n--- Buy and Hold (mesmo periodo) ---")
    bh = buy_and_hold_return(ticker, session, train_end, hoje)
    if bh["preco_inicial"] is not None:
        print(f"  Preco inicial:     R$ {bh['preco_inicial']:.2f} ({bh['data_inicial']})")
        print(f"  Preco final:       R$ {bh['preco_final']:.2f} ({bh['data_final']})")
        print(f"  Dividendos:        inclusos no preco ajustado ({bh['n_dividendos']} pagamentos)")
        print(f"  Retorno total:     {bh['retorno_total'] * 100:.4f}%")
    else:
        print("  Dados insuficientes para buy-and-hold.")

    print(f"\n--- Comparacao ---")
    if bh["preco_inicial"] is not None:
        diff = ret_acumulado - bh["retorno_total"]
        vencedor = "ESTRATEGIA" if diff > 0 else "BUY-AND-HOLD"
        print(f"  Estrategia (liq): {ret_acumulado * 100:.4f}%")
        print(f"  Buy&Hold:         {bh['retorno_total'] * 100:.4f}%")
        print(f"  Diferenca:        {diff * 100:.4f}% -> {vencedor}")

    print(f"\n  AVISO: resultados do treino NAO devem ser usados para decisao.")
    print(f"  Apenas o teste conta. Treino serve apenas para escolher parametros.")
    print("=" * 70)

