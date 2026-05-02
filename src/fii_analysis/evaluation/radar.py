from rich.console import Console
from rich.table import Table

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.features.radar import radar_matriz

console = Console()


def render_radar(tickers: list[str] | None = None):
    from src.fii_analysis.data.database import get_session_ctx

    with get_session_ctx() as session:
        if tickers is None:
            tickers = tickers_ativos(session)

        df = radar_matriz(tickers, session)

        table = Table(title="RADAR DESCRITIVO", show_lines=False)
        table.add_column("Ticker", style="bold cyan")
        table.add_column("P/VP pct<30", justify="center")
        table.add_column("DY Gap pct>70", justify="center")
        table.add_column("Saude OK", justify="center")
        table.add_column("Liquidez OK", justify="center")
        table.add_column("Vistos", justify="center", style="bold")

        for _, row in df.iterrows():
            def _check(val):
                return "[green]v[/green]" if val else "[red]x[/red]"

            table.add_row(
                row["ticker"],
                _check(row["pvp_baixo"]),
                _check(row["dy_gap_alto"]),
                _check(row["saude_ok"]),
                _check(row["liquidez_ok"]),
                str(row["vistos"]) + "/4",
            )

        console.print(table)
