"""Carga inicial do universo IFIX (F1 do PLANO_V4).

Fluxo:
  1. Composição IFIX (B3 com fallback CSV) → tabela universo
  2. Reingestão CVM dos ZIPs locais (complemento + ativo_passivo) para o universo
  3. Carga inicial yfinance (preços + dividendos) dos tickers sem histórico

Idempotente: tickers já carregados são atualizados incrementalmente.
Uso: C:/ProgramData/anaconda3/python.exe scripts/load_ifix_universe.py
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from sqlalchemy import select

from src.fii_analysis.data.database import PrecoDiario, get_session_ctx
from src.fii_analysis.data.ifix import get_ifix_composition
from src.fii_analysis.data.ingestion import (
    load_ativo_passivo_to_db,
    load_cvm_to_db,
    load_dividends_yfinance,
    load_prices_yfinance,
)

CVM_RAW = PROJECT_ROOT / "dados" / "cvm" / "raw"


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    t0 = time.time()

    with get_session_ctx() as session:
        # 1. Composição IFIX → universo
        logger.info("=== 1/3 Composição IFIX ===")
        composicao = get_ifix_composition(session)
        logger.info("Universo IFIX: {} tickers com CNPJ resolvido", len(composicao))
        if not composicao:
            logger.error("Sem composição IFIX (B3 e CSV falharam). Abortando.")
            sys.exit(1)

        # 2. CVM: reingestão dos ZIPs locais para CNPJs do universo
        logger.info("=== 2/3 Ingestão CVM (ZIPs locais) ===")
        zips = sorted(CVM_RAW.glob("inf_mensal_fii_*.zip"))
        for zip_path in zips:
            year = int(zip_path.stem.rsplit("_", 1)[-1])
            logger.info("CVM {}: complemento...", year)
            try:
                load_cvm_to_db(zip_path, year, session)
            except Exception as e:
                logger.error("CVM {} complemento: {}", year, e)
            logger.info("CVM {}: ativo_passivo...", year)
            try:
                load_ativo_passivo_to_db(zip_path, year, session)
            except Exception as e:
                logger.error("CVM {} ativo_passivo: {}", year, e)
        session.commit()

        # 3. Preços + dividendos yfinance para tickers do universo
        logger.info("=== 3/3 Preços e dividendos (yfinance) ===")
        ja_tem_preco = set(
            session.execute(select(PrecoDiario.ticker).distinct()).scalars().all()
        )
        tickers = sorted({c["ticker"] for c in composicao})
        novos = [t for t in tickers if t not in ja_tem_preco]
        logger.info("{} tickers no universo | {} sem histórico de preço", len(tickers), len(novos))

        falhas = []
        for i, t in enumerate(tickers, 1):
            try:
                load_prices_yfinance(t, session)
                load_dividends_yfinance(t, session)
                if i % 10 == 0:
                    session.commit()
                    logger.info("Progresso: {}/{}", i, len(tickers))
            except Exception as e:
                falhas.append(t)
                logger.error("{}: {}", t, e)
        session.commit()

        if falhas:
            logger.warning("Tickers com falha ({}): {}", len(falhas), ", ".join(falhas))

    logger.info("=== Concluído em {:.1f} min ===", (time.time() - t0) / 60)


if __name__ == "__main__":
    main()
