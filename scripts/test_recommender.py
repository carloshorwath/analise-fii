"""Sanity check do motor de decisao — roda decidir_ticker(KNIP11) e imprime."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.decision import decidir_ticker


def main():
    print("=" * 70)
    print("Sanity check: decidir_ticker('KNIP11')")
    print("=" * 70)

    with get_session_ctx() as session:
        d = decidir_ticker("KNIP11", session)

    print(f"\nTicker:        {d.ticker}")
    print(f"Data ref:      {d.data_referencia}")
    print(f"Classificacao: {d.classificacao}")

    print("\n--- SINAIS ---")
    print(f"  Otimizador:   {d.sinal_otimizador}")
    print(f"  Episodios:    {d.sinal_episodio}")
    print(f"  WalkForward:  {d.sinal_walkforward}")

    print("\n--- RISCO ---")
    print(f"  Destruicao capital: {d.flag_destruicao_capital} ({d.motivo_destruicao})")
    print(f"  Emissao recente:    {d.flag_emissao_recente}")
    print(f"  P/VP caro (>p95):   {d.flag_pvp_caro}")
    print(f"  DY Gap baixo (<p5): {d.flag_dy_gap_baixo}")

    print("\n--- ACAO ---")
    print(f"  Acao:               {d.acao}")
    print(f"  Concordancia:       {d.nivel_concordancia}")
    print(f"  n BUY: {d.n_concordam_buy} | n SELL: {d.n_concordam_sell}")

    print("\n--- CONTEXTO ---")
    print(f"  P/VP atual:        {d.pvp_atual}")
    print(f"  P/VP percentil:    {d.pvp_percentil}")
    print(f"  DY Gap percentil:  {d.dy_gap_percentil}")
    print(f"  Preco referencia:  {d.preco_referencia}")

    print("\n--- ESTATISTICA HISTORICA ---")
    print(f"  N episodios BUY:    {d.n_episodios_buy}")
    print(f"  Win rate BUY:       {d.win_rate_buy}")
    print(f"  Retorno medio BUY:  {d.retorno_medio_buy}")
    print(f"  Drawdown tipico:    {d.drawdown_tipico_buy}")
    print(f"  p-value WF BUY:     {d.p_value_wf_buy}")
    print(f"  N steps WF:         {d.n_steps_wf}")

    if d.rationale:
        print("\n--- RATIONALE ---")
        for r in d.rationale:
            print(f"  - {r}")

    print("\n" + "=" * 70)
    print("OK")
    print("=" * 70)


if __name__ == "__main__":
    main()
