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
            AtivoPassivo.total_investido,
            AtivoPassivo.total_necessidades_liquidez,
            AtivoPassivo.valores_receber,
            AtivoPassivo.contas_receber_aluguel,
            AtivoPassivo.outros_valores_mobliarios,
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
        return {
            "pct_imoveis": None, "pct_recebiveis": None, "pct_caixa": None,
            "pct_investimentos": None, "pct_valores_receber": None, "pct_outros": None,
            "ativo_total": None, "data_ref": None,
        }

    ativo_total = float(row.ativo_total)
    if ativo_total == 0:
        return {
            "pct_imoveis": None, "pct_recebiveis": None, "pct_caixa": None,
            "pct_investimentos": None, "pct_valores_receber": None, "pct_outros": None,
            "ativo_total": 0.0, "data_ref": row.data_referencia,
        }

    def _s(val):
        return float(val or 0)

    imoveis = _s(row.direitos_bens_imoveis)
    titulos = _s(row.cri) + _s(row.cri_cra) + _s(row.lci) + _s(row.lci_lca)
    # Caixa: disponibilidades + necessidades de liquidez (muitos FIIs reportam caixa aqui)
    caixa = _s(row.disponibilidades) + _s(row.total_necessidades_liquidez)
    valores_receber = _s(row.valores_receber) + _s(row.contas_receber_aluguel)
    # total_investido é SUPER conjunto de imoveis + titulos — subtrair para evitar dupla contagem
    outros_investimentos = max(_s(row.total_investido) - imoveis - titulos, 0)
    outros_mobliarios = _s(row.outros_valores_mobliarios)

    # Calcular "outros" como residual (garante que tudo soma a 100%)
    classificado = imoveis + titulos + caixa + outros_investimentos + valores_receber + outros_mobliarios
    outros = max(ativo_total - classificado, 0)

    return {
        "pct_imoveis": imoveis / ativo_total,
        "pct_recebiveis": titulos / ativo_total,
        "pct_caixa": caixa / ativo_total,
        "pct_investimentos": outros_investimentos / ativo_total,
        "pct_valores_receber": valores_receber / ativo_total,
        "pct_outros": outros / ativo_total,
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
