import pandas as pd
import sqlite3
import os
from pathlib import Path

# Configurações
EXCEL_PATH = r'D:/analise-de-acoes/dados/FundsExplorer/KNIP11.xlsx'
DB_PATH = r'D:/analise-de-acoes/dados/fii_data.db'
OUTPUT_CSV = r'D:/analise-de-acoes/dados/validacao_knip11.csv'
TICKER = 'KNIP11'

def validate():
    # 1. Ler Excel
    df_xlsx = pd.read_excel(EXCEL_PATH)
    # Renomear colunas para facilitar
    # Colunas: 'Data Base', 'Valor por Cota (R$)', 'Fechamento (R$)', 'Yield 1M'
    df_xlsx = df_xlsx[['Data Base', 'Valor por Cota (R$)', 'Fechamento (R$)', 'Yield 1M']].copy()
    df_xlsx.columns = ['data_com_xlsx', 'valor_xlsx', 'preco_xlsx', 'dy_xlsx']
    df_xlsx['data_com_xlsx'] = pd.to_datetime(df_xlsx['data_com_xlsx']).dt.date

    # 2. Ler SQLite - Dividendos
    conn = sqlite3.connect(DB_PATH)
    query_div = f"SELECT data_com, valor_cota FROM dividendos WHERE ticker='{TICKER}' ORDER BY data_com"
    df_db_div = pd.read_sql_query(query_div, conn)
    df_db_div['data_com'] = pd.to_datetime(df_db_div['data_com']).dt.date
    df_db_div.columns = ['data_com_db', 'valor_db']

    # 3. Ler SQLite - Preços
    query_precos = f"SELECT data, fechamento FROM precos_diarios WHERE ticker='{TICKER}' ORDER BY data"
    df_db_precos = pd.read_sql_query(query_precos, conn)
    df_db_precos['data'] = pd.to_datetime(df_db_precos['data']).dt.date
    df_db_precos.columns = ['data_preco_db', 'preco_db']

    # 4. Merge Excel com Dividendos do Banco
    df_val = pd.merge(df_xlsx, df_db_div, left_on='data_com_xlsx', right_on='data_com_db', how='left')

    # 5. Merge com Preços do Banco (na data_com)
    df_val = pd.merge(df_val, df_db_precos, left_on='data_com_xlsx', right_on='data_preco_db', how='left')

    # 6. Cálculos e Validações
    # Tolerâncias
    TOL_VALOR = 0.01
    TOL_PRECO = 0.05
    TOL_DY = 0.0005  # 0.05%

    # Data OK: se encontrou no banco
    df_val['data_ok'] = df_val['data_com_db'].notnull()

    # Valor OK
    df_val['valor_ok'] = (abs(df_val['valor_xlsx'] - df_val['valor_db']) <= TOL_VALOR)

    # Preço OK
    df_val['preco_ok'] = (abs(df_val['preco_xlsx'] - df_val['preco_db']) <= TOL_PRECO)

    # DY DB (calculado)
    df_val['dy_db'] = df_val['valor_db'] / df_val['preco_db']

    # DY OK
    # Nota: dy_xlsx na planilha geralmente está em decimal (ex: 0.0123 para 1.23%) ou já multiplicado?
    # Vamos assumir que se o valor for > 1, está em porcentagem (ex: 0.85 para 0.85%).
    # Pelo print anterior, Yield 1M parece ser porcentagem (ex: 0.85).
    def check_dy(row):
        if pd.isnull(row['dy_db']) or pd.isnull(row['dy_xlsx']):
            return False
        dy_xlsx_norm = row['dy_xlsx'] / 100.0 if row['dy_xlsx'] > 0.1 else row['dy_xlsx'] # heurística simples
        return abs(dy_xlsx_norm - row['dy_db']) <= TOL_DY

    df_val['dy_ok'] = df_val.apply(check_dy, axis=1)

    # 7. Salvar CSV
    df_val.to_csv(OUTPUT_CSV, index=False)

    # 8. Resumo
    total = len(df_xlsx)
    data_ok = df_val['data_ok'].sum()
    valor_ok = df_val['valor_ok'].sum()
    preco_ok = df_val['preco_ok'].sum()
    dy_ok = df_val['dy_ok'].sum()

    print(f"RESUMO DA VALIDAÇÃO - {TICKER}")
    print(f"Total de registros na planilha: {total}")
    print(f"Registros encontrados no banco (Data Com): {data_ok}")
    print(f"Valores batem (tolerância R$0.01): {valor_ok}")
    print(f"Preços batem (tolerância R$0.05): {preco_ok}")
    print(f"DY bate (tolerância 0.05%): {dy_ok}")

    divergencias = df_val[~(df_val['data_ok'] & df_val['valor_ok'] & df_val['preco_ok'])]
    if not divergencias.empty:
        print("\nDivergências encontradas (primeiras 5):")
        print(divergencias[['data_com_xlsx', 'valor_xlsx', 'valor_db', 'preco_xlsx', 'preco_db']].head())
    else:
        print("\nNenhuma divergência encontrada nos dados principais!")

if __name__ == "__main__":
    validate()
