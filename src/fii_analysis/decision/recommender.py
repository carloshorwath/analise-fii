"""Motor de decisao — combina os 3 modos estatisticos com flags de risco.

Tres camadas separadas semanticamente:

1. SINAL  — saida pura dos modos (BUY/SELL/NEUTRO/INDISPONIVEL).
2. RISCO  — flags de saude do fundo (destruicao de capital, emissoes,
            P/VP extremo, DY Gap baixo). Independente do sinal.
3. ACAO   — derivada (COMPRAR/VENDER/AGUARDAR/EVITAR). Risco critico
            VETA qualquer BUY mesmo com 3/3 de concordancia.

Concordancia e HEURISTICA, nao estatistica. Niveis:
    ALTA   — 3/3 modos concordam, sem flag critica
    MEDIA  — 2/3 modos concordam, sem flag critica
    BAIXA  — 1 modo isolado, ou 2+/2 com algum modo indisponivel
    VETADA — qualquer BUY com flag critica de saude

Funcoes publicas:
    decidir_ticker(ticker, session, ...)   -> TickerDecision
    decidir_universo(session, tickers=None) -> list[TickerDecision]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.decision.abertos import detectar_episodio_aberto, detectar_janela_captura
from src.fii_analysis.features.composicao import classificar_fii
from src.fii_analysis.features.momentum_signals import (
    get_dy_momentum,
    get_meses_dy_acima_cdi,
    get_pl_trend,
    get_rentab_divergencia,
)
from src.fii_analysis.features.saude import (
    emissoes_recentes,
    flag_destruicao_capital,
    get_ltv_flag,
)
from src.fii_analysis.features.valuation import (
    get_dy_gap_percentil,
    get_pvp_percentil,
    get_pvp_zscore,
)
from src.fii_analysis.features.volume_signals import (
    get_vol_ratio_21_63,
    get_volume_drop_flag,
)
from src.fii_analysis.models.episodes import get_pvp_series, identify_episodes
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2
from src.fii_analysis.models.walk_forward_rolling import walk_forward_roll


VALID_SIGNALS = ("BUY", "SELL", "NEUTRO")


@dataclass(kw_only=True)
class TickerDecision:
    """Recomendacao consolidada por ticker para um dado dia.

    Campos organizados em 5 grupos: identificacao, sinais, risco, acao, contexto.
    Estatistica historica fica em campos opcionais usados no apendice do relatorio.
    """

    # === Identificacao ===
    ticker: str
    data_referencia: date
    classificacao: Optional[str]  # Tijolo / Papel / Hibrido / None

    # === SINAIS (saida bruta dos modos) ===
    sinal_otimizador: str   # BUY/SELL/NEUTRO/INDISPONIVEL
    sinal_episodio: str     # BUY/SELL/NEUTRO/INDISPONIVEL
    sinal_walkforward: str  # BUY/SELL/NEUTRO/INDISPONIVEL

    # === RISCO (flags independentes) ===
    flag_destruicao_capital: bool
    motivo_destruicao: Optional[str]
    flag_emissao_recente: bool
    flag_pvp_caro: bool       # P/VP > p95
    flag_dy_gap_baixo: bool   # DY Gap < p5

    # === RISCO V2 (novos sinais Fase 1+2) ===
    flag_volume_queda_forte: bool = False
    vol_ratio_21_63: Optional[float] = None
    flag_ltv_alto: bool = False
    ltv_atual: Optional[float] = None
    pl_trend: Optional[str] = None
    flag_rentab_divergencia: bool = False
    rentab_div_media: Optional[float] = None
    dy_momentum: Optional[float] = None
    meses_dy_acima_cdi: Optional[int] = None
    pvp_zscore: Optional[float] = None

    # === ACAO (derivada Sinal + Risco) ===
    acao: str                 # COMPRAR / VENDER / AGUARDAR / EVITAR
    nivel_concordancia: str   # ALTA / MEDIA / BAIXA / VETADA
    n_concordam_buy: int
    n_concordam_sell: int

    # === CONTEXTO (snapshot atual) ===
    pvp_atual: Optional[float]
    pvp_percentil: Optional[float]
    dy_gap_percentil: Optional[float]
    preco_referencia: Optional[float]

    # === ESTATISTICA HISTORICA (apendice) ===
    n_episodios_buy: int = 0
    win_rate_buy: Optional[float] = None
    retorno_medio_buy: Optional[float] = None
    drawdown_tipico_buy: Optional[float] = None  # pior fwd_ret entre BUYs (descritivo)
    p_value_wf_buy: Optional[float] = None
    n_steps_wf: int = 0

    # === CDI SENSITIVITY (diagnóstico, NÃO altera ação) ===
    cdi_status: Optional[str] = None
    cdi_beta: Optional[float] = None
    cdi_r_squared: Optional[float] = None
    cdi_p_value: Optional[float] = None
    cdi_residuo_atual: Optional[float] = None
    cdi_residuo_percentil: Optional[float] = None

    # === CDI + FOCUS (contexto macro, NÃO altera ação) ===
    cdi_delta_focus_12m: Optional[float] = None
    cdi_repricing_12m: Optional[float] = None

    # === JANELAS ABERTAS HOJE (pontos de trade adicionais) ===
    # Episodio P/VP extremo ja distinto de continuacao
    episodio_eh_novo: Optional[bool] = None       # True se gap >= forward_days
    pregoes_desde_ultimo_episodio: Optional[int] = None
    # Captura de dividendo: estimativa pela mediana historica
    janela_captura_aberta: bool = False
    proxima_data_com_estimada: Optional[date] = None
    dias_ate_proxima_data_com: Optional[int] = None

    # === Auditoria ===
    rationale: list[str] = field(default_factory=list)

    @property
    def has_critical_flag(self) -> bool:
        """Flag critica = veta qualquer COMPRAR mesmo com 3/3 concordancia.

        Hoje so destruicao de capital eh veto absoluto. DY Gap baixo e P/VP caro
        sao informativos (entram no rationale, nao vetam).
        """
        return self.flag_destruicao_capital


# =============================================================================
# Helpers internos
# =============================================================================


def _sinal_episodio_atual(pvp_pct_atual: Optional[float],
                          pvp_pct_low: float = 10.0,
                          pvp_pct_high: float = 90.0) -> str:
    """Estado atual do P/VP percentil → sinal de episódio aberto agora."""
    if pvp_pct_atual is None or pd.isna(pvp_pct_atual):
        return "INDISPONIVEL"
    if pvp_pct_atual <= pvp_pct_low:
        return "BUY"
    if pvp_pct_atual >= pvp_pct_high:
        return "SELL"
    return "NEUTRO"


def _derivar_acao(n_buy: int, n_sell: int, n_validos: int,
                  has_critical: bool) -> tuple[str, str]:
    """Regra de combinacao Sinal -> Acao + nivel de concordancia heuristico.

    Veto absoluto: BUY com flag critica → EVITAR/VETADA.
    """
    if has_critical and n_buy > 0:
        return "EVITAR", "VETADA"

    if n_validos == 0:
        return "AGUARDAR", "BAIXA"

    # Concordancia forte
    if n_buy == 3:
        return "COMPRAR", "ALTA"
    if n_sell == 3:
        return "VENDER", "ALTA"

    # Concordancia media — 2 modos concordando
    if n_buy >= 2:
        return "COMPRAR", "MEDIA"
    if n_sell >= 2:
        return "VENDER", "MEDIA"

    # Concordancia baixa — sinal isolado
    if n_buy == 1 or n_sell == 1:
        return "AGUARDAR", "BAIXA"

    # Tudo neutro
    return "AGUARDAR", "BAIXA"


def _decisao_indisponivel(ticker: str, motivo: str,
                          data_ref: Optional[date] = None) -> TickerDecision:
    """Constroi TickerDecision quando nao conseguimos avaliar o ticker."""
    return TickerDecision(
        ticker=ticker,
        data_referencia=data_ref or date.today(),
        classificacao=None,
        sinal_otimizador="INDISPONIVEL",
        sinal_episodio="INDISPONIVEL",
        sinal_walkforward="INDISPONIVEL",
        flag_destruicao_capital=False,
        motivo_destruicao=None,
        flag_emissao_recente=False,
        flag_pvp_caro=False,
        flag_dy_gap_baixo=False,
        acao="AGUARDAR",
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=None,
        pvp_percentil=None,
        dy_gap_percentil=None,
        preco_referencia=None,
        rationale=[motivo],
    )


# =============================================================================
# API publica
# =============================================================================


def decidir_ticker(
    ticker: str,
    session,
    optimizer_params: Optional[dict] = None,
    *,
    cdi_sensitivity: Optional[dict] = None,
    focus_explanation: Optional[dict] = None,
    forward_days: int = 20,
    pvp_pct_low: float = 10.0,
    pvp_pct_high: float = 90.0,
) -> TickerDecision:
    """Avalia um ticker e devolve TickerDecision com Sinal/Acao/Risco.

    Parameters
    ----------
    ticker : str
    session : SQLAlchemy session
    optimizer_params : dict, optional
        Resultado de ThresholdOptimizerV2.optimize()["best_params"]. Se None,
        o sinal do otimizador fica como INDISPONIVEL (concordancia perde 1
        modo, mas a logica de veto e os outros 2 modos continuam funcionando).
    cdi_sensitivity : dict, optional
        Resultado de compute_cdi_sensitivity() serializado como dict.
        NÃO altera a ação final — é puramente diagnóstico.
    focus_explanation : dict, optional
        Resultado de build_cdi_focus_explanation().
        Preenche cdi_delta_focus_12m, cdi_repricing_12m e rationale.
        NÃO altera a ação final — é puramente informativo.
    forward_days : int
        Janela de retorno forward para episodios (default 20 pregoes).
    pvp_pct_low / pvp_pct_high : float
        Percentis para episodio BUY (low) e SELL (high). Default 10 / 90.
    """
    rationale: list[str] = []

    # -------------------------------------------------------------------------
    # 1. P/VP serie + estado atual
    # -------------------------------------------------------------------------
    df_pvp = get_pvp_series(ticker, session)
    if df_pvp.empty:
        return _decisao_indisponivel(ticker, "sem dados de P/VP")

    ult = df_pvp.iloc[-1]
    data_ref_raw = ult["data"]
    data_ref: date = (
        data_ref_raw.date() if hasattr(data_ref_raw, "date") else data_ref_raw
    )
    pvp_pct_atual = float(ult["pvp_pct"]) if pd.notna(ult["pvp_pct"]) else None
    pvp_atual = float(ult["pvp"]) if pd.notna(ult["pvp"]) else None
    preco_ref = float(ult["fechamento"]) if pd.notna(ult["fechamento"]) else None

    # -------------------------------------------------------------------------
    # 2. Sinal Otimizador
    # -------------------------------------------------------------------------
    if optimizer_params:
        try:
            opt = ThresholdOptimizerV2()
            res_opt = opt.get_signal_hoje(ticker, session, optimizer_params)
            sinal_otimizador = res_opt.get("sinal", "NEUTRO")
            if sinal_otimizador not in VALID_SIGNALS:
                sinal_otimizador = "INDISPONIVEL"
                rationale.append(f"Otimizador: {res_opt.get('details', 'sinal invalido')}")
        except Exception as exc:
            sinal_otimizador = "INDISPONIVEL"
            rationale.append(f"Otimizador erro: {exc}")
    else:
        sinal_otimizador = "INDISPONIVEL"
        rationale.append("Otimizador sem params (rode optimize() antes)")

    # -------------------------------------------------------------------------
    # 3. Sinal Episodios — estado atual + estatistica historica
    # -------------------------------------------------------------------------
    sinal_episodio = _sinal_episodio_atual(pvp_pct_atual, pvp_pct_low, pvp_pct_high)

    n_buy_hist = 0
    win_rate_buy = None
    retorno_medio_buy = None
    drawdown_tipico_buy = None
    try:
        eps = identify_episodes(
            df_pvp,
            pvp_pct_low=pvp_pct_low,
            pvp_pct_high=pvp_pct_high,
            forward_days=forward_days,
        )
        eps_buy_summary = eps["summary"]["buy"]
        n_buy_hist = int(eps_buy_summary.get("n", 0) or 0)
        win_rate_buy = eps_buy_summary.get("win_rate")
        retorno_medio_buy = eps_buy_summary.get("mean")
        drawdown_tipico_buy = eps_buy_summary.get("min")  # pior fwd_ret entre BUYs
    except Exception as exc:
        rationale.append(f"Episodios estatistica erro: {exc}")

    # -------------------------------------------------------------------------
    # 4. Sinal Walk-Forward — ultimo step
    # -------------------------------------------------------------------------
    sinal_wf = "INDISPONIVEL"
    p_value_wf_buy: Optional[float] = None
    n_steps_wf = 0
    try:
        wf = walk_forward_roll(ticker, session, forward_days=forward_days)
        if "error" in wf:
            rationale.append(f"WalkForward: {wf['error']}")
        else:
            sigs: pd.DataFrame = wf["signals"]
            if not sigs.empty:
                ultimo = sigs.iloc[-1]
                sig_raw = str(ultimo.get("signal", "NEUTRO")).upper()
                sinal_wf = sig_raw if sig_raw in VALID_SIGNALS else "NEUTRO"
                n_steps_wf = int(wf.get("n_steps", 0) or 0)
            p_value_wf_buy = wf.get("summary", {}).get("BUY", {}).get("p_value")
    except Exception as exc:
        rationale.append(f"WalkForward erro: {exc}")

    # -------------------------------------------------------------------------
    # 5. Flags de risco
    # -------------------------------------------------------------------------
    flag_destr = False
    motivo_destr: Optional[str] = None
    try:
        destr = flag_destruicao_capital(ticker, session)
        flag_destr = bool(destr.get("destruicao", False))
        motivo_destr = destr.get("motivo")
    except Exception as exc:
        rationale.append(f"Destruicao capital erro: {exc}")

    flag_emiss = False
    try:
        emiss = emissoes_recentes(ticker, session=session)
        flag_emiss = bool(emiss)
    except Exception as exc:
        rationale.append(f"Emissoes erro: {exc}")

    flag_pvp_caro = False
    try:
        pvp_pct_risk, _ = get_pvp_percentil(ticker, data_ref, 504, session)
        flag_pvp_caro = pvp_pct_risk is not None and pvp_pct_risk > 95
    except Exception as exc:
        rationale.append(f"P/VP percentil erro: {exc}")

    flag_dy_baixo = False
    dy_gap_pct: Optional[float] = None
    try:
        dy_gap_pct = get_dy_gap_percentil(ticker, data_ref, 504, session)
        flag_dy_baixo = dy_gap_pct is not None and dy_gap_pct < 5
    except Exception as exc:
        rationale.append(f"DY Gap erro: {exc}")

    # --- Sinais V2: volume, LTV, momentum fundamentalista ---
    flag_vol_drop = False
    vol_ratio = None
    try:
        flag_vol_drop = get_volume_drop_flag(ticker, data_ref, session)
        vol_ratio = get_vol_ratio_21_63(ticker, data_ref, session)
        if flag_vol_drop:
            rationale.append('Volume qualificado: queda com volume alto (pressao vendedora real)')
        if vol_ratio is not None and vol_ratio < 0.70:
            rationale.append(f'Liquidez caindo: vol_ratio_21_63={vol_ratio:.2f}')
    except Exception as exc:
        rationale.append(f'Volume signals erro: {exc}')

    flag_ltv = False
    ltv_val = None
    try:
        flag_ltv, ltv_val = get_ltv_flag(ticker, data_ref, session)
        if flag_ltv:
            rationale.append(f'LTV alto: {ltv_val:.1%} (alavancagem > 20%)')
    except Exception as exc:
        rationale.append(f'LTV erro: {exc}')

    pl_trend_val = None
    try:
        pl_trend_val = get_pl_trend(ticker, data_ref, session)
        if pl_trend_val == 'CAINDO':
            rationale.append('PL em queda 3 meses consecutivos')
    except Exception as exc:
        rationale.append(f'PL trend erro: {exc}')

    flag_rentab_div = False
    rentab_div_val = None
    try:
        flag_rentab_div, rentab_div_val = get_rentab_divergencia(ticker, data_ref, session)
        if flag_rentab_div:
            rationale.append('Rentab efetiva sistematicamente acima da patrimonial (armadilha de dividendo)')
    except Exception as exc:
        rationale.append(f'Rentab divergencia erro: {exc}')

    dy_mom = None
    meses_dy_cdi = None
    pvp_z = None
    try:
        dy_mom = get_dy_momentum(ticker, data_ref, session)
        meses_dy_cdi = get_meses_dy_acima_cdi(ticker, data_ref, session)
        pvp_z = get_pvp_zscore(ticker, data_ref, session)
    except Exception as exc:
        rationale.append(f'Sinais fundamentalistas erro: {exc}')

    # -------------------------------------------------------------------------
    # 6. Combinacao Sinal -> Acao (com veto)
    # -------------------------------------------------------------------------
    sinais = [sinal_otimizador, sinal_episodio, sinal_wf]
    sinais_validos = [s for s in sinais if s in VALID_SIGNALS]
    n_buy = sum(1 for s in sinais_validos if s == "BUY")
    n_sell = sum(1 for s in sinais_validos if s == "SELL")

    has_critical = flag_destr or (flag_vol_drop and n_buy > 0)  # veto absoluto
    acao, nivel = _derivar_acao(n_buy, n_sell, len(sinais_validos), has_critical)

    if flag_destr and n_buy > 0:
        rationale.append(f"VETO: BUY presente mas destruicao de capital ({motivo_destr})")
    if flag_vol_drop and n_buy > 0:
        rationale.append('VETO: BUY presente mas queda com volume alto detectada')
    if flag_dy_baixo and acao == "COMPRAR":
        rationale.append("Atencao: DY Gap < p5 (DY baixo vs CDI) na entrada COMPRAR")
    if flag_emiss:
        rationale.append("Atencao: emissoes recentes (>1%) — diluicao possivel")

    # -------------------------------------------------------------------------
    # 7. Janelas abertas hoje (pontos de trade adicionais)
    # -------------------------------------------------------------------------
    episodio_novo: Optional[bool] = None
    pregoes_desde: Optional[int] = None
    try:
        ep_aberto = detectar_episodio_aberto(
            df_pvp, forward_days=forward_days,
            pvp_pct_low=pvp_pct_low, pvp_pct_high=pvp_pct_high,
        )
        if ep_aberto["aberto"]:
            episodio_novo = bool(ep_aberto["novo_evento"])
            pregoes_desde = ep_aberto["pregoes_desde_ultimo"]
            if not episodio_novo and pregoes_desde is not None:
                rationale.append(
                    f"Episodio em CONTINUACAO ({pregoes_desde} pregoes desde ultimo) — "
                    "nao e ponto de entrada novo."
                )
    except Exception as exc:
        rationale.append(f"Detector episodio aberto erro: {exc}")

    janela_captura_aberta = False
    proxima_dc: Optional[date] = None
    dias_ate_dc: Optional[int] = None
    try:
        jc = detectar_janela_captura(ticker, session, hoje=data_ref)
        janela_captura_aberta = bool(jc["aberta"])
        proxima_dc = jc["proxima_data_com_estimada"]
        dias_ate_dc = jc["dias_corridos_ate"]
        if janela_captura_aberta:
            rationale.append(
                f"Janela de captura aberta: proxima data-com estimada em "
                f"{dias_ate_dc} dias ({proxima_dc.isoformat() if proxima_dc else '?'})"
            )
    except Exception as exc:
        rationale.append(f"Detector janela captura erro: {exc}")

    # -------------------------------------------------------------------------
    # 8. CDI Sensitivity (diagnóstico — NÃO altera ação)
    # -------------------------------------------------------------------------
    cdi_status_val = None
    cdi_beta_val = None
    cdi_r_squared_val = None
    cdi_p_value_val = None
    cdi_residuo_atual_val = None
    cdi_residuo_percentil_val = None

    if cdi_sensitivity is not None:
        cdi_status_val = cdi_sensitivity.get("cdi_status")
        cdi_beta_val = cdi_sensitivity.get("cdi_beta")
        cdi_r_squared_val = cdi_sensitivity.get("cdi_r_squared")
        cdi_p_value_val = cdi_sensitivity.get("cdi_p_value")
        cdi_residuo_atual_val = cdi_sensitivity.get("cdi_residuo_atual")
        cdi_residuo_percentil_val = cdi_sensitivity.get("cdi_residuo_percentil")

        if cdi_status_val == "OK":
            parts = []
            if cdi_beta_val is not None:
                parts.append(f"beta={cdi_beta_val:.4f}")
            if cdi_r_squared_val is not None:
                parts.append(f"R2={cdi_r_squared_val:.3f}")
            if cdi_p_value_val is not None:
                parts.append(f"p={cdi_p_value_val:.4f}")
            if cdi_residuo_percentil_val is not None:
                parts.append(f"residuo pct={cdi_residuo_percentil_val:.1f}")
            rationale.append(f"CDI-ajustado: {' | '.join(parts)}")

    # -------------------------------------------------------------------------
    # 8b. Focus CDI (contexto macro — NÃO altera ação)
    # -------------------------------------------------------------------------
    cdi_delta_focus_12m_val: Optional[float] = None
    cdi_repricing_12m_val: Optional[float] = None

    if focus_explanation is not None:
        cdi_delta_focus_12m_val = focus_explanation.get("delta_focus_12m")
        cdi_repricing_12m_val = focus_explanation.get("repricing_estimado_12m")

        cdi_12m = focus_explanation.get("cdi_12m_atual")
        f3 = focus_explanation.get("focus_selic_3m")
        f6 = focus_explanation.get("focus_selic_6m")
        f12 = focus_explanation.get("focus_selic_12m")
        focus_parts = []
        if cdi_12m is not None:
            focus_parts.append(f"CDI 12m atual={cdi_12m:.2%}")
        if f3 is not None:
            focus_parts.append(f"Focus 3m={f3:.2%}")
        if f6 is not None:
            focus_parts.append(f"Focus 6m={f6:.2%}")
        if f12 is not None:
            focus_parts.append(f"Focus 12m={f12:.2%}")
        if focus_parts:
            rationale.append(" | ".join(focus_parts))

        if cdi_delta_focus_12m_val is not None:
            rationale.append(f"Delta Focus 12m={cdi_delta_focus_12m_val:+.2%}")
        if cdi_repricing_12m_val is not None:
            rationale.append(f"Repricing estimado via CDI 12m: {cdi_repricing_12m_val:+.3f} no P/VP")

        for line in focus_explanation.get("explanation_lines", []):
            rationale.append(f"Leitura macro: {line}")

    # -------------------------------------------------------------------------
    # 9. Classificacao
    # -------------------------------------------------------------------------
    try:
        classif = classificar_fii(ticker, session)
    except Exception:
        classif = None

    return TickerDecision(
        ticker=ticker,
        data_referencia=data_ref,
        classificacao=classif,
        sinal_otimizador=sinal_otimizador,
        sinal_episodio=sinal_episodio,
        sinal_walkforward=sinal_wf,
        flag_destruicao_capital=flag_destr,
        motivo_destruicao=motivo_destr,
        flag_emissao_recente=flag_emiss,
        flag_pvp_caro=flag_pvp_caro,
        flag_dy_gap_baixo=flag_dy_baixo,
        flag_volume_queda_forte=flag_vol_drop,
        vol_ratio_21_63=vol_ratio,
        flag_ltv_alto=flag_ltv,
        ltv_atual=ltv_val,
        pl_trend=pl_trend_val,
        flag_rentab_divergencia=flag_rentab_div,
        rentab_div_media=rentab_div_val,
        dy_momentum=dy_mom,
        meses_dy_acima_cdi=meses_dy_cdi,
        pvp_zscore=pvp_z,
        acao=acao,
        nivel_concordancia=nivel,
        n_concordam_buy=n_buy,
        n_concordam_sell=n_sell,
        pvp_atual=pvp_atual,
        pvp_percentil=pvp_pct_atual,
        dy_gap_percentil=dy_gap_pct,
        preco_referencia=preco_ref,
        n_episodios_buy=n_buy_hist,
        win_rate_buy=win_rate_buy,
        retorno_medio_buy=retorno_medio_buy,
        drawdown_tipico_buy=drawdown_tipico_buy,
        p_value_wf_buy=p_value_wf_buy,
        n_steps_wf=n_steps_wf,
        episodio_eh_novo=episodio_novo,
        pregoes_desde_ultimo_episodio=pregoes_desde,
        janela_captura_aberta=janela_captura_aberta,
        proxima_data_com_estimada=proxima_dc,
        dias_ate_proxima_data_com=dias_ate_dc,
        cdi_status=cdi_status_val,
        cdi_beta=cdi_beta_val,
        cdi_r_squared=cdi_r_squared_val,
        cdi_p_value=cdi_p_value_val,
        cdi_residuo_atual=cdi_residuo_atual_val,
        cdi_residuo_percentil=cdi_residuo_percentil_val,
        cdi_delta_focus_12m=cdi_delta_focus_12m_val,
        cdi_repricing_12m=cdi_repricing_12m_val,
        rationale=rationale,
    )


def decidir_universo(
    session,
    tickers: Optional[list[str]] = None,
    optimizer_params_por_ticker: Optional[dict[str, dict]] = None,
    *,
    cdi_sensitivity_por_ticker: Optional[dict[str, dict]] = None,
    focus_explanation_por_ticker: Optional[dict[str, dict]] = None,
    forward_days: int = 20,
) -> list[TickerDecision]:
    """Aplica decidir_ticker em todos os tickers ativos (ou lista informada).

    Parameters
    ----------
    optimizer_params_por_ticker : dict[ticker, params], optional
        Mapa de params do otimizador por ticker. Se None ou ticker ausente,
        sinal do otimizador fica INDISPONIVEL.
    cdi_sensitivity_por_ticker : dict[ticker, dict], optional
        Mapa de resultado CDI sensitivity por ticker. Se None ou ticker
        ausente, campos CDI ficam com valor default (None).
    focus_explanation_por_ticker : dict[ticker, dict], optional
        Mapa de resultado build_cdi_focus_explanation() por ticker.
        NÃO altera a ação final — é puramente informativo.
    """
    if tickers is None:
        tickers = tickers_ativos(session)

    params_map = optimizer_params_por_ticker or {}
    cdi_map = cdi_sensitivity_por_ticker or {}
    focus_map = focus_explanation_por_ticker or {}
    decisoes: list[TickerDecision] = []
    for ticker in tickers:
        params = params_map.get(ticker)
        cdi = cdi_map.get(ticker)
        focus = focus_map.get(ticker)
        try:
            d = decidir_ticker(ticker, session, optimizer_params=params,
                               cdi_sensitivity=cdi,
                               focus_explanation=focus,
                               forward_days=forward_days)
        except Exception as exc:
            d = _decisao_indisponivel(ticker, f"erro inesperado: {exc}")
        decisoes.append(d)

    return decisoes
