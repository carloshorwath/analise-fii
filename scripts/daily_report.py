"""CLI: gera relatorio diario de recomendacoes (MD + CSV).

Uso:
    python scripts/daily_report.py
    python scripts/daily_report.py --tickers KNIP11,CPTS11
    python scripts/daily_report.py --com-otimizador  # roda optimize() para cada ticker (lento)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rich.console import Console

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.decision import decidir_universo
from src.fii_analysis.evaluation.daily_report import salvar_relatorio
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2

console = Console()
ALERTAS_DIR = Path(__file__).resolve().parents[1] / "dados" / "alertas"


def _otimizar_universo(tickers: list[str], session) -> dict[str, dict]:
    """Roda optimize() para cada ticker e devolve mapa ticker -> best_params.

    Operacao cara (centenas de combinacoes por ticker). So usar quando o
    relatorio precisa do sinal do otimizador. Para o dia-a-dia, considere
    cachear os params em arquivo (futuro).
    """
    mapa: dict[str, dict] = {}
    for ticker in tickers:
        console.print(f"[dim]Otimizando {ticker}...[/dim]")
        try:
            opt = ThresholdOptimizerV2()
            res = opt.optimize(ticker, session)
            if "error" not in res and "best_params" in res:
                mapa[ticker] = res["best_params"]
            else:
                console.print(f"  [yellow]optimize falhou: {res.get('error', 'sem best_params')}[/yellow]")
        except Exception as exc:
            console.print(f"  [red]optimize erro: {exc}[/red]")
    return mapa


def main():
    parser = argparse.ArgumentParser(description="Relatorio diario de recomendacoes FII")
    parser.add_argument("--tickers", help="Lista separada por virgula. Default = tickers_ativos().")
    parser.add_argument("--com-otimizador", action="store_true",
                        help="Roda optimize() para cada ticker (lento). Sem isso, sinal do "
                             "otimizador fica como INDISPONIVEL.")
    parser.add_argument("--output-dir", default=str(ALERTAS_DIR),
                        help=f"Diretorio de saida (default: {ALERTAS_DIR})")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    data_ref = date.today()

    with get_session_ctx() as session:
        tickers = (
            [t.strip().upper() for t in args.tickers.split(",")]
            if args.tickers else tickers_ativos(session)
        )
        console.print(f"[bold]Avaliando {len(tickers)} ticker(s):[/bold] {', '.join(tickers)}")

        params_map = None
        if args.com_otimizador:
            console.print("[dim]Rodando otimizador para cada ticker (pode demorar)...[/dim]")
            params_map = _otimizar_universo(tickers, session)
            console.print(f"[green]Otimizador concluido para {len(params_map)}/{len(tickers)} tickers[/green]")

        console.print("[dim]Avaliando decisoes...[/dim]")
        decisoes = decidir_universo(session, tickers, params_map)

    paths = salvar_relatorio(decisoes, output_dir, data_ref=data_ref)

    # Resumo no terminal
    console.print()
    console.print(f"[bold green]Relatorio salvo:[/bold green]")
    console.print(f"  [cyan]MD :[/cyan] {paths['md']}")
    console.print(f"  [cyan]CSV:[/cyan] {paths['csv']}")
    console.print()

    # Sintese rapida do que foi recomendado
    acoes_buy = [d for d in decisoes if d.acao == "COMPRAR"]
    acoes_sell = [d for d in decisoes if d.acao == "VENDER"]
    vetadas = [d for d in decisoes if d.acao == "EVITAR"]

    if acoes_buy:
        console.print(f"[green]COMPRAR:[/green] {', '.join(d.ticker for d in acoes_buy)}")
    if acoes_sell:
        console.print(f"[red]VENDER:[/red] {', '.join(d.ticker for d in acoes_sell)}")
    if vetadas:
        console.print(f"[red]VETADAS:[/red] {', '.join(d.ticker for d in vetadas)}")
    if not (acoes_buy or acoes_sell or vetadas):
        console.print("[yellow]Nenhuma acao recomendada hoje (todas em AGUARDAR).[/yellow]")


if __name__ == "__main__":
    main()
