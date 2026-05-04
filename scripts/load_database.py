import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from loguru import logger
from sqlalchemy import select

from src.fii_analysis.data.database import Carteira, Ticker, create_tables, get_session
from src.fii_analysis.data.focus_bcb import fetch_focus_selic
from src.fii_analysis.data.ingestion import (
    load_cdi_to_db,
    load_cvm_to_db,
    load_dividends_yfinance,
    load_ifix_to_db,
    load_prices_yfinance,
)
from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "dados" / "cvm" / "raw"

CVM_URLS = {
    2021: "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2021.zip",
    2022: "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2022.zip",
    2023: "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2023.zip",
    2024: "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2024.zip",
    2025: "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2025.zip",
    2026: "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip",
}


def download_cvm_zips():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    baixados = {}
    for year, url in CVM_URLS.items():
        dest = RAW_DIR / f"inf_mensal_fii_{year}.zip"
        if dest.exists() and year != 2026:
            logger.info("ZIP {} ja existe, pulando download", dest.name)
            baixados[year] = dest
            continue
        logger.info("Baixando {} ...", dest.name)
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            logger.info("ZIP {} baixado ({} KB)", dest.name, len(resp.content) // 1024)
            baixados[year] = dest
        except Exception as e:
            logger.error("Erro ao baixar {}: {}", url, e)
    return baixados


def main():
    logger.info("=== load_database.py ===")

    logger.info("Criando tabelas (se nao existem)...")
    create_tables()

    logger.info("--- Etapa 1: Download ZIPs CVM ---")
    zips = download_cvm_zips()

    session = get_session()

    logger.info("--- Etapa 2: Carga relatorios mensais CVM ---")
    for year in sorted(zips.keys()):
        zip_path = zips[year]
        if not zip_path.exists():
            logger.warning("ZIP {} nao encontrado, pulando", zip_path)
            continue
        logger.info("Processando CVM ano {} ...", year)
        try:
            load_cvm_to_db(zip_path, year, session)
        except Exception as e:
            logger.error("Erro ao processar CVM {}: {}", year, e)

    logger.info("--- Etapa 3: Carga CDI diario (BCB SGS serie 12) ---")
    try:
        load_cdi_to_db(session)
    except Exception as e:
        logger.error("Erro CDI: {}", e)

    logger.info("--- Etapa 4: Carga precos e dividendos (yfinance) ---")
    tickers = session.scalars(select(Ticker)).all()
    if not tickers:
        logger.warning("Nenhum ticker cadastrado. Cadastre FIIs na tabela tickers antes.")
    for t in tickers:
        logger.info("Processando ticker {} ...", t.ticker)
        try:
            load_prices_yfinance(t.ticker, session)
        except Exception as e:
            logger.error("Erro precos {}: {}", t.ticker, e)
        try:
            load_dividends_yfinance(t.ticker, session)
        except Exception as e:
            logger.error("Erro dividendos {}: {}", t.ticker, e)

    logger.info("--- Etapa 4.1: Carga IFIX (Benchmark) ---")
    try:
        load_ifix_to_db(session)
    except Exception as e:
        logger.error("Erro IFIX: {}", e)

    logger.info("--- Etapa 5: Focus Selic (BCB ExpectativasMercadoSelic) ---")
    try:
        focus = fetch_focus_selic(force=True)
        logger.info(
            "Focus: status={} | 3m={} | 6m={} | 12m={} | data={}",
            focus.focus_status,
            focus.focus_selic_3m,
            focus.focus_selic_6m,
            focus.focus_selic_12m,
            focus.focus_data_referencia,
        )
    except Exception as e:
        logger.error("Erro Focus Selic: {}", e)

    logger.info("--- Etapa 6: Snapshot diario (universo curado) ---")
    try:
        generate_daily_snapshot(session, force=True)
    except Exception as e:
        logger.error("Erro snapshot curado: {}", e)

    logger.info("--- Etapa 7: Snapshot diario (carteira do usuario) ---")
    try:
        carteira_rows = session.execute(select(Carteira)).scalars().all()
        if carteira_rows:
            holdings = [
                {"ticker": c.ticker, "quantidade": c.quantidade, "preco_medio": c.preco_medio}
                for c in carteira_rows
            ]
            generate_daily_snapshot(session, scope="carteira", holdings=holdings, force=True)
        else:
            logger.info("Nenhuma posicao na carteira — pulando snapshot carteira.")
    except Exception as e:
        logger.error("Erro snapshot carteira: {}", e)

    session.close()
    logger.info("=== Concluido ===")


if __name__ == "__main__":
    # Remove all loguru handlers then add exactly one to prevent duplicate output
    # if this module is somehow imported and main() called more than once.
    logger.remove()
    logger.add(sys.stderr)
    main()
