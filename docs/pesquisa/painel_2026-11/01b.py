from common import *
pd.set_option('display.width',250); pd.set_option('display.max_rows',400)
c=conn(); m=tick_cnpj(c)
cen=pd.read_csv(os.path.join(OUT,'censo_por_ticker.csv'),parse_dates=['primeiro','ultimo'],index_col=0)
d=pd.read_sql("select ticker,data_com,valor_cota from dividendos",c,parse_dates=['data_com'])
fd=d.groupby('ticker').data_com.min().rename('prim_div')
x=cen.join(fd); x['lag_dias']=(x.prim_div-x.primeiro.clip(lower=pd.Timestamp('2020-12-01'))).dt.days
print(x[['primeiro','prim_div','lag_dias']].sort_values('lag_dias',ascending=False).head(40))
print((x.lag_dias>60).sum())
# dividendos por ticker-mes vs informe dy_mes_pct
r=pd.read_sql("select cnpj,data_referencia,dy_mes_pct,rentab_efetiva from relatorios_mensais",c,parse_dates=['data_referencia']).merge(m,on='cnpj')
d['mes']=d.data_com.dt.to_period('M'); dm=d.groupby(['ticker','mes']).valor_cota.sum().rename('div').reset_index()
r['mes']=r.data_referencia.dt.to_period('M'); j=r.merge(dm,on=['ticker','mes'],how='left')
print("informes:",len(j)," sem dividendo no mes com dy_mes_pct>0:",((j['div'].isna())&(j.dy_mes_pct>0)).sum(), " com div e dy=0/NaN:",((j['div']>0)&~(j.dy_mes_pct>0)).sum())
j['ano']=j.data_referencia.dt.year
print(j.groupby('ano').apply(lambda g: pd.Series({'n':len(g),'sem_div_mas_dy':((g['div'].isna())&(g.dy_mes_pct>0)).mean()})))
print(j.dy_mes_pct.describe())
print(j[(j['div'].isna())&(j.dy_mes_pct>0)].groupby('ticker').size().sort_values(ascending=False).head(20))
