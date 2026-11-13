import sqlite3, numpy as np, pandas as pd, os, sys
ROOT = r"D:\analise-de-acoes-v3"
sys.path[:0] = [ROOT, ROOT + r"\src"]
OUT = os.path.join(os.environ.get("TEMP", r"C:\Users\carlo\AppData\Local\Temp"), "fii_painel")
DB = "file:" + ROOT.replace("\\", "/") + "/dados/fii_data.db?mode=ro"
def conn():
    return sqlite3.connect(DB, uri=True)
def ro_engine():
    from sqlalchemy import create_engine
    return create_engine("sqlite:///" + DB.replace("file:", "file:") + "&uri=true", creator=lambda: sqlite3.connect(DB, uri=True))
def tick_cnpj(c):
    t = pd.read_sql("select ticker,cnpj from tickers", c)
    u = pd.read_sql("select ticker,cnpj,data_referencia from universo order by data_referencia", c).drop_duplicates("ticker", keep="last")
    m = pd.concat([t[["ticker", "cnpj"]], u[["ticker", "cnpj"]]]).drop_duplicates("ticker", keep="first")
    return m
