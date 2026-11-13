"""Suporte estatistico dos sinais que votam no recommender.

DEFINICAO UNICA DA HIPOTESE (vale para os tres sinais: otimizador, episodio e
walk-forward; implementada em ``models/teste_excesso.py``):

    Sinal s do ativo i, direcao d (BUY ou SELL), horizonte h (pregoes).
    Periodo de avaliacao P = dias fora da amostra com retorno forward de h
        pregoes definido (otimizador: split de TESTE; episodios: toda a serie
        com percentil definido, limiares fixos 10/90; walk-forward: todos os
        dias OOS).
    Deriva  mu = media do retorno forward de h pregoes sobre TODOS os dias de P
        do mesmo ativo (incondicional; inclui os dias de evento).
    Eventos E = dias de P em que o sinal d esta ativo, afinados por gap >= h
        pregoes (thinning: janelas forward nao se sobrepoem => independentes).
    Excesso x_k = r_k - mu, k em E.
    H0: E[x] = 0 (retorno apos o sinal igual ao incondicional do mesmo ativo
        no mesmo periodo).
    Estatistica: t de 1 amostra de x (n-1 g.l.), UNICAUDAL na direcao do sinal:
        BUY  H1: E[x] > 0      SELL H1: E[x] < 0.
    p bruto: p desse teste. Guardados no resultado: n, media bruta de r, mu,
        excesso medio, p bruto.

    Correcao para multiplos testes: Benjamini-Hochberg (FDR ``decisao.fdr_q``,
    default 5%) sobre a FAMILIA = todos os sinais BUY/SELL ATIVOS avaliados na
    rodada (todos os tickers decididos, os tres tipos de sinal). Sinal ativo
    sem p calculavel entra na familia com p = 1 (conservador). Em
    ``decidir_universo`` a familia e a rodada inteira; em ``decidir_ticker``
    avulso, so os sinais ativos daquele ticker (<= 3). O p ajustado por BH
    (``p_bh``) e o "p corrigido" da trava. A selecao de parametros do
    otimizador ocorre em treino/validacao; o p de holdout NAO e multiplicado
    pelo tamanho do grid (um teste por direcao).

Regra (config.yaml, secao ``decisao``): um sinal BUY/SELL so entra no voto
(n_concordam_buy / n_concordam_sell / nivel de concordancia) se

    n de eventos independentes fora da amostra  >= suporte_n_min   (default 30)
    p_bh (BH sobre a familia da rodada)         <  fdr_q           (default 0.05)

Sinal sem suporte NAO some: continua gravado e exibido, marcado como
informativo. Sinal sem n/p disponivel e tratado como sem suporte.

Limitacoes conhecidas (nao corrigidas aqui):
    - mu e tratado como constante conhecida; seu erro amostral (retornos
      forward sobrepostos, poucos anos) nao entra na variancia do teste.
    - BH assume independencia/dependencia positiva (PRDS) entre testes; os FIIs
      e os tres sinais de um mesmo ticker compartilham mercado e dados.
    - n >= 30 eventos independentes de 20 pregoes exige >= ~2,4 anos DE SINAL
      ATIVO fora da amostra; o split de teste do otimizador raramente chega
      a esse n (ver relatorio de medicao).

Origem de n, media e p por sinal:
    otimizador   -> test_result do ThresholdOptimizerV2.optimize() (split de teste).
                    Persistido em dados/optimizer_cache/<ticker>.json (``test_stats``).
    episodio     -> identify_episodes()["summary"][buy|sell]: n (thinned, min_gap),
                    mean, drift, p_value (excesso, unicaudal).
    walkforward  -> walk_forward_roll()["summary"][BUY|SELL]: n_effective (thinned),
                    mean, drift, p_value (excesso, unicaudal).

Direcao: BUY exige excesso > 0 e SELL excesso < 0 (redundante com a cauda do
teste, mantido como verificacao explicita).
"""

from __future__ import annotations

import json
from typing import Optional, Sequence

import numpy as np

from src.fii_analysis.config_yaml import get_decisao_param
from src.fii_analysis.decision.evidencia import EVIDENCIA_PREFIX

SUPORTADO = "SUPORTADO"
SEM_SUPORTE = "SEM_SUPORTE"
NAO_APLICA = "NAO_APLICA"  # NEUTRO / INDISPONIVEL: nao votam

SUPORTE_JSON_PREFIX = "SUPORTE_JSON "
BLOQUEIO_PREFIX = "BLOQUEIO_COMPRA: "

_NOMES = {"otimizador": "Otim", "episodio": "Epi", "walkforward": "WF"}


def limiares_suporte() -> tuple[int, float]:
    """(n_min, fdr_q): n minimo de eventos independentes e q-valor BH maximo."""
    return (
        int(get_decisao_param("suporte_n_min", 30)),
        float(get_decisao_param("fdr_q", 0.05)),
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
    """Classifica um sinal como SUPORTADO / SEM_SUPORTE / NAO_APLICA.

    ``p_corrigido`` = p ajustado por BH (``p_bh``) sobre a familia da rodada.
    """
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
        razoes.append(f"p_bh={p_corrigido:.3f}>={p_max:g}")
    if direcao_ok is False:
        razoes.append("excesso contrario ao sinal")
    if razoes:
        return {**base, "status": SEM_SUPORTE, "motivo": ", ".join(razoes)}
    return {**base, "status": SUPORTADO, "motivo": f"n={int(n)}, p_bh={p_corrigido:.3f}"}


def ajustar_bh(pvalues: Sequence[float]) -> list[float]:
    """p ajustado de Benjamini-Hochberg (step-up), na ordem de entrada.

    adj_(i) = min_{j>=i} p_(j) * m / j, truncado em 1. Rejeitar adj < q controla
    o FDR em q.
    """
    p = np.asarray(list(pvalues), dtype=float)
    m = len(p)
    if m == 0:
        return []
    ordem = np.argsort(p, kind="stable")
    adj = np.empty(m)
    corrente = 1.0
    for rank in range(m, 0, -1):
        idx = ordem[rank - 1]
        corrente = min(corrente, p[idx] * m / rank)
        adj[idx] = corrente
    return [float(x) for x in adj]


def evidencia(
    sinal: str,
    n: Optional[int],
    media: Optional[float],
    deriva: Optional[float],
    p_bruto: Optional[float],
    excesso: Optional[float] = None,
) -> dict:
    """Evidencia bruta de um sinal (ainda sem correcao de familia)."""
    if excesso is None and media is not None and deriva is not None:
        excesso = float(media) - float(deriva)
    return {
        "sinal": sinal,
        "n": None if n is None else int(n),
        "media": media,
        "deriva": deriva,
        "excesso": excesso,
        "p_bruto": p_bruto,
    }


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
        "p_value_buy": tr.get("p_value_buy"),
        "p_value_sell": tr.get("p_value_sell"),
        "avg_return_buy_independent": tr.get("avg_return_buy_independent"),
        "avg_return_sell_independent": tr.get("avg_return_sell_independent"),
        "deriva": tr.get("unconditional_mean"),
        "excess_buy": tr.get("buy_excess_vs_market_independent"),
        "excess_sell": tr.get("sell_excess_vs_market_independent"),
        "n_combinations": result.get("n_combinations"),
    }


def evidencia_otimizador(sinal: str, stats: Optional[dict]) -> dict:
    if sinal not in ("BUY", "SELL") or not stats:
        return evidencia(sinal, None, None, None, None)
    k = "buy" if sinal == "BUY" else "sell"
    return evidencia(
        sinal, stats.get(f"n_{k}_thinned"), stats.get(f"avg_return_{k}_independent"),
        stats.get("deriva"), stats.get(f"p_value_{k}"), stats.get(f"excess_{k}"),
    )


def _evidencia_resumo(sinal: str, resumo: Optional[dict], chave_n: str) -> dict:
    if sinal not in ("BUY", "SELL") or not resumo:
        return evidencia(sinal, None, None, None, None)
    return evidencia(
        sinal, resumo.get(chave_n), resumo.get("mean"), resumo.get("drift"),
        resumo.get("p_value"), resumo.get("excess"),
    )


def evidencia_episodio(sinal: str, summary: Optional[dict]) -> dict:
    """``summary`` = identify_episodes()["summary"] (chaves 'buy' e 'sell')."""
    return _evidencia_resumo(sinal, (summary or {}).get("buy" if sinal == "BUY" else "sell"), "n")


def evidencia_walkforward(sinal: str, summary: Optional[dict]) -> dict:
    """``summary`` = walk_forward_roll()["summary"] (chaves 'BUY' e 'SELL')."""
    return _evidencia_resumo(sinal, (summary or {}).get(sinal), "n_effective")


def aplicar_fdr(
    evidencias: Sequence[dict],
    *,
    n_min: Optional[int] = None,
    q: Optional[float] = None,
) -> list[dict]:
    """Aplica BH sobre a familia (= evidencias BUY/SELL ativas) e julga cada uma.

    Retorna, na mesma ordem, o dict de suporte: ``p`` = ``p_bh``; ``p_bruto``,
    ``media``, ``deriva``, ``excesso`` e ``m_familia`` acompanham.
    """
    d_n, d_q = limiares_suporte()
    n_min = d_n if n_min is None else n_min
    q = d_q if q is None else q

    ativos = [i for i, e in enumerate(evidencias) if e.get("sinal") in ("BUY", "SELL")]
    m = len(ativos)
    brutos = [
        1.0 if evidencias[i].get("p_bruto") is None else min(1.0, float(evidencias[i]["p_bruto"]))
        for i in ativos
    ]
    p_bh = dict(zip(ativos, ajustar_bh(brutos)))

    saida: list[dict] = []
    for i, e in enumerate(evidencias):
        sinal = e.get("sinal")
        exc = e.get("excesso")
        direcao_ok = None if exc is None else (exc > 0 if sinal == "BUY" else exc < 0)
        tem_p = e.get("p_bruto") is not None
        res = avaliar_suporte(
            sinal, e.get("n"), p_bh.get(i) if tem_p else None,
            direcao_ok=direcao_ok, n_min=n_min, p_max=q,
        )
        if sinal in ("BUY", "SELL"):
            res.update({
                "p_bruto": None if e.get("p_bruto") is None else round(float(e["p_bruto"]), 6),
                "media": e.get("media"), "deriva": e.get("deriva"), "excesso": exc,
                "m_familia": m,
            })
        saida.append(res)
    return saida


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
            n_min, q = limiares_suporte()
            m = next((v.get("m_familia") for v in suporte_sinais.values() if v.get("m_familia")), None)
            linhas.append(
                f"Suporte estatistico (n>={n_min} indep. fora da amostra, p_BH<{q:g}, familia m={m}): "
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
    """Remove as linhas JSON de maquina (suporte e evidencia) para exibicao."""
    return [r for r in (rationale or [])
            if not (isinstance(r, str) and r.startswith((SUPORTE_JSON_PREFIX, EVIDENCIA_PREFIX)))]
