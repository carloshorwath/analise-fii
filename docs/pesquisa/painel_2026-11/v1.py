from lib import *
c=conn(); pd.set_option('display.width',250)
r=pd.read_sql("select id,data_referencia,status from snapshot_runs order by data_referencia",c); print(r.tail(12))
P=pd.read_pickle(os.path.join(OUT,"painel_final.pkl"))
runs=r[r.status!='x']
m=pd.read_sql("select s.*,r.data_referencia d from snapshot_ticker_metrics s join snapshot_runs r on r.id=s.run_id",c,parse_dates=['d'])
dc=pd.read_sql("select d.ticker,r.data_referencia d,d.flag_destruicao_capital fl,d.pvp_percentil pp from snapshot_decisions d join snapshot_runs r on r.id=d.run_id",c,parse_dates=['d'])
x=m.merge(P,left_on=['ticker','d'],right_on=['ticker','t'])
print("pares snapshot x painel:",len(x), x.d.nunique())
for a,b in [('pvp','pvp'),('pvp_percentil','pvp_pct'),('dy_12m','dy12'),('dy_gap','gap'),('dy_gap_percentil','dygap_pct'),('volatilidade_anual','vol'),('beta_ifix','beta'),('max_drawdown','mdd'),('score_total_x','score'),('liquidez_21d_brl','liq21')]:
    if a not in x: continue
    d=(x[a].astype(float)-x[b].astype(float)).abs(); ok=x[a].notna()&x[b].notna()
    print(a,b,"n",ok.sum(),"mediana |dif|",d[ok].median(),"max",d[ok].max(), "corr", np.corrcoef(x[a][ok].astype(float),x[b][ok].astype(float))[0,1] if ok.sum()>2 else None)
y=dc.merge(P,left_on=['ticker','d'],right_on=['ticker','t'])
print("flag destr: n",len(y),"concordancia",(y.fl.astype(float)==y.destr.astype(float)).mean())
print(y.groupby(['fl','destr']).size())
