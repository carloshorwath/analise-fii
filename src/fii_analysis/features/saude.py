from datetime import date

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.fii_analysis.config_yaml import get_saude_param, get_threshold
from src.fii_analysis.data.database import AtivoPassivo, RelatorioMensal, get_cnpj_by_ticker
from src.fii_analysis.features.indicators import get_relatorios_ajustados


def _informes_pit(ticker: str, session, t: date) -> pd.DataFrame:
    """Informes entregues ate `t` (point-in-time), do mais recente ao mais antigo, com
    VP/cota (vp_aj) e cotas (cotas_aj) na MESMA BASE entre informes: um split/grupamento
    dentro da janela nao pode virar "emissao" nem "queda de VP" (ver data/corporate_actions.py).
    """
    df = get_relatorios_ajustados(ticker, session)
    if df.empty:
        return df
    df = df[pd.to_datetime(df["data_entrega"]) <= pd.Timestamp(t)]
    return df.sort_values("data_referencia", ascending=False).reset_index(drop=True)


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

    df = _informes_pit(ticker, session, t)
    df = df[df["vp_aj"].notna()]
    relatorios = list(df["vp_aj"].astype(float))  # mais recente primeiro

    if not relatorios:
        return {m: {"coef_angular": None, "r2": None, "n": 0} for m in meses}

    resultado = {}
    for m in meses:
        corte = relatorios[:m]
        if len(corte) < 3:
            resultado[m] = {"coef_angular": None, "r2": None, "n": len(corte)}
            continue

        vp_vals = list(reversed(corte))
        x = np.arange(len(vp_vals), dtype=float)
        y = np.array(vp_vals)

        slope, intercept, r_value, p_value, std_err = sp_stats.linregress(x, y)
        resultado[m] = {
            "coef_angular": float(slope),
            "r2": float(r_value ** 2),
            "n": len(corte),
        }

    return resultado


def _limiares_vp_pct() -> tuple[float, float, float]:
    """Limiares de saúde em % do VP/cota por mês (config.yaml, seção ``saude``).

    Defaults preservam a calibração original para cota ~R$100: +0,1 / -0,5 por mês.
    Retorna (saudavel, severo, delta_tendencia).
    """
    return (
        float(get_saude_param("vp_pct_mes_saudavel", 0.1)),
        float(get_saude_param("vp_pct_mes_severo", -0.5)),
        float(get_saude_param("tendencia_delta_pct_mes", 0.1)),
    )


def _score_destruicao_pct(pct_mes: float, saudavel: float, severo: float) -> float:
    """Converte a variação %/mês do VP/cota em score de destruição (0=saudável, 100=severo).

    pct > saudavel -> 0 | pct = 0 -> 10 (neutro) | pct <= severo -> 100.
    Faixas intermediárias lineares (mesmo desenho da versão em R$ absolutos).
    """
    if pct_mes > saudavel:
        return 0.0
    if pct_mes > 0:
        return (saudavel - pct_mes) / saudavel * 10.0
    if pct_mes > severo:
        return 10.0 + (pct_mes / severo) * 90.0
    return 100.0


def _meses_queda_vp(vps_desc: list[float], limiar_pct: float) -> tuple[int, int]:
    """Meses consecutivos em que o VP/cota CAIU mais que ``limiar_pct`` (% no mês).

    ``vps_desc``: VP/cota do mais recente para o mais antigo. Retorna
    (streak ativo contado a partir do mais recente, maior streak da janela).
    Mede queda real do VP/cota — substitui o antigo critério
    "rent. efetiva > patrimonial", que é identicamente ``dy_mes_pct > 0``
    (efetiva - patrimonial == dy_mes_pct nos dados da CVM).
    """
    quedas: list[bool] = []
    for i in range(len(vps_desc) - 1):
        ant = vps_desc[i + 1]
        var = (vps_desc[i] - ant) / ant * 100.0 if ant > 0 else 0.0
        quedas.append(var < -limiar_pct)

    atual = 0
    for q in quedas:
        if not q:
            break
        atual += 1

    maximo = corrente = 0
    for q in reversed(quedas):
        corrente = corrente + 1 if q else 0
        maximo = max(maximo, corrente)
    return atual, maximo


def flag_destruicao_capital(ticker: str, session=None, *, t: date | None = None) -> dict:
    """Detecta destruição de capital com score de gravidade + tendência.

    Parâmetro ``t`` define o ponto de corte point-in-time: só são usados
    relatórios com ``data_entrega <= t``. Default: hoje.

    Os limiares são aplicados à variação PERCENTUAL do VP/cota por mês
    (inclinação da regressão / VP médio da janela), não a R$ absolutos —
    assim fundo de cota cara e de cota barata são julgados na mesma régua.

    Retorna um dict com:
        - destruicao (bool): True se gravidade for 'critica' ou 'alerta'
        - gravidade: 'critica' | 'alerta' | 'em_recuperacao' | 'saudavel'
        - tendencia: 'piorando' | 'estavel' | 'melhorando'
        - score_saude (0–100): 100 = saudável, 0 = destruição severa
        - score_vp_6m, score_vp_3m: componentes do score
        - pct_3m, pct_6m: variação do VP/cota em %/mês (3 e 6 relatórios)
        - meses_consecutivos: meses consecutivos de queda do VP/cota
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

    relatorios = _informes_pit(ticker, session, t)
    relatorios = relatorios[relatorios["vp_aj"].notna()].head(12)

    if len(relatorios) < 3:
        return _destruicao_result(False, "saudavel", "estavel", 100, "dados insuficientes")

    pct_saudavel, pct_severo, delta_tendencia = _limiares_vp_pct()

    # --- Meses consecutivos de queda do VP/cota (relatorios é DESC) ---
    vps_desc = [float(v) for v in relatorios["vp_aj"]]
    current_consec, max_consec = _meses_queda_vp(vps_desc, pct_saudavel)

    cond1 = max_consec >= get_threshold("meses_consec_alerta", 2)

    cotas = [float(c) for c in relatorios["cotas_aj"] if pd.notna(c)]
    cond2 = True
    if len(cotas) >= 2:
        crescimento = (cotas[0] - cotas[-1]) / cotas[-1] if cotas[-1] > 0 else 0
        cond2 = crescimento <= 0.01

    # --- Slopes VP/cota (R$/mês) ---
    vp_6m = list(reversed(vps_desc[:6]))
    slope_6m = 0.0
    if len(vp_6m) >= 2:
        slope_6m, _, _, _, _ = sp_stats.linregress(np.arange(len(vp_6m), dtype=float), np.array(vp_6m))

    vp_3m = list(reversed(vps_desc[:3]))
    slope_3m = 0.0
    if len(vp_3m) >= 2:
        slope_3m, _, _, _, _ = sp_stats.linregress(np.arange(len(vp_3m), dtype=float), np.array(vp_3m))

    # --- Variação percentual mensal do VP/cota (slope / VP médio da janela * 100) ---
    avg_vp_3m = float(np.mean(vp_3m)) if len(vp_3m) >= 1 else 0.0
    avg_vp_6m = float(np.mean(vp_6m)) if len(vp_6m) >= 1 else 0.0
    pct_3m = (slope_3m / avg_vp_3m * 100) if avg_vp_3m != 0 else 0.0
    pct_6m = (slope_6m / avg_vp_6m * 100) if avg_vp_6m != 0 else 0.0

    # --- Score VP (0=saudável, 100=severo) sobre %/mês ---
    score_vp_3m = _score_destruicao_pct(pct_3m, pct_saudavel, pct_severo)
    score_vp_6m = _score_destruicao_pct(pct_6m, pct_saudavel, pct_severo)

    # --- Score streak: só conta se o VP está caindo de fato (pct_3m abaixo de -saudavel) ---
    if pct_3m < -pct_saudavel and current_consec > 0:
        score_meses = min(current_consec / 6.0, 1.0) * 100.0
    else:
        score_meses = 0.0

    # --- Emissões ruins como agravante ---
    n_emissoes_ruins = 0
    try:
        _emissoes_check = emissoes_recentes(ticker, session=session, t=t)
        n_emissoes_ruins = sum(1 for e in _emissoes_check if e.get("ruim", False))
    except Exception:
        pass

    # --- Score composto (destruição, interno) ---
    # Pesos: VP 3m (60%) + VP 6m (30%) + meses consecutivos de queda do VP (10%)
    score_destruicao_raw = round(0.60 * score_vp_3m + 0.30 * score_vp_6m + 0.10 * score_meses)
    # Agravante: +10 pts por emissão ruim recente (max +30)
    score_destruicao_raw = min(100, score_destruicao_raw + n_emissoes_ruins * 10)

    # --- Score de SAÚDE (invertido): 100 = saudável, 0 = destruição severa ---
    score_saude = 100 - score_destruicao_raw

    # --- Condição original cond3 (retrocompatibilidade): VP/cota com tendência de queda na janela ---
    cond3 = False
    if len(vps_desc) >= 2:
        slope_janela, _, _, _, _ = sp_stats.linregress(
            np.arange(len(vps_desc), dtype=float), np.array(list(reversed(vps_desc)))
        )
        cond3 = slope_janela <= 0

    # --- Tendência: compara %/mês 3m vs 6m ---
    if len(vp_6m) >= 2 and len(vp_3m) >= 2:
        diff_pct = pct_3m - pct_6m
        if diff_pct > delta_tendencia:
            tendencia = "melhorando"
        elif diff_pct < -delta_tendencia:
            tendencia = "piorando"
        else:
            tendencia = "estavel"
    else:
        tendencia = "estavel"

    # --- Gravidade (inteligente) ---
    vp_recebendo = pct_3m > 0

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
        if pct_3m > pct_saudavel / 2:
            diag_resumo = f"VP/cota subindo (+{pct_3m:.2f}% ao mês nos últimos 3m). Gestão eficaz."
    elif gravidade == "em_recuperacao":
        diag_class = "EM RECUPERAÇÃO"
        diag_emoji = "🟡"
        diag_resumo = (
            f"Queda do VP/cota detectada no passado ({max_consec}m consec. máx.), "
            f"mas VP/cota em recuperação ({pct_3m:+.2f}% ao mês nos últimos 3m)."
        )
    elif gravidade == "alerta":
        diag_class = "ALERTA"
        diag_emoji = "🟠"
        diag_resumo = (
            f"VP/cota em queda ({pct_3m:.2f}% ao mês). "
            f"{current_consec} meses consecutivos de queda do VP/cota."
        )
    else:  # critica
        diag_class = "DESTRUIÇÃO ATIVA"
        diag_emoji = "🔴"
        diag_resumo = (
            f"VP/cota em queda severa ({pct_3m:.2f}% ao mês). "
            f"{current_consec} meses consecutivos de queda do VP/cota."
        )

    if n_emissoes_ruins > 0:
        diag_resumo += f" {n_emissoes_ruins} emissão(ões) prejudicial(es) recente(s)."

    # --- Motivo (retrocompatibilidade) ---
    motivo = f"[{diag_class}] {diag_resumo}"

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
        "cond1_queda_vp_consecutiva": cond1,
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
        "cond1_queda_vp_consecutiva": False,
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


def emissoes_recentes(
    ticker: str, threshold_pct: float = 1.0, session=None, *, t: date | None = None
) -> list[dict]:
    """Detecta emissões recentes e avalia impacto no VP/cota.

    Para cada emissão (>threshold_pct cotas), calcula a variação do VP/cota
    entre o mês anterior e o mês da emissão. Se VP/cota caiu > 1%, a emissão
    é classificada como 'prejudicial' (o fundo deu desconto aos novos cotistas).

    Parâmetro t define o ponto de corte point-in-time: só são usados
    relatórios com data_entrega <= t. Default: hoje.

    Cotas e VP/cota vêm ajustados a splits/grupamentos (mesma base entre informes),
    portanto ``cotas_ant``/``cotas_novas``/``vp_*`` estão na base da quantidade ATUAL de cotas.

    Returns:
        Lista de dicts com campos:
            data_ref, cotas_ant, cotas_novas, variacao_pct,
            vp_antes, vp_depois, impacto_vp_pct,
            ruim (bool), classificacao ('prejudicial'/'neutra'/'benefica')
    """
    if t is None:
        t = date.today()
    elif hasattr(t, "date"):
        t = t.date()
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return []

    relatorios = _informes_pit(ticker, session, t)
    relatorios = relatorios[relatorios["cotas_aj"].notna()].head(12)

    emissoes = []
    rows = list(relatorios.itertuples(index=False))
    for i in range(len(rows) - 1):
        atual = rows[i]
        anterior = rows[i + 1]
        cotas_atual = float(atual.cotas_aj)
        cotas_ant = float(anterior.cotas_aj)
        if cotas_ant > 0:
            var = (cotas_atual - cotas_ant) / cotas_ant * 100
            if var > threshold_pct:
                # Calcular impacto no VP/cota (mês anterior → mês da emissão)
                vp_depois = float(atual.vp_aj) if pd.notna(atual.vp_aj) else None
                vp_antes = float(anterior.vp_aj) if pd.notna(anterior.vp_aj) else None
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