"""Status de evidencia do sistema — fonte unica (a UI le daqui, nao duplica texto).

Estudo em painel pre-registrado (Fama-MacBeth + quintis, BH sobre os testes),
2026-11-12: nenhum indicador do sistema teve evidencia de prever qual fundo rende
mais. O sistema e DESCRITIVO. Atualize ESTA constante se um novo estudo mudar isso.
"""

from __future__ import annotations

import json
from typing import Optional

EVIDENCIA_PREFIX = "EVIDENCIA_JSON "

EVIDENCIA: dict = {
    "estudo": "painel pre-registrado, Fama-MacBeth + quintis",
    "data": "2026-11-12",
    "n_fundos": 110,
    "n_datas": 55,
    "periodo": "2022-04 a 2026-10",
    "n_testes": 100,
    "correcao": "Benjamini-Hochberg 5%",
    "sobreviventes": 0,
    "candidato_nao_confirmado": "variacao % do VP/cota em 6 meses (p_BH=0,38 em 6m)",
    "resumo": (
        "Nenhum indicador do sistema tem evidencia de prever retorno relativo entre fundos "
        "(0 de 100 testes sobrevivem a BH). Alertas e rankings sao descritivos."
    ),
}


def linha_evidencia() -> str:
    """Linha estavel e legivel por maquina para o rationale de cada decisao."""
    return EVIDENCIA_PREFIX + json.dumps(EVIDENCIA, ensure_ascii=False, sort_keys=True)


def restaurar_evidencia(rationale: list[str]) -> Optional[dict]:
    """Inverso de ``linha_evidencia``: dict, ou None se a linha nao existe (snapshots antigos)."""
    for linha in rationale or []:
        if isinstance(linha, str) and linha.startswith(EVIDENCIA_PREFIX):
            try:
                return json.loads(linha[len(EVIDENCIA_PREFIX):])
            except ValueError:
                return None
    return None


def texto_evidencia(ev: Optional[dict] = None) -> str:
    ev = ev or EVIDENCIA
    return (
        f"Estudo de {ev['data']} ({ev['n_fundos']} fundos, {ev['n_datas']} datas, "
        f"{ev['n_testes']} testes, {ev['correcao']}): {ev['sobreviventes']} sobreviventes. {ev['resumo']}"
    )
