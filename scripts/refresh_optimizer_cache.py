"""Atualiza o cache de parâmetros do otimizador para todos os tickers ativos.

Uso:
    python scripts/refresh_optimizer_cache.py
    python scripts/refresh_optimizer_cache.py --tickers KNIP11,CPTS11

Roda o ThresholdOptimizerV2.optimize() para cada ticker e salva em
dados/optimizer_cache/{ticker}.json. Executar semanalmente (ex: toda segunda).
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fii_analysis.config import TICKERS, tickers_ativos
from src.fii_analysis.data.database import create_tables, get_session_ctx
from src.fii_analysis.models.threshold_optimizer_v2 import (
    ThresholdOptimizerV2,
    save_optimizer_cache,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atualiza cache do otimizador")
    parser.add_argument(
        "--tickers",
        default="",
        help="Lista de tickers separados por vírgula (padrão: todos os ativos do config)",
    )
    args = parser.parse_args()

    create_tables()
    optimizer = ThresholdOptimizerV2()

    with get_session_ctx() as session:
        ativos = set(tickers_ativos(session))
        if args.tickers:
            alvo = [t.strip() for t in args.tickers.split(",") if t.strip()]
        else:
            alvo = [t for t in TICKERS if t in ativos]

        print(f"Atualizando cache para: {alvo}")
        ok = 0
        falhos = []
        for ticker in alvo:
            print(f"  {ticker}...", end=" ", flush=True)
            try:
                result = optimizer.optimize(ticker, session)
                if "error" in result or not result.get("best_params"):
                    print(f"ERRO: {result.get('error', 'sem best_params')}")
                    falhos.append(ticker)
                else:
                    save_optimizer_cache(ticker, result["best_params"])
                    print(f"OK (buy_pct={result['best_params'].get('pvp_percentil_buy')})")
                    ok += 1
            except Exception as e:
                print(f"EXCECAO: {e}")
                falhos.append(ticker)

    print(f"\nConcluido: {ok} OK, {len(falhos)} falhos")
    if falhos:
        print(f"Falhos: {falhos}")
        sys.exit(1)


if __name__ == "__main__":
    main()
