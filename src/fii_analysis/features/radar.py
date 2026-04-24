from datetime import date

import pandas as pd
from sqlalchemy import select

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.config_yaml import get_piso_liquidez, get_threshold
from src.fii_analysis.data.database import Dividendo, PrecoDiario, get_session, get_ultimo_preco_date, volume_medio_21d
from src.fii_analysis.features.indicators import get_pvp
from src.fii_analysis.features.saude import flag_destruicao_capital
from src.fii_analysis.features.valuation import get_dy_gap, get_dy_gap_percentil, get_pvp_percentil


def radar_matriz(tickers: list[str] | None = None, session=None) -> pd.DataFrame:
    if tickers is None:
        tickers = tickers_ativos(session)
    if session is None:
        session = get_session()

    rows = []
    for ticker in tickers:
        ultimo = get_ultimo_preco_date(ticker, session)

        if ultimo is None:
            rows.append({
                "ticker": ticker, "pvp_baixo": False, "dy_gap_alto": False,
                "saude_ok": False, "liquidez_ok": False, "vistos": 0,
                "pvp_atual": None, "pvp_percentil": None,
                "dy_gap_valor": None, "dy_gap_percentil": None,
                "volume_21d": None, "saude_motivo": "sem dados de preco",
            })
            continue

        pvp_janela = get_threshold("pvp_janela_pregoes", 504)
        pvp_pct_val, jan_usada = get_pvp_percentil(ticker, ultimo, pvp_janela, session)
        pvp_baixo = pvp_pct_val is not None and pvp_pct_val < get_threshold("pvp_percentil_barato", 30)

        pvp_atual = get_pvp(ticker, ultimo, session)

        dy_janela = get_threshold("dy_janela_pregoes", 252)
        dy_gap_pct = get_dy_gap_percentil(ticker, ultimo, dy_janela, session)
        dy_gap_alto = dy_gap_pct is not None and dy_gap_pct > get_threshold("dy_gap_percentil_caro", 70)

        dy_gap_valor = get_dy_gap(ticker, ultimo, session)

        destruicao = flag_destruicao_capital(ticker, session)
        saude_ok = not destruicao["destruicao"]
        saude_motivo = destruicao["motivo"]

        vol_medio = volume_medio_21d(ticker, ultimo, session)
        piso = get_piso_liquidez()
        liquidez_ok = vol_medio is not None and vol_medio >= piso

        vistos = sum([pvp_baixo, dy_gap_alto, saude_ok, liquidez_ok])

        rows.append({
            "ticker": ticker, "pvp_baixo": pvp_baixo, "dy_gap_alto": dy_gap_alto,
            "saude_ok": saude_ok, "liquidez_ok": liquidez_ok, "vistos": vistos,
            "pvp_atual": pvp_atual, "pvp_percentil": pvp_pct_val,
            "dy_gap_valor": dy_gap_valor, "dy_gap_percentil": dy_gap_pct,
            "volume_21d": vol_medio, "saude_motivo": saude_motivo,
        })

    df = pd.DataFrame(rows)
    # Desempate secundário por ordem alfabética do ticker para resultado estável
    df = df.sort_values(["vistos", "ticker"], ascending=[False, True]).reset_index(drop=True)
    return df
