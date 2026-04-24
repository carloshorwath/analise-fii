from datetime import date

import pandas as pd
from sqlalchemy import select

from src.fii_analysis.config_yaml import get_threshold
from src.fii_analysis.data.database import AtivoPassivo, PrecoDiario, RelatorioMensal, get_cnpj_by_ticker, get_ultimo_preco_date
from src.fii_analysis.features.indicators import get_pvp, get_pvp_serie
from src.fii_analysis.features.valuation import get_dy_n_meses


def get_payout_historico(ticker: str, cnpj: str | None = None, meses: int = 24, session=None) -> tuple[pd.DataFrame, int]:
    if cnpj is None:
        cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return pd.DataFrame(columns=["data_referencia", "rentab_efetiva_pct", "rentab_patrimonial_pct", "distribuindo_mais_que_gera"]), 0

    rows = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.rentab_efetiva,
            RelatorioMensal.rentab_patrim,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.rentab_efetiva.isnot(None),
            RelatorioMensal.rentab_patrim.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(meses)
    ).all()

    if not rows:
        return pd.DataFrame(columns=["data_referencia", "rentab_efetiva_pct", "rentab_patrimonial_pct", "distribuindo_mais_que_gera"]), 0

    records = []
    for r in reversed(rows):
        ef = float(r.rentab_efetiva) if r.rentab_efetiva is not None else None
        pa = float(r.rentab_patrim) if r.rentab_patrim is not None else None
        records.append({
            "data_referencia": r.data_referencia,
            "rentab_efetiva_pct": ef,
            "rentab_patrimonial_pct": pa,
            "distribuindo_mais_que_gera": ef is not None and pa is not None and pa > ef,
        })

    df = pd.DataFrame(records)
    meses_consec = 0
    for _, row in df.iloc[::-1].iterrows():
        if row["distribuindo_mais_que_gera"]:
            meses_consec += 1
        else:
            break

    return df, meses_consec


def get_efetiva_vs_patrimonial_resumo(ticker: str, cnpj: str | None = None, session=None) -> dict:
    if cnpj is None:
        cnpj = get_cnpj_by_ticker(ticker, session)
    
    resultado = {
        "meses_consecutivos_alerta": 0,
        "meses_saudaveis_6m": 0,
        "total_6m": 0,
    }
    if not cnpj:
        return resultado

    rows = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.rentab_efetiva,
            RelatorioMensal.rentab_patrim,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.rentab_efetiva.isnot(None),
            RelatorioMensal.rentab_patrim.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(6)
    ).all()

    if not rows:
        return resultado

    consec = 0
    saudaveis = 0
    total = 0
    ainda_consecutivo = True
    for r in rows:
        total += 1
        ef = float(r.rentab_efetiva) if r.rentab_efetiva is not None else None
        pa = float(r.rentab_patrim) if r.rentab_patrim is not None else None
        saudavel = ef is not None and pa is not None and pa >= 0 and ef >= pa
        if saudavel:
            saudaveis += 1
        if not saudavel:
            if ainda_consecutivo:
                consec += 1
        else:
            ainda_consecutivo = False

    resultado["meses_consecutivos_alerta"] = consec
    resultado["meses_saudaveis_6m"] = saudaveis
    resultado["total_6m"] = total
    return resultado


def get_dy_medias(ticker: str, cnpj: str | None = None, session=None) -> dict:
    if cnpj is None:
        cnpj = get_cnpj_by_ticker(ticker, session)

    ultimo = get_ultimo_preco_date(ticker, session)

    if ultimo is None:
        return {"dy_12m_atual": None, "media_dy_2anos": None, "media_dy_5anos": None, "percentil_na_serie_completa": None}

    dy_12m = get_dy_n_meses(ticker, ultimo, 12, session)
    dy_24m = get_dy_n_meses(ticker, ultimo, 24, session)
    dy_60m = get_dy_n_meses(ticker, ultimo, 60, session)

    if not cnpj:
        return {
            "dy_12m_atual": dy_12m,
            "media_dy_2anos": dy_24m,
            "media_dy_5anos": dy_60m,
            "percentil_na_serie_completa": None,
        }

    relatorios = session.execute(
        select(RelatorioMensal.dy_mes_pct)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.dy_mes_pct.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.asc())
    ).scalars().all()

    pct = None
    if relatorios and dy_12m is not None:
        dy_mensal = [float(d) for d in relatorios]
        dy_mensal_anualizado = [d * 12 for d in dy_mensal if d is not None]
        if dy_mensal_anualizado:
            dy_anual = dy_12m * 100
            pct = float(sum(1 for d in dy_mensal_anualizado if d <= dy_anual) / len(dy_mensal_anualizado) * 100)

    return {
        "dy_12m_atual": dy_12m,
        "media_dy_2anos": dy_24m,
        "media_dy_5anos": dy_60m,
        "percentil_na_serie_completa": pct,
    }


def get_pvp_medias(ticker: str, cnpj: str | None = None, session=None) -> dict:
    if cnpj is None:
        cnpj = get_cnpj_by_ticker(ticker, session)

    ultimo = get_ultimo_preco_date(ticker, session)

    if ultimo is None:
        return {"pvp_atual": None, "media_pvp_2anos": None, "media_pvp_5anos": None, "serie_pvp": pd.Series(dtype=float)}

    if hasattr(ultimo, "date"):
        ultimo = ultimo.date()

    pvp_atual = get_pvp(ticker, ultimo, session)

    serie_df = get_pvp_serie(ticker, session)
    if serie_df.empty:
        return {"pvp_atual": pvp_atual, "media_pvp_2anos": None, "media_pvp_5anos": None, "serie_pvp": pd.Series(dtype=float)}

    serie_pvp = serie_df.set_index("data")["pvp"].dropna()

    janela_2a = serie_pvp.iloc[-504:] if len(serie_pvp) >= 504 else serie_pvp
    janela_5a = serie_pvp.iloc[-1260:] if len(serie_pvp) >= 1260 else serie_pvp

    return {
        "pvp_atual": pvp_atual,
        "media_pvp_2anos": float(janela_2a.mean()) if len(janela_2a) > 0 else None,
        "media_pvp_5anos": float(janela_5a.mean()) if len(janela_5a) > 0 else None,
        "serie_pvp": serie_pvp,
    }


def get_pl_cotas_historico(ticker: str, cnpj: str | None = None, meses: int = 36, session=None) -> pd.DataFrame:
    if cnpj is None:
        cnpj = get_cnpj_by_ticker(ticker, session)
    if not cnpj:
        return pd.DataFrame(columns=["data_referencia", "patrimonio_liq", "cotas_emitidas", "vp_por_cota"])

    rows = session.execute(
        select(
            RelatorioMensal.data_referencia,
            RelatorioMensal.patrimonio_liq,
            RelatorioMensal.cotas_emitidas,
            RelatorioMensal.vp_por_cota,
        )
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.patrimonio_liq.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(meses)
    ).all()

    if not rows:
        return pd.DataFrame(columns=["data_referencia", "patrimonio_liq", "cotas_emitidas", "vp_por_cota"])

    records = []
    for r in reversed(rows):
        records.append({
            "data_referencia": r.data_referencia,
            "patrimonio_liq": float(r.patrimonio_liq) if r.patrimonio_liq is not None else None,
            "cotas_emitidas": int(r.cotas_emitidas) if r.cotas_emitidas is not None else None,
            "vp_por_cota": float(r.vp_por_cota) if r.vp_por_cota is not None else None,
        })

    return pd.DataFrame(records)


def get_alavancagem(ticker: str, cnpj: str | None = None, session=None) -> dict:
    if cnpj is None:
        cnpj = get_cnpj_by_ticker(ticker, session)

    resultado = {
        "ativo_total": None,
        "patrimonio_liquido": None,
        "indice": None,
        "alavancado": False,
        "data_ref": None,
    }

    if not cnpj:
        return resultado

    ap = session.execute(
        select(AtivoPassivo.ativo_total, AtivoPassivo.data_referencia)
        .where(
            AtivoPassivo.cnpj == cnpj,
            AtivoPassivo.ativo_total.isnot(None),
            AtivoPassivo.data_entrega.isnot(None),
        )
        .order_by(AtivoPassivo.data_referencia.desc())
        .limit(1)
    ).first()

    pl_row = session.execute(
        select(RelatorioMensal.patrimonio_liq, RelatorioMensal.data_referencia)
        .where(
            RelatorioMensal.cnpj == cnpj,
            RelatorioMensal.patrimonio_liq.isnot(None),
            RelatorioMensal.data_entrega.isnot(None),
        )
        .order_by(RelatorioMensal.data_referencia.desc())
        .limit(1)
    ).first()

    if pl_row is None:
        return resultado

    resultado["patrimonio_liquido"] = float(pl_row.patrimonio_liq)
    resultado["data_ref"] = pl_row.data_referencia

    if ap is not None:
        resultado["ativo_total"] = float(ap.ativo_total)

    if resultado["ativo_total"] is not None and resultado["patrimonio_liquido"] > 0:
        resultado["indice"] = resultado["ativo_total"] / resultado["patrimonio_liquido"]
        resultado["alavancado"] = resultado["indice"] > get_threshold("alavancagem_limite", 1.05)

    return resultado


def classificar_alerta_distribuicao(resumo: dict) -> tuple[str, str]:
    consec_alerta = resumo["meses_consecutivos_alerta"]
    saudaveis = resumo["meses_saudaveis_6m"]
    total = resumo["total_6m"]

    if consec_alerta >= get_threshold("meses_consec_alerta", 3):
        return ("error", f"Atencao: distribuindo mais que gera ha {consec_alerta} meses seguidos ({saudaveis}/{total})")
    elif saudaveis < 4:
        return ("warning", f"Tendencia de alerta: {saudaveis} de {total} meses saudaveis")
    else:
        return ("success", f"Geracao saudavel nos ultimos 6 meses ({saudaveis}/{total})")
