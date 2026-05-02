"""Script CLI para gerar snapshot diário de FIIs.

Uso:
    python scripts/generate_daily_snapshots.py --scope curado
    python scripts/generate_daily_snapshots.py --scope carteira --force
    python scripts/generate_daily_snapshots.py --scope db_ativos

Lógica de negócio em: src/fii_analysis/evaluation/daily_snapshots.py
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from src.fii_analysis.data.database import Carteira, create_tables, get_session_ctx
from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot


def _load_holdings(session) -> list[dict]:
    rows = session.execute(select(Carteira)).scalars().all()
    return [
        {
            "ticker": r.ticker,
            "quantidade": r.quantidade,
            "preco_medio": float(r.preco_medio),
            "data_compra": str(r.data_compra),
        }
        for r in rows
    ]


def _print_result(result: dict) -> None:
    status = result["status"]
    run_id = result.get("run_id", "?")
    data = result.get("data_referencia", "?")
    print(f"[{status.upper()}] run_id={run_id}  data={data}")

    if status == "ready":
        print(f"  metrics   : {result.get('n_metrics', 0)} tickers")
        print(f"  radar     : {result.get('n_radar', 0)} tickers")
        print(f"  decisions : {result.get('n_decisions', 0)} tickers")
        n_adv = result.get("n_advices", 0)
        if n_adv:
            print(f"  advices   : {n_adv} posições")
            print(f"  alertas   : {result.get('n_alerts', 0)}")
        falhos = result.get("tickers_falhos", [])
        if falhos:
            print(f"  falhos    : {falhos}")
    elif status == "already_ready":
        print(f"  {result.get('mensagem')}")
    else:
        print(f"  erro: {result.get('mensagem')}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera snapshot diário de FIIs")
    parser.add_argument(
        "--scope",
        default="curado",
        choices=["curado", "carteira", "db_ativos"],
        help="Universo a processar (default: curado)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerar mesmo se snapshot ready já existe para hoje",
    )
    args = parser.parse_args()

    create_tables()

    with get_session_ctx() as session:
        holdings: list[dict] = []
        if args.scope == "carteira":
            holdings = _load_holdings(session)
            if not holdings:
                print("Aviso: carteira vazia — gerando sem portfolio advices")

        result = generate_daily_snapshot(
            session,
            scope=args.scope,
            holdings=holdings or None,
            force=args.force,
        )

    _print_result(result)

    if result["status"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
