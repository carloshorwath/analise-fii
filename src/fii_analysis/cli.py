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


if __name__ == "__main__":
    app()
