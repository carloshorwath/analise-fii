from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.fii_analysis.data.corporate_actions import ajustar_relatorios, detectar_splits
from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal, get_cnpj_by_ticker


def get_relatorios_ajustados(ticker: str, session: Session, apenas_entregues: bool = True) -> pd.DataFrame:
    """Informes CVM do fundo com VP/cota e cotas na MESMA BASE do preco `fechamento`
    (quantidade atual de cotas; ver data/corporate_actions.py).

    Colunas: data_referencia, data_entrega, vp_por_cota (nominal), vp_aj, cotas_emitidas,
    cotas_aj, patrimonio_liq, fator_split. Ordenado por data_referencia ascendente.
    Unica fonte de VP/cota para qualquer P/VP do projeto.
    """
    cols = ["data_referencia", "data_entrega", "vp_por_cota", "vp_aj", "cotas_emitidas",
            "cotas_aj", "patrimonio_liq", "fator_split"]
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return pd.DataFrame(columns=cols)
    q = select(
        RelatorioMensal.data_referencia, RelatorioMensal.data_entrega, RelatorioMensal.vp_por_cota,
        RelatorioMensal.cotas_emitidas, RelatorioMensal.patrimonio_liq,
    ).where(RelatorioMensal.cnpj == cnpj).order_by(RelatorioMensal.data_referencia.asc())
    rows = session.execute(q).all()
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows, columns=["data_referencia", "data_entrega", "vp_por_cota",
                                     "cotas_emitidas", "patrimonio_liq"])
    for c in ("vp_por_cota", "cotas_emitidas", "patrimonio_liq"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    eventos, _ = detectar_splits(df)  # detecta com todos os informes (unidade, nao informacao)
    df = ajustar_relatorios(df, eventos)
    if apenas_entregues:
        df = df[df["data_entrega"].notna()]
    return df[cols].reset_index(drop=True)


def get_vp_cotas_pit(ticker: str, data: date, session: Session) -> tuple[float | None, float | None]:
    """(VP/cota, cotas) point-in-time na base do preco: ultimo informe com
    data_entrega <= data (ordem data_referencia DESC), dividido/multiplicado pelo
    fator acumulado dos splits posteriores a data_referencia do informe."""
    df = get_relatorios_ajustados(ticker, session)
    if df.empty:
        return None, None
    df = df[(pd.to_datetime(df["data_entrega"]) <= pd.Timestamp(data)) & df["vp_aj"].notna()]
    if df.empty:
        return None, None
    ult = df.sort_values("data_referencia").iloc[-1]
    cotas = float(ult["cotas_aj"]) if pd.notna(ult["cotas_aj"]) else None
    return float(ult["vp_aj"]), cotas


def get_pvp(ticker: str, data: date, session: Session) -> float | None:
    # BUG 1 fix: último preço disponível até data t (não exige match exato)
    preco_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data <= data,
        ).order_by(PrecoDiario.data.desc()).limit(1)
    ).scalar_one_or_none()
    if preco_row is None:
        return None

    vp, _ = get_vp_cotas_pit(ticker, data, session)
    if vp is None or vp <= 0:
        return None

    return float(preco_row) / float(vp)


def get_dy_trailing(ticker: str, data: date, session: Session, janela_dias: int = 365) -> float | None:
    # último preço disponível até data t (não exige match exato)
    preco_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data <= data,
        ).order_by(PrecoDiario.data.desc()).limit(1)
    ).scalar_one_or_none()
    if preco_row is None:
        return None

    inicio = data - timedelta(days=janela_dias)
    soma = session.execute(
        select(func.coalesce(func.sum(Dividendo.valor_cota), 0)).where(
            Dividendo.ticker == ticker,
            Dividendo.data_com > inicio,
            Dividendo.data_com < data,  # data_com == data so entra a partir do pregao seguinte (data-ex)
        )
    ).scalar_one()
    if soma == 0:
        return None

    return float(soma) / float(preco_row)


def get_pvp_serie(ticker: str, session: Session) -> pd.DataFrame:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return pd.DataFrame(columns=["data", "fechamento", "vp_por_cota", "pvp"])

    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not precos:
        return pd.DataFrame(columns=["data", "fechamento", "vp_por_cota", "pvp"])

    rel = get_relatorios_ajustados(ticker, session)
    rel = rel[rel["vp_aj"].notna()].sort_values("data_entrega")
    vp_por_entrega = [(pd.Timestamp(r.data_entrega).date(), float(r.vp_aj)) for r in rel.itertuples()]

    rows = []
    for d, fech in precos:
        fech_f = float(fech) if fech is not None else None
        vp_vigente = None
        for entrega, vp_val in reversed(vp_por_entrega):
            if entrega <= d:
                vp_vigente = vp_val
                break
        pvp = fech_f / vp_vigente if (fech_f is not None and vp_vigente is not None) else None
        rows.append({"data": d, "fechamento": fech_f, "vp_por_cota": vp_vigente, "pvp": pvp})

    return pd.DataFrame(rows)


def get_dy_serie(ticker: str, session: Session, janela_dias: int = 365) -> pd.DataFrame:
    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not precos:
        return pd.DataFrame(columns=["data", "fechamento", "dividendos_12m", "dy"])

    dividendos = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(Dividendo.ticker == ticker)
        .order_by(Dividendo.data_com.asc())
    ).all()

    div_dates = [d.data_com for d in dividendos]
    div_vals = [float(d.valor_cota) if d.valor_cota is not None else 0.0 for d in dividendos]

    rows = []
    for d, fech in precos:
        fech_f = float(fech) if fech is not None else None
        inicio = d - timedelta(days=janela_dias)
        soma = 0.0
        for i, dd in enumerate(div_dates):
            if inicio < dd < d:  # data_com == d so entra a partir do pregao seguinte
                soma += div_vals[i]
        dy = soma / fech_f if (fech_f is not None and fech_f > 0 and soma > 0) else None
        rows.append({"data": d, "fechamento": fech_f, "dividendos_12m": soma if soma > 0 else None, "dy": dy})

    return pd.DataFrame(rows)
