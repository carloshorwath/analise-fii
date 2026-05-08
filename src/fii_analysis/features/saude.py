from datetime import date

import numpy as np
from scipy import stats as sp_stats
from sqlalchemy import select

from src.fii_analysis.config_yaml import get_threshold
from src.fii_analysis.data.database import AtivoPassivo, RelatorioMensal, get_cnpj_by_ticker


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
    """Detecta destruição de capital com score de gravidade + tendência.

    Parâmetro ``t`` define o ponto de corte point-in-time: só são usados
    relatórios com ``data_entrega <= t``. Default: hoje.

    Retorna um dict com:
        - destruicao (bool): True se gravidade for 'critica' ou 'alerta'
        - gravidade: 'critica' | 'alerta' | 'em_recuperacao' | 'saudavel'
        - tendencia: 'piorando' | 'estavel' | 'melhorando'
        - score_saude (0–100): 100 = saudável, 0 = destruição severa
        - score_vp_6m, score_vp_3m: componentes do score
        - meses_consecutivos: meses consecutivos com rent_efetiva > rent_patrim
        - n_emissoes_ruins: emissões prejudiciais recentes
        - motivo: texto explicativo
        - cond1/2/3: condições originais (retrocompatibilidade)
    """
    if t is None:
        t = date.today()
    elif hasattr(t, "date"):
        t = t.date()
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return _destruicao_result(False, "saudavel", "estavel", 100, "ticker nao encontrado")

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
        .limit(12)
    ).all()

    if len(relatorios) < 3:
        return _destruicao_result(False, "saudavel", "estavel", 100, "dados insuficientes")

    # --- Consecutividade rent_efetiva > rent_patrim ---
    # max_consec: maior streak histórico (display). current_consec: streak ativo (score).
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

    # current_consec: streak a partir do mês mais recente.
    # Se o mês mais recente NÃO é ruim → current_consec = 0 (problema parou).
    current_consec = 0
    for r in relatorios:
        ef = float(r.rentab_efetiva) if r.rentab_efetiva is not None else None
        pa = float(r.rentab_patrim) if r.rentab_patrim is not None else None
        if ef is not None and pa is not None and ef > pa:
            current_consec += 1
        else:
            break

    cond1 = max_consec >= get_threshold("meses_consec_alerta", 3)
    cond1_current = current_consec >= get_threshold("meses_consec_alerta", 3)

    janela_streak = relatorios[:streak_end_idx + 1]

    cotas = [float(r.cotas_emitidas) for r in janela_streak if r.cotas_emitidas is not None]
    cond2 = True
    if len(cotas) >= 2:
        crescimento = (cotas[0] - cotas[-1]) / cotas[-1] if cotas[-1] > 0 else 0
        cond2 = crescimento <= 0.01

    # --- Slopes VP/cota ---
    vp_6m = [float(r.vp_por_cota) for r in reversed(relatorios[:min(6, len(relatorios))])
             if r.vp_por_cota is not None]
    slope_6m = 0.0
    if len(vp_6m) >= 2:
        x6 = np.arange(len(vp_6m), dtype=float)
        y6 = np.array(vp_6m)
        slope_6m, _, _, _, _ = sp_stats.linregress(x6, y6)

    vp_3m = [float(r.vp_por_cota) for r in reversed(relatorios[:min(3, len(relatorios))])
             if r.vp_por_cota is not None]
    slope_3m = 0.0
    if len(vp_3m) >= 2:
        x3 = np.arange(len(vp_3m), dtype=float)
        y3 = np.array(vp_3m)
        slope_3m, _, _, _, _ = sp_stats.linregress(x3, y3)

    # --- Score VP: converte slope em score de destruição (0=saudável, 100=severo) ---
    # slope > 0.1 → 0 (saudável) | slope = 0 → 10 (neutro) | slope < -0.5 → 100 (severo)
    def _slope_score(sl: float) -> float:
        if sl > 0.1:
            return 0.0
        elif sl > 0:
            return (0.1 - sl) / 0.1 * 10.0
        elif sl > -0.5:
            return 10.0 + (-sl / 0.5) * 90.0
        else:
            return 100.0

    # --- Percentual mensal do VP/cota (slope / média * 100) ---
    avg_vp_3m = float(np.mean(vp_3m)) if len(vp_3m) >= 1 else 0.0
    avg_vp_6m = float(np.mean(vp_6m)) if len(vp_6m) >= 1 else 0.0
    pct_3m = (slope_3m / avg_vp_3m * 100) if avg_vp_3m != 0 else 0.0
    pct_6m = (slope_6m / avg_vp_6m * 100) if avg_vp_6m != 0 else 0.0

    score_vp_3m = _slope_score(slope_3m)
    score_vp_6m = _slope_score(slope_6m)

    # --- Score streak: só conta se VP está caindo significativamente ---
    # Se slope_3m >= -0.1 (VP estável ou subindo), streak é irrelevante
    if slope_3m < -0.1 and current_consec > 0:
        score_meses = min(current_consec / 6.0, 1.0) * 100.0
    else:
        score_meses = 0.0

    # --- Emissões ruins como agravante ---
    n_emissoes_ruins = 0
    try:
        _emissoes_check = emissoes_recentes(ticker, session=session)
        n_emissoes_ruins = sum(1 for e in _emissoes_check if e.get("ruim", False))
    except Exception:
        pass

    # --- Score composto (destruição, interno) ---
    # Pesos: VP 3m (60%) + VP 6m (30%) + consecutivos (10%)
    score_destruicao_raw = round(0.60 * score_vp_3m + 0.30 * score_vp_6m + 0.10 * score_meses)
    # Agravante: +10 pts por emissão ruim recente (max +30)
    score_destruicao_raw = min(100, score_destruicao_raw + n_emissoes_ruins * 10)

    # --- Score de SAÚDE (invertido): 100 = saudável, 0 = destruição severa ---
    score_saude = 100 - score_destruicao_raw

    # --- Condição original cond3 (retrocompatibilidade) ---
    vp_periodo = [float(r.vp_por_cota) for r in reversed(janela_streak)
                  if r.vp_por_cota is not None]
    cond3 = False
    if len(vp_periodo) >= 2:
        x = np.arange(len(vp_periodo), dtype=float)
        y = np.array(vp_periodo)
        slope_streak, _, _, _, _ = sp_stats.linregress(x, y)
        cond3 = slope_streak <= 0

    # --- Tendência: compara slope 3m vs 6m ---
    if len(vp_6m) >= 2 and len(vp_3m) >= 2:
        diff_slopes = slope_3m - slope_6m
        if diff_slopes > 0.1:
            tendencia = "melhorando"
        elif diff_slopes < -0.1:
            tendencia = "piorando"
        else:
            tendencia = "estavel"
    else:
        tendencia = "estavel"

    # --- Gravidade (inteligente) ---
    vp_recebendo = slope_3m > 0

    if score_saude >= 75:
        gravidade = "saudavel"
    elif vp_recebendo and score_saude >= 50:
        gravidade = "em_recuperacao"
    elif score_saude >= 30:
        gravidade = "alerta"
    else:
        gravidade = "critica"

    # --- Flag booleano (retrocompatibilidade) ---
    # "em_recuperacao" NÃO veta — o fundo está melhorando, não destruindo
    destruicao = gravidade in ("critica", "alerta")

    # --- Diagnóstico narrativo (inteligente) ---
    if gravidade == "saudavel":
        diag_class = "SAUDÁVEL"
        diag_emoji = "🟢"
        diag_resumo = "VP/cota estável ou em alta. Sem sinais de destruição de capital."
        if slope_3m > 0.05:
            diag_resumo = f"VP/cota subindo (+{pct_3m:.2f}% ao mês nos últimos 3m). Gestão eficaz."
    elif gravidade == "em_recuperacao":
        diag_class = "EM RECUPERAÇÃO"
        diag_emoji = "🟡"
        diag_resumo = (
            f"Destruição detectada no passado ({max_consec}m consec. máx.), "
            f"mas VP/cota em recuperação ({pct_3m:+.2f}% ao mês nos últimos 3m)."
        )
    elif gravidade == "alerta":
        diag_class = "ALERTA"
        diag_emoji = "🟠"
        diag_resumo = f"VP/cota em queda ({pct_3m:.2f}% ao mês). {current_consec} meses consecutivos com rent. efetiva > patrimonial."
    else:  # critica
        diag_class = "DESTRUIÇÃO ATIVA"
        diag_emoji = "🔴"
        diag_resumo = f"VP/cota em queda severa ({pct_3m:.2f}% ao mês). {current_consec} meses consecutivos de destruição."

    if n_emissoes_ruins > 0:
        diag_resumo += f" {n_emissoes_ruins} emissão(ões) prejudicial(es) recente(s)."

    # --- Motivo (retrocompatibilidade) ---
    motivo = f"[{diag_class}] {diag_resumo}"

    motivos_det = []
    if not cond1:
        motivos_det.append("cond1_fail: rent.efetiva > rent.patrim < 3 meses consecutivos")
    if not cond2:
        motivos_det.append("cond2_fail: cotas cresceram > 1% no periodo")
    if not cond3:
        motivos_det.append("cond3_fail: VP/cota com tendencia positiva")

    return {
        "destruicao": destruicao,
        "gravidade": gravidade,
        "tendencia": tendencia,
        "score_saude": int(score_saude),
        "score_vp_6m": round(score_vp_6m, 1),
        "score_vp_3m": round(score_vp_3m, 1),
        "motivo": motivo,
        "meses_consecutivos": current_consec,
        "max_consec_historico": max_consec,
        "current_consec": current_consec,
        "n_emissoes_ruins": n_emissoes_ruins,
        "cond1_efetiva_gt_patrim": cond1,
        "cond2_cotas_estaveis": cond2,
        "cond3_vp_tendencia_negativa": cond3,
        "slope_6m": round(float(slope_6m), 4) if slope_6m else None,
        "slope_3m": round(float(slope_3m), 4) if slope_3m else None,
        "pct_3m": round(float(pct_3m), 4),
        "pct_6m": round(float(pct_6m), 4),
        # Diagnóstico narrativo inteligente
        "diagnostico_class": diag_class,
        "diagnostico_emoji": diag_emoji,
        "diagnostico_resumo": diag_resumo,
    }


def _destruicao_result(destruicao, gravidade, tendencia, score_saude, motivo, **extra):
    """Helper para construir o dict de retorno de flag_destruicao_capital.

    ``score_saude``: 100 = saudável, 0 = destruição severa.
    """
    return {
        "destruicao": destruicao,
        "gravidade": gravidade,
        "tendencia": tendencia,
        "score_saude": score_saude,
        "score_vp_6m": 0.0,
        "score_vp_3m": 0.0,
        "motivo": motivo,
        "meses_consecutivos": 0,
        "max_consec_historico": 0,
        "current_consec": 0,
        "n_emissoes_ruins": 0,
        "cond1_efetiva_gt_patrim": False,
        "cond2_cotas_estaveis": True,
        "cond3_vp_tendencia_negativa": False,
        "slope_6m": None,
        "slope_3m": None,
        "pct_3m": 0.0,
        "pct_6m": 0.0,
        "diagnostico_class": "SAUDÁVEL" if gravidade == "saudavel" else "N/A",
        "diagnostico_emoji": "🟢" if gravidade == "saudavel" else "⚪",
        "diagnostico_resumo": motivo,
        **extra,
    }


def emissoes_recentes(ticker: str, threshold_pct: float = 1.0, session=None) -> list[dict]:
    """Detecta emissões recentes e avalia impacto no VP/cota.

    Para cada emissão (>threshold_pct cotas), calcula a variação do VP/cota
    entre o mês anterior e o mês da emissão. Se VP/cota caiu > 1%, a emissão
    é classificada como 'prejudicial' (o fundo deu desconto aos novos cotistas).

    Returns:
        Lista de dicts com campos:
            data_ref, cotas_ant, cotas_novas, variacao_pct,
            vp_antes, vp_depois, impacto_vp_pct,
            ruim (bool), classificacao ('prejudicial'/'neutra'/'benefica')
    """
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return []

    relatorios = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.cotas_emitidas,
            RelatorioMensal.vp_por_cota,
        )
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
                # Calcular impacto no VP/cota (mês anterior → mês da emissão)
                vp_depois = float(atual.vp_por_cota) if atual.vp_por_cota is not None else None
                vp_antes = float(anterior.vp_por_cota) if anterior.vp_por_cota is not None else None
                impacto_vp_pct = None
                ruim = False
                classificacao = "neutra"
                if vp_antes is not None and vp_depois is not None and vp_antes > 0:
                    impacto_vp_pct = (vp_depois - vp_antes) / vp_antes * 100
                    if impacto_vp_pct < -1.0:
                        ruim = True
                        classificacao = "prejudicial"
                    elif impacto_vp_pct > 1.0:
                        classificacao = "benefica"
                    else:
                        classificacao = "neutra"

                emissoes.append({
                    "data_ref": atual.data_referencia,
                    "cotas_ant": cotas_ant,
                    "cotas_novas": cotas_atual,
                    "variacao_pct": float(var),
                    "vp_antes": vp_antes,
                    "vp_depois": vp_depois,
                    "impacto_vp_pct": round(impacto_vp_pct, 2) if impacto_vp_pct is not None else None,
                    "ruim": ruim,
                    "classificacao": classificacao,
                })

    return emissoes


def get_ltv_flag(
    ticker: str,
    target_date: date,
    session: "Session",
    limite_ltv: float = 0.20,
) -> tuple[bool, float | None]:
    """Estima LTV como (ativo_total - pl) / ativo_total."""
    cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return False, None

    ap = session.execute(
        select(AtivoPassivo.ativo_total)
        .where(AtivoPassivo.cnpj == cnpj, AtivoPassivo.data_entrega <= target_date)
        .order_by(AtivoPassivo.data_referencia.desc())
        .limit(1)
    ).first()
    if ap is None or ap.ativo_total is None or float(ap.ativo_total) == 0:
        return False, None

    rm = session.execute(
        select(RelatorioMensal.patrimonio_liq)
        .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega <= target_date)
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(1)
    ).first()
    if rm is None or rm.patrimonio_liq is None:
        return False, None

    ativo_total = float(ap.ativo_total)
    pl = float(rm.patrimonio_liq)
    passivo_estimado = max(0.0, ativo_total - pl)
    ltv = passivo_estimado / ativo_total
    return ltv > limite_ltv, round(ltv, 4)