from datetime import date

from sqlalchemy import select, text

from src.fii_analysis.data.database import AtivoPassivo, get_cnpj_by_ticker


LIMITE_CLASSIFICACAO = 0.60  # fracao do ativo (config sugerida: composicao.limite_classificacao)

_COLS_SOCIEDADES = ("acoes_sociedades_fii", "cotas_sociedades_fii")


def _tem_colunas_sociedades(session) -> bool:
    """True se a tabela ativo_passivo ja tem as colunas de sociedades (migracao 009).
    Evita quebrar leitores em bancos ainda nao migrados."""
    cols = {r[1] for r in session.execute(text("PRAGMA table_info(ativo_passivo)")).all()}
    return all(c in cols for c in _COLS_SOCIEDADES)


def composicao_ativo(ticker: str, session=None) -> dict:
    """Composicao do ativo do ultimo informe, em fracao do ativo_total.

    Parcelas MUTUAMENTE EXCLUSIVAS (somam ~100%; ``pct_outros`` e o residual):
      imoveis (diretos) + sociedades imobiliarias + recebiveis (CRI/LCI) + caixa
      + investimentos (resto de total_investido) + valores a receber + outros mobiliarios.

    Verificado nos informes CVM: Valores_Receber JA CONTEM Contas_Receber_Aluguel;
    Total_Necessidades_Liquidez JA CONTEM Disponibilidades; Total_Investido contem
    imoveis, titulos e participacoes em sociedades.
    ``pct_imoveis_total`` = diretos + sociedades (base da classificacao Tijolo).
    Cotas de outros FIIs NAO entram em imoveis.
    """
    cnpj = get_cnpj_by_ticker(ticker, session)
    if cnpj is None:
        return {"pct_imoveis": None, "pct_recebiveis": None, "pct_caixa": None, "ativo_total": None, "data_ref": None}

    sociedades_ok = _tem_colunas_sociedades(session)
    colunas = [
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
    ]
    if sociedades_ok:
        colunas += [AtivoPassivo.acoes_sociedades_fii, AtivoPassivo.cotas_sociedades_fii]
    row = session.execute(
        select(*colunas)
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
    sociedades = (_s(row.acoes_sociedades_fii) + _s(row.cotas_sociedades_fii)) if sociedades_ok else 0.0
    titulos = _s(row.cri) + _s(row.cri_cra) + _s(row.lci) + _s(row.lci_lca)
    # Caixa: Total_Necessidades_Liquidez ja inclui Disponibilidades (nao somar os dois)
    caixa = max(_s(row.total_necessidades_liquidez), _s(row.disponibilidades))
    # Valores_Receber ja inclui Contas_Receber_Aluguel; so recorre ao aluguel se o total faltar
    valores_receber = _s(row.valores_receber) if row.valores_receber is not None else _s(row.contas_receber_aluguel)
    # total_investido é SUPER conjunto de imoveis + sociedades + titulos — subtrair para evitar dupla contagem
    outros_investimentos = max(_s(row.total_investido) - imoveis - sociedades - titulos, 0)
    outros_mobliarios = _s(row.outros_valores_mobliarios)

    # Calcular "outros" como residual (garante que tudo soma a 100%)
    classificado = imoveis + sociedades + titulos + caixa + outros_investimentos + valores_receber + outros_mobliarios
    outros = max(ativo_total - classificado, 0)

    return {
        "pct_imoveis": imoveis / ativo_total,
        "pct_sociedades_imobiliarias": sociedades / ativo_total,
        "pct_imoveis_total": (imoveis + sociedades) / ativo_total,
        "sociedades_disponivel": sociedades_ok and row.acoes_sociedades_fii is not None,
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
    # Imoveis = diretos + participacoes em sociedades de atividade FII (SPE); sem a coluna, so diretos
    if comp.get("pct_imoveis_total", comp["pct_imoveis"]) >= LIMITE_CLASSIFICACAO:
        return "Tijolo"
    if comp["pct_recebiveis"] >= LIMITE_CLASSIFICACAO:
        return "Papel"
    return "Hibrido"
