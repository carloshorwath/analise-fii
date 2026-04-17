from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from sqlalchemy import select

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import PrecoDiario, get_session
from src.fii_analysis.features.composicao import classificar_fii
from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital
from src.fii_analysis.features.valuation import get_pvp_percentil, get_dy_gap_percentil

console = Console()
ALERTAS_DIR = Path(__file__).resolve().parents[3] / "dados" / "alertas"


def _fmt(val, fmt=".2f"):
    if val is None:
        return "n/d"
    return f"{val:{fmt}}"


def gerar_alertas_diarios():
    session = get_session()
    hoje = date.today()
    linhas_terminal = []
    linhas_md = [f"# Alertas FII — {hoje.isoformat()}", ""]

    tem_alerta = False

    for ticker in tickers_ativos(session):
        ultimo = session.execute(
            select(PrecoDiario.data)
            .where(PrecoDiario.ticker == ticker)
            .order_by(PrecoDiario.data.desc())
            .limit(1)
        ).scalar_one_or_none()

        if ultimo is None:
            continue

        alertas_ticker = []

        destruicao = flag_destruicao_capital(ticker, session)
        if destruicao["destruicao"]:
            alertas_ticker.append(f"DESTRUICAO DE CAPITAL ({destruicao['motivo']})")

        emiss = emissoes_recentes(ticker, session=session)
        if emiss:
            alertas_ticker.append(f"{len(emiss)} emissoes recentes (>1%)")

        pvp_pct = get_pvp_percentil(ticker, ultimo, 504, session)
        if pvp_pct is not None and pvp_pct > 95:
            alertas_ticker.append(f"P/VP no percentil {pvp_pct:.0f} (muito caro)")

        dy_gap_pct = get_dy_gap_percentil(ticker, ultimo, 504, session)
        if dy_gap_pct is not None and dy_gap_pct < 5:
            alertas_ticker.append(f"DY Gap no percentil {dy_gap_pct:.0f} (DY baixo vs CDI)")

        if alertas_ticker:
            tem_alerta = True
            tipo = classificar_fii(ticker, session)
            header = f"[bold red]{ticker}[/bold red] ({tipo})"
            console.print(header)
            for a in alertas_ticker:
                console.print(f"  [yellow]- {a}[/yellow]")
                linhas_terminal.append(f"{ticker}: {a}")

            linhas_md.append(f"## {ticker} ({tipo})")
            for a in alertas_ticker:
                linhas_md.append(f"- {a}")
            linhas_md.append("")

    if not tem_alerta:
        console.print("[green]Nenhum alerta critico hoje.[/green]")
        linhas_md.append("Nenhum alerta critico.")

    session.close()

    ALERTAS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = ALERTAS_DIR / f"{hoje.isoformat()}.md"
    md_path.write_text("\n".join(linhas_md), encoding="utf-8")
    console.print(f"\n[dim]Salvo em {md_path}[/dim]")
