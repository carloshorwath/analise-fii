"""Migrações idempotentes para SQLite — sem Alembic.

Cada migração usa ALTER TABLE ADD COLUMN com verificação prévia.
Se a tabela não existir ou a coluna já existir, não faz nada.

Uso:
    from src.fii_analysis.data.migrations import run_migrations
    run_migrations(db_path)
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from sqlalchemy import text

from src.fii_analysis.data.database import DEFAULT_DB_PATH, get_engine


def _get_columns(conn, table: str) -> set[str]:
    """Retorna nomes das colunas existentes em uma tabela."""
    try:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {row[1] for row in rows}
    except Exception:
        return set()


def _table_exists(conn, table: str) -> bool:
    """Verifica se tabela existe."""
    rows = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchall()
    return len(rows) > 0


def _add_column(conn, table: str, column: str, col_type: str) -> None:
    """Adiciona coluna se não existir (idempotente)."""
    if not _table_exists(conn, table):
        logger.debug("Tabela {} nao existe, pulando coluna {}", table, column)
        return
    cols = _get_columns(conn, table)
    if column in cols:
        return
    logger.info("Migracao: ALTER TABLE {} ADD COLUMN {} {}", table, column, col_type)
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


def run_migrations(db_path: Path | None = None) -> None:
    """Executa todas as migrações pendentes (idempotente).

    Ordem: migrations mais antigas primeiro.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    engine = get_engine(db_path)
    with engine.connect() as conn:
        # Migração 001: CDI Sensitivity em snapshot_decisions (V1)
        _add_column(conn, "snapshot_decisions", "cdi_status", "TEXT")
        _add_column(conn, "snapshot_decisions", "cdi_beta", "REAL")
        _add_column(conn, "snapshot_decisions", "cdi_r_squared", "REAL")
        _add_column(conn, "snapshot_decisions", "cdi_p_value", "REAL")
        _add_column(conn, "snapshot_decisions", "cdi_residuo_atual", "REAL")
        _add_column(conn, "snapshot_decisions", "cdi_residuo_percentil", "REAL")
        conn.commit()

        # Migração 002: Focus BCB em snapshot_runs + CDI/Focus em snapshot_decisions
        _add_column(conn, "snapshot_runs", "focus_data_referencia", "DATE")
        _add_column(conn, "snapshot_runs", "focus_coletado_em", "DATETIME")
        _add_column(conn, "snapshot_runs", "focus_selic_3m", "REAL")
        _add_column(conn, "snapshot_runs", "focus_selic_6m", "REAL")
        _add_column(conn, "snapshot_runs", "focus_selic_12m", "REAL")
        _add_column(conn, "snapshot_runs", "focus_status", "TEXT")
        _add_column(conn, "snapshot_decisions", "cdi_delta_focus_12m", "REAL")
        _add_column(conn, "snapshot_decisions", "cdi_repricing_12m", "REAL")
        conn.commit()

        # Migração 003: Risk metrics em snapshot_ticker_metrics (Fase 1.5)
        _add_column(conn, "snapshot_ticker_metrics", "volatilidade_anual", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "beta_ifix", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "max_drawdown", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "liquidez_21d_brl", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "retorno_total_12m", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "dy_3m_anualizado", "REAL")
        conn.commit()

    logger.info("Migracoes aplicadas em {}", db_path)
