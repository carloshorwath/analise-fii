from datetime import date

import pandas as pd
from sqlalchemy import func, select

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.config_yaml import get_piso_liquidez
from src.fii_analysis.data.database import Dividendo, PrecoDiario, Ticker, get_session
from src.fii_analysis.features.composicao import classificar_fii
from src.fii_analysis.features.indicators import get_pvp
from src.fii_analysis.features.saude import flag_destruicao_capital
from src.fii_analysis.features.valuation import get_dy_gap, get_dy_gap_percentil, get_pvp_percentil


def _volume_medio_21d(ticker: str, t: date, session) -> float | None:
    """Volume financeiro médio dos últimos 21 pregões até t (inclusive)."""
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


def radar_matriz(tickers: list[str] | None = None, session=None) -> pd.DataFrame:
    if tickers is None:
        tickers = tickers_ativos(session)
    if session is None:
        session = get_session()

    rows = []
    for ticker in tickers:
        ultimo = session.execute(
            select(PrecoDiario.data)
            .where(PrecoDiario.ticker == ticker)
            .order_by(PrecoDiario.data.desc())
            .limit(1)
        ).scalar_one_or_none()

        if ultimo is None:
            rows.append({
                "ticker": ticker, "pvp_baixo": False, "dy_gap_alto": False,
                "saude_ok": False, "liquidez_ok": False, "vistos": 0,
                "pvp_atual": None, "pvp_percentil": None,
                "dy_gap_valor": None, "dy_gap_percentil": None,
                "volume_21d": None, "saude_motivo": "sem dados de preco",
            })
            continue

        pvp_pct = get_pvp_percentil(ticker, ultimo, 504, session)
        pvp_baixo = pvp_pct is not None and pvp_pct < 30

        pvp_atual = get_pvp(ticker, ultimo, session)

        dy_gap_pct = get_dy_gap_percentil(ticker, ultimo, 504, session)
        dy_gap_alto = dy_gap_pct is not None and dy_gap_pct > 70

        dy_gap_valor = get_dy_gap(ticker, ultimo, session)

        destruicao = flag_destruicao_capital(ticker, session)
        saude_ok = not destruicao["destruicao"]
        saude_motivo = destruicao["motivo"]

        vol_medio = _volume_medio_21d(ticker, ultimo, session)
        piso = get_piso_liquidez()
        liquidez_ok = vol_medio is not None and vol_medio >= piso

        vistos = sum([pvp_baixo, dy_gap_alto, saude_ok, liquidez_ok])

        rows.append({
            "ticker": ticker, "pvp_baixo": pvp_baixo, "dy_gap_alto": dy_gap_alto,
            "saude_ok": saude_ok, "liquidez_ok": liquidez_ok, "vistos": vistos,
            "pvp_atual": pvp_atual, "pvp_percentil": pvp_pct,
            "dy_gap_valor": dy_gap_valor, "dy_gap_percentil": dy_gap_pct,
            "volume_21d": vol_medio, "saude_motivo": saude_motivo,
        })

    df = pd.DataFrame(rows)
    # Desempate secundário por ordem alfabética do ticker para resultado estável
    df = df.sort_values(["vistos", "ticker"], ascending=[False, True]).reset_index(drop=True)
    return df
