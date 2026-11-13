"""Teste de excesso sobre a deriva — implementacao unica dos tres sinais.

A definicao da hipotese (H0/H1, estatistica, cauda, familia) esta documentada
em UM lugar: docstring de ``src/fii_analysis/decision/suporte.py``. Este modulo
so executa o calculo (otimizador, episodios e walk-forward chamam a mesma funcao).
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from scipy import stats

N_MIN_TESTE = 5


def excesso_vs_deriva(
    retornos_eventos: Sequence[float],
    deriva: float,
    direcao: Optional[str],
    n_min: int = N_MIN_TESTE,
) -> dict:
    """t de 1 amostra do excesso (retorno do evento - deriva) contra 0.

    Parameters
    ----------
    retornos_eventos : retornos forward dos eventos JA independentes (thinned).
    deriva : media incondicional do retorno forward de mesmo horizonte, sobre
        todos os dias elegiveis do periodo de avaliacao do mesmo ativo.
    direcao : "BUY" (H1: excesso > 0), "SELL" (H1: excesso < 0) ou None/outro
        (bicaudal; uso descritivo, p.ex. NEUTRO).
    n_min : n minimo de eventos para calcular o p-valor.

    Returns
    -------
    dict(n, media_bruta, deriva, excesso, t_stat, p_value). ``p_value``/``t_stat``
    sao None se n < n_min ou se o excesso nao tem variancia (SE = 0).
    """
    r = np.asarray(list(retornos_eventos), dtype=float)
    n = int(len(r))
    out = {
        "n": n,
        "media_bruta": float(np.mean(r)) if n else None,
        "deriva": float(deriva),
        "excesso": float(np.mean(r) - deriva) if n else None,
        "t_stat": None,
        "p_value": None,
    }
    if n < max(2, n_min):
        return out
    exc = r - float(deriva)
    if float(np.std(exc, ddof=1)) < 1e-12:
        return out
    alternativa = {"BUY": "greater", "SELL": "less"}.get(direcao or "", "two-sided")
    t_stat, p = stats.ttest_1samp(exc, 0.0, alternative=alternativa)
    out["t_stat"] = float(t_stat)
    out["p_value"] = float(p)
    return out
