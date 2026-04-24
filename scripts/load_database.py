import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from loguru import logger
from sqlalchemy import select

from src.fii_analysis.data.database import Ticker, create_tables, get_session
from src.fii_analysis.data.ingestion import (
    load_cdi_to_db,
    load_cvm_to_db,
    load_dividends_yfinance,
    load_prices_yfinance,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "dados" / "cvm" / "raw"

CVM_URLS = {
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

    session.close()
    logger.info("=== Concluido ===")


if __name__ == "__main__":
    main()
