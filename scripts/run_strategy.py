"""
Estratégia Dividend Capture — janela otimizada por ticker.

Para cada ticker:
  1. Otimiza (dias_antes, dias_depois) no período de TREINO
  2. Aplica a janela ótima no período de TESTE
  3. Compara com Buy-and-Hold no mesmo período de teste
  4. Roda CriticAgent nos dados de treino para avaliar qualidade do sinal
  5. Reporta métricas de risco (Sharpe, Sortino, drawdown, perdas consecutivas)

Retornos brutos E líquidos (custos + IR 20%) são reportados lado a lado.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fii_analysis.config import (
    TICKERS, TRAIN_START, TRAIN_END, TEST_START, TEST_END,
    DIAS_ANTES_RANGE, DIAS_DEPOIS_RANGE,
    CUSTO_POR_TRADE, IR_GANHO_CAPITAL,
)
from src.fii_analysis.data.database import get_session
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.models.critic import run_critic
from src.fii_analysis.models.strategy import (
    buy_and_hold_return,
    compute_risk_metrics,
    optimize_strategy,
    simulate_strategy,
)


def run_ticker(ticker: str, session) -> dict:
    print("\n" + "=" * 78)
    print(f"  {ticker}")
    print(f"  Treino: {TRAIN_START} a {TRAIN_END}")
    print(f"  Teste:  {TEST_START} a {TEST_END}")
    print(f"  Custo/trade: {CUSTO_POR_TRADE*100:.2f}%  |  IR ganho: {IR_GANHO_CAPITAL*100:.0f}%")
    print("=" * 78)

    # ── 1. Otimização no treino ──────────────────────────────────────────
    print("\n--- Otimizacao (treino) ---")
    opt = optimize_strategy(
        ticker, session,
        train_end_date=TRAIN_END,
        train_start_date=TRAIN_START,
        dias_antes_range=DIAS_ANTES_RANGE,
        dias_depois_range=DIAS_DEPOIS_RANGE,
        custo_por_trade=CUSTO_POR_TRADE,
        ir_ganho_capital=IR_GANHO_CAPITAL,
    )

    if opt["dias_antes"] is None:
        print("  Nenhum par valido no treino.")
        return {"ticker": ticker, "otimizado": False}

    da = opt["dias_antes"]
    dd = opt["dias_depois"]
    print(f"  Melhor janela:     dias_antes={da}, dias_depois={dd}")
    print(f"  Taxa acerto (liq): {opt['taxa_acerto'] * 100:.1f}%")
    print(f"  Retorno medio bruto:   {opt['retorno_medio_bruto'] * 100:.4f}%")
    print(f"  Retorno medio liquido: {opt['retorno_medio_liq'] * 100:.4f}%")
    print(f"  Eventos treino:        {opt['n_eventos']}")

    grid = opt["grid"].dropna(subset=["retorno_medio_liq"]).sort_values("retorno_medio_liq", ascending=False)
    print(f"\n  Top 5 pares (treino — por retorno liquido):")
    print(f"  {'Antes':>5} {'Depois':>6} {'Ac%':>5} {'Bruto%':>8} {'Liq%':>8} {'N':>4}")
    for _, r in grid.head(5).iterrows():
        print(f"  {int(r['dias_antes']):>5} {int(r['dias_depois']):>6} "
              f"{r['taxa_acerto']*100:>5.1f} {r['retorno_medio_bruto']*100:>8.4f} "
              f"{r['retorno_medio_liq']*100:>8.4f} {int(r['n_eventos']):>4}")

    # ── 2. Aplicar janela ótima no teste ────────────────────────────────
    print(f"\n--- Teste fora da amostra ({TEST_START} a {TEST_END}) ---")
    print(f"  Janela aplicada: dias_antes={da}, dias_depois={dd}")

    sim = simulate_strategy(ticker, da, dd, session,
                            start_date=TEST_START, end_date=TEST_END,
                            custo_por_trade=CUSTO_POR_TRADE,
                            ir_ganho_capital=IR_GANHO_CAPITAL)

    if sim.empty:
        print("  Nenhum evento no periodo de teste.")
        bh = buy_and_hold_return(ticker, session, TEST_START, TEST_END)
        return {"ticker": ticker, "otimizado": True, "da": da, "dd": dd,
                "n_teste": 0, "taxa": None, "ret_acum_bruto": None, "ret_acum_liq": None,
                "bh": bh["retorno_total"]}

    # retorno_liquido = retorno total (preço ajustado) - emolumentos B3
    n_trades = len(sim)
    taxa = float((sim["retorno_liquido"] > 0).mean())
    r_med = float(sim["retorno_liquido"].mean())
    r_acu = float((1 + sim["retorno_liquido"]).prod() - 1)

    # IR: 20% sobre ganho de capital bruto acumulado (ret_preco), não sobre dividendo
    # Prejuízo compensa lucro
    ret_preco_acum = float((1 + sim["ret_preco"].fillna(0)).prod() - 1)
    ir_devido = max(0.0, ret_preco_acum) * IR_GANHO_CAPITAL
    r_acu_pos_ir = r_acu - ir_devido

    print(f"  Eventos:               {n_trades}")
    print(f"  Taxa acerto:           {taxa * 100:.1f}%")
    print(f"  Retorno medio:         {r_med * 100:.4f}%")
    print(f"  Retorno acumulado:     {r_acu * 100:.4f}%")
    print(f"  Ganho capital bruto:   {ret_preco_acum * 100:.4f}%  (base p/ IR)")
    print(f"  IR devido (20%):       {ir_devido * 100:.4f}%")
    print(f"  Retorno pos-IR:        {r_acu_pos_ir * 100:.4f}%")

    # Métricas de risco
    risk = compute_risk_metrics(sim["retorno_liquido"])
    print(f"\n  --- Metricas de Risco ---")
    if risk["max_drawdown"] is not None:
        print(f"  Max Drawdown:          {risk['max_drawdown'] * 100:.2f}%")
        print(f"  Sharpe (anual):        {risk['sharpe']:.2f}" if risk["sharpe"] else "  Sharpe:                N/A")
        print(f"  Sortino (anual):       {risk['sortino']:.2f}" if risk["sortino"] else "  Sortino:               N/A")
        print(f"  Max perdas seguidas:   {risk['max_consecutive_losses']}")
    else:
        print("  Eventos insuficientes para metricas de risco.")

    print(f"\n  {'Data-com':>12}  {'Total%':>8}  {'Capital%':>9}  {'Div%':>7}")
    for _, r in sim.iterrows():
        rt = f"{r['retorno_liquido']*100:+.4f}"
        rp = f"{r['ret_preco']*100:+.4f}" if r["ret_preco"] is not None else "  N/A  "
        rd = f"{r['ret_dividendo']*100:+.4f}" if r["ret_dividendo"] is not None else "  N/A  "
        print(f"  {str(r['data_com']):>12}  {rt:>8}  {rp:>9}  {rd:>7}")

    # ── 3. Buy-and-Hold (preço ajustado = retorno total) ────────────────
    bh = buy_and_hold_return(ticker, session, TEST_START, TEST_END)
    print(f"\n--- Buy and Hold ({TEST_START} a {TEST_END}) ---")
    bh_ret = None
    if bh["preco_inicial"] is not None:
        bh_ret = bh["retorno_total"]
        print(f"  Retorno total (aj):  {bh_ret * 100:.4f}%")
        print(f"  Dividendos:          {bh['n_dividendos']} pagamentos")
    else:
        print("  Dados insuficientes.")

    if bh_ret is not None:
        diff = r_acu_pos_ir - bh_ret
        venc = "ESTRATEGIA" if diff > 0 else "BUY-AND-HOLD"
        print(f"\n--- Comparacao ---")
        print(f"  Estrategia (pos-IR):  {r_acu_pos_ir * 100:.4f}%")
        print(f"  Buy&Hold:             {bh_ret * 100:.4f}%")
        print(f"  Diferenca:            {diff * 100:.4f}% -> {venc} vence")

    # ── 4. CriticAgent (treino) ─────────────────────────────────────────
    windows = get_dividend_windows(ticker, session)
    if not windows.empty:
        wt = windows[
            (windows["data_com"] >= TRAIN_START) &
            (windows["data_com"] <= TRAIN_END)
        ].copy()
        if not wt.empty:
            print()
            run_critic(ticker, wt, session)

    return {
        "ticker": ticker, "otimizado": True,
        "da": da, "dd": dd,
        "n_treino": opt["n_eventos"],
        "n_teste": n_trades,
        "taxa_teste": taxa,
        "ret_acum": r_acu,
        "ret_acum_pos_ir": r_acu_pos_ir,
        "bh_ret": bh_ret,
        "risk": risk,
    }


def print_summary(resultados: list) -> None:
    print("\n\n" + "=" * 100)
    print("  RESUMO — RETORNO TOTAL (preco ajustado) | IR 20% s/ ganho de capital")
    print(f"  Treino: {TRAIN_START} a {TRAIN_END} | Teste: {TEST_START} a {TEST_END}")
    print(f"  Custo/trade: {CUSTO_POR_TRADE*100:.3f}% (emolumentos B3)")
    print("=" * 100)
    print(f"  {'Ticker':>8}  {'Janela':>10}  {'N':>3}  "
          f"{'Acerto%':>7}  {'RetAcum%':>9}  {'PosIR%':>8}  {'BH%':>8}  {'Diff%':>8}  "
          f"{'MaxDD%':>7}  {'Sharpe':>6}  {'MaxLoss':>7}")

    for r in resultados:
        if not r.get("otimizado"):
            print(f"  {r['ticker']:>8}  {'SEM DADOS':>10}")
            continue
        janela = f"{r['da']}d/{r['dd']}d"
        ac     = f"{r['taxa_teste']*100:.1f}" if r.get("taxa_teste") is not None else "N/A"
        ret    = f"{r['ret_acum']*100:.4f}" if r.get("ret_acum") is not None else "N/A"
        pir    = f"{r['ret_acum_pos_ir']*100:.4f}" if r.get("ret_acum_pos_ir") is not None else "N/A"
        bh_v   = f"{r['bh_ret']*100:.4f}" if r.get("bh_ret") is not None else "N/A"
        diff   = ""
        if r.get("ret_acum_pos_ir") is not None and r.get("bh_ret") is not None:
            d = r["ret_acum_pos_ir"] - r["bh_ret"]
            diff = f"{d*100:+.4f}"
        risk = r.get("risk", {})
        mdd    = f"{risk['max_drawdown']*100:.2f}" if risk.get("max_drawdown") is not None else "N/A"
        sharpe = f"{risk['sharpe']:.2f}" if risk.get("sharpe") is not None else "N/A"
        mloss  = f"{risk['max_consecutive_losses']}" if risk.get("max_consecutive_losses") is not None else "N/A"
        print(f"  {r['ticker']:>8}  {janela:>10}  {r.get('n_teste',0):>3}  "
              f"{ac:>7}  {ret:>9}  {pir:>8}  {bh_v:>8}  {diff:>8}  "
              f"{mdd:>7}  {sharpe:>6}  {mloss:>7}")

    print("=" * 100)
    print("  Retorno = preco ajustado (inclui dividendo). IR 20% s/ ganho capital bruto.")
    print("  Prejuizo compensa lucro. Emolumentos B3: 0.03%/trade.")
    print("=" * 100)


def main():
    session = get_session()
    resultados = []
    for ticker in TICKERS:
        resultados.append(run_ticker(ticker, session))
    print_summary(resultados)
    session.close()


if __name__ == "__main__":
    main()
