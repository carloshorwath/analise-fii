import pytest
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

import src.fii_analysis.data.database as db
from src.fii_analysis.data.database import Base, Ticker, PrecoDiario, Dividendo, RelatorioMensal, CdiDiario, BenchmarkDiario, Carteira

# Use an in-memory database with StaticPool to share connection across sessions
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

# Overwrite database engine globally for tests
db._engine = test_engine
db.get_engine = lambda db_path=None: test_engine

# Function-scoped fixture ensures complete test isolation
@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(test_engine)
    
    # Populate initial synthetic data
    session = Session(test_engine)
    try:
        # 1. Tickers
        t1 = Ticker(
            cnpj="11.111.111/0001-11",
            ticker="MOCK11",
            nome="Mock Fund 11",
            segmento="Tijolo",
            mandato="Renda",
            tipo_gestao="Ativa",
            codigo_isin="BRMOCK11",
            data_inicio=date(2023, 1, 1),
            inativo_em=None
        )
        t2 = Ticker(
            cnpj="22.222.222/0001-22",
            ticker="MOCK12",
            nome="Mock Fund 12",
            segmento="Papel",
            mandato="Recebiveis",
            tipo_gestao="Ativa",
            codigo_isin="BRMOCK12",
            data_inicio=date(2023, 1, 1),
            inativo_em=None
        )
        session.add_all([t1, t2])
        session.commit()

        # 2. Generate 600 trading days starting from 2024-01-01
        start_date = date(2024, 1, 1)
        curr = start_date
        trading_days = []
        while len(trading_days) < 600:
            if curr.weekday() < 5:  # Monday to Friday
                trading_days.append(curr)
            curr += timedelta(days=1)

        # 3. Populate prices, CDI and benchmark
        precos = []
        cdis = []
        benchmarks = []
        for i, d in enumerate(trading_days):
            p1 = PrecoDiario(
                ticker="MOCK11",
                data=d,
                abertura=100.0,
                maxima=101.0,
                minima=99.0,
                fechamento=100.0,
                fechamento_aj=100.0,
                volume=1000000,
                fonte="yfinance",
                coletado_em=datetime.now(timezone.utc)
            )
            p2 = PrecoDiario(
                ticker="MOCK12",
                data=d,
                abertura=90.0,
                maxima=91.0,
                minima=89.0,
                fechamento=90.0,
                fechamento_aj=90.0,
                volume=800000,
                fonte="yfinance",
                coletado_em=datetime.now(timezone.utc)
            )
            precos.extend([p1, p2])

            cdi = CdiDiario(
                data=d,
                taxa_diaria_pct=0.04,  # Approx 10% p.a. (in percent)
                coletado_em=datetime.now(timezone.utc)
            )
            cdis.append(cdi)

            bench = BenchmarkDiario(
                ticker="XFIX11",
                data=d,
                fechamento=100.0 + (i * 0.01),  # Slightly increasing index
                coletado_em=datetime.now(timezone.utc)
            )
            benchmarks.append(bench)

        session.add_all(precos)
        session.add_all(cdis)
        session.add_all(benchmarks)
        session.commit()

        # 4. Generate 24 monthly reports and dividends
        months = []
        last_ref = None
        for d in trading_days:
            ref_month = date(d.year, d.month, 1)
            if ref_month != last_ref:
                if last_ref is not None:
                    months.append(last_day)
                last_ref = ref_month
            last_day = d
        months.append(last_day)
        months = sorted(list(set(months)))[:24]

        relatorios = []
        dividendos = []
        for d in months:
            delivery_date = d + timedelta(days=10)
            
            r1 = RelatorioMensal(
                cnpj="11.111.111/0001-11",
                data_referencia=d,
                data_entrega=delivery_date,
                vp_por_cota=100.0,
                patrimonio_liq=100_000_000.0,
                cotas_emitidas=1_000_000,
                dy_mes_pct=1.0,
                rentab_efetiva=0.8,
                rentab_patrim=0.9
            )
            r2 = RelatorioMensal(
                cnpj="22.222.222/0001-22",
                data_referencia=d,
                data_entrega=delivery_date,
                vp_por_cota=90.0,
                patrimonio_liq=90_000_000.0,
                cotas_emitidas=1_000_000,
                dy_mes_pct=1.0,
                rentab_efetiva=0.7,
                rentab_patrim=0.8
            )
            relatorios.extend([r1, r2])

            div1 = Dividendo(
                ticker="MOCK11",
                data_com=d,
                valor_cota=1.0,
                fonte="yfinance"
            )
            div2 = Dividendo(
                ticker="MOCK12",
                data_com=d,
                valor_cota=0.9,
                fonte="yfinance"
            )
            dividendos.extend([div1, div2])

        session.add_all(relatorios)
        session.add_all(dividendos)
        session.commit()

    finally:
        session.close()

    yield

    Base.metadata.drop_all(test_engine)

@pytest.fixture
def db_session():
    """Provides a transactional session for a test and rolls back changes at the end."""
    session = Session(test_engine)
    try:
        yield session
    finally:
        session.close()
