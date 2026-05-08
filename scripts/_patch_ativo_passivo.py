"""Add new columns to ativo_passivo and re-ingest data from CVM zips.

Strategy: Delete all existing ativo_passivo rows and re-ingest from CVM zips
using the updated ingestion code that populates the new columns.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3
from loguru import logger

DB_PATH = Path(__file__).resolve().parents[1] / "dados" / "fii_data.db"
RAW_DIR = Path(__file__).resolve().parents[1] / "dados" / "cvm" / "raw"


def migrate_schema():
    """Add new columns to ativo_passivo table."""
    logger.info("DB path: {}", DB_PATH)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("PRAGMA table_info(ativo_passivo)")
    existing = {r[1] for r in c.fetchall()}

    new_cols = {
        "total_investido": "NUMERIC",
        "total_necessidades_liquidez": "NUMERIC",
        "valores_receber": "NUMERIC",
        "contas_receber_aluguel": "NUMERIC",
        "outros_valores_mobliarios": "NUMERIC",
    }

    for col, col_type in new_cols.items():
        if col not in existing:
            c.execute(f"ALTER TABLE ativo_passivo ADD COLUMN {col} {col_type}")
            conn.commit()
            logger.info("Added column: {}", col)
        else:
            logger.info("Column already exists: {}", col)

    conn.close()
    logger.info("Schema migration complete.")


def backfill_data():
    """Delete existing ativo_passivo rows and re-ingest from CVM zips."""
    from src.fii_analysis.data.database import get_session
    from src.fii_analysis.data.ingestion import load_ativo_passivo_to_db

    session = get_session()

    # Count existing rows
    from sqlalchemy import text
    count = session.execute(text("SELECT COUNT(*) FROM ativo_passivo")).scalar()
    logger.info("Existing ativo_passivo rows: {}", count)

    # Delete all rows for re-ingestion
    session.execute(text("DELETE FROM ativo_passivo"))
    session.commit()
    logger.info("Deleted all ativo_passivo rows.")

    # Find CVM zips
    if not RAW_DIR.exists():
        logger.error("CVM raw dir not found: {}", RAW_DIR)
        session.close()
        return

    zips = sorted(RAW_DIR.glob("inf_mensal_fii_*.zip"))
    logger.info("Found {} CVM zips: {}", len(zips), [z.name for z in zips])

    for zip_path in zips:
        # Extract year from filename: inf_mensal_fii_2024.zip -> 2024
        year = int(zip_path.stem.split("_")[-1])
        logger.info("Processing {} (year {})...", zip_path.name, year)
        try:
            load_ativo_passivo_to_db(zip_path, year, session)
        except Exception as e:
            logger.error("Error processing {}: {}", zip_path.name, e)

    # Verify
    new_count = session.execute(text("SELECT COUNT(*) FROM ativo_passivo")).scalar()
    logger.info("New ativo_passivo rows: {}", new_count)
    session.close()
    logger.info("Backfill complete.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr)
    migrate_schema()
    backfill_data()
