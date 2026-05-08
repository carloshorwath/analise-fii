import numpy as np
from sqlalchemy import select

from src.fii_analysis.data.database import PrecoDiario, BenchmarkDiario, Dividendo


def volatilidade_anualizada(ticker: str, janela: int = 252, session=None) -> float | None:
    """Calcula a volatilidade anualizada baseada no desvio padrão dos log-retornos diários."""
    rows = session.execute(
        select(PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento_aj.isnot(None))
        .order_by(PrecoDiario.data.desc())
        .limit(janela)
    ).all()

    if not rows or len(rows) < 63:
        return None

    prices = [float(r[0]) for r in rows][::-1]

    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] <= 0:
            continue
        returns.append(np.log(prices[i] / prices[i-1]))

    if not returns:
        return None

    return float(np.std(returns, ddof=1) * np.sqrt(252))


def beta_vs_ifix(ticker: str, janela: int = 252, session=None) -> float | None:
    """Calcula o beta do ticker em relação ao XFIX11 (Cov(R_FII, R_XFIX11) / Var(R_XFIX11))."""
    rows = session.execute(
        select(PrecoDiario.fechamento_aj, BenchmarkDiario.fechamento)
        .select_from(PrecoDiario)
        .join(
            BenchmarkDiario,
            (PrecoDiario.data == BenchmarkDiario.data) & (BenchmarkDiario.ticker == "XFIX11"),
        )
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento_aj.isnot(None), BenchmarkDiario.fechamento.isnot(None))
        .order_by(PrecoDiario.data.desc())
        .limit(janela)
    ).all()

    if not rows or len(rows) < 63:
        return None

    fii_prices = [float(r[0]) for r in rows][::-1]
    ifix_prices = [float(r[1]) for r in rows][::-1]

    fii_returns = []
    ifix_returns = []
    for i in range(1, len(fii_prices)):
        if fii_prices[i-1] <= 0 or ifix_prices[i-1] <= 0:
            continue
        fii_returns.append(np.log(fii_prices[i] / fii_prices[i-1]))
        ifix_returns.append(np.log(ifix_prices[i] / ifix_prices[i-1]))

    if not fii_returns or not ifix_returns:
        return None

    cov_matrix = np.cov(fii_returns, ifix_returns)
    if cov_matrix.shape != (2, 2) or cov_matrix[1, 1] == 0:
        return None

    beta = cov_matrix[0, 1] / cov_matrix[1, 1]
    return float(beta)


def max_drawdown(ticker: str, janela: int = 504, session=None) -> float | None:
    """Calcula o Maximum Drawdown real baseado no fechamento ajustado."""
    rows = session.execute(
        select(PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento_aj.isnot(None))
        .order_by(PrecoDiario.data.desc())
        .limit(janela)
    ).all()

    if not rows or len(rows) < 63:
        return None

    prices = [float(r[0]) for r in rows][::-1]

    max_price = prices[0]
    mdd = 0.0
    for price in prices:
        if price > max_price:
            max_price = price
        drawdown = (price - max_price) / max_price if max_price > 0 else 0
        if drawdown < mdd:
            mdd = drawdown

    return float(mdd)


def liquidez_media_21d(ticker: str, session=None) -> float | None:
    """Média de volume financeiro diário em R$ dos últimos 21 pregões."""
    rows = session.execute(
        select(PrecoDiario.fechamento, PrecoDiario.volume)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento.isnot(None), PrecoDiario.volume.isnot(None))
        .order_by(PrecoDiario.data.desc())
        .limit(21)
    ).all()

    if not rows:
        return None

    volumes = [float(r[0]) * float(r[1]) for r in rows]
    avg_vol = np.mean(volumes)
    return float(avg_vol) if avg_vol > 0 else None


def retorno_total_12m(ticker: str, session=None) -> float | None:
    """Calcula (P_t - P_{t-252} + soma_dividendos_12m) / P_{t-252}."""
    rows = session.execute(
        select(PrecoDiario.fechamento_aj, PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento_aj.isnot(None))
        .order_by(PrecoDiario.data.desc())
        .limit(253)
    ).all()

    if not rows or len(rows) < 252:
        return None

    hoje_row = rows[0]
    t252_row = rows[-1]

    p_t = float(hoje_row[0])
    p_t252 = float(t252_row[0])

    data_t = hoje_row[1]
    data_t252 = t252_row[1]

    divs = session.execute(
        select(Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker, Dividendo.data_com > data_t252, Dividendo.data_com <= data_t)
    ).all()

    soma_divs = sum(float(d[0]) for d in divs if d[0] is not None)

    if p_t252 <= 0:
        return None

    retorno = (p_t - p_t252 + soma_divs) / p_t252
    return float(retorno)


def dy_3m_anualizado(ticker: str, session=None) -> float | None:
    """Soma de dividendos dos últimos 63 pregões multiplicada por 4, dividida pelo preço hoje."""
    rows = session.execute(
        select(PrecoDiario.fechamento, PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.fechamento.isnot(None))
        .order_by(PrecoDiario.data.desc())
        .limit(64)
    ).all()

    if not rows or len(rows) < 63:
        return None

    hoje_row = rows[0]
    t63_row = rows[-1]

    preco_hoje = float(hoje_row[0])
    if preco_hoje <= 0:
        return None

    data_t = hoje_row[1]
    data_t63 = t63_row[1]

    divs = session.execute(
        select(Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker, Dividendo.data_com > data_t63, Dividendo.data_com <= data_t)
    ).all()

    soma_divs = sum(float(d[0]) for d in divs if d[0] is not None)

    dy_3m_anual = (soma_divs * 4) / preco_hoje
    return float(dy_3m_anual)


def yield_on_cost(ticker: str, preco_medio: float, session=None) -> float | None:
    """Soma de dividendos de 12m dividida pelo preço médio."""
    if preco_medio <= 0:
        return None

    rows = session.execute(
        select(PrecoDiario.data)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.desc())
        .limit(253)
    ).all()

    if not rows or len(rows) < 252:
        return None

    data_t = rows[0][0]
    data_t252 = rows[-1][0]

    divs = session.execute(
        select(Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker, Dividendo.data_com > data_t252, Dividendo.data_com <= data_t)
    ).all()

    soma_divs = sum(float(d[0]) for d in divs if d[0] is not None)

    return float(soma_divs / preco_medio)
