from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Generator

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String, Text, create_engine, func, select
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
