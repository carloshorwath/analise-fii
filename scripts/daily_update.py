"""
daily_update.py — Fast daily update script (no CVM download).

Updates prices, CDI, IFIX benchmark, optimizer cache, and daily snapshot.
Incremental by default: only loads new data since last run.

Usage:
    C:/ProgramData/anaconda3/python.exe scripts/daily_update.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date
from loguru import logger

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import get_session_ctx
from src.fii_analysis.data.ingestion import (
    load_prices_yfinance,
    load_dividends_yfinance,
    load_cdi_to_db,
    load_benchmark_yfinance,
    load_benchmark_brapi,
)
from src.fii_analysis.models.threshold_optimizer_v2 import (
    ThresholdOptimizerV2,
    load_optimizer_cache,
    save_optimizer_cache,
)
from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot


def _update_prices(session):
    """Update prices for all active tickers (incremental)."""
    logger.info("--- Updating prices (yfinance) ---")
    tickers = tickers_ativos(session)
    for ticker in tickers:
        try:
            load_prices_yfinance(ticker, session)
        except Exception as e:
            logger.error("Error updating prices for {}: {}", ticker, e)


def _update_dividends(session):
    """Update dividends for all active tickers."""
    logger.info("--- Updating dividends (yfinance) ---")
    tickers = tickers_ativos(session)
    for ticker in tickers:
        try:
            load_dividends_yfinance(ticker, session)
        except Exception as e:
            logger.error("Error updating dividends for {}: {}", ticker, e)


def _update_cdi(session):
    """Update CDI from BCB SGS (incremental)."""
    logger.info("--- Updating CDI (BCB SGS) ---")
    try:
        load_cdi_to_db(session)
    except Exception as e:
        logger.error("Error updating CDI: {}", e)


def _update_ifix(session):
    """Update IFIX benchmark via yfinance and brapi."""
    logger.info("--- Updating IFIX benchmark ---")
    try:
        load_benchmark_yfinance("IFIX.SA", session)
    except Exception as e:
        logger.error("Error updating IFIX via yfinance: {}", e)
    try:
        load_benchmark_brapi("IFIX.SA", session)
    except Exception as e:
        logger.error("Error updating IFIX via brapi: {}", e)


def _refresh_optimizer_cache_if_needed(session):
    """Refresh optimizer cache for tickers with expired or missing cache.

    This runs the full grid search optimization and saves the best params
    to cache for tickers that need it (cache missing or older than 7 days).
    """
    logger.info("--- Refreshing optimizer cache (if needed) ---")
    tickers = tickers_ativos(session)
    optimizer = ThresholdOptimizerV2()

    for ticker in tickers:
        try:
            cached = load_optimizer_cache(ticker, max_age_days=7)
            if cached is not None:
                logger.info("{}: optimizer cache is fresh, skipping", ticker)
                continue

            logger.info("{}: optimizer cache missing or expired, optimizing...", ticker)
            result = optimizer.optimize(ticker, session)

            if result and result.get("best_params"):
                save_optimizer_cache(ticker, result["best_params"])
                logger.info("{}: optimizer cache saved", ticker)
            else:
                logger.warning("{}: optimization failed or no best_params", ticker)
        except Exception as e:
            logger.error("Error refreshing optimizer cache for {}: {}", ticker, e)


def _generate_snapshot(session):
    """Generate daily snapshot for curated universe."""
    logger.info("--- Generating daily snapshot ---")
    try:
        result = generate_daily_snapshot(session, scope="curado", force=False)
        status = result.get("status", "unknown")
        msg = result.get("mensagem", "no message")
        logger.info("Snapshot status: {} | {}", status, msg)
    except Exception as e:
        logger.error("Error generating snapshot: {}", e)


def main():
    logger.remove()
    logger.add(sys.stderr)

    logger.info("=== daily_update.py ===")
    logger.info("Date: {}", date.today())

    with get_session_ctx() as session:
        _update_prices(session)
        _update_dividends(session)
        _update_cdi(session)
        _update_ifix(session)
        _refresh_optimizer_cache_if_needed(session)
        _generate_snapshot(session)

    logger.info("=== Complete ===")


if __name__ == "__main__":
    main()
