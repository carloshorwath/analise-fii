"""Detectores de oportunidades abertas hoje.

Produz pontos de trade adicionais ao relatorio sem extrapolar:

- detectar_episodio_aberto: estado atual + gap desde ultimo episodio do mesmo
  lado. Distingue NOVO evento (independente, gap >= forward_days) de
  CONTINUACAO (mesmo evento ainda dentro do horizonte de retorno forward).

- detectar_janela_captura: estima a proxima data-com a partir do espacamento
  mediano historico das datas-com e diz se hoje estamos na janela pre.
  Eh estimativa, nao previsao — a data-com real so eh confirmada quando o
  fundo divulga.

Nenhum detector usa modelo preditivo — sao funcoes deterministicas sobre
estado factual.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select

from src.fii_analysis.data.database import Dividendo


# =============================================================================
# Episodio aberto agora (gap-aware)
# =============================================================================


def detectar_episodio_aberto(
    df_pvp: pd.DataFrame,
    forward_days: int = 20,
    pvp_pct_low: float = 10.0,
    pvp_pct_high: float = 90.0,
) -> dict:
    """Avalia se o ticker esta em episodio aberto agora e se eh evento novo.

    Parameters
    ----------
    df_pvp : DataFrame retornado por get_pvp_series — colunas data, pvp, pvp_pct
    forward_days : pregoes que definem a janela de retorno forward (gap minimo
        entre eventos independentes)
    pvp_pct_low / high : percentis para BUY (low) e SELL (high)

    Returns
    -------
    dict com:
      - lado: "BUY" | "SELL" | None
      - aberto: bool
      - novo_evento: bool — True se o gap desde o ultimo evento do mesmo
        lado e >= forward_days (ou nao ha evento anterior)
      - pregoes_desde_ultimo: int | None
      - data_ultimo_episodio: date | None
    """
    base = {
        "lado": None,
        "aberto": False,
        "novo_evento": False,
        "pregoes_desde_ultimo": None,
        "data_ultimo_episodio": None,
    }

    if df_pvp.empty or "pvp_pct" not in df_pvp.columns:
        return base

    df = df_pvp.dropna(subset=["pvp_pct"]).sort_values("data").reset_index(drop=True)
    if df.empty:
        return base

    ult = df.iloc[-1]
    pvp_pct_atual = float(ult["pvp_pct"])

    if pvp_pct_atual <= pvp_pct_low:
        lado = "BUY"
        mask = df["pvp_pct"] <= pvp_pct_low
    elif pvp_pct_atual >= pvp_pct_high:
        lado = "SELL"
        mask = df["pvp_pct"] >= pvp_pct_high
    else:
        return base

    # Indices (em pregoes consecutivos do df) onde houve eventos do mesmo lado.
    # O ultimo eh o de hoje; queremos o anterior.
    idx_eventos = list(np.where(mask.values)[0])
    idx_hoje = len(df) - 1

    pregoes_desde = None
    data_ultimo = None
    if len(idx_eventos) >= 2:
        idx_anterior = idx_eventos[-2]  # o penultimo evento (antes do de hoje)
        pregoes_desde = idx_hoje - idx_anterior
        data_ultimo_raw = df.iloc[idx_anterior]["data"]
        data_ultimo = data_ultimo_raw.date() if hasattr(data_ultimo_raw, "date") else data_ultimo_raw

    novo_evento = pregoes_desde is None or pregoes_desde >= forward_days

    return {
        "lado": lado,
        "aberto": True,
        "novo_evento": novo_evento,
        "pregoes_desde_ultimo": pregoes_desde,
        "data_ultimo_episodio": data_ultimo,
    }


# =============================================================================
# Janela de captura de dividendo
# =============================================================================


def _estimar_intervalo_mediano(datas_com: list[date]) -> Optional[int]:
    """Mediana do espacamento entre datas-com consecutivas, em dias corridos.

    FIIs pagam mensalmente, entao tipicamente eh ~30 dias. Usamos as ultimas
    12 datas-com para amortecer outliers.
    """
    if len(datas_com) < 2:
        return None
    datas_ord = sorted(datas_com)[-12:]
    diffs = [(datas_ord[i + 1] - datas_ord[i]).days for i in range(len(datas_ord) - 1)]
    diffs = [d for d in diffs if d > 0]
    if not diffs:
        return None
    return int(np.median(diffs))


def detectar_janela_captura(
    ticker: str,
    session,
    janela_pre_pregoes: int = 10,
    hoje: Optional[date] = None,
) -> dict:
    """Estima a proxima data-com e diz se hoje esta na janela pre de captura.

    Heuristica simples: proxima data-com = ultima + intervalo_mediano historico.
    Eh ESTIMATIVA: a data real eh divulgada pelo fundo e pode variar +-2 dias.

    Returns
    -------
    dict com:
      - aberta: bool — True se a estimativa de proxima data-com cai em <= janela_pre dias corridos
      - proxima_data_com_estimada: date | None
      - dias_corridos_ate: int | None
      - intervalo_mediano_dias: int | None
      - ultima_data_com: date | None
      - n_datas_com_historico: int
    """
    hoje = hoje or date.today()

    rows = session.execute(
        select(Dividendo.data_com)
        .where(Dividendo.ticker == ticker)
        .order_by(Dividendo.data_com.asc())
    ).all()

    datas_com = [r[0] for r in rows if r[0] is not None]
    base = {
        "aberta": False,
        "proxima_data_com_estimada": None,
        "dias_corridos_ate": None,
        "intervalo_mediano_dias": None,
        "ultima_data_com": None,
        "n_datas_com_historico": len(datas_com),
    }

    if not datas_com:
        return base

    ultima = datas_com[-1]
    base["ultima_data_com"] = ultima

    intervalo = _estimar_intervalo_mediano(datas_com)
    if intervalo is None:
        return base
    base["intervalo_mediano_dias"] = intervalo

    proxima_estimada = ultima + timedelta(days=intervalo)
    # Se a estimativa ja passou (atrasou), avanca para a proxima ocorrencia
    while proxima_estimada < hoje:
        proxima_estimada += timedelta(days=intervalo)
    base["proxima_data_com_estimada"] = proxima_estimada

    dias_ate = (proxima_estimada - hoje).days
    base["dias_corridos_ate"] = dias_ate

    # Janela_pre eh em pregoes; converter para dias corridos com fator ~1.4
    # (~5 pregoes = 7 dias corridos). Mais simples: aceitar se dias_ate <= janela_pre + 4.
    base["aberta"] = 0 <= dias_ate <= (janela_pre_pregoes + 4)

    return base
