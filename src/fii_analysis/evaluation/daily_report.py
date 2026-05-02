"""Relatorio diario acionavel — sintese das decisoes para o trader.

Consome List[TickerDecision] e produz:

1. Markdown com 4 secoes (Acoes Hoje | Watchlist | Riscos | Apendice).
2. CSV plano (uma linha por ticker) para abrir em planilha.

A logica de decisao em si vive em decision/recommender.py — este modulo cuida
exclusivamente de formatacao e persistencia.
"""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Iterable

from src.fii_analysis.decision import TickerDecision

# =============================================================================
# Helpers de formatacao
# =============================================================================


def _fmt_pct(val: float | None, casas: int = 1) -> str:
    if val is None:
        return "n/d"
    return f"{val * 100:.{casas}f}%"


def _fmt_num(val: float | None, casas: int = 2) -> str:
    if val is None:
        return "n/d"
    return f"{val:.{casas}f}"


def _fmt_pct_value(val: float | None) -> str:
    """Para percentil ja em escala 0-100."""
    if val is None:
        return "n/d"
    return f"{val:.0f}"


def _sinais_str(d: TickerDecision) -> str:
    """Compacta os 3 sinais como 'BUY/BUY/NEUTRO' (Otim/Epi/WF)."""
    def short(s: str) -> str:
        if s == "INDISPONIVEL":
            return "—"
        return s
    return f"{short(d.sinal_otimizador)}/{short(d.sinal_episodio)}/{short(d.sinal_walkforward)}"


def _flags_str(d: TickerDecision) -> str:
    flags = []
    if d.flag_destruicao_capital:
        flags.append("destr.capital")
    if d.flag_emissao_recente:
        flags.append("emissao")
    if d.flag_pvp_caro:
        flags.append("P/VP>p95")
    if d.flag_dy_gap_baixo:
        flags.append("DYgap<p5")
    return ", ".join(flags) if flags else "—"


# =============================================================================
# Particionamento das decisoes em buckets (Acao / Watchlist / Risco)
# =============================================================================


def _partition(decisoes: Iterable[TickerDecision]) -> dict[str, list[TickerDecision]]:
    """Separa decisoes em 4 buckets para o relatorio."""
    decisoes = list(decisoes)
    return {
        "acoes": [d for d in decisoes if d.acao in ("COMPRAR", "VENDER")
                  and d.nivel_concordancia in ("ALTA", "MEDIA")],
        "watchlist": [d for d in decisoes if d.acao == "AGUARDAR"
                      and (d.n_concordam_buy + d.n_concordam_sell) >= 1],
        "riscos": [d for d in decisoes
                   if d.acao == "EVITAR" or d.flag_destruicao_capital
                   or d.flag_emissao_recente or d.flag_pvp_caro
                   or d.flag_dy_gap_baixo],
        "todas": decisoes,
    }


# =============================================================================
# Renderizacao Markdown
# =============================================================================


def _render_secao_acoes(decisoes: list[TickerDecision]) -> list[str]:
    linhas = ["## Acoes Hoje", ""]
    if not decisoes:
        linhas.append("_Nenhuma acao recomendada hoje (todas decisoes em AGUARDAR ou EVITAR)._")
        linhas.append("")
        return linhas

    linhas.append("_Decisoes com concordancia ALTA ou MEDIA entre os 3 modos._")
    linhas.append("")
    linhas.append("| Ticker | Acao | Concordancia | Sinais (Otim/Epi/WF) | P/VP | P/VP pct | Preco ref | Flags |")
    linhas.append("|---|---|---|---|---|---|---|---|")
    for d in sorted(decisoes, key=lambda x: (x.acao, -x.n_concordam_buy, x.ticker)):
        linhas.append(
            f"| {d.ticker} | **{d.acao}** | {d.nivel_concordancia} | "
            f"{_sinais_str(d)} | {_fmt_num(d.pvp_atual)} | "
            f"{_fmt_pct_value(d.pvp_percentil)} | "
            f"{_fmt_num(d.preco_referencia)} | {_flags_str(d)} |"
        )
    linhas.append("")
    return linhas


def _render_secao_watchlist(decisoes: list[TickerDecision]) -> list[str]:
    linhas = ["## Watchlist", ""]
    if not decisoes:
        linhas.append("_Sem sinais isolados em observacao._")
        linhas.append("")
        return linhas

    linhas.append("_Sinais isolados (1 modo) ou sem concordancia — observar nos proximos pregoes._")
    linhas.append("")
    linhas.append("| Ticker | Sinais (Otim/Epi/WF) | P/VP pct | DY Gap pct | n_BUY | n_SELL |")
    linhas.append("|---|---|---|---|---|---|")
    for d in sorted(decisoes,
                    key=lambda x: (-(x.n_concordam_buy + x.n_concordam_sell), x.ticker)):
        linhas.append(
            f"| {d.ticker} | {_sinais_str(d)} | "
            f"{_fmt_pct_value(d.pvp_percentil)} | "
            f"{_fmt_pct_value(d.dy_gap_percentil)} | "
            f"{d.n_concordam_buy} | {d.n_concordam_sell} |"
        )
    linhas.append("")
    return linhas


def _render_secao_janelas_abertas(todas: list[TickerDecision]) -> list[str]:
    """Episodios novos + janelas de captura — pontos extras a observar.

    Inclui tickers em qualquer Acao (inclusive AGUARDAR) desde que tenham
    pelo menos uma janela aberta hoje.
    """
    linhas = ["## Janelas Abertas Hoje", ""]

    com_episodio_novo = [d for d in todas
                         if d.episodio_eh_novo is True]
    com_captura = [d for d in todas if d.janela_captura_aberta]

    if not com_episodio_novo and not com_captura:
        linhas.append("_Sem episodios novos nem janelas de captura abertas hoje._")
        linhas.append("")
        return linhas

    if com_episodio_novo:
        linhas.append("### Episodios P/VP recem-abertos")
        linhas.append("_Estado extremo + gap >= forward_days do ultimo evento (entrada nova, nao continuacao)._")
        linhas.append("")
        linhas.append("| Ticker | Lado | P/VP pct | Pregoes desde ultimo | Acao atual |")
        linhas.append("|---|---|---|---|---|")
        for d in sorted(com_episodio_novo, key=lambda x: x.ticker):
            lado = d.sinal_episodio if d.sinal_episodio in ("BUY", "SELL") else "—"
            gap = d.pregoes_desde_ultimo_episodio
            gap_str = "primeiro" if gap is None else str(gap)
            linhas.append(
                f"| {d.ticker} | {lado} | "
                f"{_fmt_pct_value(d.pvp_percentil)} | {gap_str} | {d.acao} |"
            )
        linhas.append("")

    if com_captura:
        linhas.append("### Janelas de captura de dividendo")
        linhas.append("_Proxima data-com **estimada** pela mediana historica. Validar com release do fundo._")
        linhas.append("")
        linhas.append("| Ticker | Proxima data-com | Dias corridos ate | Acao atual |")
        linhas.append("|---|---|---|---|")
        for d in sorted(com_captura, key=lambda x: x.dias_ate_proxima_data_com or 999):
            dc = d.proxima_data_com_estimada
            dc_str = dc.isoformat() if dc else "n/d"
            linhas.append(
                f"| {d.ticker} | {dc_str} | {d.dias_ate_proxima_data_com} | {d.acao} |"
            )
        linhas.append("")

    return linhas


def _render_secao_riscos(decisoes: list[TickerDecision]) -> list[str]:
    linhas = ["## Riscos", ""]
    if not decisoes:
        linhas.append("_Nenhum alerta critico hoje._")
        linhas.append("")
        return linhas

    linhas.append("_Vetos e flags de saude do fundo._")
    linhas.append("")
    for d in sorted(decisoes, key=lambda x: (x.acao != "EVITAR", x.ticker)):
        prefix = "**VETADO**" if d.acao == "EVITAR" else "Atencao"
        linha = f"- **{d.ticker}** ({d.classificacao or '?'}) — {prefix}: "
        motivos = []
        if d.flag_destruicao_capital:
            motivos.append(f"destruicao de capital ({d.motivo_destruicao or 'sem detalhe'})")
        if d.flag_emissao_recente:
            motivos.append("emissao recente >1%")
        if d.flag_pvp_caro:
            motivos.append(f"P/VP no percentil {_fmt_pct_value(d.pvp_percentil)} (>p95)")
        if d.flag_dy_gap_baixo:
            motivos.append(f"DY Gap no percentil {_fmt_pct_value(d.dy_gap_percentil)} (<p5)")
        linha += "; ".join(motivos) if motivos else "n/d"
        linhas.append(linha)
    linhas.append("")
    return linhas


def _render_apendice(decisoes: list[TickerDecision]) -> list[str]:
    linhas = ["## Apendice — Estatistica Historica", ""]
    linhas.append("_Numeros que sustentam (ou nao) cada recomendacao._")
    linhas.append("")
    if not decisoes:
        linhas.append("_Sem decisoes para detalhar._")
        return linhas

    for d in sorted(decisoes, key=lambda x: x.ticker):
        linhas.append(f"### {d.ticker} ({d.classificacao or '?'})")
        linhas.append(f"- Acao: **{d.acao}** ({d.nivel_concordancia})")
        linhas.append(
            f"- Sinais: Otimizador={d.sinal_otimizador} | "
            f"Episodios={d.sinal_episodio} | WalkForward={d.sinal_walkforward}"
        )
        linhas.append(
            f"- P/VP atual: {_fmt_num(d.pvp_atual)} (percentil {_fmt_pct_value(d.pvp_percentil)})"
        )
        linhas.append(f"- DY Gap percentil: {_fmt_pct_value(d.dy_gap_percentil)}")
        linhas.append(
            f"- Episodios BUY historicos: n={d.n_episodios_buy} | "
            f"win_rate={_fmt_pct(d.win_rate_buy)} | "
            f"retorno_medio={_fmt_pct(d.retorno_medio_buy, casas=2)}"
        )
        linhas.append(
            f"- Drawdown tipico no historico de BUY (pior fwd_ret): "
            f"{_fmt_pct(d.drawdown_tipico_buy)}"
        )
        if d.p_value_wf_buy is not None:
            linhas.append(f"- p-value WalkForward BUY: {d.p_value_wf_buy:.4f} (n_steps={d.n_steps_wf})")
        if d.rationale:
            linhas.append("- Notas:")
            for nota in d.rationale:
                linhas.append(f"  - {nota}")
        # CDI sensitivity (diagnóstico V1)
        cdi_status = getattr(d, "cdi_status", None)
        if cdi_status and cdi_status not in ("SEM_CDI", "DADOS_INSUFICIENTES"):
            cdi_beta = getattr(d, "cdi_beta", None)
            cdi_r2 = getattr(d, "cdi_r_squared", None)
            cdi_p = getattr(d, "cdi_p_value", None)
            cdi_resid = getattr(d, "cdi_residuo_atual", None)
            cdi_resid_pct = getattr(d, "cdi_residuo_percentil", None)
            linhas.append(
                f"- CDI-ajustado: beta={_fmt_num(cdi_beta, 4)} | "
                f"R2={_fmt_num(cdi_r2, 3)} | p={_fmt_num(cdi_p, 4)} | "
                f"residuo pct={_fmt_pct_value(cdi_resid_pct)}"
            )
            # Focus CDI context
            cdi_delta = getattr(d, "cdi_delta_focus_12m", None)
            cdi_repr = getattr(d, "cdi_repricing_12m", None)
            if cdi_delta is not None or cdi_repr is not None:
                parts = []
                if cdi_delta is not None:
                    parts.append(f"Delta Focus 12m={cdi_delta:+.2%}")
                if cdi_repr is not None:
                    parts.append(f"Repricing 12m={cdi_repr:+.3f}")
                linhas.append(f"- Contexto juros: {' | '.join(parts)}")
        linhas.append("")
    return linhas


# =============================================================================
# Saidas
# =============================================================================


def render_markdown(decisoes: list[TickerDecision], data_ref: date | None = None) -> str:
    """Gera o relatorio diario completo em Markdown."""
    data_ref = data_ref or date.today()
    buckets = _partition(decisoes)

    out: list[str] = []
    out.append(f"# Recomendacoes Diarias FII — {data_ref.isoformat()}")
    out.append("")
    out.append(
        f"_{len(buckets['todas'])} ticker(s) avaliado(s). "
        f"Acoes: {len(buckets['acoes'])} | Watchlist: {len(buckets['watchlist'])} | "
        f"Riscos: {len(buckets['riscos'])}._"
    )
    out.append("")
    out.append("> Sinal e estatistico (saida dos modos). Acao e a decisao derivada com veto de risco.")
    out.append("> Concordancia e heuristica (3/3, 2/3, 1/3) — nao e intervalo de confianca.")
    out.append("")

    out.extend(_render_secao_acoes(buckets["acoes"]))
    out.extend(_render_secao_watchlist(buckets["watchlist"]))
    out.extend(_render_secao_janelas_abertas(buckets["todas"]))
    out.extend(_render_secao_riscos(buckets["riscos"]))
    # Apendice cobre tickers acionados, em watchlist ou vetados — todos os
    # casos onde o trader pode querer auditar o porque da decisao.
    vetadas = [d for d in buckets["todas"] if d.acao == "EVITAR"]
    apendice_alvo = buckets["acoes"] + buckets["watchlist"] + vetadas
    # Dedup mantendo ordem
    seen = set()
    apendice_alvo = [d for d in apendice_alvo if not (d.ticker in seen or seen.add(d.ticker))]
    out.extend(_render_apendice(apendice_alvo))

    return "\n".join(out)


def render_csv(decisoes: list[TickerDecision]) -> str:
    """Gera CSV plano (uma linha por ticker, todos os campos relevantes)."""
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "ticker", "data_referencia", "classificacao",
        "sinal_otimizador", "sinal_episodio", "sinal_walkforward",
        "acao", "nivel_concordancia", "n_concordam_buy", "n_concordam_sell",
        "flag_destruicao_capital", "motivo_destruicao",
        "flag_emissao_recente", "flag_pvp_caro", "flag_dy_gap_baixo",
        "pvp_atual", "pvp_percentil", "dy_gap_percentil", "preco_referencia",
        "n_episodios_buy", "win_rate_buy", "retorno_medio_buy",
        "drawdown_tipico_buy", "p_value_wf_buy", "n_steps_wf",
        "episodio_eh_novo", "pregoes_desde_ultimo_episodio",
        "janela_captura_aberta", "proxima_data_com_estimada",
        "dias_ate_proxima_data_com",
        "cdi_status", "cdi_beta", "cdi_r_squared", "cdi_p_value",
        "cdi_residuo_atual", "cdi_residuo_percentil",
        "cdi_delta_focus_12m", "cdi_repricing_12m",
        "rationale",
    ])
    for d in decisoes:
        writer.writerow([
            d.ticker, d.data_referencia.isoformat(), d.classificacao or "",
            d.sinal_otimizador, d.sinal_episodio, d.sinal_walkforward,
            d.acao, d.nivel_concordancia, d.n_concordam_buy, d.n_concordam_sell,
            int(d.flag_destruicao_capital), d.motivo_destruicao or "",
            int(d.flag_emissao_recente), int(d.flag_pvp_caro), int(d.flag_dy_gap_baixo),
            d.pvp_atual if d.pvp_atual is not None else "",
            d.pvp_percentil if d.pvp_percentil is not None else "",
            d.dy_gap_percentil if d.dy_gap_percentil is not None else "",
            d.preco_referencia if d.preco_referencia is not None else "",
            d.n_episodios_buy,
            d.win_rate_buy if d.win_rate_buy is not None else "",
            d.retorno_medio_buy if d.retorno_medio_buy is not None else "",
            d.drawdown_tipico_buy if d.drawdown_tipico_buy is not None else "",
            d.p_value_wf_buy if d.p_value_wf_buy is not None else "",
            d.n_steps_wf,
            "" if d.episodio_eh_novo is None else int(d.episodio_eh_novo),
            d.pregoes_desde_ultimo_episodio if d.pregoes_desde_ultimo_episodio is not None else "",
            int(d.janela_captura_aberta),
            d.proxima_data_com_estimada.isoformat() if d.proxima_data_com_estimada else "",
            d.dias_ate_proxima_data_com if d.dias_ate_proxima_data_com is not None else "",
            getattr(d, "cdi_status", "") or "",
            getattr(d, "cdi_beta", "") if getattr(d, "cdi_beta", None) is not None else "",
            getattr(d, "cdi_r_squared", "") if getattr(d, "cdi_r_squared", None) is not None else "",
            getattr(d, "cdi_p_value", "") if getattr(d, "cdi_p_value", None) is not None else "",
            getattr(d, "cdi_residuo_atual", "") if getattr(d, "cdi_residuo_atual", None) is not None else "",
            getattr(d, "cdi_residuo_percentil", "") if getattr(d, "cdi_residuo_percentil", None) is not None else "",
            getattr(d, "cdi_delta_focus_12m", "") if getattr(d, "cdi_delta_focus_12m", None) is not None else "",
            getattr(d, "cdi_repricing_12m", "") if getattr(d, "cdi_repricing_12m", None) is not None else "",
            " | ".join(d.rationale),
        ])
    return buf.getvalue()


def salvar_relatorio(
    decisoes: list[TickerDecision],
    output_dir: Path,
    data_ref: date | None = None,
) -> dict[str, Path]:
    """Persiste MD e CSV em output_dir/{data}_recomendacoes.{ext}."""
    data_ref = data_ref or date.today()
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"{data_ref.isoformat()}_recomendacoes.md"
    csv_path = output_dir / f"{data_ref.isoformat()}_recomendacoes.csv"

    md_path.write_text(render_markdown(decisoes, data_ref), encoding="utf-8")
    csv_path.write_text(render_csv(decisoes), encoding="utf-8")

    return {"md": md_path, "csv": csv_path}
