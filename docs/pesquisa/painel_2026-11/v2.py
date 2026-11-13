from lib import *
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.fii_analysis.features.valuation import get_pvp_percentil, get_dy_gap, get_dy_gap_percentil, get_dy_n_meses
from src.fii_analysis.features.indicators import get_pvp
from src.fii_analysis.features.saude import flag_destruicao_capital
eng = create_engine("sqlite://", creator=lambda: sqlite3.connect(DB, uri=True)); S = Session(eng)
P=pd.read_pickle(os.path.join(OUT,"painel_final.pkl"))
s=P[P.dygap_pct.notna()].sample(40,random_state=1)
rows=[]
for r in s.itertuples():
    t=r.t.date()
    pp,_=get_pvp_percentil(r.ticker,t,504,S); pv=get_pvp(r.ticker,t,S); g=get_dy_gap(r.ticker,t,S); gp=get_dy_gap_percentil(r.ticker,t,252,S)
    fl=flag_destruicao_capital(r.ticker,S,t=t)
    rows.append(dict(tk=r.ticker,t=t,pvp_me=r.pvp,pvp_sys=pv,pp_me=r.pvp_pct,pp_sys=pp,gap_me=r.gap,gap_sys=g,gp_me=r.dygap_pct,gp_sys=gp,fl_me=r.destr,fl_sys=fl['destruicao']))
d=pd.DataFrame(rows)
for a,b in [('pvp_me','pvp_sys'),('pp_me','pp_sys'),('gap_me','gap_sys'),('gp_me','gp_sys')]:
    dd=(d[a]-d[b]).abs(); print(a,"n",d[[a,b]].notna().all(axis=1).sum(),"max|dif|",dd.max(),"mediana",dd.median(),"n com dif>1e-6:",(dd>1e-6).sum())
print("flag concord:",(d.fl_me==d.fl_sys).mean())
print(d[(d.gp_me-d.gp_sys).abs()>0.5].head(10))
