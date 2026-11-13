"""Elegibilidade de COMPRA: fundo encerrado/em liquidacao, preco desatualizado e sem negocios.

Tres condicoes impedem qualquer recomendacao de compra (acao COMPRAR, badge
AUMENTAR, candidato de rotacao). A posicao ja existente continua aparecendo
normalmente — o bloqueio e so do lado COMPRAR.

    1. Evento de liquidacao/encerramento vigente na data de referencia
       (tabela eventos_corporativos, ``data <= data_ref``).
    2. Ultimo preco do ticker com atraso > N pregoes em relacao a data de
       referencia (config.yaml: decisao.preco_defasado_dias_uteis, default 5).
       Atraso = numero de pregoes do mercado (datas distintas em precos_diarios)
       apos o ultimo preco do ticker, ate a data de referencia.
    3. Os ultimos N pregoes CONSECUTIVOS do ticker (suas proprias linhas de preco,
       ate a data de referencia) com volume 0: o preco e so repeticao do ultimo
       negocio e nao e executavel (config sugerida: decisao.sem_negocios_pregoes,
       default 5).

Alem do bloqueio, ``liquidez_intermitente`` MARCA (sem bloquear) o ticker com >= 4 dos
ultimos 10 pregoes com volume 0 (config sugerida: decisao.liquidez_intermitente_min_zeros
e decisao.liquidez_intermitente_janela).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, select

from src.fii_analysis.config_yaml import get_decisao_param
from src.fii_analysis.data.database import EventoCorporativo, PrecoDiario

# Substrings (minusculas, sem acento) do campo eventos_corporativos.tipo
_TIPOS_ENCERRAMENTO = ("liquid", "encerr")


def limite_dias_preco_defasado() -> int:
    return int(get_decisao_param("preco_defasado_dias_uteis", 5))


def limite_pregoes_sem_negocios() -> int:
    return int(get_decisao_param("sem_negocios_pregoes", 5))


def janela_liquidez_intermitente() -> tuple[int, int]:
    """(janela de pregoes, minimo de pregoes com volume 0 para marcar)."""
    return (
        int(get_decisao_param("liquidez_intermitente_janela", 10)),
        int(get_decisao_param("liquidez_intermitente_min_zeros", 4)),
    )


def data_referencia_mercado(session) -> Optional[date]:
    """Ultima data com preco no banco (referencia de mercado)."""
    return session.execute(select(func.max(PrecoDiario.data))).scalar_one_or_none()


def evento_encerramento_vigente(ticker: str, data_ref: date, session) -> Optional[tuple[date, str]]:
    """(data, tipo) do evento de liquidacao/encerramento mais antigo com data <= data_ref."""
    rows = session.execute(
        select(EventoCorporativo.data, EventoCorporativo.tipo)
        .where(EventoCorporativo.ticker == ticker, EventoCorporativo.data <= data_ref)
        .order_by(EventoCorporativo.data.asc())
    ).all()
    for data_evt, tipo in rows:
        if any(k in (tipo or "").lower() for k in _TIPOS_ENCERRAMENTO):
            return data_evt, tipo
    return None


def atraso_preco_pregoes(ticker: str, data_ref: date, session) -> Optional[tuple[date, int]]:
    """(ultimo_preco, pregoes_de_atraso) ou None se o ticker nao tem preco ate data_ref."""
    ultimo = session.execute(
        select(func.max(PrecoDiario.data)).where(
            PrecoDiario.ticker == ticker, PrecoDiario.data <= data_ref
        )
    ).scalar_one_or_none()
    if ultimo is None:
        return None
    atraso = session.execute(
        select(func.count(func.distinct(PrecoDiario.data))).where(
            PrecoDiario.data > ultimo, PrecoDiario.data <= data_ref
        )
    ).scalar_one()
    return ultimo, int(atraso or 0)


def volumes_recentes(ticker: str, data_ref: date, session, n: int) -> list[Optional[float]]:
    """Volume dos ultimos ``n`` pregoes do ticker (linhas de preco com data <= data_ref),
    do mais recente ao mais antigo. Volume NULL (desconhecido) vem como None."""
    rows = session.execute(
        select(PrecoDiario.volume)
        .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= data_ref)
        .order_by(PrecoDiario.data.desc())
        .limit(n)
    ).scalars().all()
    return [None if v is None else float(v) for v in rows]


def pregoes_consecutivos_sem_volume(ticker: str, data_ref: date, session, *, maximo: int = 400) -> int:
    """Quantos pregoes seguidos, contando do mais recente para tras, tem volume 0.
    Volume NULL (desconhecido) interrompe a sequencia (nao e tratado como zero)."""
    n = 0
    for v in volumes_recentes(ticker, data_ref, session, maximo):
        if v is None or v != 0:
            break
        n += 1
    return n


def liquidez_intermitente(
    ticker: str, data_ref: date, session, *, janela: Optional[int] = None, min_zeros: Optional[int] = None
) -> Optional[tuple[int, int]]:
    """(pregoes_com_volume_0, janela) se >= ``min_zeros`` dos ultimos ``janela`` pregoes
    tem volume 0; senao None. So avalia com a janela completa (fundo recem-listado nao marca).
    Informativo: NAO bloqueia compra."""
    j_cfg, z_cfg = janela_liquidez_intermitente()
    janela = j_cfg if janela is None else janela
    min_zeros = z_cfg if min_zeros is None else min_zeros
    vols = volumes_recentes(ticker, data_ref, session, janela)
    if len(vols) < janela:
        return None
    zeros = sum(1 for v in vols if v == 0)
    return (zeros, janela) if zeros >= min_zeros else None


def motivo_bloqueio_compra(
    ticker: str, data_ref: Optional[date], session, *, limite_pregoes: Optional[int] = None
) -> Optional[str]:
    """Texto do motivo se o ticker nao pode receber compra em ``data_ref``; senao None."""
    if data_ref is None:
        data_ref = data_referencia_mercado(session)
        if data_ref is None:
            return None
    evento = evento_encerramento_vigente(ticker, data_ref, session)
    if evento is not None:
        data_evt, tipo = evento
        rotulo = "em liquidacao" if "liquid" in (tipo or "").lower() else "encerrado"
        return f"fundo {rotulo} desde {data_evt.isoformat()}"

    limite = limite_dias_preco_defasado() if limite_pregoes is None else limite_pregoes
    atraso = atraso_preco_pregoes(ticker, data_ref, session)
    if atraso is not None and atraso[1] > limite:
        ultimo, n = atraso
        return (
            f"preco desatualizado: ultimo preco em {ultimo.isoformat()} "
            f"({n} pregoes de atraso vs {data_ref.isoformat()}; limite {limite})"
        )

    limite_zero = limite_pregoes_sem_negocios()
    seguidos = pregoes_consecutivos_sem_volume(ticker, data_ref, session)
    if seguidos >= limite_zero:
        return f"sem negocios ha {seguidos} pregoes (volume 0; preco repetido nao e executavel; limite {limite_zero})"
    return None
