"""Eventos corporativos (split/grupamento) e retorno total — logica pura, sem I/O.

BASE UNICA DE COTA (decisao documentada)
----------------------------------------
Preco (`fechamento`), dividendo por cota (`dividendos.valor_cota`) e VP/cota
usados em qualquer razao (P/VP, DY) ficam na base da QUANTIDADE ATUAL DE COTAS
(split-ajustada para tras), a mesma do `Close` do yfinance. O VP/cota da CVM e
nominal (contemporaneo ao informe); a conversao e feita por `ajustar_relatorios`.

DETECCAO DE SPLIT (so com dados do proprio banco, relatorios_mensais)
---------------------------------------------------------------------
Entre dois informes consecutivos: cotas_emitidas varia por fator F (>= 1,8 ou
<= 1/1,8), VP/cota varia por ~1/F e o patrimonio liquido fica estavel
(+-20%). Emissao/amortizacao mexem no PL e por isso nao sao confundidas.
F e arredondado ao fator "redondo" mais proximo (tolerancia 8%); se nao houver,
o evento e ignorado (ambiguo).

INSTANTE EM QUE O SPLIT VALE
----------------------------
O evento e ancorado no PRIMEIRO INFORME pos-split (data_referencia). Todo
informe anterior e dividido por F, inclusive os entregues depois da data do
split no preco (o VP vigente ainda e o antigo ate chegar o primeiro informe
pos-split). Isto troca apenas a UNIDADE: P_aj/VP_aj == P_nominal/VP_nominal,
logo nao ha vazamento de informacao futura.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

FATORES_REDONDOS = (2, 3, 4, 5, 6, 8, 9, 10, 12, 15, 20, 25, 50, 100)
TOL_FATOR = 0.08
TOL_PL = 0.20
FATOR_MIN = 1.8
DEDUP_DIAS = 7


@dataclass(frozen=True)
class SplitEvento:
    """fator = cotas_novas / cotas_antigas (10 = desdobramento 1:10; 0,1 = grupamento)."""

    primeiro_informe_pos: date
    fator: float
    razao_cotas: float
    razao_vp: float
    razao_pl: float


def _fator_redondo(razao_vp: float) -> float | None:
    """Fator redondo mais proximo de 1/razao_vp (desdobramento) ou razao_vp (grupamento)."""
    if razao_vp <= 0 or not np.isfinite(razao_vp):
        return None
    f = 1.0 / razao_vp
    cand = f if f >= 1 else razao_vp
    melhor = min(FATORES_REDONDOS, key=lambda n: abs(cand / n - 1))
    if abs(cand / melhor - 1) > TOL_FATOR:
        return None
    return float(melhor) if f >= 1 else 1.0 / melhor


def detectar_splits(rel: pd.DataFrame) -> tuple[list[SplitEvento], list[dict]]:
    """Detecta splits em UM fundo. `rel`: data_referencia, vp_por_cota,
    patrimonio_liq, cotas_emitidas. Retorna (eventos, ambiguos)."""
    if rel is None or len(rel) < 2:
        return [], []
    d = rel.dropna(subset=["vp_por_cota", "patrimonio_liq", "cotas_emitidas"]).copy()
    d = d[(d.vp_por_cota > 0) & (d.patrimonio_liq > 0) & (d.cotas_emitidas > 0)]
    d = d.sort_values("data_referencia").reset_index(drop=True)
    eventos: list[SplitEvento] = []
    ambiguos: list[dict] = []
    for i in range(1, len(d)):
        a, b = d.iloc[i - 1], d.iloc[i]
        rc = float(b.cotas_emitidas) / float(a.cotas_emitidas)
        if FATOR_MIN > rc > 1 / FATOR_MIN:
            continue
        rv = float(b.vp_por_cota) / float(a.vp_por_cota)
        rp = float(b.patrimonio_liq) / float(a.patrimonio_liq)
        if abs(rp - 1) > TOL_PL or abs(rc * rv - 1) > TOL_PL + 0.05:
            continue  # PL mexeu: emissao/amortizacao/dado ruim, nao e split
        f = _fator_redondo(rv)
        ref = pd.Timestamp(b.data_referencia).date()
        if f is None:
            ambiguos.append({"primeiro_informe_pos": ref, "razao_cotas": rc, "razao_vp": rv, "razao_pl": rp})
            continue
        eventos.append(SplitEvento(ref, f, rc, rv, rp))
    return eventos, ambiguos


def ajustar_relatorios(rel: pd.DataFrame, eventos: list[SplitEvento]) -> pd.DataFrame:
    """Acrescenta fator_split, vp_aj e cotas_aj (base da quantidade atual de cotas)."""
    out = rel.copy()
    ref = pd.to_datetime(out["data_referencia"])
    fator = pd.Series(1.0, index=out.index)
    for ev in eventos:
        fator = fator * np.where(ref < pd.Timestamp(ev.primeiro_informe_pos), ev.fator, 1.0)
    out["fator_split"] = fator.astype(float)
    out["vp_aj"] = out["vp_por_cota"].astype(float) / out["fator_split"]
    if "cotas_emitidas" in out.columns:
        out["cotas_aj"] = out["cotas_emitidas"].astype(float) * out["fator_split"]
    return out


def deduplicar_proximos(
    linhas: list[tuple[date, float]],
    preferidas: set[date] | None = None,
    dias: int = DEDUP_DIAS,
) -> list[date]:
    """Datas a REMOVER: mesmo valor por cota e data-com a <= `dias` dias de uma
    linha mantida. Mantem a data em `preferidas` (convencao data-com correta);
    senao a mais antiga. `linhas` = [(data_com, valor)] de UM ticker."""
    preferidas = preferidas or set()
    mantidas: list[tuple[date, float]] = []
    remover: list[date] = []
    for dt, v in sorted(linhas, key=lambda x: x[0]):
        v = float(v)
        alvo = None
        for k, (dk, vk) in enumerate(mantidas):
            if 0 <= (dt - dk).days <= dias and abs(v - vk) <= max(1e-9, 1e-6 * max(abs(v), abs(vk))):
                alvo = k
                break
        if alvo is None:
            mantidas.append((dt, v))
        elif dt in preferidas and mantidas[alvo][0] not in preferidas:
            remover.append(mantidas[alvo][0])
            mantidas[alvo] = (dt, v)
        else:
            remover.append(dt)
    return remover


def calcular_retorno_total(
    precos: pd.Series,
    dividendos: list[tuple[date, float]],
) -> pd.Series:
    """Serie de RETORNO TOTAL (dividendo reinvestido na data-ex), escalada para
    terminar igual ao ultimo `fechamento` (fator 1 no ultimo dia, acumulado para tras).

    precos: fechamento indexado por data (NaN/<=0 ignorados -> saida NaN nesses dias).
    dividendos: [(data_com, valor)] na convencao da tabela (data_com = pregao
    anterior a data-ex). Data-ex = primeiro pregao COM PRECO estritamente depois
    da data-com. Nesse dia: TR_t = TR_{t-1} * (P_t + D) / P_{t-1}.
    Dividendo cuja data-ex ainda nao ocorreu (apos o ultimo preco) e ignorado.
    Funcao pura e deterministica: recalculavel por inteiro a cada atualizacao.
    """
    p = precos.astype(float)
    valido = p[(p > 0) & p.notna()]
    saida = pd.Series(np.nan, index=p.index, dtype=float)
    if valido.empty:
        return saida
    idx = [pd.Timestamp(i).date() for i in valido.index]
    div_por_ex: dict[int, float] = {}
    for dc, v in dividendos:
        if v is None or not np.isfinite(float(v)) or float(v) <= 0:
            continue
        pos = int(np.searchsorted(np.array(idx, dtype="datetime64[D]"), np.datetime64(dc), side="right"))
        if pos >= len(idx) or pos == 0:
            continue  # ex fora da serie (futura) ou sem preco anterior
        div_por_ex[pos] = div_por_ex.get(pos, 0.0) + float(v)
    vals = valido.to_numpy()
    tr = np.empty(len(vals))
    tr[0] = vals[0]
    for i in range(1, len(vals)):
        tr[i] = tr[i - 1] * (vals[i] + div_por_ex.get(i, 0.0)) / vals[i - 1]
    tr = tr * (vals[-1] / tr[-1])
    saida.loc[valido.index] = tr
    return saida
