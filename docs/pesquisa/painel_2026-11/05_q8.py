from lib import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 40)
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))

def ser_test(s, h):
    s = s.dropna(); T = len(s)
    if T < 5: return dict(T=T, mean=np.nan, t=np.nan, p=np.nan)
    se = nw_se(s.values, h if h > 1 else 1); t = s.mean() / se; neff = max(T // h, 1)
    return dict(T=T, neff=neff, mean=s.mean(), t=t, p=2 * (1 - stats.t.cdf(abs(t), max(neff - 1, 1))))
def group_vs_rest(mask, y, h, minn=3):
    d = P.assign(_m=mask)[["t", "_m", y]].dropna()
    s = {}
    for t, g in d.groupby("t"):
        a = g[g._m == True][y]; b = g[g._m == False][y]
        if len(a) >= minn and len(b) >= minn: s[t] = (a.mean(), b.mean(), len(a))
    s = pd.DataFrame(s, index=["g", "rest", "n"]).T
    return s
print("=== 0. Equivalencia dos alvos (a,b,c,d): coeficiente FM identico? ===")
for k in ["x_pvp_pct", "x_dvp6", "d_destr"]:
    for h in (1, 6):
        r = []
        for y in ("ex%d" % h, "r%d" % h, "exc%d" % h, "exx%d" % h):
            dd = P.copy()
            r.append(fm(dd, k, y, h, min_each=5 if k.startswith("d_") else None)["coef"])
        print(k, h, ["%.6f" % x for x in r])
print("\n=== 8A. Flag destruicao de capital ===")
print("share flagged geral %.3f ; por ano:" % P.d_destr.mean(), P.groupby(P.t.dt.year).d_destr.mean().round(3).to_dict())
print("ultima data %s: flagged %.3f (n=%d)" % (P.t.max().date(), P[P.t == P.t.max()].d_destr.mean(), (P.t == P.t.max()).sum()))
rows = []
for h in HS:
    y = "ex%d" % h
    s = group_vs_rest(P.d_destr == 1, y, h)
    fl = ser_test(s.g, h); nf = ser_test(s.rest, h); df = ser_test(s.g - s.rest, h)
    rows.append(dict(h=h, flag_media_pct=fl["mean"] * 100, naoflag_media_pct=nf["mean"] * 100, dif_pct=df["mean"] * 100, t_dif=df["t"], p_dif=df["p"], neff=df.get("neff"), n_datas=df["T"], n_flag_obs=int((P.d_destr == 1).sum())))
print(pd.DataFrame(rows).round(3).to_string())
print("-- por gravidade (excesso medio %, media das datas), h=1,3,6,12; t NW (vs 0)")
rows = []
for gv in ["saudavel", "em_recuperacao", "alerta", "critica"]:
    for h in HS:
        s = group_vs_rest(P.gravidade == gv, "ex%d" % h, h, 3)
        r_ = ser_test(s.g, h); rows.append(dict(grav=gv, h=h, media_pct=r_["mean"] * 100, t=r_["t"], n_obs=int((P.gravidade == gv).sum())))
print(pd.DataFrame(rows).pivot(index="grav", columns="h", values="media_pct").round(2))
print("-- por gravidade: n obs", P.gravidade.value_counts().to_dict())
print("-- destr: tambem testar com retorno bruto e exigindo VP caindo (pct_3m<0) -> descritivo")
for h in (1, 6):
    s = P.groupby("d_destr")["r%d" % h].mean() * 100; print("retorno bruto medio %d m por flag:" % h, s.round(2).to_dict())

print("\n=== 8B. dy_gap_alto (dygap_pct>70) ===")
print("share dygap_alto por data (media; min; max):", P.groupby("t").d_dygap_alto.mean().agg(["mean", "min", "max"]).round(3).to_dict())
print("share ultima data:", P[P.t == P.t.max()].d_dygap_alto.mean().round(3), " n=", P[(P.t == P.t.max())].d_dygap_alto.notna().sum())
sh = P.groupby("t").d_dygap_alto.mean().dropna(); print("share ult 12 datas:", sh.tail(12).round(2).to_dict())
rows = []
for h in HS:
    y = "ex%d" % h
    s = group_vs_rest(P.d_dygap_alto == 1, y, h)
    df_ = ser_test(s.g - s.rest, h); rows.append(dict(h=h, alto_pct=s.g.mean() * 100, resto_pct=s.rest.mean() * 100, dif_pct=df_["mean"] * 100, t=df_["t"], p=df_["p"], T=df_["T"]))
print(pd.DataFrame(rows).round(3).to_string())

print("\n=== 8C. BUY episodio (pvp_pct<=10) vs barato vs pares (Q1 P/VP cross-section, x<0.2) ===")
P["q1_pvpcs"] = (P.x_pvp_cs < 0.2).where(P.x_pvp_cs.notna())
P["q1_seg"] = (P.x_pvp_seg < 0.2).where(P.x_pvp_seg.notna())
ok = P.d_buy_ep.notna() & P.q1_pvpcs.notna()
print("obs: buy_ep=%d  q1_pvpcs=%d  ambos=%d ; so buy_ep=%d ; so q1=%d" % ((P.d_buy_ep == 1).sum(), (P.q1_pvpcs == 1).sum(), ((P.d_buy_ep == 1) & (P.q1_pvpcs == 1)).sum(), ((P.d_buy_ep == 1) & (P.q1_pvpcs == 0)).sum(), ((P.d_buy_ep == 0) & (P.q1_pvpcs == 1)).sum()))
rows = []
for h in HS:
    y = "ex%d" % h
    sb = group_vs_rest((P.d_buy_ep == 1), y, h, 3); sq = group_vs_rest((P.q1_pvpcs == True), y, h, 3); ss = group_vs_rest((P.q1_seg == True), y, h, 3)
    idx = sb.index.intersection(sq.index)
    rb = ser_test(sb.g, h); rq = ser_test(sq.g, h); rs_ = ser_test(ss.g, h); dd = ser_test(sb.g.loc[idx] - sq.g.loc[idx], h)
    rows.append(dict(h=h, buy_ep_pct=rb["mean"] * 100, t_buy=rb["t"], q1_pares_pct=rq["mean"] * 100, t_q1=rq["t"], q1_segmento_pct=rs_["mean"] * 100, t_q1seg=rs_["t"], dif_buy_menos_q1_pct=dd["mean"] * 100, t_dif=dd["t"], p_dif=dd["p"], T=dd["T"]))
print(pd.DataFrame(rows).round(3).to_string())
print("-- sell_ep (pvp_pct>=90) excesso medio %, t:")
for h in HS:
    s = group_vs_rest(P.d_sell_ep == 1, "ex%d" % h, h, 3); r_ = ser_test(s.g, h); print(h, round(r_["mean"] * 100, 2), round(r_["t"], 2), r_["T"])

print("\n=== 8D. P/VP < 0.5 e faixas de P/VP ===")
low = P[P.pvp < 0.5]
print("obs pvp<0.5:", len(low), " tickers distintos:", low.ticker.nunique(), " por ano:", low.groupby(low.t.dt.year).size().to_dict())
print("top tickers:", low.ticker.value_counts().head(12).to_dict())
rows = []
for h in HS:
    y = "ex%d" % h
    s = group_vs_rest(P.pvp < 0.5, y, h, 3); r_ = ser_test(s.g, h); dd = ser_test(s.g - s.rest, h)
    rows.append(dict(h=h, media_pct=r_["mean"] * 100, t=r_["t"], dif_vs_resto_pct=dd["mean"] * 100, t_dif=dd["t"], T=dd["T"], n_obs_retorno=int(low["ex%d" % h].notna().sum()), n_tickers=low[low["ex%d" % h].notna()].ticker.nunique()))
print(pd.DataFrame(rows).round(3).to_string())
low2 = P[(P.pvp < 0.5) & ~P.ticker.isin(["CACR11", "MFII11", "HCTR11", "DEVA11", "TGAR11", "URPR11"])]
print("sem tickers estranhos: n=", len(low2), " tickers:", low2.ticker.nunique())
bins = [0, 0.5, 0.7, 0.85, 1.0, 1.15, 5]; lab = ["<0.50", "0.50-0.70", "0.70-0.85", "0.85-1.00", "1.00-1.15", ">1.15"]
P["faixa"] = pd.cut(P.pvp, bins, labels=lab, right=False)
rows = []
for f_ in lab:
    r = dict(faixa=f_, n_obs=int((P.faixa == f_).sum()), n_tick=P[P.faixa == f_].ticker.nunique())
    for h in HS:
        s = group_vs_rest(P.faixa == f_, "ex%d" % h, h, 3); r_ = ser_test(s.g, h); r["ex%dm_pct" % h] = r_["mean"] * 100; r["t%d" % h] = r_["t"]
    rows.append(r)
print(pd.DataFrame(rows).round(2).to_string())
print("-- P/VP<0.5: retorno bruto medio e excesso: % de obs com excesso<0 (6m):", (low.ex6.dropna() < 0).mean().round(3), " mediana ex6 %:", round(low.ex6.median() * 100, 2))
print("-- por segmento (pvp<0.5):", low.seg.value_counts().to_dict())
print("-- pvp<0.5 e flag destr:", low.d_destr.mean().round(3))
