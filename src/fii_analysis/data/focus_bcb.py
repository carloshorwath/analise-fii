"""Fetch Focus Selic — camada pura de dados, sem lógica de decisão.

Fontes (em ordem de prioridade):
1. BCB Olinda — ExpectativasMercadoSelic (endpoint dedicado, sem filtro).
   Retorna medianas por reunião Copom (Reuniao = "R{N}/{YYYY}").
   Público, sem autenticação.
2. API Dados de Mercado (https://api.dadosdemercado.com.br) — alternativa.
   Requer token (DADOSDEMERCADO_API_KEY no .env).

Regras:
- Não inclui selic_atual (isso vem de outra fonte — cdi_diario).
- Se API falhar: status=ERRO_API, campos=None, nunca quebra o fluxo.
- Cache em memória com TTL de 4h para economizar chamadas.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv
from loguru import logger

# Carregar .env externo (token nunca fica no projeto)
load_dotenv(r"C:\Modelos-AI\Brapi\.env")

# Cache em memória
_cache: FocusSelicResult | None = None
_cache_ts: float = 0.0
_CACHE_TTL_SECONDS = 4 * 3600  # 4 horas

# Mapa Copom: número da reunião → mês aproximado
# O Copom se reúne 8 vezes por ano (~6 semanas entre reuniões).
# Calendário típico: Jan/Fev, Mar, Mai, Jun, Jul, Set, Out, Dez
# Baseado no calendário real 2025: R1=Jan, R2=Mar, R3=Mai, R4=Jun,
#   R5=Jul, R6=Set, R7=Out, R8=Dez
_REUNIAO_TO_MES = {1: 1, 2: 3, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 12}


@dataclass
class FocusSelicResult:
    """Resultado do fetch Focus Selic."""

    focus_status: str  # OK | ERRO_API | SEM_DADOS
    focus_selic_3m: float | None = None   # Mediana 3 meses (fração, ex: 0.145)
    focus_selic_6m: float | None = None   # Mediana 6 meses
    focus_selic_12m: float | None = None  # Mediana 12 meses
    focus_data_referencia: date | None = None  # Data-base do boletim Focus
    focus_coletado_em: datetime | None = None   # Timestamp da coleta
    focus_fonte: str | None = None  # "bcb_selic" | "dadosdemercado"


def fetch_focus_selic(*, force: bool = False) -> FocusSelicResult:
    """Busca expectativas Focus Selic (medianas 3m/6m/12m).

    Usa cache em memória com TTL de 4h. Use force=True para ignorar cache.

    Estratégia:
    1. Tenta BCB ExpectativasMercadoSelic (endpoint dedicado, sem filtro).
    2. Se falhar e houver token Dados de Mercado, tenta essa API.
    3. Se ambas falharem: ERRO_API.

    Returns
    -------
    FocusSelicResult
    """
    global _cache, _cache_ts

    if not force and _cache is not None and (time.time() - _cache_ts) < _CACHE_TTL_SECONDS:
        return _cache

    coletado_em = datetime.now(timezone.utc)

    # ─── Fonte 1: BCB ExpectativasMercadoSelic ─────────────────────
    result = _fetch_bcb_selic(coletado_em)
    if result.focus_status == "OK":
        _cache = result
        _cache_ts = time.time()
        return result

    logger.warning("BCB Selic falhou ({}), tentando Dados de Mercado...", result.focus_status)

    # ─── Fonte 2: Dados de Mercado ─────────────────────────────────
    token = os.getenv("DADOSDEMERCADO_API_KEY")
    if token:
        result = _fetch_dadosdemercado(token, coletado_em)
        if result.focus_status == "OK":
            _cache = result
            _cache_ts = time.time()
            return result

    # Ambas falharam
    if result.focus_status != "OK":
        _cache = result
        _cache_ts = time.time()

    logger.info(
        "Focus: status={} | fonte={} | 3m={} | 6m={} | 12m={}",
        result.focus_status,
        result.focus_fonte,
        result.focus_selic_3m,
        result.focus_selic_6m,
        result.focus_selic_12m,
    )
    return result


def _fetch_bcb_selic(coletado_em: datetime) -> FocusSelicResult:
    """Busca Focus Selic via BCB ExpectativasMercadoSelic.

    Endpoint dedicado — não precisa de filtro por indicador.
    Retorna uma row por Reuniao Copom com Mediana.
    """
    try:
        url = (
            "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/"
            "odata/ExpectativasMercadoSelic"
        )
        params = {
            "$format": "json",
            "$top": "50",
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        logger.warning("BCB ExpectativasMercadoSelic falhou: {}", exc)
        return FocusSelicResult(
            focus_status="ERRO_API",
            focus_coletado_em=coletado_em,
            focus_fonte="bcb_selic",
        )

    rows = body.get("value", [])
    if not rows:
        return FocusSelicResult(
            focus_status="SEM_DADOS",
            focus_coletado_em=coletado_em,
            focus_fonte="bcb_selic",
        )

    # Determinar data do boletim mais recente
    today = date.today()
    datas_disponiveis = set()
    for r in rows:
        raw = r.get("Data", "")
        if raw:
            try:
                datas_disponiveis.add(str(raw)[:10])
            except (ValueError, IndexError):
                pass

    if not datas_disponiveis:
        return FocusSelicResult(
            focus_status="SEM_DADOS",
            focus_coletado_em=coletado_em,
            focus_fonte="bcb_selic",
        )

    data_boletim_str = max(datas_disponiveis)
    data_boletim = date.fromisoformat(data_boletim_str)

    # Filtrar rows do boletim mais recente + baseCalculo=1 (4-day window, mais atual)
    rows_recente = [
        r for r in rows
        if str(r.get("Data", ""))[:10] == data_boletim_str
        and r.get("baseCalculo") == 1
    ]

    # Se não houver baseCalculo=1, usar todas do boletim
    if not rows_recente:
        rows_recente = [
            r for r in rows
            if str(r.get("Data", ""))[:10] == data_boletim_str
        ]

    # Calcular horizonte em meses para cada Reunião
    candidates: list[tuple[int, float]] = []  # (meses_diff, mediana_frac)
    for r in rows_recente:
        reuniao = r.get("Reuniao", "")
        mediana = r.get("Mediana")
        if not reuniao or mediana is None:
            continue

        meses = _parse_reuniao_to_meses(reuniao, today)
        if meses is None or meses <= 0:
            continue

        mediana_frac = float(mediana) / 100.0
        candidates.append((meses, mediana_frac))

    # Encontrar a reunião mais próxima de 3, 6 e 12 meses
    selic_3m = _find_closest(candidates, target=3)
    selic_6m = _find_closest(candidates, target=6)
    selic_12m = _find_closest(candidates, target=12)

    if selic_3m is None and selic_6m is None and selic_12m is None:
        return FocusSelicResult(
            focus_status="SEM_DADOS",
            focus_data_referencia=data_boletim,
            focus_coletado_em=coletado_em,
            focus_fonte="bcb_selic",
        )

    return FocusSelicResult(
        focus_status="OK",
        focus_selic_3m=selic_3m,
        focus_selic_6m=selic_6m,
        focus_selic_12m=selic_12m,
        focus_data_referencia=data_boletim,
        focus_coletado_em=coletado_em,
        focus_fonte="bcb_selic",
    )


def _parse_reuniao_to_meses(reuniao: str, today: date) -> int | None:
    """Converte 'R{N}/{YYYY}' em horizonte em meses.

    Ex: R2/2028 com today=2026-04-29 → (2028*12+3) - (2026*12+4) = 24339-24316 = 23 meses
    """
    m = re.match(r"R(\d+)/(\d{4})", reuniao)
    if not m:
        return None
    n_reuniao = int(m.group(1))
    ano = int(m.group(2))
    mes = _REUNIAO_TO_MES.get(n_reuniao)
    if mes is None:
        return None
    total_ref = ano * 12 + mes
    total_now = today.year * 12 + today.month
    return total_ref - total_now


def _find_closest(
    candidates: list[tuple[int, float]], *, target: int
) -> float | None:
    """Encontra a mediana do horizonte mais próximo do target (em meses)."""
    if not candidates:
        return None
    # Ordenar por distância ao target
    candidates_sorted = sorted(candidates, key=lambda x: abs(x[0] - target))
    return candidates_sorted[0][1]


def _fetch_dadosdemercado(token: str, coletado_em: datetime) -> FocusSelicResult:
    """Busca Focus Selic via API Dados de Mercado (fallback).

    Endpoint: GET /v1/macro/focus/selic
    Retorna lista com campos: date, index, last_month, last_week, last,
    answers, target_date.
    """
    try:
        resp = requests.get(
            "https://api.dadosdemercado.com.br/v1/macro/focus/selic",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:
        logger.warning("Dados de Mercado API falhou: {}", exc)
        return FocusSelicResult(
            focus_status="ERRO_API",
            focus_coletado_em=coletado_em,
            focus_fonte="dadosdemercado",
        )

    if not rows or not isinstance(rows, list):
        return FocusSelicResult(
            focus_status="SEM_DADOS",
            focus_coletado_em=coletado_em,
            focus_fonte="dadosdemercado",
        )

    today = date.today()
    selic_3m: float | None = None
    selic_6m: float | None = None
    selic_12m: float | None = None
    data_boletim: date | None = None

    for row in rows:
        target_date_val = row.get("target_date")
        last_val = row.get("last")
        date_str = row.get("date")

        if target_date_val is None or last_val is None:
            continue

        if data_boletim is None and date_str:
            try:
                data_boletim = date.fromisoformat(str(date_str)[:10])
            except (ValueError, IndexError):
                pass

        td = int(target_date_val)
        td_year = td // 100
        td_month = td % 100
        meses_diff = (td_year - today.year) * 12 + (td_month - today.month)

        if meses_diff <= 0:
            continue

        mediana_frac = float(last_val) / 100.0

        if 1 <= meses_diff <= 3 and selic_3m is None:
            selic_3m = mediana_frac
        elif 4 <= meses_diff <= 6 and selic_6m is None:
            selic_6m = mediana_frac
        elif 7 <= meses_diff <= 12 and selic_12m is None:
            selic_12m = mediana_frac

    if selic_3m is None and selic_6m is None and selic_12m is None:
        return FocusSelicResult(
            focus_status="SEM_DADOS",
            focus_data_referencia=data_boletim,
            focus_coletado_em=coletado_em,
            focus_fonte="dadosdemercado",
        )

    return FocusSelicResult(
        focus_status="OK",
        focus_selic_3m=selic_3m,
        focus_selic_6m=selic_6m,
        focus_selic_12m=selic_12m,
        focus_data_referencia=data_boletim,
        focus_coletado_em=coletado_em,
        focus_fonte="dadosdemercado",
    )