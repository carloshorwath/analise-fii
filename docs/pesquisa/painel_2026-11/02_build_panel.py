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
out = []
t0 = time.time()
xr_all = None
for tk in tickers:
    cnpj = t2c[tk]
    f = F[tk].dropna(); a = A[tk].dropna(); v = V[tk]
    first_px = f.index.min()
    rel = rel_cached(tk, S)
    rel = rel[rel.vp_aj.notna() & (rel.vp_aj > 0)].copy()
    rs = rel.sort_values("data_entrega")
    cur_ref = pd.Timestamp.min; cur_vp = np.nan; vv = []
    for r_ in rs.itertuples():
        if r_.data_referencia >= cur_ref:
            cur_ref = r_.data_referencia; cur_vp = r_.vp_aj
        vv.append(cur_vp)
    rs = rs.assign(vp_vig=vv)
    rsd = rs[["data_entrega", "vp_vig"]].copy()
    rsd["data_entrega"] = pd.to_datetime(rsd["data_entrega"])
    rsd = rsd.sort_values("data_entrega").drop_duplicates("data_entrega", keep="last")
    fd = pd.DataFrame({"data": f.index, "preco": f.values})
    fd = pd.merge_asof(fd, rsd, left_on="data", right_on="data_entrega", direction="backward").dropna(subset=["vp_vig"])
    fd["pvp"] = fd.preco / fd.vp_vig
    fd["pvp_pct"] = pvp_percentil_ate_t_menos_1(fd["pvp"].values, 504, 63)
    fd["n_prev"] = np.minimum(np.arange(len(fd)), 504)
    fd = fd.set_index("data")
    dv = divs.get(tk)
    dyd = pd.Series(np.nan, index=f.index)
    if dv is not None:
        dd = dv.data_com.values; cs = np.concatenate([[0.0], np.cumsum(dv.d.values.astype(float))])
        idx_t = np.searchsorted(dd, f.index.values, side="right")
        starts = (f.index - pd.DateOffset(months=12))
        idx_s = np.searchsorted(dd, starts.values, side="right")
        soma = cs[idx_t] - cs[idx_s]
        ok = (starts >= COV_START) & (starts >= first_px) & (soma > 0)
        dyd[:] = np.where(ok, soma / f.values, np.nan)
    gap = dyd - cdi12.reindex(dyd.index)
    liq21 = (f * v.reindex(f.index)).rolling(21, min_periods=1).mean()
    inf_r = R[R.cnpj == cnpj].sort_values("data_referencia")
    ap_r = AP[AP.cnpj == cnpj]
    for t in forms:
        if t not in f.index: continue
        o = {"ticker": tk, "t": t, "preco": f[t], "seg": segmento[tk], "primeiro_preco": first_px}
        if t in fd.index:
            o["pvp"] = fd.at[t, "pvp"]; o["pvp_pct"] = fd.at[t, "pvp_pct"]; o["n_prev"] = fd.at[t, "n_prev"]
        o["dy12"] = dyd.get(t, np.nan); o["gap"] = gap.get(t, np.nan)
        if not np.isnan(o["gap"]):
            pos = f.index.get_loc(t)
            w = gap.iloc[max(0, pos - 252):pos].dropna(); n = len(w)
            if n >= 50:
                o["dygap_pct"] = float((w <= o["gap"]).sum() / n * 100); o["dygap_n"] = n
        for k in (1, 3, 6, 12):
            t_k = t - pd.DateOffset(months=k)
            if t_k >= pd.Timestamp("2022-04-01"):
                ak = a[a.index <= t_k]
                if len(ak) and (t_k - ak.index[-1]).days <= 7:
                    o["mom%d" % k] = a[t] / ak.iloc[-1] - 1
        o["liq21"] = liq21.get(t, np.nan)
        pos_a = a.index.get_loc(t)
        w252 = a.iloc[max(0, pos_a - 251):pos_a + 1]
        if len(w252) >= 63:
            r_ = np.log(w252).diff().dropna(); o["vol"] = float(r_.std(ddof=1) * np.sqrt(252))
            xx = xf.reindex(w252.index); ok = xx.notna()
            if ok.sum() >= 63:
                ra = np.log(w252[ok]).diff().dropna(); rx = np.log(xx[ok]).diff().dropna()
                if rx.var() > 0: o["beta"] = float(np.cov(ra, rx)[0, 1] / rx.var())
        w504 = a.iloc[max(0, pos_a - 503):pos_a + 1]
        if len(w504) >= 63:
            o["mdd"] = float((w504 / w504.cummax() - 1).min())
        pit = inf_r[inf_r.data_entrega <= t]
        if len(pit):
            dyv = pit.tail(24).dy_mes_pct.dropna(); dyv = dyv[dyv > 0]
            if len(dyv) >= 6 and dyv.mean() > 0:
                cv = dyv.std(ddof=0) / dyv.mean(); o["score_hist"] = max(0, min(100, round((1 - min(cv / 0.5, 1)) * 100)))
            else: o["score_hist"] = 50
        rr = rel[pd.to_datetime(rel.data_entrega) <= t].sort_values("data_referencia")
        if len(rr):
            vp0 = rr.iloc[-1]; ref0 = vp0.data_referencia
            for k in (3, 6):
                prev = rr[rr.data_referencia == ref0 - pd.DateOffset(months=k)]
                if len(prev): o["dvp%d" % k] = vp0.vp_aj / prev.iloc[0].vp_aj - 1
            o["pl"] = vp0.patrimonio_liq; o["ref_vp"] = ref0
            ap_p = ap_r[(ap_r.data_entrega <= t) & (ap_r.data_referencia == ref0)]
            if len(ap_p) and pd.notna(ap_p.iloc[-1].ativo_total) and vp0.patrimonio_liq and vp0.patrimonio_liq > 0:
                o["lev"] = float(ap_p.iloc[-1].ativo_total) / float(vp0.patrimonio_liq)
        out.append(o)
P = pd.DataFrame(out)
print("painel base", P.shape, time.time() - t0)
t0 = time.time()
sc = []
for r_ in P[["ticker", "t"]].itertuples():
    try:
        fl = saude_mod.flag_destruicao_capital(r_.ticker, S, t=r_.t.date())
        sc.append((fl["destruicao"], fl["gravidade"], fl["score_saude"], fl["pct_3m"], fl["pct_6m"], fl["motivo"][:30]))
    except Exception as e:
        sc.append((None, None, None, None, None, "ERR " + str(e)[:30]))
P[["destr", "gravidade", "saude", "saude_pct3m", "saude_pct6m", "saude_motivo"]] = pd.DataFrame(sc, index=P.index)
print("saude", time.time() - t0, P.saude_motivo.str.startswith("ERR").sum())
P.to_pickle(os.path.join(OUT, "painel_base.pkl"))
pickle.dump({"F": F, "A": A, "V": V, "cal": cal, "forms": forms, "me": me, "cdi": cdi, "xf": xf, "segmento": segmento}, open(os.path.join(OUT, "wide.pkl"), "wb"))
