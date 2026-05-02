"""
Configuração centralizada do projeto.

Tickers, períodos, custos e parâmetros de otimização ficam aqui.
Nenhum script deve hardcodar esses valores.
"""
from datetime import date

# FIIs monitorados — ordem alfabética
TICKERS = [
    "CPTS11",
    "CPSH11",
    "GARE11",
    "HSRE11",
    "KNIP11",
    "SNEL11",
    "SNFF11",
]


def tickers_ativos(session=None) -> list[str]:
    """Retorna tickers com inativo_em IS NULL. Fecha session se criada internamente."""
    from sqlalchemy import select
    close = session is None
    if session is None:
        from src.fii_analysis.data.database import get_session_ctx, Ticker
        ctx = get_session_ctx()
        session = ctx.__enter__()
    else:
        from src.fii_analysis.data.database import Ticker
        ctx = None
    rows = session.execute(
        select(Ticker.ticker).where(Ticker.inativo_em.is_(None))
    ).scalars().all()
    if close:
        session.close()
        if ctx is not None:
            ctx.__exit__(None, None, None)
    return list(rows)

# Períodos de treino e teste
TRAIN_START = date(2023, 1, 1)
TRAIN_END = date(2025, 3, 31)
TEST_START = date(2025, 4, 1)
TEST_END = date.today()

# Espaço de busca para otimização
DIAS_ANTES_RANGE = range(1, 11)
DIAS_DEPOIS_RANGE = range(1, 11)

# Custos de transação (ida + volta)
# Apenas emolumentos B3: liquidação (0.025%) + emolumentos (0.005%) = 0.03%
# Corretagem zero (maioria das corretoras)
CUSTO_POR_TRADE = 0.0003  # 0.03% round-trip

# IR sobre ganho de capital em FIIs: 20%
# Nota: prejuízo compensa lucro. IR calculado sobre saldo líquido da série,
# não por trade individual.
IR_GANHO_CAPITAL = 0.20
