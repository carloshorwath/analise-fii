from datetime import date

import numpy as np
from scipy import stats as sp_stats
from sqlalchemy import select

from src.fii_analysis.config_yaml import get_threshold
from src.fii_analysis.data.database import RelatorioMensal, get_cnpj_by_ticker


def tendencia_pl(ticker: str, meses: list[int] | None = None, session=None, *, t: date | None = None) -> dict:
    """Tendência de PL por cota via regressão linear.

    Parâmetro ``t`` define o ponto de corte point-in-time: só são usados
    relatórios com ``data_entrega <= t``. Default: hoje.
    """
    if meses is None:
        meses = [6, 12]
    if t is None:
        t = date.today()
    elif hasattr(t, "date"):
        t = t.date()
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return {m: {"coef_angular": None, "r2": None, "n": 0} for m in meses}

    relatorios = session.execute(
        select(RelatorioMensal.data_referencia, RelatorioMensal.vp_por_cota)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.vp_por_cota.isnot(None),
            RelatorioMensal.data_entrega <= t,
        )
        .order_by(RelatorioMensal.data_referencia.desc())
    ).all()

    if not relatorios:
        return {m: {"coef_angular": None, "r2": None, "n": 0} for m in meses}

    resultado = {}
    for m in meses:
        corte = relatorios[:m]
        if len(corte) < 3:
            resultado[m] = {"coef_angular": None, "r2": None, "n": len(corte)}
            continue

        vp_vals = [float(r.vp_por_cota) for r in reversed(corte)]
        x = np.arange(len(vp_vals), dtype=float)
        y = np.array(vp_vals)

        slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x, y)
        resultado[m] = {
            "coef_angular": float(slope),
            "r2": float(r_value ** 2),
            "n": len(corte),
        }

    return resultado


def flag_destruicao_capital(ticker: str, session=None, *, t: date | None = None) -> dict:
    """Detecta destruição de capital com três condições alinhadas na mesma janela temporal.

    Parâmetro ``t`` define o ponto de corte point-in-time: só são usados
    relatórios com ``data_entrega <= t``. Default: hoje.

    Janela: últimos 6 relatórios mensais.
    """
    if t is None:
        t = date.today()
    elif hasattr(t, "date"):
        t = t.date()
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return {"destruicao": False, "motivo": "ticker nao encontrado",
                "meses_consecutivos": 0}

    relatorios = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.rentab_efetiva,
            RelatorioMensal.rentab_patrim,
            RelatorioMensal.cotas_emitidas,
            RelatorioMensal.vp_por_cota,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.rentab_efetiva.isnot(None),
            RelatorioMensal.rentab_patrim.isnot(None),
            RelatorioMensal.data_entrega <= t,
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(6)
    ).all()

    if len(relatorios) < 3:
        return {"destruicao": False, "motivo": "dados insuficientes",
                "meses_consecutivos": 0}

    consec = 0
    max_consec = 0
    streak_end_idx = 0
    for i, r in enumerate(relatorios):
        ef = float(r.rentab_efetiva) if r.rentab_efetiva is not None else None
        pa = float(r.rentab_patrim) if r.rentab_patrim is not None else None
        if ef is not None and pa is not None and ef > pa:
            consec += 1
            if consec > max_consec:
                max_consec = consec
                streak_end_idx = i
        else:
            consec = 0

    cond1 = max_consec >= get_threshold("meses_consec_alerta", 3)

    janela_streak = relatorios[:streak_end_idx + 1]

    cotas = [float(r.cotas_emitidas) for r in janela_streak if r.cotas_emitidas is not None]
    cond2 = True
    if len(cotas) >= 2:
        crescimento = (cotas[0] - cotas[-1]) / cotas[-1] if cotas[-1] > 0 else 0
        cond2 = crescimento <= 0.01

    vp_periodo = [float(r.vp_por_cota) for r in reversed(janela_streak)
                  if r.vp_por_cota is not None]
    cond3 = False
    if len(vp_periodo) >= 2:
        x = np.arange(len(vp_periodo), dtype=float)
        y = np.array(vp_periodo)
        slope, _, _, _, _ = sp_stats.linregress(x, y)
        cond3 = slope <= 0

    destruicao = cond1 and cond2 and cond3
    motivos = []
    if not cond1:
        motivos.append("cond1_fail: rent.efetiva > rent.patrim < 3 meses consecutivos")
    if not cond2:
        motivos.append("cond2_fail: cotas cresceram > 1% no periodo")
    if not cond3:
        motivos.append("cond3_fail: VP/cota com tendencia positiva")

    return {
        "destruicao": destruicao,
        "motivo": " | ".join(motivos) if not destruicao else "todas condicoes atendidas",
        "meses_consecutivos": max_consec,
        "cond1_efetiva_gt_patrim": cond1,
        "cond2_cotas_estaveis": cond2,
        "cond3_vp_tendencia_negativa": cond3,
    }


def emissoes_recentes(ticker: str, threshold_pct: float = 1.0, session=None) -> list[dict]:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return []

    relatorios = session.execute(
        select(RelatorioMensal.data_referencia, RelatorioMensal.cotas_emitidas)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.cotas_emitidas.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(12)
    ).all()

    emissoes = []
    rows = list(relatorios)
    for i in range(len(rows) - 1):
        atual = rows[i]
        anterior = rows[i + 1]
        cotas_atual = float(atual.cotas_emitidas)
        cotas_ant = float(anterior.cotas_emitidas)
        if cotas_ant > 0:
            var = (cotas_atual - cotas_ant) / cotas_ant * 100
            if var > threshold_pct:
                emissoes.append({
                    "data_ref": atual.data_referencia,
                    "cotas_ant": cotas_ant,
                    "cotas_novas": cotas_atual,
                    "variacao_pct": float(var),
                })

    return emissoes
