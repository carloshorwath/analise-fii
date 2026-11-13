from common import *
pd.set_option('display.width',250); pd.set_option('display.max_rows',400)
c=conn(); m=tick_cnpj(c)
d=pd.read_sql("select ticker,data_com,valor_cota,fonte from dividendos",c,parse_dates=['data_com'])
print(d.fonte.value_counts())
d['mes']=d.data_com.dt.to_period('M')
x=d.groupby('mes').ticker.nunique(); print(x['2021-06':'2022-12'].to_string()); print(x['2023-01':].describe())
print(x['2015-01':'2021-05'].describe())
# TR vs price: ratio aj/fech
p=pd.read_sql("select ticker,data,fechamento f,fechamento_aj a from precos_diarios where fechamento is not null",c,parse_dates=['data'])
p['ratio']=p.a/p.f
g=p.groupby('ticker')
# fraction of tickers with ratio change (i.e. dividends reinvested) per year
p['ano']=p.data.dt.year
p=p.sort_values(['ticker','data']); p['dlr']=np.log(p.ratio).groupby(p.ticker).diff()
print(p[p.dlr.abs()>1e-9].groupby(p.data.dt.to_period('Q')).ticker.nunique()['2020Q1':'2023Q2'])
print(p[p.ticker=='HGLG11'].set_index('data').ratio.resample('QE').last()['2019':'2023'])
