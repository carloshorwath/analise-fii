from common import *
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
eng=create_engine("sqlite://", creator=lambda: sqlite3.connect(DB, uri=True))
s=Session(eng)
from src.fii_analysis.features.indicators import get_relatorios_ajustados
from src.fii_analysis.features.saude import flag_destruicao_capital
import datetime as dt
t0=time.time()
r=get_relatorios_ajustados('HGLG11',s); print(r.tail(3).T, len(r), time.time()-t0)
t0=time.time()
f=flag_destruicao_capital('HGLG11',s,t=dt.date(2025,6,30)); print({k:f[k] for k in ['destruicao','gravidade','score_saude','pct_3m','pct_6m']}, time.time()-t0)
print(s.bind.url)
