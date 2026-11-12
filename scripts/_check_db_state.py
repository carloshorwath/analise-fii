"""Inspecao ad-hoc do estado do banco (debug)."""
import sqlite3

con = sqlite3.connect(r"D:\analise-de-acoes-v3\dados\fii_data.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("TABELAS:", tables)
for t in ["universo", "snapshot_opportunities", "llm_journal", "decisoes_log"]:
    if t in tables:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n} rows")
    else:
        print(f"{t}: NAO EXISTE")
print("precos_diarios:", cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker), MAX(data) FROM precos_diarios").fetchone())
print("relatorios_mensais:", cur.execute("SELECT COUNT(*), COUNT(DISTINCT cnpj) FROM relatorios_mensais").fetchone())
print("snapshot_runs ultimos:")
for row in cur.execute("SELECT id, data_referencia, status, universe_scope FROM snapshot_runs ORDER BY id DESC LIMIT 6"):
    print("  ", row)
if "universo" in tables:
    print("universo sample:", cur.execute("SELECT ticker, cnpj, peso_ifix, data_referencia, fonte FROM universo LIMIT 5").fetchall())
con.close()
