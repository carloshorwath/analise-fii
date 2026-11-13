from common import *
c=conn(); pd.set_option('display.width',250)
print(pd.read_sql("select * from eventos_corporativos",c).T)
print(pd.read_sql("select ticker,count(*),min(data),max(data) from precos_diarios where ticker in ('SNFF11','HSRE11','GAME11') group by 1",c))
print(pd.read_sql("select ticker,data,fechamento,volume from precos_diarios where ticker='SNFF11' order by data desc limit 5",c))
print(pd.read_sql("select * from tickers where ticker in ('SNFF11','HSRE11','GAME11','HREC11')",c).T)
