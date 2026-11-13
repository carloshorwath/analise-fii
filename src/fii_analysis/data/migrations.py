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


def corrigir_pregoes_blob(conn) -> int:
    """Migracao 010: snapshot_decisions.pregoes_desde_ultimo_episodio gravado como BLOB
    (numpy.int64 de 8 bytes little-endian) -> INTEGER. Idempotente; devolve n corrigidas."""
    if not _table_exists(conn, "snapshot_decisions"):
        return 0
    rows = conn.execute(text(
        "SELECT id, pregoes_desde_ultimo_episodio FROM snapshot_decisions "
        "WHERE typeof(pregoes_desde_ultimo_episodio) = 'blob'"
    )).all()
    for rid, blob in rows:
        conn.execute(
            text("UPDATE snapshot_decisions SET pregoes_desde_ultimo_episodio = :v WHERE id = :i"),
            {"v": int.from_bytes(bytes(blob), "little", signed=True), "i": rid},
        )
    if rows:
        logger.info("Migracao: {} pregoes_desde_ultimo_episodio BLOB -> INTEGER", len(rows))
    return len(rows)


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

        # Migração 003: risk_metrics em snapshot_ticker_metrics (Fase 1.5)
        _add_column(conn, "snapshot_ticker_metrics", "volatilidade_anual", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "beta_ifix", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "max_drawdown", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "liquidez_21d_brl", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "retorno_total_12m", "REAL")
        _add_column(conn, "snapshot_ticker_metrics", "dy_3m_anualizado", "REAL")
        conn.commit()

        # Migração 004: score 0-100 em snapshot_ticker_metrics + snapshot_decisions (Fase 2)
        _add_column(conn, "snapshot_ticker_metrics", "score_total", "INTEGER")
        _add_column(conn, "snapshot_ticker_metrics", "score_valuation", "INTEGER")
        _add_column(conn, "snapshot_ticker_metrics", "score_risco", "INTEGER")
        _add_column(conn, "snapshot_ticker_metrics", "score_liquidez", "INTEGER")
        _add_column(conn, "snapshot_ticker_metrics", "score_historico", "INTEGER")
        _add_column(conn, "snapshot_decisions", "score_total", "INTEGER")
        conn.commit()

        # Migração 005: Tabela universo para IFIX
        if not _table_exists(conn, "universo"):
            logger.info("Migracao: CREATE TABLE universo")
            conn.execute(text("""
                CREATE TABLE universo (
                    ticker TEXT NOT NULL,
                    cnpj TEXT NOT NULL,
                    em_ifix BOOLEAN NOT NULL CHECK (em_ifix IN (0, 1)),
                    peso_ifix REAL,
                    data_referencia DATE NOT NULL,
                    fonte TEXT NOT NULL,
                    atualizado_em DATETIME NOT NULL,
                    PRIMARY KEY (ticker, data_referencia)
                )
            """))
            conn.commit()

        # Migração 006: Tabela snapshot_opportunities
        if not _table_exists(conn, "snapshot_opportunities"):
            logger.info("Migracao: CREATE TABLE snapshot_opportunities")
            conn.execute(text("""
                CREATE TABLE snapshot_opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    data_referencia DATE NOT NULL,
                    vender TEXT NOT NULL,
                    comprar TEXT NOT NULL,
                    segmento TEXT NOT NULL,
                    spread_pvp_pct REAL NOT NULL,
                    spread_dy_gap REAL NOT NULL,
                    delta_score REAL NOT NULL,
                    custo_estimado_pct REAL NOT NULL,
                    spread_liquido_pct REAL NOT NULL,
                    dias_persistencia INTEGER NOT NULL,
                    racional_json TEXT NOT NULL,
                    vetos_json TEXT NOT NULL,
                    critic_veredicto TEXT NOT NULL
                )
            """))
            conn.execute(text("CREATE INDEX ix_snapshot_opportunities_run ON snapshot_opportunities (run_id)"))
            conn.commit()

        # Migração 007: Tabela llm_journal
        if not _table_exists(conn, "llm_journal"):
            logger.info("Migracao: CREATE TABLE llm_journal")
            conn.execute(text("""
                CREATE TABLE llm_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data DATE NOT NULL,
                    template TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    modelo TEXT,
                    ticker TEXT,
                    snapshot_run_id INTEGER,
                    resposta_md TEXT NOT NULL,
                    latencia_ms INTEGER
                )
            """))
            conn.execute(text("CREATE INDEX ix_llm_journal_run_ticker ON llm_journal (snapshot_run_id, ticker)"))
            conn.commit()

        # Migração 008: Tabela decisoes_log
        if not _table_exists(conn, "decisoes_log"):
            logger.info("Migracao: CREATE TABLE decisoes_log")
            conn.execute(text("""
                CREATE TABLE decisoes_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data DATE NOT NULL,
                    tipo TEXT NOT NULL,
                    ticker_vendido TEXT,
                    ticker_comprado TEXT,
                    quantidade INTEGER,
                    preco REAL,
                    opportunity_id INTEGER,
                    racional_usuario TEXT
                )
            """))
            conn.commit()

        # Migração 009: participacoes em sociedades de atividade FII (classificacao Tijolo)
        _add_column(conn, "ativo_passivo", "acoes_sociedades_fii", "NUMERIC")
        _add_column(conn, "ativo_passivo", "cotas_sociedades_fii", "NUMERIC")
        conn.commit()

        # Migração 010: BLOB numpy em pregoes_desde_ultimo_episodio -> INTEGER
        corrigir_pregoes_blob(conn)
        conn.commit()

    logger.info("Migracoes aplicadas em {}", db_path)

