from datetime import date

from sqlalchemy import select

from src.fii_analysis.data.database import AtivoPassivo, get_cnpj_by_ticker


def composicao_ativo(ticker: str, session=None) -> dict:
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return {"pct_imoveis": None, "pct_recebiveis": None, "pct_caixa": None, "ativo_total": None, "data_ref": None}

    row = session.execute(
        select(
            AtivoPassivo.data_referencia,
            AtivoPassivo.direitos_bens_imoveis,
            AtivoPassivo.cri,
            AtivoPassivo.cri_cra,
            AtivoPassivo.lci,
            AtivoPassivo.lci_lca,
            AtivoPassivo.disponibilidades,
            AtivoPassivo.ativo_total,
        )
        .where(
            AtivoPassivo.cnpj == cnpj,
            AtivoPassivo.ativo_total.isnot(None),
        )
        .order_by(AtivoPassivo.data_referencia.desc())
        .limit(1)
    ).first()

    if row is None:
        return {"pct_imoveis": None, "pct_recebiveis": None, "pct_caixa": None, "ativo_total": None, "data_ref": None}

    ativo_total = float(row.ativo_total)
    if ativo_total == 0:
        return {"pct_imoveis": None, "pct_recebiveis": None, "pct_caixa": None, "ativo_total": 0.0, "data_ref": row.data_referencia}

    imoveis = float(row.direitos_bens_imoveis or 0)
    recebiveis = float(row.cri or 0) + float(row.cri_cra or 0) + float(row.lci or 0) + float(row.lci_lca or 0)
    caixa = float(row.disponibilidades or 0)

    return {
        "pct_imoveis": imoveis / ativo_total,
        "pct_recebiveis": recebiveis / ativo_total,
        "pct_caixa": caixa / ativo_total,
        "ativo_total": ativo_total,
        "data_ref": row.data_referencia,
    }


def classificar_fii(ticker: str, session=None) -> str:
    comp = composicao_ativo(ticker, session)
    if comp["pct_imoveis"] is None:
        return "Indefinido"
    if comp["pct_imoveis"] >= 0.60:
        return "Tijolo"
    if comp["pct_recebiveis"] >= 0.60:
        return "Papel"
    return "Hibrido"
