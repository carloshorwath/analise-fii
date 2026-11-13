from common import *
import time, datetime as dt, warnings, pickle
warnings.filterwarnings("ignore")
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import src.fii_analysis.features.saude as saude_mod
from src.fii_analysis.features.indicators import get_relatorios_ajustados
from src.fii_analysis.models.episodes import pvp_percentil_ate_t_menos_1

c = conn(); m = tick_cnpj(c)
eng = create_engine("sqlite://", creator=lambda: sqlite3.connect(DB, uri=True)); S = Session(eng)
_cache = {}
def rel_cached(ticker, session, apenas_entregues=True):
    if ticker not in _cache:
        _cache[ticker] = get_relatorios_ajustados(ticker, session, apenas_entregues)
    d = _cache[ticker].copy()
    d["data_referencia"] = pd.to_datetime(d["data_referencia"]); d["data_entrega"] = pd.to_datetime(d["data_entrega"])
    return d
saude_mod.get_relatorios_ajustados = rel_cached

COV_START = pd.Timestamp("2022-03-31"); SAMPLE_START = pd.Timestamp("2022-04-29")
p = pd.read_sql("select ticker,data,fechamento f,fechamento_aj a,volume v from precos_diarios where fechamento is not null and fechamento_aj is not null", c, parse_dates=["data"])
p = p[p.data >= "2020-12-01"].sort_values(["ticker", "data"])
tickers = sorted(p.ticker.unique())
cal_cnt = p.groupby("data").ticker.count()
cal = cal_cnt[cal_cnt >= 30].index
F = p.pivot(index="data", columns="ticker", values="f").reindex(cal)
A = p.pivot(index="data", columns="ticker", values="a").reindex(cal)
V = p.pivot(index="data", columns="ticker", values="v").reindex(cal)
me = pd.DatetimeIndex(pd.Series(cal, index=cal).groupby([cal.year, cal.month]).max().values)
forms = me[(me >= SAMPLE_START) & (me < pd.Timestamp('2026-11-01'))]
print("formacoes:", len(forms), forms[0].date(), forms[-1].date(), "cal ultimo", cal[-1].date())

cdi = pd.read_sql("select data,taxa_diaria_pct r from cdi_diario", c, parse_dates=["data"]).set_index("data").r.sort_index() / 100.0
lcdi = np.log1p(cdi).cumsum()
xf = pd.read_sql("select data,fechamento x from benchmark_diario where ticker='XFIX11'", c, parse_dates=["data"]).set_index("data").x
xf = xf.reindex(cal).ffill(limit=5)
D = pd.read_sql("select ticker,data_com,valor_cota d from dividendos where valor_cota is not null", c, parse_dates=["data_com"])
divs = {k: g.sort_values("data_com") for k, g in D.groupby("ticker")}
R = pd.read_sql("select cnpj,data_referencia,data_entrega,dy_mes_pct from relatorios_mensais", c, parse_dates=["data_referencia", "data_entrega"])
AP = pd.read_sql("select cnpj,data_referencia,data_entrega,ativo_total from ativo_passivo", c, parse_dates=["data_referencia", "data_entrega"])
t2c = dict(zip(m.ticker, m.cnpj))

ap_full = pd.read_sql("select * from ativo_passivo", c, parse_dates=["data_referencia"])
ap_full = ap_full[ap_full.ativo_total.notna()].sort_values("data_referencia").groupby("cnpj").tail(1)
def classif(row):
    at = float(row.ativo_total)
    if at == 0: return "Indefinido"
    s = lambda x: float(x) if pd.notna(x) else 0.0
    imov = s(row.direitos_bens_imoveis); soc = s(row.acoes_sociedades_fii) + s(row.cotas_sociedades_fii)
    tit = s(row.cri) + s(row.cri_cra) + s(row.lci) + s(row.lci_lca)
    if (imov + soc) / at >= 0.60: return "Tijolo"
    if tit / at >= 0.60: return "Papel"
    return "Hibrido"
seg = {r.cnpj: classif(r) for r in ap_full.itertuples()}
segmento = {tk: seg.get(t2c.get(tk), "Indefinido") for tk in tickers}
print("segmentos:", pd.Series(segmento).value_counts().to_dict())

lc = lcdi.reindex(cal, method="ffill")
lc_m12 = lcdi.reindex(cal - pd.DateOffset(months=12), method="ffill"); lc_m12.index = cal
cdi_idx = cdi.index
n_end = np.searchsorted(cdi_idx.values, cal.values, side="right"); n_st = np.searchsorted(cdi_idx.values, (cal - pd.DateOffset(months=12)).values, side="right")
cdi12 = pd.Series(np.where((n_end - n_st) >= 200, np.expm1(lc.values - lc_m12.values), np.nan), index=cal)
