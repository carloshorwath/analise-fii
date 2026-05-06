import typer
from loguru import logger

app = typer.Typer(help="FII Analytics — analise de fundos imobiliarios")


@app.command()
def panorama():
    """Panorama geral da carteira monitorada."""
    from src.fii_analysis.evaluation.panorama import render_panorama
    render_panorama()


@app.command()
def fii(ticker: str):
    """Detalhe completo de um FII."""
    from src.fii_analysis.evaluation.panorama import render_fii_detalhe
    render_fii_detalhe(ticker)


@app.command()
def carteira():
    """Alocacao e concentracao da carteira."""
    from src.fii_analysis.evaluation.panorama import render_carteira
    render_carteira()


@app.command()
def calendario(dias: int = typer.Option(30, help="Numero de dias a frente")):
    """Datas-com dos proximos dias."""
    from src.fii_analysis.evaluation.panorama import render_calendario
    render_calendario(dias)


@app.command()
def alertas():
    """Gera alertas diarios de saude financeira."""
    from src.fii_analysis.evaluation.alertas import gerar_alertas_diarios
    gerar_alertas_diarios()


@app.command()
def radar():
    """Radar descritivo com filtros booleanos."""
    from src.fii_analysis.evaluation.radar import render_radar
    render_radar()


@app.command()
def consulta(ticker: str):
    """Consulta analítica via Gemini usando Google Search."""
    import subprocess
    from src.fii_analysis.data.database import get_session_ctx
    from src.fii_analysis.features.fundamentos import (
        get_dy_medias,
        get_pvp_medias,
        get_efetiva_vs_patrimonial_resumo
    )

    ticker = ticker.upper()
    with get_session_ctx() as session:
        pvp_atual = get_pvp_medias(ticker, session=session)['pvp_atual']
        dy_12m = get_dy_medias(ticker, session=session)['dy_12m_atual']
        saude = get_efetiva_vs_patrimonial_resumo(ticker, session=session)

        pvp_str = f"{pvp_atual:.2f}" if pvp_atual else "n/d"
        dy_str = f"{dy_12m * 100:.2f}%" if dy_12m else "n/d"
        saudaveis = saude.get("meses_saudaveis_6m", 0)
        consec = saude.get("meses_consecutivos_alerta", 0)
        total = saude.get("total_6m", 6)

        prompt = (
            f"Você é um analista de FIIs brasileiros. Use Google Search para buscar notícias recentes sobre {ticker}. "
            f"Dados quantitativos internos (calculados com point-in-time): "
            f"P/VP={pvp_str}, DY 12m={dy_str}, "
            f"Saúde financeira={saudaveis}/{total} meses saudáveis nos últimos 6m"
            f"{', ALERTA: ' + str(consec) + ' meses consecutivos distribuindo mais que gera' if consec >= 3 else ''}. "
            f"Retorne análise estruturada em 4 seções: "
            f"1. Sumário Executivo, 2. Análise Quantitativa (interprete os indicadores acima), "
            f"3. Estratégia (comprar/aguardar/evitar com justificativa), 4. Riscos."
        )

    subprocess.run(['gemini', '-p', prompt, '-o', 'text', '-y'], capture_output=False)


@app.command("update-prices")
def update_prices(
    force_snapshot: bool = typer.Option(False, "--force", help="Força regeneração do snapshot mesmo que já exista"),
):
    """Atualização diária: preços, dividendos, CDI, IFIX, cache otimizador e snapshot."""
    import sys as _sys
    from datetime import date
    from src.fii_analysis.config import tickers_ativos
    from src.fii_analysis.data.database import get_session_ctx
    from src.fii_analysis.data.ingestion import (
        load_prices_yfinance, load_dividends_yfinance,
        load_cdi_to_db, load_benchmark_yfinance, load_benchmark_brapi,
    )
    from src.fii_analysis.models.threshold_optimizer_v2 import (
        ThresholdOptimizerV2, load_optimizer_cache, save_optimizer_cache,
    )
    from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot

    logger.remove()
    logger.add(_sys.stderr, level="INFO")
    logger.info("=== fii update-prices — {} ===", date.today())

    with get_session_ctx() as session:
        tickers = tickers_ativos(session)
        logger.info("{} tickers ativos", len(tickers))

        logger.info("Atualizando precos...")
        for t in tickers:
            try:
                load_prices_yfinance(t, session)
            except Exception as e:
                logger.error("{}: {}", t, e)

        logger.info("Atualizando dividendos...")
        for t in tickers:
            try:
                load_dividends_yfinance(t, session)
            except Exception as e:
                logger.error("{}: {}", t, e)

        logger.info("Atualizando CDI...")
        try:
            load_cdi_to_db(session)
        except Exception as e:
            logger.error("CDI: {}", e)

        logger.info("Atualizando IFIX...")
        for fn in [lambda: load_benchmark_yfinance("IFIX.SA", session),
                   lambda: load_benchmark_brapi("IFIX.SA", session)]:
            try:
                fn()
            except Exception as e:
                logger.warning("IFIX: {}", e)

        logger.info("Verificando cache otimizador...")
        optimizer = ThresholdOptimizerV2()
        for t in tickers:
            try:
                if load_optimizer_cache(t, max_age_days=7) is None:
                    result = optimizer.optimize(t, session)
                    if result and result.get("best_params"):
                        save_optimizer_cache(t, result["best_params"])
                        logger.info("{}: cache otimizador salvo", t)
            except Exception as e:
                logger.error("{} otimizador: {}", t, e)

        logger.info("Gerando snapshot...")
        try:
            result = generate_daily_snapshot(session, scope="curado", force=force_snapshot)
            logger.info("Snapshot: {} | {}", result.get("status"), result.get("mensagem"))
        except Exception as e:
            logger.error("Snapshot: {}", e)

    logger.info("=== Concluido ===")


@app.command()
def diario():
    """Resumo das decisoes do dia no terminal (sem abrir o app Streamlit)."""
    import sys as _sys
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from src.fii_analysis.data.database import (
        get_session_ctx, get_latest_ready_snapshot_run,
        SnapshotDecisions, SnapshotTickerMetrics,
    )
    from sqlalchemy import select

    console = Console(width=120)
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session, scope="curado")
        if run is None:
            console.print("[yellow]Nenhum snapshot disponivel. Execute: fii update-prices[/yellow]")
            raise typer.Exit(1)

        decisions = session.execute(
            select(SnapshotDecisions).where(SnapshotDecisions.run_id == run.id)
            .order_by(SnapshotDecisions.acao, SnapshotDecisions.ticker)
        ).scalars().all()

        metrics_map: dict[str, SnapshotTickerMetrics] = {}
        metrics_rows = session.execute(
            select(SnapshotTickerMetrics).where(SnapshotTickerMetrics.run_id == run.id)
        ).scalars().all()
        for m in metrics_rows:
            metrics_map[m.ticker] = m

    ts = run.finalizado_em.strftime("%d/%m/%Y %H:%M") if run.finalizado_em else "?"
    console.print(f"\n[bold]Cockpit do Dia — snapshot {ts}[/bold]\n")

    _ACAO_COLOR = {
        "COMPRAR": "green", "VENDER": "red",
        "AGUARDAR": "yellow", "EVITAR": "magenta",
    }
    _CONC_PREFIX = {"ALTA": "[*]", "MEDIA": "[~]", "BAIXA": "[-]", "VETADA": "[!]"}

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    table.add_column("Ticker", style="bold", min_width=7, no_wrap=True)
    table.add_column("Acao", min_width=8, no_wrap=True)
    table.add_column("Concordancia", min_width=13, no_wrap=True)
    table.add_column("Otim", min_width=7, no_wrap=True)
    table.add_column("Epi", min_width=7, no_wrap=True)
    table.add_column("WF", min_width=7, no_wrap=True)
    table.add_column("Score", min_width=6, no_wrap=True)
    table.add_column("PVP%ile", min_width=7, no_wrap=True)
    table.add_column("DYGap%ile", min_width=9, no_wrap=True)

    for d in decisions:
        m = metrics_map.get(d.ticker)
        acao_color = _ACAO_COLOR.get(d.acao or "", "white")
        conc_prefix = _CONC_PREFIX.get(d.nivel_concordancia or "", "   ")
        conc_str = f"{conc_prefix} {d.nivel_concordancia or 'n/d'}"
        score_str = str(m.score_total) if m and m.score_total is not None else "n/d"
        pvp_str = f"{m.pvp_percentil:.0f}%" if m and m.pvp_percentil is not None else "n/d"
        dygap_str = f"{m.dy_gap_percentil:.0f}%" if m and m.dy_gap_percentil is not None else "n/d"
        table.add_row(
            d.ticker or "",
            f"[{acao_color}]{d.acao or 'n/d'}[/{acao_color}]",
            conc_str,
            d.sinal_otimizador or "n/d",
            d.sinal_episodio or "n/d",
            d.sinal_walkforward or "n/d",
            score_str,
            pvp_str,
            dygap_str,
        )

    console.print(table)
    console.print("[dim]Execute 'fii update-prices' para atualizar os dados.[/dim]\n")


if __name__ == "__main__":
    app()
