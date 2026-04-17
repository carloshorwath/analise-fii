import typer

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


if __name__ == "__main__":
    app()
