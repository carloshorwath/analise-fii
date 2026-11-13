"""
Utilitários de UI para carteira — carregamento e persistência com cache Streamlit.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.fii_analysis.config import tickers_ativos
from src.fii_analysis.data.database import Carteira, get_session_ctx


@st.cache_data(ttl=300)
def load_tickers_ativos() -> list[str]:
    with get_session_ctx() as session:
        return tickers_ativos(session)


@st.cache_data(ttl=300, show_spinner=False)
def load_carteira_db() -> list[dict]:
    from sqlalchemy import select
    with get_session_ctx() as session:
        rows = session.execute(
            select(Carteira).order_by(Carteira.ticker)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "ticker": r.ticker,
                "quantidade": r.quantidade,
                "preco_medio": float(r.preco_medio),
                "data_compra": str(r.data_compra),
            }
            for r in rows
        ]


@st.cache_data(ttl=300, show_spinner=False)
def load_tickers_existentes() -> list[str]:
    """Todos os tickers conhecidos (ativos e inativos) -- usado para validar posicoes."""
    from sqlalchemy import select
    from src.fii_analysis.data.database import Ticker
    with get_session_ctx() as session:
        try:  # backend: tickers U universo IFIX
            from src.fii_analysis.decision.carteira_validacao import tickers_conhecidos
            return sorted(tickers_conhecidos(session))
        except ImportError:
            return sorted(session.execute(select(Ticker.ticker)).scalars().all())


@st.cache_data(ttl=300, show_spinner=False)
def load_seletor_info() -> tuple[list[str], dict[str, str]]:
    """Tickers para seletores: carteira (sempre) U curados U universo com preco.

    Retorna (lista, notas) onde notas[ticker] = 'em liquidacao' / 'preco parado desde DD/MM'.
    """
    from sqlalchemy import func, select
    from src.fii_analysis.config import TICKERS
    from src.fii_analysis.data.database import PrecoDiario, Ticker
    with get_session_ctx() as session:
        ultimo = dict(session.execute(
            select(PrecoDiario.ticker, func.max(PrecoDiario.data)).group_by(PrecoDiario.ticker)
        ).all())
        inativos = dict(session.execute(
            select(Ticker.ticker, Ticker.inativo_em).where(Ticker.inativo_em.is_not(None))
        ).all())
        cart = set(session.execute(select(Carteira.ticker)).scalars().all())
    lista = sorted(cart | set(TICKERS) | set(ultimo))
    max_data = max(ultimo.values()) if ultimo else None
    notas: dict[str, str] = {}
    for t in lista:
        if t in inativos:
            notas[t] = f"em liquidacao desde {inativos[t].strftime('%d/%m/%Y')}"
        elif max_data and t in ultimo and (max_data - ultimo[t]).days > 7:
            notas[t] = f"preco parado desde {ultimo[t].strftime('%d/%m/%Y')}"
    return lista, notas


def rotulo_seletor(ticker: str, notas: dict[str, str]) -> str:
    return f"{ticker} ({notas[ticker]})" if ticker in notas else ticker


@st.cache_data(ttl=300, show_spinner=False)
def load_tickers_modelo() -> list[str]:
    """Lista curta para paginas de modelo: ativos U posicoes da carteira."""
    return sorted(set(load_tickers_ativos()) | {h["ticker"] for h in load_carteira_db()})


def validar_posicao(ticker, quantidade, preco_medio, tickers_validos) -> list[str]:
    """Erros de uma posicao (lista vazia = valida). Usa o backend se existir."""
    try:
        from fii_analysis.decision.carteira_validacao import validar_posicao as _v
        return list(_v(ticker, quantidade, preco_medio, tickers_validos))
    except Exception:
        pass
    erros = []
    try:
        q = float(quantidade)
        if not q > 0 or not q.is_integer():
            erros.append("quantidade deve ser inteiro maior que 0")
    except (TypeError, ValueError):
        erros.append("quantidade vazia ou invalida")
    try:
        if not float(preco_medio) > 0:
            erros.append("preco deve ser maior que 0")
    except (TypeError, ValueError):
        erros.append("preco vazio ou invalido")
    if str(ticker).upper().strip() not in set(tickers_validos):
        erros.append(f"ticker {ticker} inexistente")
    return erros


def validar_registros(records: list[dict], tickers_validos) -> list[str]:
    """Erros linha a linha ('linha N: ...') de uma lista de posicoes do CSV."""
    out = []
    for i, r in enumerate(records, start=1):
        for e in validar_posicao(r["ticker"], r["quantidade"], r["preco_medio"], tickers_validos):
            out.append(f"linha {i} ({r['ticker']}): {e}")
    return out


def save_carteira_posicao(ticker: str, quantidade: int, preco_medio: float, data_compra: date):
    with get_session_ctx() as session:
        pos = Carteira(
            ticker=ticker,
            quantidade=quantidade,
            preco_medio=preco_medio,
            data_compra=data_compra,
        )
        session.add(pos)
        session.commit()


def delete_carteira_posicao(pos_id: int):
    with get_session_ctx() as session:
        pos = session.get(Carteira, pos_id)
        if pos:
            session.delete(pos)
            session.commit()


def _parse_br_number(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("valor vazio")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    text = text.replace("R$", "").replace("%", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    if not text:
        raise ValueError("valor vazio")
    return float(text)


def _parse_canonical_number(value) -> float:
    """CSV canonico usa ponto decimal ('89.59'); vazio/NaN levanta ValueError."""
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            raise ValueError("valor vazio")
        return float(value)
    return _parse_br_number(value)


def normalize_carteira_csv(df_csv: pd.DataFrame, default_date: date | None = None) -> tuple[list[dict], str]:
    """Aceita CSV canônico ou export consolidado de corretora."""
    default_date = default_date or date.today()

    canonical = {"ticker", "quantidade", "preco_medio", "data_compra"}
    if canonical.issubset(set(df_csv.columns)):
        records, erros = [], []
        for i, (_, row) in enumerate(df_csv.iterrows(), start=1):
            try:
                qtd = _parse_canonical_number(row["quantidade"])
                records.append({
                    "ticker": str(row["ticker"]).upper().strip(),
                    "quantidade": int(qtd) if qtd == int(qtd) else qtd,
                    "preco_medio": _parse_canonical_number(row["preco_medio"]),
                    "data_compra": pd.to_datetime(row["data_compra"]).date(),
                })
            except (ValueError, TypeError) as exc:
                erros.append(f"linha {i}: valor vazio ou invalido ({exc})")
        if erros:
            raise ValueError("\n".join(erros))
        return records, "canonical"

    broker_export = {"Ativo", "Qtd", "Preço médio"}
    if broker_export.issubset(set(df_csv.columns)):
        records, erros = [], []
        for i, (_, row) in enumerate(df_csv.iterrows(), start=1):
            ticker = str(row["Ativo"]).upper().strip()
            if not ticker or "ATIVOS" in ticker:
                continue
            try:
                qtd = _parse_br_number(row["Qtd"])
                records.append({
                    "ticker": ticker,
                    "quantidade": int(qtd) if qtd == int(qtd) else qtd,
                    "preco_medio": _parse_br_number(row["Preço médio"]),
                    "data_compra": default_date,
                })
            except (ValueError, TypeError) as exc:
                erros.append(f"linha {i} ({ticker}): valor vazio ou invalido ({exc})")
        if erros:
            raise ValueError("\n".join(erros))
        return records, "broker_export"

    available = ", ".join(map(str, df_csv.columns))
    raise ValueError(
        "CSV em formato nao suportado. "
        "Use `ticker,quantidade,preco_medio,data_compra` ou `Ativo,Qtd,Preço médio`. "
        f"Colunas encontradas: {available}"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def calcular_sinais_carteira_ao_vivo(posicoes_t: tuple, precos_t: tuple, data_ultimo_preco):
    """Sinais ao vivo (somente leitura) chaveados por carteira + data do ultimo preco.

    Evita rodar decidir_universo (50-90 s) a cada rerun. Retorna (advices, alertas).
    """
    from src.fii_analysis.decision import aconselhar_carteira, alertas_estruturais, decidir_universo
    from src.fii_analysis.models.threshold_optimizer_v2 import load_optimizer_cache

    posicoes = [
        {"ticker": t, "quantidade": q, "preco_medio": pm, "data_compra": dc}
        for t, q, pm, dc in posicoes_t
    ]
    with get_session_ctx() as session:
        tickers_dec = sorted({p["ticker"] for p in posicoes} | set(tickers_ativos(session)))
        opt_params = {t: c for t in tickers_dec if (c := load_optimizer_cache(t)) is not None}
        decisoes = decidir_universo(
            session, tickers=tickers_dec, optimizer_params_por_ticker=opt_params or None
        )
    advices = aconselhar_carteira(decisoes, posicoes, precos_atuais=dict(precos_t))
    return advices, alertas_estruturais(advices)


def decisao_ja_registrada(
    opportunity_id, tipo, vendido, comprado, quantidade, data, racional
) -> str | None:
    """Descricao do registro existente (mesma oportunidade, ou mesma decisao avulsa) ou None."""
    from sqlalchemy import select
    from src.fii_analysis.data.database import DecisaoLog

    with get_session_ctx() as session:
        q = select(DecisaoLog)
        if opportunity_id is not None:
            q = q.where(DecisaoLog.opportunity_id == opportunity_id)
        else:
            q = q.where(
                DecisaoLog.opportunity_id.is_(None),
                DecisaoLog.tipo == tipo.upper(),
                DecisaoLog.data == data,
                DecisaoLog.ticker_vendido == vendido,
                DecisaoLog.ticker_comprado == comprado,
                DecisaoLog.quantidade == quantidade,
                DecisaoLog.racional_usuario == racional,
            )
        r = session.execute(q.order_by(DecisaoLog.id.desc()).limit(1)).scalar_one_or_none()
        if r is None:
            return None
        return f"ID {r.id} ({r.tipo}, {r.data})"
