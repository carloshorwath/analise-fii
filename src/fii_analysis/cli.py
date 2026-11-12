import typer
from typing import Optional
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
def prompt(
    ticker: Optional[str] = typer.Argument(None, help="Ticker do FII (ex: KNIP11)"),
    oportunidades: bool = typer.Option(False, "--oportunidades", help="Gera prompts para todas as oportunidades de rotação ativas"),
):
    """Gera Prompt Pack local em Markdown para colagem manual."""
    from rich.console import Console
    from sqlalchemy import select
    from src.fii_analysis.data.database import get_session_ctx, get_latest_ready_snapshot_run, SnapshotOpportunities
    from src.fii_analysis.llm.context_builder import build_ticker_context, build_opportunity_context
    from src.fii_analysis.llm.gateway import export_prompt_pack
    from src.fii_analysis.llm.prompts import render_prompt

    console = Console()

    if oportunidades:
        with get_session_ctx() as session:
            run = get_latest_ready_snapshot_run(session)
            if run is None:
                console.print("[red]Nenhum snapshot pronto encontrado. Execute 'fii update-prices' primeiro.[/red]")
                raise typer.Exit(1)
            
            opps = session.execute(
                select(SnapshotOpportunities).where(SnapshotOpportunities.run_id == run.id)
            ).scalars().all()
            
            if not opps:
                console.print("[yellow]Nenhuma oportunidade de rotação ativa no último snapshot.[/yellow]")
                return
            
            for o in opps:
                ctx = build_opportunity_context(o.vender, o.comprar, session)
                sys_prompt, user_prompt, _ = render_prompt("oportunidade_rotacao", ctx)
                ticker_pair = f"{o.vender}_{o.comprar}"
                filepath = export_prompt_pack(sys_prompt, user_prompt, "oportunidade_rotacao", ticker_pair)
                console.print(f"[green]Prompt Pack de rotação gerado em:[/green] [bold]{filepath}[/bold]")
        return

    if not ticker:
        console.print("[red]Ticker ou a opção --oportunidades deve ser fornecido.[/red]")
        raise typer.Exit(1)

    ticker = ticker.upper()
    with get_session_ctx() as session:
        ctx = build_ticker_context(ticker, session)
        if "erro" in ctx:
            console.print(f"[red]{ctx['erro']}[/red]")
            raise typer.Exit(1)
        sys_prompt, user_prompt, _ = render_prompt("analise_ticker", ctx)
        filepath = export_prompt_pack(sys_prompt, user_prompt, "analise_ticker", ticker)
        console.print(f"[green]Prompt Pack gerado em:[/green] [bold]{filepath}[/bold]")


@app.command()
def analise(
    ticker: str,
    pergunta: Optional[str] = typer.Option(None, "--pergunta", "-p", help="Pergunta extra para a análise qualitativa"),
    via_n8n: bool = typer.Option(True, help="Tenta enviar a requisição automática via n8n"),
):
    """Análise qualitativa enriquecida com IA (via gateway ou prompt pack)."""
    from rich.console import Console
    from src.fii_analysis.data.database import get_session_ctx, get_latest_ready_snapshot_run
    from src.fii_analysis.llm.context_builder import build_ticker_context
    from src.fii_analysis.llm.gateway import ask_llm, export_prompt_pack
    from src.fii_analysis.llm.journal import registrar_resposta_llm
    from src.fii_analysis.llm.prompts import render_prompt, PROMPTS

    console = Console()
    ticker = ticker.upper()

    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session)
        run_id = run.id if run else None

        ctx = build_ticker_context(ticker, session)
        if "erro" in ctx:
            console.print(f"[red]{ctx['erro']}[/red]")
            raise typer.Exit(1)

        if not via_n8n:
            sys_prompt, user_prompt, _ = render_prompt("analise_ticker", ctx, pergunta)
            filepath = export_prompt_pack(sys_prompt, user_prompt, "analise_ticker", ticker)
            console.print(f"[yellow]Modo local ativo.[/yellow] Prompt Pack exportado para: [bold]{filepath}[/bold]")
            return

        console.print(f"[cyan]Enviando contexto de {ticker} para o gateway LLM...[/cyan]")
        res = ask_llm("analise_ticker", ctx, pergunta)

        if res.status == "OK":
            console.print("\n[bold green]=== Análise Qualitativa (Opinião LLM — não validada estatisticamente) ===[/bold green]\n")
            console.print(res.resposta_md)
            console.print(f"\n[dim]Modelo: {res.modelo} | Latência: {res.latencia_ms}ms[/dim]\n")
            
            version = PROMPTS["analise_ticker"]["version"]
            registrar_resposta_llm(
                session=session,
                template="analise_ticker",
                prompt_version=version,
                ticker=ticker,
                snapshot_run_id=run_id,
                resposta_md=res.resposta_md,
                modelo=res.modelo,
                latencia_ms=res.latencia_ms
            )
            session.commit()
        else:
            console.print(f"\n[red]Falha no gateway LLM (status: {res.status}).[/red]")
            if res.erro_mensagem:
                console.print(f"[red]Mensagem: {res.erro_mensagem}[/red]")
            if res.prompt_pack_path:
                console.print(f"[yellow]Fallback ativo.[/yellow] Prompt Pack gerado para colagem manual em:\n[bold]{res.prompt_pack_path}[/bold]\n")


@app.command()
def consulta(ticker: str):
    """[DEPRECADO] Use 'fii analise TICKER' para análise qualitativa via n8n ou prompt pack."""
    logger.warning("O comando 'consulta' foi deprecado e será removido. Use 'fii analise {}' no lugar.", ticker)
    analise(ticker, pergunta=None, via_n8n=True)


@app.command("update-prices")
def update_prices(
    force_snapshot: bool = typer.Option(False, "--force", help="Força regeneração do snapshot mesmo que já exista"),
    scope: str = typer.Option("ifix", help="Escopo de tickers a atualizar (ifix = IFIX ∪ curado ∪ carteira; ou curado)"),
):
    """Atualização diária: preços, dividendos, CDI, IFIX, cache otimizador e snapshot."""
    import sys as _sys
    from datetime import date
    from src.fii_analysis.config import tickers_ativos
    from src.fii_analysis.data.database import get_session_ctx
    from src.fii_analysis.data.ingestion import (
        load_prices_yfinance, load_dividends_yfinance,
        load_cdi_to_db, load_benchmark_yfinance,
        refresh_cvm_current_year,
    )
    from src.fii_analysis.models.threshold_optimizer_v2 import (
        ThresholdOptimizerV2, load_optimizer_cache, save_optimizer_cache,
    )
    from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot, resolve_snapshot_universe

    logger.remove()
    logger.add(_sys.stderr, level="INFO")
    logger.info("=== fii update-prices — {} ===", date.today())

    with get_session_ctx() as session:
        try:
            tickers = resolve_snapshot_universe(session, scope=scope)
        except Exception:
            tickers = tickers_ativos(session)
            
        logger.info("{} tickers encontrados no escopo '{}'", len(tickers), scope)

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

        logger.info("Verificando relatorios CVM (ZIP do ano corrente)...")
        try:
            refresh_cvm_current_year(session)
        except Exception as e:
            logger.error("CVM refresh: {}", e)

        logger.info("Atualizando CDI...")
        try:
            load_cdi_to_db(session)
        except Exception as e:
            logger.error("CDI: {}", e)

        logger.info("Atualizando XFIX11 (yfinance)...")
        try:
            load_benchmark_yfinance("XFIX11", session)
        except Exception as e:
            logger.warning("XFIX11: {}", e)

        # Otimizador roda apenas para os tickers de decisão (curado + carteira) —
        # o universo IFIX é observação (métricas/radar) e não passa pelos 3 motores.
        decision_tickers = sorted(
            set(resolve_snapshot_universe(session, "curado"))
            | set(resolve_snapshot_universe(session, "carteira"))
        )
        logger.info("Verificando cache otimizador ({} tickers de decisão)...", len(decision_tickers))
        optimizer = ThresholdOptimizerV2()
        for t in decision_tickers:
            try:
                if load_optimizer_cache(t, max_age_days=7) is None:
                    result = optimizer.optimize(t, session)
                    if result and result.get("best_params"):
                        save_optimizer_cache(t, result["best_params"])
                        logger.info("{}: cache otimizador salvo", t)
            except Exception as e:
                logger.error("{} otimizador: {}", t, e)

        logger.info("Gerando snapshot para o escopo '{}'...", scope)
        try:
            from src.fii_analysis.data.database import Carteira
            from sqlalchemy import select as _select
            carteira_rows = session.execute(_select(Carteira)).scalars().all()
            holdings = [
                {
                    "ticker": c.ticker,
                    "quantidade": c.quantidade,
                    "preco_medio": float(c.preco_medio),
                    "data_compra": c.data_compra,
                }
                for c in carteira_rows
            ] or None
            result = generate_daily_snapshot(
                session, scope=scope, holdings=holdings, force=force_snapshot
            )
            logger.info("Snapshot: {} | {}", result.get("status"), result.get("mensagem"))
        except Exception as e:
            logger.error("Snapshot: {}", e)

    logger.info("=== Concluido ===")


@app.command()
def diario(
    diff: bool = typer.Option(True, "--diff/--no-diff", help="Compara com o snapshot anterior e exibe as mudanças"),
):
    """Resumo das decisoes do dia no terminal (sem abrir o app Streamlit)."""
    import sys as _sys
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from rich.markdown import Markdown
    from src.fii_analysis.data.database import (
        get_session_ctx, get_latest_ready_snapshot_run,
        SnapshotDecisions, SnapshotTickerMetrics, SnapshotRun,
    )
    from src.fii_analysis.evaluation.daily_diff import calcular_diff_diario, render_diff_markdown
    from sqlalchemy import select

    console = Console(width=120)
    with get_session_ctx() as session:
        if diff:
            runs = session.execute(
                select(SnapshotRun)
                .where(SnapshotRun.status == "ready")
                .order_by(SnapshotRun.data_referencia.desc(), SnapshotRun.criado_em.desc())
                .limit(2)
            ).scalars().all()
            
            if len(runs) >= 2:
                run_atual, run_anterior = runs[0], runs[1]
                diff_obj = calcular_diff_diario(session, run_atual.id, run_anterior.id)
                diff_md = render_diff_markdown(diff_obj)
                console.print(Markdown(diff_md))
                console.print("\n" + "="*80 + "\n")
            elif len(runs) == 1:
                console.print("[yellow]Apenas 1 snapshot disponível. Sem histórico para comparar.[/yellow]\n")

        run = get_latest_ready_snapshot_run(session)
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


@app.command()
def oportunidades():
    """Exibe as oportunidades de rotação ativas a partir do último snapshot."""
    import sys as _sys
    import json
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from src.fii_analysis.data.database import (
        get_session_ctx, get_latest_ready_snapshot_run,
        SnapshotOpportunities,
    )
    from sqlalchemy import select

    console = Console(width=120)
    with get_session_ctx() as session:
        run = get_latest_ready_snapshot_run(session)
        if run is None:
            console.print("[yellow]Nenhum snapshot disponivel. Execute: fii update-prices[/yellow]")
            raise typer.Exit(1)

        opps = session.execute(
            select(SnapshotOpportunities).where(SnapshotOpportunities.run_id == run.id)
            .order_by(SnapshotOpportunities.spread_liquido_pct.desc())
        ).scalars().all()

    ts = run.finalizado_em.strftime("%d/%m/%Y %H:%M") if run.finalizado_em else "?"
    console.print(f"\n[bold]Oportunidades de Rotação — snapshot {ts}[/bold]\n")

    if not opps:
        console.print("[green]Nenhuma oportunidade acionável hoje.[/green]\n")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold green")
    table.add_column("Vender", style="bold red", min_width=7, no_wrap=True)
    table.add_column("Comprar", style="bold green", min_width=7, no_wrap=True)
    table.add_column("Segmento", min_width=10, no_wrap=True)
    table.add_column("Spread PVP", min_width=10, no_wrap=True)
    table.add_column("Custo Est.", min_width=10, no_wrap=True)
    table.add_column("Spread Líq.", min_width=11, no_wrap=True)
    table.add_column("Delta Score", min_width=11, no_wrap=True)
    table.add_column("Veredicto", min_width=11, no_wrap=True)

    for o in opps:
        table.add_row(
            o.vender,
            o.comprar,
            o.segmento,
            f"{o.spread_pvp_pct:+.1f} pp",
            f"{o.custo_estimado_pct:.2f}%",
            f"{o.spread_liquido_pct:+.1f} pp",
            f"{o.delta_score:+.0f}",
            o.critic_veredicto,
        )

    console.print(table)
    console.print()


@app.command("registrar-decisao")
def registrar_decisao_cli(
    tipo: str = typer.Option(..., "--tipo", help="COMPRA / VENDA / ROTACAO / IGNORADA"),
    vender: Optional[str] = typer.Option(None, "--vender", help="Ticker vendido (para rotação/venda)"),
    comprar: Optional[str] = typer.Option(None, "--comprar", help="Ticker comprado (para rotação/compra)"),
    qtd: Optional[int] = typer.Option(None, "--qtd", help="Quantidade de cotas"),
    preco: Optional[float] = typer.Option(None, "--preco", help="Preço executado (fechamento por padrão)"),
    opportunity_id: Optional[int] = typer.Option(None, "--opportunity-id", help="ID da oportunidade em snapshot_opportunities"),
    racional: Optional[str] = typer.Option(None, "--racional", help="Racional da operação"),
):
    """Registra uma operação ou decisão no log de decisões."""
    from rich.console import Console
    from datetime import date
    from src.fii_analysis.data.database import get_session_ctx, SnapshotOpportunities
    from src.fii_analysis.decision.decision_journal import registrar_decisao, get_fechamento_on_or_before

    console = Console()
    tipo = tipo.upper()
    if tipo not in ["COMPRA", "VENDA", "ROTACAO", "IGNORADA"]:
        console.print(f"[red]Erro: Tipo '{tipo}' inválido. Escolha entre COMPRA, VENDA, ROTACAO, IGNORADA.[/red]")
        raise typer.Exit(1)

    with get_session_ctx() as session:
        ref_date = date.today()
        if opportunity_id:
            opp = session.get(SnapshotOpportunities, opportunity_id)
            if opp:
                if not vender:
                    vender = opp.vender
                if not comprar:
                    comprar = opp.comprar
                ref_date = opp.data_referencia
            else:
                console.print(f"[yellow]Oportunidade {opportunity_id} não encontrada no banco. Usando hoje como data.[/yellow]")

        if preco is None:
            ticker_para_preco = comprar or vender
            if ticker_para_preco:
                preco = get_fechamento_on_or_before(session, ticker_para_preco, ref_date)

        registrar_decisao(
            session=session,
            tipo=tipo,
            ticker_vendido=vender.upper() if vender else None,
            ticker_comprado=comprar.upper() if comprar else None,
            quantidade=qtd,
            preco=preco,
            opportunity_id=opportunity_id,
            racional_usuario=racional,
            data=ref_date,
        )
        console.print("[green]Decisão registrada com sucesso![/green]")


@app.command("review")
def review(
    periodo: int = typer.Option(90, "--periodo", help="Período de avaliação em dias (ex: 30, 60, 90)"),
):
    """Exibe relatório ex-post de assertividade das rotações recomendadas vs XFIX11."""
    from rich.console import Console
    from rich.table import Table
    from rich import box
    from src.fii_analysis.data.database import get_session_ctx
    from src.fii_analysis.decision.decision_journal import calcular_retornos_ex_post

    console = Console(width=120)
    with get_session_ctx() as session:
        resultados = calcular_retornos_ex_post(session, dias_horizonte=periodo)

    if not resultados:
        console.print(f"[yellow]Nenhuma recomendação avaliável encontrada com horizonte mínimo de {periodo} dias.[/yellow]\n")
        return

    n_total = len(resultados)
    n_acted = sum(1 for r in resultados if r["realizada"])
    n_ignored = n_total - n_acted
    
    ret_medio_par = sum(r["retorno_par"] for r in resultados) / n_total
    ret_medio_bench = sum(r["retorno_xfix11"] for r in resultados) / n_total
    hit_rate = sum(1 for r in resultados if r["bateu_xfix11"]) / n_total

    ignored_returns = [r["retorno_par"] for r in resultados if not r["realizada"]]
    custo_oportunidade = sum(ignored_returns) / len(ignored_returns) if ignored_returns else 0.0

    console.print(f"\n[bold green]=== Relatório de Performance Ex-Post (Horizonte: {periodo} dias) ===[/bold green]\n")
    console.print(f"Total de Rotações Avaliadas: [bold]{n_total}[/bold]")
    console.print(f"  Realizadas: [bold cyan]{n_acted}[/bold cyan] | Ignoradas: [bold]{n_ignored}[/bold]")
    console.print(f"Hit-Rate vs XFIX11: [bold]{hit_rate * 100:.1f}%[/bold] (pares que renderam mais que o índice)")
    console.print(f"Retorno Médio do Par: [bold]{ret_medio_par * 100:+.2f}%[/bold]")
    console.print(f"Retorno Médio do XFIX11: [bold]{ret_medio_bench * 100:+.2f}%[/bold]")
    console.print(f"Custo de Oportunidade (Média dos Ignorados): [bold]{custo_oportunidade * 100:+.2f}%[/bold]")
    console.print()

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    table.add_column("Data Rec.", min_width=10, no_wrap=True)
    table.add_column("Vender", style="red", min_width=7, no_wrap=True)
    table.add_column("Comprar", style="green", min_width=7, no_wrap=True)
    table.add_column("Ret Vender", min_width=10, no_wrap=True)
    table.add_column("Ret Comprar", min_width=11, no_wrap=True)
    table.add_column("Ret Par", style="bold", min_width=9, no_wrap=True)
    table.add_column("Ret XFIX11", min_width=10, no_wrap=True)
    table.add_column("Bateu?", min_width=7, no_wrap=True)
    table.add_column("Realizada?", min_width=10, no_wrap=True)

    for r in resultados:
        bateu_str = "[green]SIM[/green]" if r["bateu_xfix11"] else "[red]NÃO[/red]"
        realizada_str = "[cyan]SIM[/cyan]" if r["realizada"] else "NÃO"
        
        table.add_row(
            r["data_recomendacao"].strftime("%d/%m/%Y"),
            r["vender"],
            r["comprar"],
            f"{r['retorno_vender'] * 100:+.1f}%",
            f"{r['retorno_comprar'] * 100:+.1f}%",
            f"{r['retorno_par'] * 100:+.1f}%",
            f"{r['retorno_xfix11'] * 100:+.1f}%",
            bateu_str,
            realizada_str,
        )

    console.print(table)
    console.print()


if __name__ == "__main__":
    app()

