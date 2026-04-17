from datetime import date, timedelta

from rich.console import Console
from rich.table import Table
from sqlalchemy import select, func

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import Dividendo, PrecoDiario, Ticker, get_session
from src.fii_analysis.features.composicao import classificar_fii, composicao_ativo
from src.fii_analysis.features.portfolio import carteira_panorama
from src.fii_analysis.features.saude import emissoes_recentes, flag_destruicao_capital, tendencia_pl
from src.fii_analysis.features.valuation import get_dy_n_meses, get_pvp_percentil

console = Console()


def _fmt(val, fmt=".2f", pct=False, suffix=""):
    if val is None:
        return "n/d"
    if pct:
        return f"{val * 100:{fmt}}%{suffix}"
    return f"{val:{fmt}}{suffix}"


def render_panorama(df=None):
    if df is None:
        session = get_session()
        ativos = tickers_ativos(session)
        df = carteira_panorama(ativos, session)
        session.close()

    table = Table(title="PANORAMA DA CARTEIRA", show_lines=False)
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Preco", justify="right")
    table.add_column("VP", justify="right")
    table.add_column("P/VP", justify="right")
    table.add_column("DY 12m", justify="right")
    table.add_column("DY 24m", justify="right")
    table.add_column("Rent. Acum", justify="right")
    table.add_column("Tipo", justify="center")
    table.add_column("Aviso", style="bold red")

    for _, row in df.iterrows():
        session = get_session()
        tipo = classificar_fii(row["ticker"], session)
        session.close()

        cvm_flag = "[CVM defasada]" if row.get("cvm_defasada") else ""
        table.add_row(
            row["ticker"],
            _fmt(row.get("preco"), ".2f", suffix=""),
            _fmt(row.get("vp"), ".2f"),
            _fmt(row.get("pvp"), ".4f"),
            _fmt(row.get("dy_12m"), ".2f", pct=True),
            _fmt(row.get("dy_24m"), ".2f", pct=True),
            _fmt(row.get("rent_acum"), ".2f", pct=True),
            tipo,
            cvm_flag,
        )

    console.print(table)

    # Rodapé: versão dos preços ajustados (point-in-time do yfinance)
    session = get_session()
    coletado_em_rows = {}
    for ticker_item in (df["ticker"].tolist() if df is not None else tickers_ativos()):
        ts = session.execute(
            select(func.max(PrecoDiario.coletado_em))
            .where(PrecoDiario.ticker == ticker_item)
        ).scalar_one_or_none()
        if ts:
            coletado_em_rows[ticker_item] = ts
    session.close()
    if coletado_em_rows:
        mais_antigo = min(coletado_em_rows.values())
        console.print(
            f"[dim][Nota: fechamento_aj (preço ajustado) recalculado retroativamente pelo yfinance. "
            f"Coletado em: {mais_antigo.strftime('%Y-%m-%d %H:%M') if hasattr(mais_antigo, 'strftime') else mais_antigo}][/dim]"
        )


def render_fii_detalhe(ticker: str):
    session = get_session()

    # Check if inactive
    inativo = session.execute(
        select(Ticker.inativo_em).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()

    inativo_label = ""
    if inativo is not None:
        inativo_label = f"  [bold red][INATIVO desde {inativo}][/bold red]"

    table = Table(title=f"DETALHE — {ticker}{inativo_label}", show_lines=True)
    table.add_column("Indicador", style="bold")
    table.add_column("Valor", justify="right")

    pan = carteira_panorama([ticker], session)
    if pan.empty:
        console.print(f"[red]Ticker {ticker} nao encontrado[/red]")
        session.close()
        return

    row = pan.iloc[0]
    table.add_row("Preco", _fmt(row.get("preco"), ".2f"))
    table.add_row("VP/cota", _fmt(row.get("vp"), ".4f"))
    table.add_row("P/VP", _fmt(row.get("pvp"), ".4f"))

    ultimo = session.execute(
        select(PrecoDiario.data).where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc()).limit(1)
    ).scalar_one_or_none()

    if ultimo:
        for janela in [252, 504, 756]:
            pct = get_pvp_percentil(ticker, ultimo, janela, session)
            table.add_row(f"P/VP pct ({janela}d)", _fmt(pct, ".1f") + " pct" if pct else "n/d")

        for n_meses in [12, 24, 36]:
            dy = get_dy_n_meses(ticker, ultimo, n_meses, session)
            table.add_row(f"DY {n_meses}m", _fmt(dy, ".2f", pct=True))

    comp = composicao_ativo(ticker, session)
    table.add_row("Tipo FII", classificar_fii(ticker, session))
    table.add_row("% Imoveis", _fmt(comp.get("pct_imoveis"), ".1f", pct=True))
    table.add_row("% Recebiveis", _fmt(comp.get("pct_recebiveis"), ".1f", pct=True))
    table.add_row("% Caixa", _fmt(comp.get("pct_caixa"), ".1f", pct=True))

    tend = tendencia_pl(ticker, session=session)
    for m, vals in tend.items():
        table.add_row(f"Tend. PL {m}m coef", _fmt(vals.get("coef_angular"), ".6f"))
        table.add_row(f"Tend. PL {m}m R2", _fmt(vals.get("r2"), ".4f"))

    destruicao = flag_destruicao_capital(ticker, session)
    status = "[red]ALERTA: destruicao de capital[/red]" if destruicao["destruicao"] else "[green]OK[/green]"
    table.add_row("Saude", status)
    table.add_row("Motivo", destruicao["motivo"])

    emiss = emissoes_recentes(ticker, session=session)
    if emiss:
        table.add_row("Emissoes recentes", f"{len(emiss)} eventos (>1%)")
        for e in emiss[:3]:
            table.add_row(f"  {e['data_ref']}", f"+{e['variacao_pct']:.1f}%")

    cvm_def = row.get("cvm_defasada", False)
    if cvm_def:
        table.add_row("[red]CVM[/red]", "[red]DEFASADA[/red]")

    console.print(table)
    session.close()


def render_carteira():
    session = get_session()
    ativos = tickers_ativos(session)
    df = carteira_panorama(ativos, session)

    console.print("\n[bold]Alocacao por Classificacao:[/bold]")
    from src.fii_analysis.features.composicao import classificar_fii as cf
    classificacoes = {}
    for _, row in df.iterrows():
        tipo = cf(row["ticker"], session)
        preco = row.get("preco") or 0
        classificacoes[tipo] = classificacoes.get(tipo, 0) + preco

    total = sum(classificacoes.values())
    for tipo, val in sorted(classificacoes.items(), key=lambda x: -x[1]):
        pct = val / total * 100 if total > 0 else 0
        console.print(f"  {tipo}: R$ {val:,.2f} ({pct:.1f}%)")

    from src.fii_analysis.features.portfolio import herfindahl
    pesos = [p for p in df["preco"].dropna().tolist() if p > 0]
    hh = herfindahl(pesos)
    console.print(f"\n[bold]Herfindahl:[/bold] {hh['hh']:.4f}  |  Maior peso: {hh['maior_peso']:.1%}")

    session.close()


def render_calendario(dias: int = 30):
    session = get_session()
    hoje = date.today()
    limite = hoje + timedelta(days=dias)

    table = Table(title=f"CALENDARIO DATAS-COM (proximos {dias} dias)")
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Data-Com", justify="center")
    table.add_column("Valor/cota", justify="right")
    table.add_column("Dias", justify="right")

    ativos = tickers_ativos(session)
    divs = session.execute(
        select(Dividendo.ticker, Dividendo.data_com, Dividendo.valor_cota)
        .where(
            Dividendo.data_com >= hoje,
            Dividendo.data_com <= limite,
            Dividendo.ticker.in_(ativos),
        )
        .order_by(Dividendo.data_com.asc())
    ).all()

    if not divs:
        console.print("[yellow]Nenhuma data-com nos proximos dias.[/yellow]")
    else:
        for d in divs:
            delta = (d.data_com - hoje).days
            table.add_row(d.ticker, str(d.data_com), _fmt(d.valor_cota, ".4f"), str(delta))

    console.print(table)
    session.close()
