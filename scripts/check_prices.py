import sqlite3
import pandas as pd

conn = sqlite3.connect('D:/analise-de-acoes/dados/fii_data.db')
query = """
SELECT data, fechamento, fechamento_aj 
FROM precos_diarios 
WHERE ticker='KNIP11' AND data BETWEEN '2025-01-01' AND '2026-03-31'
ORDER BY data
"""
df = pd.read_sql_query(query, conn)
df['data_dt'] = pd.to_datetime(df['data'])

dates_of_interest = ['2026-01-30', '2025-12-30', '2025-11-28', '2025-10-31', '2025-09-30']
for d in dates_of_interest:
    target = pd.to_datetime(d)
    print(f"\nAround {d}:")
    mask = (df['data_dt'] >= target - pd.Timedelta(days=2)) & (df['data_dt'] <= target + pd.Timedelta(days=2))
    print(df[mask])
conn.close()
