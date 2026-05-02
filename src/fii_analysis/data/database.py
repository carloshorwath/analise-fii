from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, Numeric, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "dados" / "fii_data.db"

_engine = None


class Base(DeclarativeBase):
    pass


class Ticker(Base):
    __tablename__ = "tickers"

    cnpj: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    nome: Mapped[str | None] = mapped_column(String)
    segmento: Mapped[str | None] = mapped_column(String)
    mandato: Mapped[str | None] = mapped_column(String)
    tipo_gestao: Mapped[str | None] = mapped_column(String)
    codigo_isin: Mapped[str | None] = mapped_column(String)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    inativo_em: Mapped[date | None] = mapped_column(Date)


class EventoCorporativo(Base):
    __tablename__ = "eventos_corporativos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    cnpj: Mapped[str | None] = mapped_column(String)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    cnpj_antigo: Mapped[str | None] = mapped_column(String)
    cnpj_novo: Mapped[str | None] = mapped_column(String)
    observacao: Mapped[str | None] = mapped_column(Text)


class PrecoDiario(Base):
    __tablename__ = "precos_diarios"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    abertura: Mapped[float | None] = mapped_column(Numeric)
    maxima: Mapped[float | None] = mapped_column(Numeric)
    minima: Mapped[float | None] = mapped_column(Numeric)
    fechamento: Mapped[float | None] = mapped_column(Numeric)
    fechamento_aj: Mapped[float | None] = mapped_column(Numeric)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    fonte: Mapped[str | None] = mapped_column(String)
    coletado_em: Mapped[datetime | None] = mapped_column(DateTime)


class Dividendo(Base):
    __tablename__ = "dividendos"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    data_com: Mapped[date] = mapped_column(Date, primary_key=True)
    valor_cota: Mapped[float | None] = mapped_column(Numeric)
    fonte: Mapped[str | None] = mapped_column(String)


class RelatorioMensal(Base):
    __tablename__ = "relatorios_mensais"

    cnpj: Mapped[str] = mapped_column(String, primary_key=True)
    data_referencia: Mapped[date] = mapped_column(Date, primary_key=True)
    data_entrega: Mapped[date | None] = mapped_column(Date)
    vp_por_cota: Mapped[float | None] = mapped_column(Numeric)
    patrimonio_liq: Mapped[float | None] = mapped_column(Numeric)
    cotas_emitidas: Mapped[int | None] = mapped_column(BigInteger)
    dy_mes_pct: Mapped[float | None] = mapped_column(Numeric)
    rentab_efetiva: Mapped[float | None] = mapped_column(Numeric)
    rentab_patrim: Mapped[float | None] = mapped_column(Numeric)


class AtivoPassivo(Base):
    __tablename__ = "ativo_passivo"

    cnpj: Mapped[str] = mapped_column(String, primary_key=True)
    data_referencia: Mapped[date] = mapped_column(Date, primary_key=True)
    data_entrega: Mapped[date | None] = mapped_column(Date)
    direitos_bens_imoveis: Mapped[float | None] = mapped_column(Numeric)
    cri: Mapped[float | None] = mapped_column(Numeric)
    cri_cra: Mapped[float | None] = mapped_column(Numeric)
    lci: Mapped[float | None] = mapped_column(Numeric)
    lci_lca: Mapped[float | None] = mapped_column(Numeric)
    disponibilidades: Mapped[float | None] = mapped_column(Numeric)
    ativo_total: Mapped[float | None] = mapped_column(Numeric)


class CdiDiario(Base):
    """CDI diário obtido do BCB SGS série 12. taxa_diaria_pct em % ao dia (ex: 0.050788)."""

    __tablename__ = "cdi_diario"

    data: Mapped[date] = mapped_column(Date, primary_key=True)
    taxa_diaria_pct: Mapped[float] = mapped_column(Numeric, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BenchmarkDiario(Base):
    """Fechamento diário de benchmarks (ex: IFIX.SA) para comparação de retorno."""

    __tablename__ = "benchmark_diario"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    fechamento: Mapped[float | None] = mapped_column(Numeric)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Carteira(Base):
    __tablename__ = "carteira"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_medio: Mapped[float] = mapped_column(Numeric, nullable=False)
    data_compra: Mapped[date] = mapped_column(Date, nullable=False)


class SnapshotRun(Base):
    """Envelope de metadados de um snapshot diário. Imutável após status=ready."""

    __tablename__ = "snapshot_runs"
    __table_args__ = (
        Index("ix_snapshot_runs_date_status", "data_referencia", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # running | ready | failed
    engine_version_global: Mapped[str | None] = mapped_column(String)
    universe_scope: Mapped[str | None] = mapped_column(String)  # curado | carteira | db_ativos
    universe_hash: Mapped[str | None] = mapped_column(String)
    carteira_hash: Mapped[str | None] = mapped_column(String)
    base_preco_ate: Mapped[date | None] = mapped_column(Date)
    base_dividendo_ate: Mapped[date | None] = mapped_column(Date)
    base_cdi_ate: Mapped[date | None] = mapped_column(Date)
    mensagem_erro: Mapped[str | None] = mapped_column(Text)
    tickers_falhos: Mapped[str | None] = mapped_column(Text)  # JSON list de tickers que falharam
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime)

    # Focus BCB (contexto macro — preenchido uma vez por run)
    focus_data_referencia: Mapped[date | None] = mapped_column(Date)
    focus_coletado_em: Mapped[datetime | None] = mapped_column(DateTime)
    focus_selic_3m: Mapped[float | None] = mapped_column(Numeric)
    focus_selic_6m: Mapped[float | None] = mapped_column(Numeric)
    focus_selic_12m: Mapped[float | None] = mapped_column(Numeric)
    focus_status: Mapped[str | None] = mapped_column(String)


class SnapshotTickerMetrics(Base):
    """Métricas pré-calculadas por ticker em um snapshot_run."""

    __tablename__ = "snapshot_ticker_metrics"
    __table_args__ = (
        Index("ix_snapshot_ticker_metrics_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    preco: Mapped[float | None] = mapped_column(Numeric)
    vp: Mapped[float | None] = mapped_column(Numeric)
    pvp: Mapped[float | None] = mapped_column(Numeric)
    pvp_percentil: Mapped[float | None] = mapped_column(Numeric)
    dy_12m: Mapped[float | None] = mapped_column(Numeric)
    dy_24m: Mapped[float | None] = mapped_column(Numeric)
    rent_12m: Mapped[float | None] = mapped_column(Numeric)
    rent_24m: Mapped[float | None] = mapped_column(Numeric)
    dy_gap: Mapped[float | None] = mapped_column(Numeric)
    dy_gap_percentil: Mapped[float | None] = mapped_column(Numeric)
    volume_21d: Mapped[float | None] = mapped_column(Numeric)
    cvm_defasada: Mapped[bool | None] = mapped_column(Boolean)
    segmento: Mapped[str | None] = mapped_column(String)

    # Fase 1.5 — risk metrics
    volatilidade_anual: Mapped[float | None] = mapped_column(Numeric)
    beta_ifix: Mapped[float | None] = mapped_column(Numeric)
    max_drawdown: Mapped[float | None] = mapped_column(Numeric)
    liquidez_21d_brl: Mapped[float | None] = mapped_column(Numeric)
    retorno_total_12m: Mapped[float | None] = mapped_column(Numeric)
    dy_3m_anualizado: Mapped[float | None] = mapped_column(Numeric)


class SnapshotRadar(Base):
    """Flags booleanas do radar por ticker em um snapshot_run."""

    __tablename__ = "snapshot_radar"
    __table_args__ = (
        Index("ix_snapshot_radar_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    pvp_baixo: Mapped[bool | None] = mapped_column(Boolean)
    dy_gap_alto: Mapped[bool | None] = mapped_column(Boolean)
    saude_ok: Mapped[bool | None] = mapped_column(Boolean)
    liquidez_ok: Mapped[bool | None] = mapped_column(Boolean)
    vistos: Mapped[int | None] = mapped_column(Integer)  # contagem de filtros que passam (0-4)
    saude_motivo: Mapped[str | None] = mapped_column(Text)


class SnapshotDecisions(Base):
    """Decisões consolidadas por ticker (Fase 3). Versionamento por motor por linha."""

    __tablename__ = "snapshot_decisions"
    __table_args__ = (
        Index("ix_snapshot_decisions_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    data_referencia: Mapped[date | None] = mapped_column(Date)

    # Sinais brutos dos 3 motores
    sinal_otimizador: Mapped[str | None] = mapped_column(String)
    sinal_episodio: Mapped[str | None] = mapped_column(String)
    sinal_walkforward: Mapped[str | None] = mapped_column(String)

    # Ação derivada
    acao: Mapped[str | None] = mapped_column(String)
    nivel_concordancia: Mapped[str | None] = mapped_column(String)
    n_concordam_buy: Mapped[int | None] = mapped_column(Integer)
    n_concordam_sell: Mapped[int | None] = mapped_column(Integer)

    # Flags de risco (colunas consultáveis — não usar rationale_json para filtrar)
    flag_destruicao_capital: Mapped[bool | None] = mapped_column(Boolean)
    motivo_destruicao: Mapped[str | None] = mapped_column(Text)
    flag_emissao_recente: Mapped[bool | None] = mapped_column(Boolean)
    flag_pvp_caro: Mapped[bool | None] = mapped_column(Boolean)
    flag_dy_gap_baixo: Mapped[bool | None] = mapped_column(Boolean)

    # Contexto de mercado no momento do snapshot
    preco_referencia: Mapped[float | None] = mapped_column(Numeric)
    pvp_atual: Mapped[float | None] = mapped_column(Numeric)
    pvp_percentil: Mapped[float | None] = mapped_column(Numeric)
    dy_gap_percentil: Mapped[float | None] = mapped_column(Numeric)

    # Janelas abertas
    episodio_eh_novo: Mapped[bool | None] = mapped_column(Boolean)
    pregoes_desde_ultimo_episodio: Mapped[int | None] = mapped_column(Integer)
    janela_captura_aberta: Mapped[bool | None] = mapped_column(Boolean)
    proxima_data_com_estimada: Mapped[date | None] = mapped_column(Date)
    dias_ate_proxima_data_com: Mapped[int | None] = mapped_column(Integer)

    # CDI Sensitivity (diagnostico V1 - NAO altera acao)
    cdi_status: Mapped[str | None] = mapped_column(String)
    cdi_beta: Mapped[float | None] = mapped_column(Numeric)
    cdi_r_squared: Mapped[float | None] = mapped_column(Numeric)
    cdi_p_value: Mapped[float | None] = mapped_column(Numeric)
    cdi_residuo_atual: Mapped[float | None] = mapped_column(Numeric)
    cdi_residuo_percentil: Mapped[float | None] = mapped_column(Numeric)

    # CDI + Focus (contexto macro — NÃO altera ação)
    cdi_delta_focus_12m: Mapped[float | None] = mapped_column(Numeric)
    cdi_repricing_12m: Mapped[float | None] = mapped_column(Numeric)

    # Auditoria humana — não usar como base de queries analíticas (dívida técnica v1)
    rationale_json: Mapped[str | None] = mapped_column(Text)

    # Versionamento por motor por linha (não só no snapshot_run)
    version_otimizador: Mapped[str | None] = mapped_column(String)
    version_episodios: Mapped[str | None] = mapped_column(String)
    version_walkforward: Mapped[str | None] = mapped_column(String)
    version_recommender: Mapped[str | None] = mapped_column(String)


class SnapshotPortfolioAdvices(Base):
    """Conselhos de carteira pré-calculados por run_id + carteira_hash."""

    __tablename__ = "snapshot_portfolio_advices"
    __table_args__ = (
        Index("ix_snapshot_portfolio_advices_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    carteira_hash: Mapped[str | None] = mapped_column(String)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    quantidade: Mapped[int | None] = mapped_column(Integer)
    preco_medio: Mapped[float | None] = mapped_column(Numeric)
    preco_atual: Mapped[float | None] = mapped_column(Numeric)
    valor_mercado: Mapped[float | None] = mapped_column(Numeric)
    peso_carteira: Mapped[float | None] = mapped_column(Numeric)
    badge: Mapped[str | None] = mapped_column(String)
    prioridade: Mapped[str | None] = mapped_column(String)
    acao_recomendada: Mapped[str | None] = mapped_column(String)
    nivel_concordancia: Mapped[str | None] = mapped_column(String)
    flags_resumo: Mapped[str | None] = mapped_column(String)
    racional: Mapped[str | None] = mapped_column(Text)
    valida_ate: Mapped[date | None] = mapped_column(Date)


class SnapshotStructuralAlerts(Base):
    """Alertas estruturais de concentração de carteira por run_id + carteira_hash."""

    __tablename__ = "snapshot_structural_alerts"
    __table_args__ = (
        Index("ix_snapshot_structural_alerts_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    carteira_hash: Mapped[str | None] = mapped_column(String)
    tipo: Mapped[str | None] = mapped_column(String)
    severidade: Mapped[str | None] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(Text)
    valor: Mapped[float | None] = mapped_column(Numeric)


def get_engine(db_path: Path = DEFAULT_DB_PATH):
    global _engine
    if _engine is not None and Path(_engine.url.database) == Path(db_path):
        return _engine
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    return _engine


@contextmanager
def get_session_ctx(db_path: Path = DEFAULT_DB_PATH) -> Generator[Session, None, None]:
    session = Session(get_engine(db_path))
    try:
        yield session
    finally:
        session.close()


def get_session(db_path: Path = DEFAULT_DB_PATH):
    return Session(get_engine(db_path))


def create_tables(db_path: Path = DEFAULT_DB_PATH):
    Base.metadata.create_all(get_engine(db_path))


def get_cnpj_by_ticker(ticker: str, session: Session) -> str | None:
    return session.execute(
        select(Ticker.cnpj).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()


def get_ultimo_preco_date(ticker: str, session: Session) -> date | None:
    return session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_ultima_coleta(db_path: Path = DEFAULT_DB_PATH) -> datetime | None:
    with get_session_ctx(db_path) as session:
        return session.execute(
            select(func.max(PrecoDiario.coletado_em))
        ).scalar()


def volume_medio_21d(ticker: str, t: date, session: Session) -> float | None:
    rows = session.execute(
        select(PrecoDiario.fechamento, PrecoDiario.volume)
        .where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data <= t,
        )
        .order_by(PrecoDiario.data.desc())
        .limit(21)
    ).all()
    if not rows:
        return None
    vals = [float(f) * float(v) for f, v in rows if f is not None and v is not None]
    return sum(vals) / len(vals) if vals else None


# =============================================================================
# Helpers de snapshot
# =============================================================================


def get_latest_ready_snapshot_run(
    session: Session,
    scope: str | None = None,
    carteira_hash: str | None = None,
) -> SnapshotRun | None:
    q = select(SnapshotRun).where(SnapshotRun.status == "ready")
    if scope is not None:
        q = q.where(SnapshotRun.universe_scope == scope)
    if carteira_hash is not None:
        q = q.where(SnapshotRun.carteira_hash == carteira_hash)
    q = q.order_by(SnapshotRun.data_referencia.desc(), SnapshotRun.criado_em.desc()).limit(1)
    return session.execute(q).scalar_one_or_none()


def get_snapshot_run_by_date(
    session: Session, data_ref: date, scope: str | None = None
) -> SnapshotRun | None:
    q = select(SnapshotRun).where(
        SnapshotRun.data_referencia == data_ref,
        SnapshotRun.status == "ready",
    )
    if scope is not None:
        q = q.where(SnapshotRun.universe_scope == scope)
    q = q.order_by(SnapshotRun.criado_em.desc()).limit(1)
    return session.execute(q).scalar_one_or_none()


def create_snapshot_run(
    session: Session,
    *,
    data_referencia: date,
    scope: str,
    universe_hash: str,
    carteira_hash: str | None = None,
    engine_version: str = "snapshot_v1",
    base_preco_ate: date | None = None,
    base_dividendo_ate: date | None = None,
    base_cdi_ate: date | None = None,
) -> int:
    run = SnapshotRun(
        data_referencia=data_referencia,
        criado_em=datetime.now(timezone.utc),
        status="running",
        engine_version_global=engine_version,
        universe_scope=scope,
        universe_hash=universe_hash,
        carteira_hash=carteira_hash,
        base_preco_ate=base_preco_ate,
        base_dividendo_ate=base_dividendo_ate,
        base_cdi_ate=base_cdi_ate,
    )
    session.add(run)
    session.flush()
    return run.id


def mark_snapshot_run_ready(
    session: Session, run_id: int, *, tickers_falhos: list[str] | None = None
) -> None:
    run = session.get(SnapshotRun, run_id)
    if run is None:
        return
    run.status = "ready"
    run.finalizado_em = datetime.now(timezone.utc)
    if tickers_falhos:
        run.tickers_falhos = json.dumps(tickers_falhos)
    session.flush()


def mark_snapshot_run_failed(session: Session, run_id: int, erro: str) -> None:
    run = session.get(SnapshotRun, run_id)
    if run is None:
        return
    run.status = "failed"
    run.mensagem_erro = erro[:500]
    run.finalizado_em = datetime.now(timezone.utc)
    session.flush()
