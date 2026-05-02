"""Camada de explicação CDI + Focus — reúne sensibilidade, CDI atual e expectativas.

Puramente informativo. NÃO altera decisão, NÃO gera score, NÃO é sinal.
Reúne dados de cdi_sensitivity, cdi_diario e Focus BCB para explicar ao usuário
se o P/VP atual pode estar parcialmente associado ao cenário esperado de juros.

Regras inegociáveis:
- Não usar Focus em backtest.
- Não mexer em _derivar_acao() do recommender.
- Não transformar em score numérico.
- Focus entra apenas como narrativa macro.
"""

from __future__ import annotations

from datetime import date

from loguru import logger

from src.fii_analysis.data.cdi import get_cdi_acumulado_12m
from src.fii_analysis.data.focus_bcb import FocusSelicResult, fetch_focus_selic
from src.fii_analysis.models.cdi_sensitivity import (
    CdiSensitivityResult,
    compute_cdi_sensitivity,
)


def build_cdi_focus_explanation(
    ticker: str,
    session,
    data_ref: date | None = None,
    focus_data: FocusSelicResult | None = None,
    cdi_sensitivity: CdiSensitivityResult | dict | None = None,
) -> dict:
    """Reúne sensibilidade CDI + Focus Selic → explicação macro para o usuário.

    Parameters
    ----------
    ticker : str
    session : SQLAlchemy session
    data_ref : date, optional
        Data de referência (default: hoje).
    focus_data : FocusSelicResult, optional
        Se fornecido, usa este payload (ex: do snapshot).
        Se None, busca via fetch_focus_selic().
    cdi_sensitivity : CdiSensitivityResult, optional
        Se fornecido, usa este resultado. Se None, computa agora.

    Returns
    -------
    dict com campos:
      cdi_status, cdi_beta, cdi_r_squared, cdi_p_value,
      cdi_residuo_atual, cdi_residuo_percentil,
      cdi_12m_atual,
      focus_status, focus_selic_3m, focus_selic_6m, focus_selic_12m,
      focus_data_referencia,
      delta_focus_3m, delta_focus_6m, delta_focus_12m,
      repricing_estimado_12m,
      explanation_lines (list[str])
    """
    if data_ref is None:
        data_ref = date.today()

    # ─── 1. CDI Sensitivity ─────────────────────────────────────────
    if cdi_sensitivity is None:
        try:
            cdi_sensitivity = compute_cdi_sensitivity(ticker, session, t=data_ref)
        except Exception as exc:
            logger.warning("cdi_sensitivity falhou para {}: {}", ticker, exc)
            cdi_sensitivity = CdiSensitivityResult(status="CONVERGENCIA_FALHOU")

    # Suporta tanto CdiSensitivityResult quanto dict (do cdi_sensitivity_to_dict)
    if isinstance(cdi_sensitivity, dict):
        cdi_status = cdi_sensitivity.get("cdi_status", "SEM_CDI")
        cdi_beta = cdi_sensitivity.get("cdi_beta")
        cdi_r_squared = cdi_sensitivity.get("cdi_r_squared")
        cdi_p_value = cdi_sensitivity.get("cdi_p_value")
        cdi_residuo_atual = cdi_sensitivity.get("cdi_residuo_atual")
        cdi_residuo_percentil = cdi_sensitivity.get("cdi_residuo_percentil")
    else:
        cdi_status = cdi_sensitivity.status
        cdi_beta = cdi_sensitivity.beta
        cdi_r_squared = cdi_sensitivity.r_squared
        cdi_p_value = cdi_sensitivity.p_value
        cdi_residuo_atual = cdi_sensitivity.residuo_atual
        cdi_residuo_percentil = cdi_sensitivity.residuo_percentil

    # ─── 2. CDI 12m atual ────────────────────────────────────────────
    cdi_12m_atual: float | None = None
    try:
        cdi_12m_atual = get_cdi_acumulado_12m(data_ref, session)
    except Exception:
        pass

    # ─── 3. Focus Selic ──────────────────────────────────────────────
    if focus_data is None:
        try:
            focus_data = fetch_focus_selic()
        except Exception:
            focus_data = FocusSelicResult(focus_status="ERRO_API")

    focus_status = focus_data.focus_status
    focus_selic_3m = focus_data.focus_selic_3m
    focus_selic_6m = focus_data.focus_selic_6m
    focus_selic_12m = focus_data.focus_selic_12m
    focus_data_referencia = focus_data.focus_data_referencia

    # ─── 4. Deltas e Repricing ───────────────────────────────────────
    delta_focus_3m: float | None = None
    delta_focus_6m: float | None = None
    delta_focus_12m: float | None = None
    repricing_estimado_12m: float | None = None

    if cdi_12m_atual is not None:
        if focus_selic_3m is not None:
            delta_focus_3m = focus_selic_3m - cdi_12m_atual
        if focus_selic_6m is not None:
            delta_focus_6m = focus_selic_6m - cdi_12m_atual
        if focus_selic_12m is not None:
            delta_focus_12m = focus_selic_12m - cdi_12m_atual

    # Repricing = beta * delta_focus_12m
    if cdi_beta is not None and delta_focus_12m is not None:
        repricing_estimado_12m = cdi_beta * delta_focus_12m

    # ─── 5. Heurística textual ───────────────────────────────────────
    explanation_lines = _build_explanation(
        cdi_status=cdi_status,
        cdi_beta=cdi_beta,
        cdi_r_squared=cdi_r_squared,
        cdi_p_value=cdi_p_value,
        cdi_residuo_percentil=cdi_residuo_percentil,
        cdi_12m_atual=cdi_12m_atual,
        focus_status=focus_status,
        focus_selic_12m=focus_selic_12m,
        delta_focus_12m=delta_focus_12m,
        repricing_estimado_12m=repricing_estimado_12m,
    )

    return {
        "cdi_status": cdi_status,
        "cdi_beta": cdi_beta,
        "cdi_r_squared": cdi_r_squared,
        "cdi_p_value": cdi_p_value,
        "cdi_residuo_atual": cdi_residuo_atual,
        "cdi_residuo_percentil": cdi_residuo_percentil,
        "cdi_12m_atual": cdi_12m_atual,
        "focus_status": focus_status,
        "focus_selic_3m": focus_selic_3m,
        "focus_selic_6m": focus_selic_6m,
        "focus_selic_12m": focus_selic_12m,
        "focus_data_referencia": focus_data_referencia,
        "delta_focus_3m": delta_focus_3m,
        "delta_focus_6m": delta_focus_6m,
        "delta_focus_12m": delta_focus_12m,
        "repricing_estimado_12m": repricing_estimado_12m,
        "explanation_lines": explanation_lines,
    }


def _build_explanation(
    *,
    cdi_status: str,
    cdi_beta: float | None,
    cdi_r_squared: float | None,
    cdi_p_value: float | None,
    cdi_residuo_percentil: float | None,
    cdi_12m_atual: float | None,
    focus_status: str,
    focus_selic_12m: float | None,
    delta_focus_12m: float | None,
    repricing_estimado_12m: float | None,
) -> list[str]:
    """Gera linhas de explicação textual a partir dos dados macro + sensitivity.

    Heurística simples e transparente. Sem score. Combinações de:
    - beta CDI (negativo = juros sobem, P/VP desce)
    - delta Focus 12m (negativo = mercado espera queda de juros)
    - repricing estimado (impacto no P/VP)
    - resíduo percentil (ajustado ou não)
    - R² (capacidade explicativa do CDI)
    """
    lines: list[str] = []

    # Se não há sensibilidade CDI, explicar pouco
    if cdi_status != "OK" or cdi_beta is None:
        if cdi_status == "DADOS_INSUFICIENTES":
            lines.append("Dados insuficientes para regressão CDI (mínimo 104 semanas).")
        elif cdi_status == "SEM_CDI":
            lines.append("Sem dados de CDI no banco para análise de sensibilidade.")
        elif cdi_status == "CONVERGENCIA_FALHOU":
            lines.append("Regressão CDI não convergiu para este fundo.")
        else:
            lines.append("Sensibilidade CDI indisponível.")

        # Se Focus disponível, mencionar contexto
        if focus_status == "OK" and focus_selic_12m is not None and cdi_12m_atual is not None:
            direcao = "queda" if focus_selic_12m < cdi_12m_atual else "alta"
            lines.append(
                f"Focus aponta {direcao} de juros nos próximos 12 meses "
                f"(Focus 12m: {focus_selic_12m:.2%} vs CDI atual: {cdi_12m_atual:.2%})."
            )
        return lines

    # ─── Sensibilidade CDI disponível ────────────────────────────────
    # Beta negativo = juros sobe → P/VP desce (relação inversa, típico)
    # Beta positivo = juros sobe → P/VP sobe (atípico)
    beta_negativo = cdi_beta < 0

    # R² baixo = CDI explica pouco
    r2_baixo = cdi_r_squared is not None and cdi_r_squared < 0.15
    r2_alto = cdi_r_squared is not None and cdi_r_squared >= 0.30

    if r2_baixo:
        lines.append(
            f"O cenário de juros explica pouco do preço atual (R²={cdi_r_squared:.2f})."
        )

    # ─── Focus disponível ────────────────────────────────────────────
    if focus_status != "OK" or delta_focus_12m is None:
        lines.append("Focus BCB indisponível — análise limitada ao CDI histórico.")
        # Ainda podemos falar do resíduo
        if cdi_residuo_percentil is not None:
            if cdi_residuo_percentil > 75:
                lines.append(
                    f"Resíduo CDI-ajustado no percentil {cdi_residuo_percentil:.0f}% "
                    "(preço acima do esperado pelo CDI)."
                )
            elif cdi_residuo_percentil < 25:
                lines.append(
                    f"Resíduo CDI-ajustado no percentil {cdi_residuo_percentil:.0f}% "
                    "(preço abaixo do esperado pelo CDI)."
                )
        return lines

    # ─── Cenário A: Beta negativo + Focus queda = favorável ──────────
    if beta_negativo and delta_focus_12m < -0.005:
        lines.append(
            "Queda esperada de juros tende a favorecer este fundo "
            f"(beta={cdi_beta:.3f}, Focus 12m {delta_focus_12m:+.2%} vs CDI atual)."
        )
        if repricing_estimado_12m is not None and abs(repricing_estimado_12m) > 0.02:
            lines.append(
                f"Repricing estimado via CDI 12m: {repricing_estimado_12m:+.3f} no P/VP."
            )
            lines.append(
                "Parte do P/VP atual pode ser repricing racional pelo cenário de juros."
            )

    # ─── Cenário B: Beta negativo + Focus alta = desfavorável ────────
    elif beta_negativo and delta_focus_12m > 0.005:
        lines.append(
            "Cenário esperado de alta de juros tende a pressionar este fundo "
            f"(beta={cdi_beta:.3f}, Focus 12m {delta_focus_12m:+.2%} vs CDI atual)."
        )

    # ─── Cenário C: Beta positivo (atípico) ──────────────────────────
    elif not beta_negativo:
        if delta_focus_12m < -0.005:
            lines.append(
                f"Relação atípica com CDI (beta positivo={cdi_beta:.3f}). "
                "Queda de juros pode não favorecer este fundo."
            )
        elif delta_focus_12m > 0.005:
            lines.append(
                f"Relação atípica com CDI (beta positivo={cdi_beta:.3f}). "
                "Alta de juros pode não pressionar este fundo."
            )

    # ─── Resíduo elevado ─────────────────────────────────────────────
    if cdi_residuo_percentil is not None:
        if cdi_residuo_percentil > 80:
            lines.append(
                f"Mesmo ajustando por juros, o resíduo segue elevado "
                f"(percentil {cdi_residuo_percentil:.0f}%)."
            )
        elif cdi_residuo_percentil < 20:
            lines.append(
                f"Ajustando por juros, o resíduo está baixo "
                f"(percentil {cdi_residuo_percentil:.0f}%)."
            )

    # ─── R² alto + resumo ────────────────────────────────────────────
    if r2_alto and not r2_baixo:
        lines.append(
            f"CDI explica parcela relevante do P/VP (R²={cdi_r_squared:.2f})."
        )

    # Se não gerou nenhuma linha específica, pelo menos contextualizar
    if not lines:
        if abs(delta_focus_12m) < 0.005:
            lines.append(
                "Expectativa de juros pouco alterada em relação ao CDI atual."
            )
        else:
            lines.append(
                "Cenário de juros apresenta leve divergência vs CDI atual, "
                "mas impacto estimado é moderado."
            )

    return lines