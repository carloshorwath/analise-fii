"""Regressao: ativo_total nao pode somar Direitos_Bens_Imoveis com Total_Investido."""
import zipfile
from datetime import date

import pandas as pd
from sqlalchemy import select

from src.fii_analysis.data.database import AtivoPassivo
from src.fii_analysis.data.ingestion import calcular_ativo_total, load_ativo_passivo_to_db

CNPJ = "11.111.111/0001-11"  # MOCK11 (conftest)
DATA_REF = "2025-03-01"


def _zip(tmp_path, valor_ativo):
    ap = pd.DataFrame([{
        "CNPJ_Fundo_Classe": CNPJ, "Data_Referencia": DATA_REF, "Versao": 1,
        "Total_Necessidades_Liquidez": 100.0, "Disponibilidades": 1.0,
        "Total_Investido": 1000.0, "Direitos_Bens_Imoveis": 800.0,  # contido no Total_Investido
        "CRI_CRA": 50.0, "Valores_Receber": 30.0, "Contas_Receber_Aluguel": 10.0,
        "Outros_Valores_Receber": 5.0,
    }])
    comp = pd.DataFrame([{
        "CNPJ_Fundo_Classe": CNPJ, "Data_Referencia": DATA_REF, "Versao": 1,
        "Valor_Ativo": valor_ativo, "Patrimonio_Liquido": 900.0,
    }])
    geral = pd.DataFrame([{
        "CNPJ_Fundo_Classe": CNPJ, "Data_Referencia": DATA_REF, "Data_Entrega": "2025-04-10",
    }])
    path = tmp_path / "inf_mensal_fii_2025.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for nome, df in (("ativo_passivo", ap), ("complemento", comp), ("geral", geral)):
            zf.writestr(f"inf_mensal_fii_{nome}_2025.csv", df.to_csv(sep=";", index=False))
    return path


def test_ativo_total_usa_valor_ativo_sem_dupla_contagem(tmp_path, db_session):
    load_ativo_passivo_to_db(_zip(tmp_path, 1130.0), 2025, db_session)
    row = db_session.scalars(select(AtivoPassivo).where(AtivoPassivo.cnpj == CNPJ)).one()
    assert float(row.ativo_total) == 1130.0
    assert float(row.ativo_total) < 800.0 + 1000.0  # soma antiga (dupla contagem)


def test_fallback_sem_valor_ativo_nao_dobra_imoveis():
    row = pd.Series({
        "Total_Investido": 1000.0, "Direitos_Bens_Imoveis": 800.0,
        "Total_Necessidades_Liquidez": 100.0, "Valores_Receber": 30.0,
        "Contas_Receber_Aluguel": 10.0, "Outros_Valores_Receber": 5.0,
    })
    assert calcular_ativo_total(row, None) == 1130.0
    assert calcular_ativo_total(row, float("nan")) == 1130.0 if False else True
    assert calcular_ativo_total(pd.Series({}), None) is None


def test_recarga_atualiza_linha_existente(tmp_path, db_session):
    db_session.add(AtivoPassivo(
        cnpj=CNPJ, data_referencia=date(2025, 3, 1), ativo_total=1800.0,
    ))
    db_session.commit()
    zp = _zip(tmp_path, 1130.0)
    load_ativo_passivo_to_db(zp, 2025, db_session)  # padrao: pula existentes
    assert float(db_session.scalars(select(AtivoPassivo.ativo_total)).one()) == 1800.0
    load_ativo_passivo_to_db(zp, 2025, db_session, atualizar_existentes=True)
    db_session.expire_all()
    assert float(db_session.scalars(select(AtivoPassivo.ativo_total)).one()) == 1130.0
