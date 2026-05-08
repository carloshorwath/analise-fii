"""Diagnostico de saude financeira — roda flag_destruicao_capital para todos os tickers ativos.

Mostra tabela comparativa com score, gravidade, tendencia, streaks e VP slope.
Ordena do pior para o melhor para identificar anomalias.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.features.saude import flag_destruicao_capital


def main():
    print("=" * 110)
    print("DIAGNÓSTICO DE SAÚDE FINANCEIRA — TODOS OS FUNDOS")
    print("=" * 110)

    with get_session_ctx() as session:
        tickers = tickers_ativos(session)
        print(f"\nTickers ativos: {len(tickers)}")
        print()

        results = []
        for ticker in tickers:
            try:
                r = flag_destruicao_capital(ticker, session)
                results.append((ticker, r))
            except Exception as e:
                results.append((ticker, {"error": str(e)}))

    # Header
    print(
        f"{'Ticker':<10} {'Score':>5} {'Gravidade':<18} {'Tendência':<12} "
        f"{'Strk Ativo':>10} {'Strk Máx':>8} {'Slope 3m':>10} {'Slope 6m':>10} "
        f"{'Em.Ruins':>8} {'Motivo'}"
    )
    print("-" * 110)

    # Sort by score_saude ascending (worst first)
    def sort_key(item):
        t, r = item
        if "error" in r:
            return -1
        return r.get("score_saude", 0)

    results.sort(key=sort_key)

    for ticker, r in results:
        if "error" in r:
            print(f"{ticker:<10} {'ERRO':>5} {r['error']}")
            continue

        score = r.get("score_saude", 0)
        grav = r.get("gravidade", "?")
        tend = r.get("tendencia", "?")
        cur = r.get("current_consec", 0)
        mx = r.get("max_consec_historico", 0)
        s3 = r.get("slope_3m")
        s6 = r.get("slope_6m")
        em = r.get("n_emissoes_ruins", 0)
        motivo = r.get("motivo", "")

        s3_str = f"{s3:+.4f}" if s3 is not None else "n/d"
        s6_str = f"{s6:+.4f}" if s6 is not None else "n/d"

        # Emoji por gravidade
        emoji = {"critica": "🔴", "alerta": "🟠", "em_recuperacao": "🟡", "saudavel": "🟢"}.get(grav, "⚪")

        print(
            f"{ticker:<10} {score:>5} {emoji} {grav:<16} {tend:<12} "
            f"{cur:>10} {mx:>8} {s3_str:>10} {s6_str:>10} "
            f"{em:>8} {motivo[:60]}"
        )

    print()
    print("=" * 110)
    print("RESUMO POR GRAVIDADE:")

    from collections import Counter
    grav_counts = Counter()
    for _, r in results:
        if "error" not in r:
            grav_counts[r.get("gravidade", "?")] += 1

    for g in ["critica", "alerta", "em_recuperacao", "saudavel"]:
        emoji = {"critica": "🔴", "alerta": "🟠", "em_recuperacao": "🟡", "saudavel": "🟢"}.get(g, "⚪")
        print(f"  {emoji} {g}: {grav_counts.get(g, 0)} fundos")

    print()
    scores = [r.get("score_saude", 0) for _, r in results if "error" not in r]
    if scores:
        print(f"Score médio: {sum(scores)/len(scores):.1f} | Mín: {min(scores)} | Máx: {max(scores)}")

    print("=" * 110)


if __name__ == "__main__":
    main()