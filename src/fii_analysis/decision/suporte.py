"""Suporte estatistico dos sinais que votam no recommender.

Regra (config.yaml, secao ``decisao``): um sinal BUY/SELL so entra no voto
(n_concordam_buy / n_concordam_sell / nivel de concordancia) se

    n de eventos independentes fora da amostra  >= suporte_n_min   (default 30)
    p-valor corrigido para multiplos testes     <  suporte_p_max   (default 0.05)

Sinal sem suporte NAO some: continua gravado e exibido, marcado como
informativo. Sinal sem n/p disponivel e tratado como sem suporte.

Origem de n e p por sinal:
    otimizador   -> test_result do ThresholdOptimizerV2.optimize() (split de teste,
                    n_*_thinned; p Bonferroni sobre o grid). Persistido em
                    dados/optimizer_cache/<ticker>.json (chave ``test_stats``).
    episodio     -> identify_episodes()["summary"][buy|sell]: n (thinned, min_gap)
                    e p do t-test (H0 media=0), corrigido por Bonferroni
                    (m = decisao.testes_episodio). Limiares 10/90 sao fixos
                    (nada ajustado), logo os eventos sao fora da amostra.
    walkforward  -> walk_forward_roll()["summary"][BUY|SELL]: n_effective
                    (thinned, OOS por construcao) e p do t-test, corrigido
                    por Bonferroni (m = decisao.testes_walkforward).

Direcao: BUY exige media > 0 e SELL media < 0 nos eventos (um p baixo com
sinal contrario ao do voto nao e suporte).
"""

from __future__ import annotations

import json
from typing import Optional

from src.fii_analysis.config_yaml import get_decisao_param

SUPORTADO = "SUPORTADO"
SEM_SUPORTE = "SEM_SUPORTE"
NAO_APLICA = "NAO_APLICA"  # NEUTRO / INDISPONIVEL: nao votam

SUPORTE_JSON_PREFIX = "SUPORTE_JSON "
BLOQUEIO_PREFIX = "BLOQUEIO_COMPRA: "

_NOMES = {"otimizador": "Otim", "episodio": "Epi", "walkforward": "WF"}


def limiares_suporte() -> tuple[int, float]:
    return (
        int(get_decisao_param("suporte_n_min", 30)),
        float(get_decisao_param("suporte_p_max", 0.05)),
    )


def avaliar_suporte(
    sinal: str,
    n: Optional[int],
    p_corrigido: Optional[float],
    *,
    direcao_ok: Optional[bool] = True,
    n_min: Optional[int] = None,
    p_max: Optional[float] = None,
) -> dict:
    """Classifica um sinal como SUPORTADO / SEM_SUPORTE / NAO_APLICA."""
    if n_min is None or p_max is None:
        d_n, d_p = limiares_suporte()
        n_min = d_n if n_min is None else n_min
        p_max = d_p if p_max is None else p_max

    base = {
        "sinal": sinal,
        "n": None if n is None else int(n),
        "p": None if p_corrigido is None else round(float(p_corrigido), 6),
    }
    if sinal not in ("BUY", "SELL"):
        return {**base, "status": NAO_APLICA, "motivo": ""}

    if n is None or p_corrigido is None:
        return {**base, "status": SEM_SUPORTE, "motivo": "n/p indisponivel"}

    razoes: list[str] = []
    if n < n_min:
        razoes.append(f"n={int(n)}<{n_min}")
    if p_corrigido >= p_max:
        razoes.append(f"p_corr={p_corrigido:.3f}>={p_max:g}")
    if direcao_ok is False:
        razoes.append("media contraria ao sinal")
    if razoes:
        return {**base, "status": SEM_SUPORTE, "motivo": ", ".join(razoes)}
    return {**base, "status": SUPORTADO, "motivo": f"n={int(n)}, p_corr={p_corrigido:.3f}"}


def _bonferroni(p: Optional[float], m: int) -> Optional[float]:
    if p is None:
        return None
    return min(1.0, float(p) * max(1, int(m)))


def extrair_stats_otimizador(result: dict) -> Optional[dict]:
    """Extrai de ``optimize()`` as estatisticas do split de TESTE (so leitura)."""
    if not result or "error" in result:
        return None
    tr = result.get("test_result")
    if not tr:
        return None
    return {
        "n_buy_thinned": tr.get("n_buy_thinned"),
        "n_sell_thinned": tr.get("n_sell_thinned"),
        "p_value_buy_bonferroni": tr.get("p_value_buy_bonferroni"),
        "p_value_sell_bonferroni": tr.get("p_value_sell_bonferroni"),
        "avg_return_buy_independent": tr.get("avg_return_buy_independent"),
        "n_combinations": result.get("n_combinations"),
    }


def suporte_otimizador(sinal: str, stats: Optional[dict]) -> dict:
    if not stats:
        d = avaliar_suporte(sinal, None, None)
        if d["status"] == SEM_SUPORTE:
            d["motivo"] = "sem estatisticas de teste do otimizador (rode refresh_optimizer_cache)"
        return d
    if sinal == "BUY":
        media = stats.get("avg_return_buy_independent")
        return avaliar_suporte(
            sinal, stats.get("n_buy_thinned"), stats.get("p_value_buy_bonferroni"),
            direcao_ok=None if media is None else media > 0,
        )
    # SELL: o teste do otimizador ja e unicaudal (excesso vs mercado < 0)
    return avaliar_suporte(sinal, stats.get("n_sell_thinned"), stats.get("p_value_sell_bonferroni"))


def _suporte_por_resumo(sinal: str, resumo: Optional[dict], chave_n: str, m: int) -> dict:
    if sinal not in ("BUY", "SELL") or not resumo:
        return avaliar_suporte(sinal, None, None)
    n = resumo.get(chave_n)
    media = resumo.get("mean")
    if media is None:
        direcao = None
    else:
        direcao = media > 0 if sinal == "BUY" else media < 0
    return avaliar_suporte(sinal, n, _bonferroni(resumo.get("p_value"), m), direcao_ok=direcao)


def suporte_episodio(sinal: str, summary: Optional[dict]) -> dict:
    """``summary`` = identify_episodes()["summary"] (chaves 'buy' e 'sell')."""
    resumo = (summary or {}).get("buy" if sinal == "BUY" else "sell")
    return _suporte_por_resumo(sinal, resumo, "n", int(get_decisao_param("testes_episodio", 2)))


def suporte_walkforward(sinal: str, summary: Optional[dict]) -> dict:
    """``summary`` = walk_forward_roll()["summary"] (chaves 'BUY' e 'SELL')."""
    resumo = (summary or {}).get(sinal)
    return _suporte_por_resumo(sinal, resumo, "n_effective", int(get_decisao_param("testes_walkforward", 2)))


def conta_no_voto(suporte: Optional[dict]) -> bool:
    return bool(suporte) and suporte.get("status") == SUPORTADO


def rotulo_sinal(sinal: Optional[str], suporte: Optional[dict]) -> str:
    """Rotulo curto para UI/CLI: 'BUY' ou 'BUY (info)' quando sem suporte."""
    s = sinal or "n/d"
    if sinal in ("BUY", "SELL") and suporte and suporte.get("status") == SEM_SUPORTE:
        return f"{s} (info)"
    return s


def linhas_rationale(suporte_sinais: dict, bloqueio: Optional[str]) -> list[str]:
    """Linhas para rationale_json: resumo legivel + JSON restauravel + bloqueio."""
    linhas: list[str] = []
    if suporte_sinais:
        partes = []
        for chave, nome in _NOMES.items():
            s = suporte_sinais.get(chave)
            if not s or s.get("status") == NAO_APLICA:
                continue
            if s["status"] == SUPORTADO:
                partes.append(f"{nome} {s['sinal']} suportado ({s['motivo']})")
            else:
                partes.append(f"{nome} {s['sinal']} informativo/sem suporte ({s['motivo']})")
        if partes:
            n_min, p_max = limiares_suporte()
            linhas.append(
                f"Suporte estatistico (n>={n_min} indep. fora da amostra, p corrigido<{p_max:g}): "
                + " | ".join(partes)
            )
        linhas.append(SUPORTE_JSON_PREFIX + json.dumps(suporte_sinais, ensure_ascii=False, sort_keys=True))
    if bloqueio:
        linhas.append(BLOQUEIO_PREFIX + bloqueio)
    return linhas


def restaurar_de_rationale(rationale: list[str]) -> tuple[dict, Optional[str]]:
    """Inverso de ``linhas_rationale``: (suporte_sinais, bloqueio_compra)."""
    suporte: dict = {}
    bloqueio: Optional[str] = None
    for linha in rationale or []:
        if not isinstance(linha, str):
            continue
        if linha.startswith(SUPORTE_JSON_PREFIX):
            try:
                suporte = json.loads(linha[len(SUPORTE_JSON_PREFIX):])
            except ValueError:
                suporte = {}
        elif linha.startswith(BLOQUEIO_PREFIX):
            bloqueio = linha[len(BLOQUEIO_PREFIX):]
    return suporte, bloqueio


def rationale_legivel(rationale: list[str]) -> list[str]:
    """Remove a linha JSON de maquina (para exibicao)."""
    return [r for r in (rationale or []) if not (isinstance(r, str) and r.startswith(SUPORTE_JSON_PREFIX))]
