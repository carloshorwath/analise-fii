"""Motor de decisao — combina os 3 modos estatisticos com flags de risco.

Tres camadas separadas semanticamente:

1. SINAL  — saida pura dos modos (BUY/SELL/NEUTRO/INDISPONIVEL).
2. RISCO  — flags de saude do fundo (destruicao de capital, emissoes,
            P/VP extremo, DY Gap baixo). Independente do sinal.
3. ACAO   — derivada (COMPRAR/VENDER/AGUARDAR). Flags de risco sao ALERTAS
            descritivos no rationale: NAO vetam nem geram acao (estudo em painel
            2026-11-12: sem evidencia de que antecipem retorno pior; ver evidencia.py).

Concordancia e HEURISTICA, nao estatistica. Um sinal so entra no voto se tiver
suporte estatistico (n de eventos independentes fora da amostra e p-valor
corrigido; ver decision/suporte.py) — sinal sem suporte e gravado e exibido como
informativo, mas nao conta. Niveis:
    ALTA   — 3/3 modos concordam
    MEDIA  — 2/3 modos concordam
    BAIXA  — 1 modo isolado, ou 2+/2 com algum modo indisponivel
(``EVITAR`` / ``VETADA`` nao sao mais produzidos; existem so em snapshots antigos.)

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
from src.fii_analysis.decision.elegibilidade import data_referencia_mercado, motivo_bloqueio_compra
from src.fii_analysis.decision.evidencia import linha_evidencia
from src.fii_analysis.decision.suporte import (
    aplicar_fdr,
    conta_no_voto,
    evidencia_episodio,
    evidencia_otimizador,
    evidencia_walkforward,
    linhas_rationale,
)
from src.fii_analysis.features.composicao import classificar_fii
from src.fii_analysis.features.momentum_signals import (
    get_dividend_safety,
    get_dy_momentum,
    get_meses_dy_acima_cdi,
    get_momentum_relativo_ifix,
    get_pl_trend,
    get_rentab_divergencia,
)
from src.fii_analysis.features.saude import (
    emissoes_recentes,
    flag_destruicao_capital,
    get_ltv_flag,
)
from src.fii_analysis.features.valuation import (
    get_cap_rate_spread,
    get_dy_gap_percentil,
    get_pvp_percentil,
    get_pvp_zscore,
)
from src.fii_analysis.features.volume_signals import (
    get_vol_ratio_21_63,
    get_volume_drop_flag,
)
from src.fii_analysis.models.episodes import get_pvp_series, identify_episodes
from src.fii_analysis.models.threshold_optimizer_v2 import ThresholdOptimizerV2, load_optimizer_cache_stats
from src.fii_analysis.models.walk_forward_rolling import walk_forward_roll


VALID_SIGNALS = ("BUY", "SELL", "NEUTRO")

# Janelas dos percentis EXIBIDOS/gravados na decisao e usados nos flags.
# Devem ser iguais as de evaluation/daily_snapshots.build_snapshot_ticker_metrics
# (get_pvp_percentil(..., 504, ...) e get_dy_gap_percentil(..., 252, ...)), para
# o mesmo run nao mostrar dois numeros diferentes para a mesma metrica.
JANELA_PVP_PERCENTIL = 504
JANELA_DY_GAP_PERCENTIL = 252


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

    # === RISCO F3 (sinais Fase 3) ===
    momentum_ifix_21d: Optional[float] = None       # retorno_fii - retorno_ifix (pp, 21d)
    cap_rate_anualizado: Optional[float] = None     # (1 + rentab_efetiva_6m)^12 - 1
    cap_rate_spread_cdi: Optional[float] = None     # cap_rate - CDI 12m
    dividend_safety_flag: bool = False              # payout > 110% do que ganha
    payout_vs_caixa: Optional[float] = None        # dy_mes / rentab_efetiva medio
    cortes_24m: int = 0                            # quedas consecutivas de DY nos 24m

    # === ACAO (derivada Sinal + Risco) ===
    acao: str                 # COMPRAR / VENDER / AGUARDAR (EVITAR so em snapshots antigos)
    nivel_concordancia: str   # ALTA / MEDIA / BAIXA (VETADA so em snapshots antigos)
    n_concordam_buy: int
    n_concordam_sell: int

    # === CONTEXTO (snapshot atual) ===
    pvp_atual: Optional[float]
    pvp_percentil: Optional[float]
    dy_gap_percentil: Optional[float]
    preco_referencia: Optional[float]
    score_total: Optional[int] = None

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

    # === Suporte estatistico dos sinais (so quem tem suporte vota) ===
    # {"otimizador"|"episodio"|"walkforward": {sinal, status, n, p, motivo}}
    suporte_sinais: dict = field(default_factory=dict)

    # === Elegibilidade de compra ===
    # Motivo textual se o ticker nao pode receber COMPRAR/AUMENTAR/candidato
    # (fundo em liquidacao/encerrado, preco desatualizado). None = elegivel.
    bloqueio_compra: Optional[str] = None

    # === Auditoria ===
    rationale: list[str] = field(default_factory=list)

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


def _derivar_acao(n_buy: int, n_sell: int, n_validos: int) -> tuple[str, str]:
    """Regra de combinacao Sinal -> Acao + nivel de concordancia heuristico.

    Sem veto por flag de risco: a flag vira alerta no rationale (ver _finalizar_votos).
    """
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
    **kwargs,
) -> TickerDecision:
    """Decisao de UM ticker (chamada avulsa).

    A familia do ajuste Benjamini-Hochberg e o conjunto dos sinais BUY/SELL
    ativos DESTE ticker (<= 3). Para a familia da rodada inteira use
    ``decidir_universo``. Parametros: ver ``_decidir_ticker_base``.
    """
    d = _decidir_ticker_base(ticker, session, optimizer_params, **kwargs)
    _finalizar_votos([d])
    return d


def _decidir_ticker_base(
    ticker: str,
    session,
    optimizer_params: Optional[dict] = None,
    *,
    cdi_sensitivity: Optional[dict] = None,
    focus_explanation: Optional[dict] = None,
    forward_days: int = 20,
    pvp_pct_low: float = 10.0,
    pvp_pct_high: float = 90.0,
    optimizer_stats: Optional[dict] = None,
    data_ref_mercado: Optional[date] = None,
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
    optimizer_stats : dict, optional
        Estatisticas de teste do otimizador (extrair_stats_otimizador). Se None,
        tenta o cache em dados/optimizer_cache (so se best_params coincidir);
        ausentes => sinal do otimizador sem suporte (nao vota).
    data_ref_mercado : date, optional
        Data de referencia do mercado/snapshot para elegibilidade de compra
        (liquidacao vigente, preco desatualizado). Default: ultima data com
        preco no banco.
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
    # Percentil INTERNO do modelo de episodios (so gera sinal_episodio); janela
    # ate t-1, mesma definicao de valuation.get_pvp_percentil.
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

    eps_summary: Optional[dict] = None
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
        eps_summary = eps["summary"]
        eps_buy_summary = eps["summary"]["buy"]
        n_buy_hist = int(eps_buy_summary.get("n", 0) or 0)
        win_rate_buy = eps_buy_summary.get("win_rate")
        retorno_medio_buy = eps_buy_summary.get("mean")
        drawdown_tipico_buy = eps_buy_summary.get("min")  # pior fwd_ret entre BUYs
    except Exception as exc:
        rationale.append(f"Episodios estatistica erro: {exc}")

    # -------------------------------------------------------------------------
    # 4. Sinal Walk-Forward — sinal_hoje (extrapolado) com fallback ao ultimo OOS
    # -------------------------------------------------------------------------
    sinal_wf = "INDISPONIVEL"
    p_value_wf_buy: Optional[float] = None
    n_steps_wf = 0
    wf_summary: Optional[dict] = None
    try:
        wf = walk_forward_roll(ticker, session, forward_days=forward_days)
        if "error" in wf:
            rationale.append(f"WalkForward: {wf['error']}")
        else:
            n_steps_wf = int(wf.get("n_steps", 0) or 0)
            wf_summary = wf.get("summary")
            p_value_wf_buy = wf.get("summary", {}).get("BUY", {}).get("p_value")
            # Preferir sinal_hoje (extrapolado do threshold mais recente) sobre ultimo OOS
            sh = wf.get("sinal_hoje", {})
            sh_sinal = sh.get("sinal", "INDISPONIVEL")
            if sh_sinal in VALID_SIGNALS:
                sinal_wf = sh_sinal
                data_ult = sh.get("data_ultimo_sinal_oos")
                if data_ult:
                    rationale.append(f"WalkForward extrapolado (ultimo OOS: {data_ult}): {sinal_wf}")
            else:
                # Fallback: último sinal OOS da série
                sigs: pd.DataFrame = wf["signals"]
                if not sigs.empty:
                    ultimo_oos = sigs.iloc[-1]
                    sig_raw = str(ultimo_oos.get("signal", "NEUTRO")).upper()
                    sinal_wf = sig_raw if sig_raw in VALID_SIGNALS else "NEUTRO"
    except Exception as exc:
        rationale.append(f"WalkForward erro: {exc}")

    # -------------------------------------------------------------------------
    # 5. Flags de risco
    # -------------------------------------------------------------------------
    flag_destr = False
    motivo_destr: Optional[str] = None
    gravidade_destr: Optional[str] = None
    try:
        destr = flag_destruicao_capital(ticker, session, t=data_ref)
        flag_destr = bool(destr.get("destruicao", False))
        motivo_destr = destr.get("motivo")
        gravidade_destr = destr.get("gravidade")
        tendencia_destr = destr.get("tendencia", "")
        score_destr = destr.get("score_destruicao", 0)
        score_saude = destr.get("score_saude", 50)
        if gravidade_destr == "em_recuperacao":
            rationale.append(
                f"Saude: EM RECUPERACAO (score {score_saude}/100, {tendencia_destr}) — "
                f"gestao revertendo destruicao. {motivo_destr}"
            )
        elif gravidade_destr == "alerta":
            rationale.append(
                f"Saude: ALERTA destruicao capital (score {score_saude}/100, {tendencia_destr}) — {motivo_destr}"
            )
        elif gravidade_destr == "critica":
            rationale.append(
                f"Saude: CRITICA destruicao capital (score {score_saude}/100, {tendencia_destr}) — {motivo_destr}"
            )
    except Exception as exc:
        rationale.append(f"Destruicao capital erro: {exc}")

    flag_emiss = False
    try:
        emiss = emissoes_recentes(ticker, session=session, t=data_ref)
        flag_emiss = bool(emiss)
    except Exception as exc:
        rationale.append(f"Emissoes erro: {exc}")

    # Percentis EXIBIDOS/gravados = metrica do snapshot; flags usam os mesmos numeros.
    flag_pvp_caro = False
    pvp_pct_exibido: Optional[float] = None
    try:
        pvp_pct_exibido, _ = get_pvp_percentil(ticker, data_ref, JANELA_PVP_PERCENTIL, session)
        flag_pvp_caro = pvp_pct_exibido is not None and pvp_pct_exibido > 95
    except Exception as exc:
        rationale.append(f"P/VP percentil erro: {exc}")

    flag_dy_baixo = False
    dy_gap_pct: Optional[float] = None
    try:
        dy_gap_pct = get_dy_gap_percentil(ticker, data_ref, JANELA_DY_GAP_PERCENTIL, session)
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
            rationale.append(f'Rentab efetiva - patrimonial medio {rentab_div_val:+.2f} p.p./mes (= rendimento distribuido; nao indica distribuicao acima da geracao)')
    except Exception as exc:
        rationale.append(f'Rentab divergencia erro: {exc}')

    dy_mom = None
    meses_dy_cdi = None
    pvp_z = None
    try:
        dy_mom = get_dy_momentum(ticker, data_ref, session)
        meses_dy_cdi = get_meses_dy_acima_cdi(ticker, data_ref, session)
        pvp_z = get_pvp_zscore(ticker, data_ref, session=session)
    except Exception as exc:
        rationale.append(f'Sinais fundamentalistas erro: {exc}')

    # --- F3: momentum relativo IFIX, Cap Rate spread, Dividend Safety ---
    mom_ifix: Optional[float] = None
    cap_rate_anual: Optional[float] = None
    cap_rate_spread: Optional[float] = None
    div_safety_flag = False
    payout_caixa: Optional[float] = None
    cortes_dy = 0
    try:
        mom_ifix = get_momentum_relativo_ifix(ticker, data_ref, session)
    except Exception as exc:
        rationale.append(f'Momentum IFIX erro: {exc}')
    try:
        cap_rate_anual, cap_rate_spread = get_cap_rate_spread(ticker, data_ref, session)
        if cap_rate_spread is not None and cap_rate_spread < 0:
            rationale.append(f'Alerta: Cap Rate spread negativo ({cap_rate_spread:.2%}) — fundo rende menos que CDI')
    except Exception as exc:
        rationale.append(f'Cap Rate spread erro: {exc}')
    try:
        safety = get_dividend_safety(ticker, data_ref, session)
        div_safety_flag = safety.get('flag_insustentavel', False)
        payout_caixa = safety.get('payout_vs_caixa')
        cortes_dy = safety.get('cortes_24m', 0)
        if div_safety_flag:
            rationale.append(f'Alerta: Dividendo insustentavel — payout {payout_caixa:.0%} do resultado' if payout_caixa else 'Alerta: Dividendo possivelmente insustentavel')
        if cortes_dy >= 4:
            rationale.append(f'Atencao: {cortes_dy} cortes de DY nos ultimos 24 meses')
    except Exception as exc:
        rationale.append(f'Dividend Safety erro: {exc}')

    # -------------------------------------------------------------------------
    # 6. Evidencia por sinal (Sinal -> Acao com veto e BH: _finalizar_votos)
    # -------------------------------------------------------------------------
    # Evidencia estatistica bruta por sinal (excesso sobre a deriva). A correcao
    # BH e o voto/acao sao resolvidos em _finalizar_votos() sobre a familia da rodada.
    opt_stats = optimizer_stats
    if opt_stats is None and optimizer_params:
        try:
            opt_stats = load_optimizer_cache_stats(ticker, best_params=optimizer_params)
        except Exception as exc:
            rationale.append(f"Otimizador stats erro: {exc}")
    suporte_sinais = {
        "otimizador": evidencia_otimizador(sinal_otimizador, opt_stats),
        "episodio": evidencia_episodio(sinal_episodio, eps_summary),
        "walkforward": evidencia_walkforward(sinal_wf, wf_summary),
    }

    # Elegibilidade de compra: liquidacao/encerramento vigente ou preco defasado
    bloqueio_compra: Optional[str] = None
    try:
        ref_mercado = data_ref_mercado or data_referencia_mercado(session) or data_ref
        bloqueio_compra = motivo_bloqueio_compra(ticker, ref_mercado, session)
    except Exception as exc:
        rationale.append(f"Elegibilidade de compra erro: {exc}")

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
            if pregoes_desde is not None:
                pregoes_desde = int(pregoes_desde)  # numpy.int64 viraria BLOB no SQLite
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
        momentum_ifix_21d=mom_ifix,
        cap_rate_anualizado=cap_rate_anual,
        cap_rate_spread_cdi=cap_rate_spread,
        dividend_safety_flag=div_safety_flag,
        payout_vs_caixa=payout_caixa,
        cortes_24m=cortes_dy,
        acao="AGUARDAR",          # provisorios: _finalizar_votos() define
        nivel_concordancia="BAIXA",
        n_concordam_buy=0,
        n_concordam_sell=0,
        pvp_atual=pvp_atual,
        pvp_percentil=pvp_pct_exibido,
        dy_gap_percentil=dy_gap_pct,
        preco_referencia=preco_ref,
        n_episodios_buy=n_buy_hist,
        win_rate_buy=win_rate_buy,
        retorno_medio_buy=retorno_medio_buy,
        drawdown_tipico_buy=drawdown_tipico_buy,
        p_value_wf_buy=p_value_wf_buy,
        n_steps_wf=n_steps_wf,
        suporte_sinais=suporte_sinais,
        bloqueio_compra=bloqueio_compra,
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


def _finalizar_votos(decisoes: list[TickerDecision]) -> None:
    """BH sobre a familia (sinais BUY/SELL ativos de ``decisoes``) -> voto -> acao.

    Muta as decisoes. Decisoes sem evidencias (indisponiveis) ficam como estao.
    Deve ser chamada UMA vez por decisao (anexa linhas ao rationale).
    """
    chaves = ("otimizador", "episodio", "walkforward")
    for d in decisoes:
        d.rationale.append(linha_evidencia())
    alvo = [d for d in decisoes if d.suporte_sinais]
    flat = [d.suporte_sinais[k] for d in alvo for k in chaves]
    julgados = aplicar_fdr(flat)
    for j, d in enumerate(alvo):
        suporte = dict(zip(chaves, julgados[j * 3:(j + 1) * 3]))
        sinais = {
            "otimizador": d.sinal_otimizador,
            "episodio": d.sinal_episodio,
            "walkforward": d.sinal_walkforward,
        }
        n_validos = sum(1 for v in sinais.values() if v in VALID_SIGNALS)
        votos = [sinais[k] for k in chaves if conta_no_voto(suporte[k])]
        n_buy = sum(1 for v in votos if v == "BUY")
        n_sell = sum(1 for v in votos if v == "SELL")

        acao, nivel = _derivar_acao(n_buy, n_sell, n_validos)

        if d.bloqueio_compra:
            if acao == "COMPRAR":
                acao, nivel = "AGUARDAR", "BAIXA"
                d.rationale.append(
                    f"COMPRA BLOQUEADA ({d.bloqueio_compra}): COMPRAR rebaixado para AGUARDAR"
                )
            else:
                d.rationale.append(f"Compra bloqueada: {d.bloqueio_compra}")
        if d.flag_destruicao_capital and n_buy > 0:
            d.rationale.append(
                f"ALERTA (descritivo, nao veta): BUY presente e destruicao de capital ({d.motivo_destruicao}); "
                "sem evidencia de que a flag antecipe retorno pior"
            )
        if d.flag_volume_queda_forte and n_buy > 0:
            d.rationale.append("ALERTA (descritivo, nao veta): BUY presente e queda com volume alto detectada")
        if d.flag_dy_gap_baixo and acao == "COMPRAR":
            d.rationale.append("Atencao: DY Gap < p5 (DY baixo vs CDI) na entrada COMPRAR")

        d.suporte_sinais = suporte
        d.n_concordam_buy = n_buy
        d.n_concordam_sell = n_sell
        d.acao = acao
        d.nivel_concordancia = nivel
        d.rationale.extend(linhas_rationale(suporte, d.bloqueio_compra))


def decidir_universo(
    session,
    tickers: Optional[list[str]] = None,
    optimizer_params_por_ticker: Optional[dict[str, dict]] = None,
    *,
    cdi_sensitivity_por_ticker: Optional[dict[str, dict]] = None,
    focus_explanation_por_ticker: Optional[dict[str, dict]] = None,
    forward_days: int = 20,
    optimizer_stats_por_ticker: Optional[dict[str, dict]] = None,
    data_ref_mercado: Optional[date] = None,
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
    optimizer_stats_por_ticker : dict[ticker, dict], optional
        Estatisticas de teste do otimizador (n/p) por ticker; define se o sinal
        do otimizador tem suporte para votar. Ausente => cache em disco.
    data_ref_mercado : date, optional
        Data de referencia do snapshot para elegibilidade de compra.
        Default: ultima data com preco no banco.

    A correcao Benjamini-Hochberg (``decisao.fdr_q``) usa como familia os sinais
    BUY/SELL ativos de TODOS os ``tickers`` desta chamada: um subconjunto gera
    familia menor (menos conservadora) que o universo inteiro.
    """
    if tickers is None:
        tickers = tickers_ativos(session)
    if data_ref_mercado is None:
        data_ref_mercado = data_referencia_mercado(session)
    stats_map = optimizer_stats_por_ticker or {}

    params_map = optimizer_params_por_ticker or {}
    cdi_map = cdi_sensitivity_por_ticker or {}
    focus_map = focus_explanation_por_ticker or {}
    decisoes: list[TickerDecision] = []
    for ticker in tickers:
        params = params_map.get(ticker)
        cdi = cdi_map.get(ticker)
        focus = focus_map.get(ticker)
        try:
            d = _decidir_ticker_base(ticker, session, optimizer_params=params,
                               cdi_sensitivity=cdi,
                               focus_explanation=focus,
                               forward_days=forward_days,
                               optimizer_stats=stats_map.get(ticker),
                               data_ref_mercado=data_ref_mercado)
        except Exception as exc:
            d = _decisao_indisponivel(ticker, f"erro inesperado: {exc}")
        decisoes.append(d)

    # Familia BH = todos os sinais BUY/SELL ativos da rodada (todos os tickers).
    _finalizar_votos(decisoes)
    return decisoes
