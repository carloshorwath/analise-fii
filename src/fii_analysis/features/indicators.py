from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select

from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal, Ticker


def _get_cnpj(ticker: str, session) -> str | None:
    return session.execute(
        select(Ticker.cnpj).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()


# VP/PL ajustado: subtrai dividendos pagos apos data_referencia do relatorio e antes de t (point-in-time)
def get_vp_point_in_time(cnpj: str, ticker: str, data: date, session) -> dict | None:
    rel = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.vp_por_cota,
            RelatorioMensal.patrimonio_liq,
            RelatorioMensal.cotas_emitidas,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.data_entrega <= data,
            RelatorioMensal.vp_por_cota.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(1)
    ).first()
    if rel is None:
        return None

    vp_relatorio = float(rel.vp_por_cota)
    pl = float(rel.patrimonio_liq) if rel.patrimonio_liq is not None else None
    cotas = int(rel.cotas_emitidas) if rel.cotas_emitidas is not None else None
    data_ref = rel.data_referencia

    divs = session.execute(
        select(Dividendo.valor_cota)
        .where(
            Dividendo.ticker == ticker,
            Dividendo.data_com > data_ref,
            Dividendo.data_com < data,
            Dividendo.valor_cota.isnot(None),
        )
    ).scalars().all()

    soma_div_cota = sum(float(v) for v in divs)

    if pl is None or cotas is None:
        vp_ajustado = vp_relatorio - soma_div_cota
        return {
            "vp_relatorio": vp_relatorio,
            "pl_ajustado": None,
            "vp_ajustado": vp_ajustado,
            "dividendos_subtraidos": len(divs),
            "valor_subtraido": soma_div_cota,
        }

    valor_subtraido = soma_div_cota * cotas
    pl_ajustado = pl - valor_subtraido
    vp_ajustado = pl_ajustado / cotas if cotas > 0 else vp_relatorio - soma_div_cota

    return {
        "vp_relatorio": vp_relatorio,
        "pl_ajustado": pl_ajustado,
        "vp_ajustado": vp_ajustado,
        "dividendos_subtraidos": len(divs),
        "valor_subtraido": valor_subtraido,
    }


def get_pvp(ticker: str, data: date, session) -> float | None:
    preco_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data == data,
        )
    ).scalar_one_or_none()
    if preco_row is None:
        return None

    cnpj = _get_cnpj(ticker, session)
    if cnpj is None:
        return None

    vp_info = get_vp_point_in_time(cnpj, ticker, data, session)
    if vp_info is None:
        return None

    vp = vp_info["vp_ajustado"]
    if vp is None:
        return None

    return float(preco_row) / float(vp)


def get_dy_trailing(ticker: str, data: date, session, janela_dias: int = 365) -> float | None:
    preco_row = session.execute(
        select(PrecoDiario.fechamento).where(
            PrecoDiario.ticker == ticker,
            PrecoDiario.data == data,
        )
    ).scalar_one_or_none()
    if preco_row is None:
        return None

    inicio = data - timedelta(days=janela_dias)
    soma = session.execute(
        select(func.coalesce(func.sum(Dividendo.valor_cota), 0)).where(
            Dividendo.ticker == ticker,
            Dividendo.data_com > inicio,
            Dividendo.data_com <= data,
        )
    ).scalar_one()
    if soma == 0:
        return None

    return float(soma) / float(preco_row)


def get_pvp_serie(ticker: str, session) -> pd.DataFrame:
    cnpj = _get_cnpj(ticker, session)
    if cnpj is None:
        return pd.DataFrame(columns=["data", "fechamento", "vp_por_cota", "pvp"])

    precos = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento)
        .where(PrecoDiario.ticker == ticker)
        .order_by(PrecoDiario.data.asc())
    ).all()
    if not precos:
        return pd.DataFrame(columns=["data", "fechamento", "vp_por_cota", "pvp"])

    relatorios = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.data_entrega,
            RelatorioMensal.vp_por_cota,
            RelatorioMensal.patrimonio_liq,
            RelatorioMensal.cotas_emitidas,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.vp_por_cota.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_entrega.asc())
    ).all()

    rel_ordenados = [
        {
            "data_ref": r.data_referencia,
            "data_entrega": r.data_entrega,
            "vp": float(r.vp_por_cota),
            "pl": float(r.patrimonio_liq) if r.patrimonio_liq is not None else None,
            "cotas": int(r.cotas_emitidas) if r.cotas_emitidas is not None else None,
        }
        for r in relatorios
    ]

    divs = session.execute(
        select(Dividendo.data_com, Dividendo.valor_cota)
        .where(
            Dividendo.ticker == ticker,
            Dividendo.valor_cota.isnot(None),
        )
        .order_by(Dividendo.data_com.asc())
    ).all()
    div_dates = [d.data_com for d in divs]
    div_vals = [float(d.valor_cota) for d in divs]

    rows = []
    for d, fech in precos:
        fech_f = float(fech) if fech is not None else None
        vp_vigente = None
        rel_ativo = None
        for r in reversed(rel_ordenados):
            if r["data_entrega"] <= d:
                vp_vigente = r["vp"]
                rel_ativo = r
                break
        if vp_vigente is not None and rel_ativo is not None and rel_ativo["pl"] is not None and rel_ativo["cotas"] is not None:
            data_ref = rel_ativo["data_ref"]
            cotas = rel_ativo["cotas"]
            pl = rel_ativo["pl"]
            valor_sub = sum(
                div_vals[i] * cotas
                for i, dd in enumerate(div_dates)
                if data_ref < dd <= d
            )
            pl_ajustado = pl - valor_sub
            vp_usado = pl_ajustado / cotas if cotas > 0 else vp_vigente
        else:
            vp_usado = vp_vigente
        pvp = fech_f / vp_usado if (fech_f is not None and vp_usado is not None) else None
        rows.append({"data": d, "fechamento": fech_f, "vp_por_cota": vp_usado, "pvp": pvp})

    return pd.DataFrame(rows)


def get_dy_serie(ticker: str, session, janela_dias: int = 365) -> pd.DataFrame:
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
            if inicio < dd <= d:
                soma += div_vals[i]
        dy = soma / fech_f if (fech_f is not None and fech_f > 0 and soma > 0) else None
        rows.append({"data": d, "fechamento": fech_f, "dividendos_12m": soma if soma > 0 else None, "dy": dy})

    return pd.DataFrame(rows)
