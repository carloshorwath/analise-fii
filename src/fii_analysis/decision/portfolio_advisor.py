"""Advisor de carteira — cruza decisoes do recommender com posicoes do trader.

Produz orientacoes DESCRITIVAS, nao prescritivas:

  HOLD       — manter posicao (default; inclui posicoes com alerta de risco)
  AUMENTAR   — sinal COMPRAR COM SUPORTE estatistico + posicao com folga
  REDUZIR    — sinal VENDER COM SUPORTE estatistico

Criterio: so FATO ou sinal com suporte estatistico gera badge de acao. A flag de
destruicao de capital e um ALERTA DE RISCO descritivo (vai no racional e em
flags_resumo; badge continua HOLD): o estudo em painel de 2026-11-12 nao achou
evidencia de que ela antecipe retorno pior (ver decision/evidencia.py). Os badges
SAIR e EVITAR_NOVOS_APORTES nao sao mais produzidos (existem so em snapshots
antigos). Bloqueios factuais (liquidacao, preco parado, sem negocios) so impedem
AUMENTAR; alertas estruturais de carteira (HHI/top-2) seguem em alertas_estruturais.

Tambem produz alertas estruturais da carteira (concentracao via Herfindahl,
peso do top-N) — separados dos sinais taticos. Nao mistura "estrutura"
com "tatica" numa unica regra de rebalanceamento automatico.

Vocabulario evita "SELL" puro (que pode ser lido como "zere agora") em favor
de "REDUZIR / SAIR / EVITAR NOVOS APORTES" — sintaxe de gestao de carteira,
nao mesa de operacoes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from io import StringIO
from typing import Optional

from src.fii_analysis.decision.recommender import TickerDecision


# Limites default — descritivos (alertas), nao bloqueantes.
DEFAULT_PESO_MAX_TICKER = 0.30   # 30% — acima disso, AUMENTAR vira HOLD
DEFAULT_HHI_ATENCAO = 0.25       # > 0.25 ja eh concentracao alta
DEFAULT_TOP_2_PESO = 0.50        # top 2 holdings somando >50% = atencao


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class HoldingAdvice:
    """Conselho descritivo para uma posicao da carteira."""

    ticker: str
    quantidade: int
    preco_medio: float
    preco_atual: Optional[float]
    valor_mercado: Optional[float]
    peso_carteira: Optional[float]   # 0-1

    # Conselho derivado da decisao + posicao
    badge: str       # HOLD / AUMENTAR / REDUZIR (SAIR / EVITAR_NOVOS_APORTES so em snapshots antigos)
    racional: str    # 1-2 linhas explicando o badge
    prioridade: str  # ALTA / MEDIA / BAIXA — para ordenacao no relatorio

    # Eco da decisao do recommender
    acao_recomendada: str        # COMPRAR / VENDER / AGUARDAR / EVITAR
    nivel_concordancia: str      # ALTA / MEDIA / BAIXA / VETADA
    flags_resumo: str            # "destr.capital, emissao" ou "—"

    # Validade
    valida_ate: date


@dataclass
class AlertaEstrutural:
    """Alerta DESCRITIVO sobre estrutura da carteira — nao sugere acao."""

    tipo: str         # 'concentracao' | 'top_2_peso' | 'tickers_unicos'
    severidade: str   # 'info' | 'atencao'
    descricao: str
    valor: float


# =============================================================================
# Helpers internos
# =============================================================================


def _proxima_segunda(hoje: date) -> date:
    """Proxima segunda-feira apos hoje (trader reavalia semanalmente)."""
    dias_para_segunda = (7 - hoje.weekday()) % 7
    if dias_para_segunda == 0:
        dias_para_segunda = 7
    return hoje + timedelta(days=dias_para_segunda)


def _flags_resumo(d: TickerDecision) -> str:
    flags = []
    if d.flag_destruicao_capital:
        flags.append("destr.capital (alerta descritivo)")
    if d.flag_emissao_recente:
        flags.append("emissao")
    if d.flag_pvp_caro:
        flags.append("P/VP>p95")
    if d.flag_dy_gap_baixo:
        flags.append("DYgap<p5")
    if d.bloqueio_compra:
        flags.append("compra bloqueada")
    return ", ".join(flags) if flags else "—"


def _consolidar_holdings(holdings: list[dict]) -> dict[str, dict]:
    """Agrupa multiplas posicoes do mesmo ticker (preco medio ponderado)."""
    consol: dict[str, dict] = {}
    for h in holdings:
        ticker = h["ticker"]
        qty = int(h.get("quantidade", 0))
        preco_med = float(h.get("preco_medio", 0))
        if ticker not in consol:
            consol[ticker] = {
                "ticker": ticker,
                "quantidade": qty,
                "valor_total_investido": qty * preco_med,
            }
        else:
            consol[ticker]["quantidade"] += qty
            consol[ticker]["valor_total_investido"] += qty * preco_med

    for ticker, c in consol.items():
        if c["quantidade"] > 0:
            c["preco_medio"] = c["valor_total_investido"] / c["quantidade"]
        else:
            c["preco_medio"] = 0.0
    return consol


# =============================================================================
# Mapeamento Acao + Posicao -> Badge
# =============================================================================


def _alerta_risco(d: TickerDecision) -> str:
    """Texto do alerta descritivo de destruicao de capital ('' se nao ha flag).

    ``motivo_destruicao`` ja traz a gravidade ([ALERTA]/[DESTRUICAO ATIVA]) e o numero
    (ex.: 'VP/cota em queda (-0.59% ao mes)').
    """
    if not d.flag_destruicao_capital:
        return ""
    return (
        f"ALERTA DE RISCO (descritivo): {d.motivo_destruicao or 'destruicao de capital'} "
        "Sem evidencia de que o alerta antecipe retorno pior."
    )


def _derivar_badge(
    decisao: TickerDecision,
    peso_carteira: Optional[float],
    peso_max_ticker: float,
) -> tuple[str, str, str]:
    """Mapeia (Acao do recommender + peso atual) para (badge, racional, prioridade).

    O alerta de risco (se houver) e anexado ao racional de qualquer badge; nunca
    muda o badge.
    """
    badge, racional, prioridade = _badge_base(decisao, peso_carteira, peso_max_ticker)
    alerta = _alerta_risco(decisao)
    if alerta:
        racional = f"{racional} {alerta}"
        if prioridade == "BAIXA":
            prioridade = "MEDIA"
    return badge, racional, prioridade


def _badge_base(
    decisao: TickerDecision,
    peso_carteira: Optional[float],
    peso_max_ticker: float,
) -> tuple[str, str, str]:
    peso = peso_carteira or 0.0
    flags = _flags_resumo(decisao)

    # Sinal de venda: REDUZIR (mais brando que SAIR)
    if decisao.acao == "VENDER":
        racional = (
            f"Sinais indicam venda ({decisao.nivel_concordancia} concordancia, "
            f"sinais Otim/Epi/WF: {decisao.sinal_otimizador}/{decisao.sinal_episodio}/"
            f"{decisao.sinal_walkforward}). Considere reduzir exposicao."
        )
        prioridade = "ALTA" if decisao.nivel_concordancia == "ALTA" else "MEDIA"
        return "REDUZIR", racional, prioridade

    # Compra bloqueada (fundo em liquidacao/encerrado, preco desatualizado):
    # a posicao continua listada, mas nunca vira AUMENTAR.
    if decisao.bloqueio_compra and decisao.acao == "COMPRAR":
        racional = (
            f"Compra bloqueada: {decisao.bloqueio_compra}. Manter a posicao sob observacao; "
            "nao aumentar."
        )
        return "HOLD", racional, "MEDIA"

    # Sinal de compra: AUMENTAR ou HOLD (se ja concentrado)
    if decisao.acao == "COMPRAR":
        if peso >= peso_max_ticker:
            racional = (
                f"Sinal de compra ({decisao.nivel_concordancia}), mas posicao "
                f"ja em {peso * 100:.1f}% (>= {peso_max_ticker * 100:.0f}%). "
                "Manter sem aumentar — concentracao no limite."
            )
            return "HOLD", racional, "MEDIA"
        racional = (
            f"Sinal de compra ({decisao.nivel_concordancia} concordancia). "
            f"Posicao em {peso * 100:.1f}% — espaco para aumentar ate "
            f"{peso_max_ticker * 100:.0f}%."
        )
        prioridade = "ALTA" if decisao.nivel_concordancia == "ALTA" else "MEDIA"
        return "AUMENTAR", racional, prioridade

    # Sinal AGUARDAR: HOLD com flags informativos
    if decisao.bloqueio_compra:
        racional = f"Sem sinal de acao. Compra bloqueada: {decisao.bloqueio_compra}."
        return "HOLD", racional, "MEDIA"
    if flags != "—":
        racional = f"Sem sinal de acao. Atencao: {flags}."
        return "HOLD", racional, "BAIXA"
    racional = "Sem sinal de acao no momento — manter."
    return "HOLD", racional, "BAIXA"


# =============================================================================
# API publica
# =============================================================================


def aconselhar_carteira(
    decisoes: list[TickerDecision],
    holdings: list[dict],
    *,
    precos_atuais: Optional[dict[str, float]] = None,
    peso_max_ticker: float = DEFAULT_PESO_MAX_TICKER,
    valida_ate: Optional[date] = None,
) -> list[HoldingAdvice]:
    """Cruza decisoes com posicoes da carteira e produz HoldingAdvice por holding.

    Parameters
    ----------
    decisoes : list[TickerDecision]
        Saida de decidir_universo() — uma por ticker (do universo monitorado).
    holdings : list[dict]
        Posicoes da carteira (formato de load_carteira_db()): cada dict tem
        ticker, quantidade, preco_medio, data_compra. Multiplas posicoes do
        mesmo ticker sao consolidadas com preco medio ponderado.
    precos_atuais : dict[ticker, preco] | None
        Mapa de preco corrente. Se None, usa preco_referencia da decisao.
    peso_max_ticker : float
        Acima desse peso, AUMENTAR vira HOLD (concentracao no limite).
    valida_ate : date | None
        Data ate quando a sugestao vale. Default = proxima segunda-feira.
    """
    if valida_ate is None:
        valida_ate = _proxima_segunda(date.today())

    consolidados = _consolidar_holdings(holdings)
    decisoes_por_ticker = {d.ticker: d for d in decisoes}

    # Precos para calcular peso
    if precos_atuais is None:
        precos_atuais = {d.ticker: d.preco_referencia for d in decisoes
                         if d.preco_referencia is not None}

    # Valor de mercado total (para peso)
    valor_mercado_total = 0.0
    valores_mercado: dict[str, Optional[float]] = {}
    for ticker, c in consolidados.items():
        preco = precos_atuais.get(ticker)
        if preco is not None:
            vm = c["quantidade"] * preco
            valores_mercado[ticker] = vm
            valor_mercado_total += vm
        else:
            valores_mercado[ticker] = None

    advices: list[HoldingAdvice] = []
    for ticker, c in consolidados.items():
        if c["quantidade"] <= 0:
            continue

        decisao = decisoes_por_ticker.get(ticker)
        vm = valores_mercado.get(ticker)
        peso = (vm / valor_mercado_total) if (vm is not None and valor_mercado_total > 0) else None

        if decisao is None:
            advices.append(HoldingAdvice(
                ticker=ticker,
                quantidade=c["quantidade"],
                preco_medio=c["preco_medio"],
                preco_atual=precos_atuais.get(ticker),
                valor_mercado=vm,
                peso_carteira=peso,
                badge="HOLD",
                racional=(
                    "Ticker fora do universo monitorado — sem sinal estatistico. "
                    "Manter sob observacao manual."
                ),
                prioridade="BAIXA",
                acao_recomendada="AGUARDAR",
                nivel_concordancia="BAIXA",
                flags_resumo="—",
                valida_ate=valida_ate,
            ))
            continue

        badge, racional, prioridade = _derivar_badge(
            decisao, peso, peso_max_ticker
        )

        advices.append(HoldingAdvice(
            ticker=ticker,
            quantidade=c["quantidade"],
            preco_medio=c["preco_medio"],
            preco_atual=precos_atuais.get(ticker),
            valor_mercado=vm,
            peso_carteira=peso,
            badge=badge,
            racional=racional,
            prioridade=prioridade,
            acao_recomendada=decisao.acao,
            nivel_concordancia=decisao.nivel_concordancia,
            flags_resumo=_flags_resumo(decisao),
            valida_ate=valida_ate,
        ))

    # Ordena: ALTA prioridade primeiro, depois ticker
    prioridade_ordem = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}
    advices.sort(key=lambda a: (prioridade_ordem.get(a.prioridade, 9), a.ticker))
    return advices


def alertas_estruturais(
    advices: list[HoldingAdvice],
    *,
    hhi_atencao: float = DEFAULT_HHI_ATENCAO,
    top_2_peso_atencao: float = DEFAULT_TOP_2_PESO,
) -> list[AlertaEstrutural]:
    """Alertas DESCRITIVOS de estrutura — nao sugerem rebalanceamento.

    Concentracao alta nao eh necessariamente errada (pode ser conviccao).
    Por isso os alertas sao informativos: dizem o que esta acontecendo,
    nao o que fazer.
    """
    alertas: list[AlertaEstrutural] = []

    pesos = sorted(
        [a.peso_carteira for a in advices if a.peso_carteira is not None],
        reverse=True,
    )
    if not pesos:
        return alertas

    # 1. Herfindahl
    hh = sum(p * p for p in pesos)
    severidade_hh = "atencao" if hh > hhi_atencao else "info"
    alertas.append(AlertaEstrutural(
        tipo="concentracao",
        severidade=severidade_hh,
        descricao=(
            f"Herfindahl = {hh:.3f} ({len(pesos)} ativos). "
            f"Acima de {hhi_atencao:.2f} indica concentracao alta — "
            "nao necessariamente erro, mas digno de revisao consciente."
        ),
        valor=hh,
    ))

    # 2. Peso do top 2
    if len(pesos) >= 2:
        top2 = pesos[0] + pesos[1]
        severidade_t2 = "atencao" if top2 > top_2_peso_atencao else "info"
        alertas.append(AlertaEstrutural(
            tipo="top_2_peso",
            severidade=severidade_t2,
            descricao=(
                f"Top 2 holdings somam {top2 * 100:.1f}% da carteira. "
                f"Acima de {top_2_peso_atencao * 100:.0f}% indica dependencia alta de poucos ativos."
            ),
            valor=top2,
        ))

    # 3. Numero de ativos
    n = len(pesos)
    if n < 5:
        alertas.append(AlertaEstrutural(
            tipo="tickers_unicos",
            severidade="info",
            descricao=(
                f"Carteira com {n} ativo(s). FIIs costumam diluir risco com 5-10 holdings — "
                "mas projetos focados em poucos podem ser intencionais."
            ),
            valor=float(n),
        ))

    return alertas


# =============================================================================
# Exportacao — sempre com disclaimer explicito
# =============================================================================


_DISCLAIMER = (
    "AVISO: este arquivo e DESCRITIVO: o estudo em painel de 2026-11-12 nao achou "
    "indicador do sistema que preveja retorno relativo entre fundos. Nao sao "
    "ordens de compra/venda. Cada linha tem "
    "prazo de validade — reavaliar a partir desta data. Validar com julgamento "
    "humano antes de executar."
)


def exportar_sugestoes_md(advices: list[HoldingAdvice], data_ref: date) -> str:
    """Markdown com disclaimer no topo + tabela escaneavel."""
    out: list[str] = []
    out.append(f"# Sugestoes Operacionais — Carteira em {data_ref.isoformat()}")
    out.append("")
    out.append(f"> {_DISCLAIMER}")
    out.append("")
    if not advices:
        out.append("_Nenhuma posicao na carteira._")
        return "\n".join(out)

    out.append("| Ticker | Sugestao | Prioridade | Peso | Racional | Valida ate |")
    out.append("|---|---|---|---|---|---|")
    for a in advices:
        peso_str = f"{a.peso_carteira * 100:.1f}%" if a.peso_carteira is not None else "n/d"
        out.append(
            f"| {a.ticker} | **{a.badge}** | {a.prioridade} | {peso_str} | "
            f"{a.racional} | {a.valida_ate.isoformat()} |"
        )
    out.append("")
    return "\n".join(out)


def exportar_sugestoes_csv(advices: list[HoldingAdvice]) -> str:
    """CSV com disclaimer como primeira linha (comentario)."""
    buf = StringIO()
    buf.write(f"# {_DISCLAIMER}\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "ticker", "sugestao", "prioridade",
        "quantidade", "preco_medio", "preco_atual", "valor_mercado", "peso_carteira",
        "acao_recomendada", "nivel_concordancia", "flags_resumo",
        "racional", "valida_ate",
    ])
    for a in advices:
        writer.writerow([
            a.ticker, a.badge, a.prioridade,
            a.quantidade, a.preco_medio,
            a.preco_atual if a.preco_atual is not None else "",
            a.valor_mercado if a.valor_mercado is not None else "",
            a.peso_carteira if a.peso_carteira is not None else "",
            a.acao_recomendada, a.nivel_concordancia, a.flags_resumo,
            a.racional, a.valida_ate.isoformat(),
        ])
    return buf.getvalue()
