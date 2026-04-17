from datetime import date, datetime
from pathlib import Path

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

# Raiz do projeto — funciona independente de onde o script é executado
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "dados" / "fii_data.db"


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
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


def get_session(db_path: Path = DEFAULT_DB_PATH):
    return Session(get_engine(db_path))


def create_tables(db_path: Path = DEFAULT_DB_PATH):
    Base.metadata.create_all(get_engine(db_path))
