from lib import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 60)
P = pd.read_pickle(os.path.join(OUT, "painel_base.pkl"))
P["t"] = pd.to_datetime(P["t"])
print("base:", P.shape, "erros saude:", P.saude_motivo.str.startswith("ERR").sum())
P = add_returns(P)
# --- alvo (a): excesso sobre EW cross-section (todos os fundos com retorno valido na data)
for h in HS:
    for suf in ("", "_lag1"):
        c_ = "r%d%s" % (h, suf)
        P["ex%d%s" % (h, suf)] = P[c_] - P.groupby("t")[c_].transform("mean")
    P["exc%d" % h] = P["r%d" % h] - P["cdi%d" % h]
    P["exx%d" % h] = P["r%d" % h] - P["xf%d" % h]
# --- score total (replica aproximada, PIT)
def pr(s):  # percentil sem interpolacao dentro da data: % estritamente abaixo
    v = s.values; o = np.full(len(v), np.nan); ok = ~np.isnan(v); vv = v[ok]
    o[ok] = [(vv < x).sum() / len(vv) * 100 for x in vv]; return pd.Series(o, index=s.index)
P["abs_beta"] = P.beta.abs(); P["abs_mdd"] = P.mdd.abs()
for c_ in ("vol", "abs_beta", "abs_mdd"):
    P["pr_" + c_] = P.groupby("t")[c_].transform(pr)
P["s_risco"] = P[["pr_vol", "pr_abs_beta", "pr_abs_mdd"]].rsub(100).mean(axis=1, skipna=True).fillna(50).round()
P["s_val"] = (0.6 * (100 - P.pvp_pct) + 0.4 * P.dygap_pct.fillna(50)).where(P.pvp_pct.notna())
P["s_val"] = P["s_val"].round()
def bands(x):
    if pd.isna(x) or x < 2e5: return 20
    if x < 1e6: return 50
    if x < 5e6: return 75
    return 90
P["s_liq"] = P.liq21.map(bands)
P["score"] = (0.35 * P.s_val + 0.30 * P.s_risco + 0.20 * P.s_liq + 0.15 * P.score_hist).round()
# --- preditores
ok252 = P.n_prev >= 252
P["v_pvp_pct"] = P.pvp_pct.where(ok252)
P["v_pvp_pct63"] = P.pvp_pct
P["v_pvp_cs"] = P.pvp.where(P.pvp > 0)
P["v_pvp_seg"] = P.pvp.where((P.pvp > 0) & (P.seg != "Indefinido"))
P["v_dy12"] = P.dy12; P["v_dygap_pct"] = P.dygap_pct
for k in ("dvp3", "dvp6", "mom1", "mom3", "mom6", "mom12"): P["v_" + k] = P[k]
P["v_liq"] = np.log(P.liq21.where(P.liq21 > 0)); P["v_lev"] = P.lev; P["v_vol"] = P.vol
P["v_score"] = P.score.where(P.v_pvp_pct.notna()); P["v_saude"] = P.saude.astype(float)
CONT = ["pvp_pct", "pvp_cs", "pvp_seg", "dy12", "dygap_pct", "dvp3", "dvp6", "mom1", "mom3", "mom6", "mom12", "liq", "lev", "vol", "score", "saude"]
for c_ in CONT:
    P["x_" + c_] = cs_rank(P, "v_" + c_, 20, by="seg" if c_ == "pvp_seg" else None)
P["x_pvp_pct63"] = cs_rank(P, "v_pvp_pct63", 20)
# discretos
vp = P.v_pvp_pct
P["d_buy_ep"] = (vp <= 10).astype(float).where(vp.notna())
P["d_sell_ep"] = (vp >= 90).astype(float).where(vp.notna())
P["d_destr"] = P.destr.astype(float).where(P.destr.notna())
P["d_pvp_baixo"] = (vp < 30).astype(float).where(vp.notna())
P["d_dygap_alto"] = (P.dygap_pct > 70).astype(float).where(P.dygap_pct.notna())
P["d_liq_ok"] = (P.liq21 >= 5e5).astype(float).where(P.liq21.notna())
b1 = (P.pvp_pct < 30).fillna(False); b2 = (P.dygap_pct > 70).fillna(False); b3 = ~P.destr.fillna(True).astype(bool); b4 = (P.liq21 >= 5e5).fillna(False)
P["vistos"] = b1.astype(int) + b2.astype(int) + b3.astype(int) + b4.astype(int)
P["d_vistos"] = P.vistos.astype(float).where(P.pvp.notna())
P["d_vistos4"] = (P.vistos == 4).astype(float).where(P.pvp.notna())
P["d_pvp_lt05"] = (P.pvp < 0.5).astype(float).where(P.pvp > 0)
# flags de exclusao
WEIRD = ["CACR11", "MFII11", "HCTR11", "DEVA11", "TGAR11", "URPR11"]
P["weird"] = P.ticker.isin(WEIRD)
P["idade_dias"] = (P.t - P.primeiro_preco).dt.days
P.to_pickle(os.path.join(OUT, "painel_final.pkl"))
# ---- QC / censo
print("linhas", len(P), "tickers", P.ticker.nunique(), "datas", P.t.nunique())
cs = P.groupby("t").ticker.count(); print("tamanho cross-section: min %d med %d max %d" % (cs.min(), cs.median(), cs.max()))
print("ticker-meses por ano (com preco na formacao):"); print(P.groupby(P.t.dt.year).size())
cols = ["v_" + c for c in CONT] + ["d_buy_ep", "d_destr", "d_dygap_alto", "d_pvp_lt05"]
tab = pd.DataFrame({c: P.groupby(P.t.dt.year)[c].apply(lambda s: s.notna().sum()) for c in cols}).T
print("ticker-meses UTEIS por preditor e ano:"); print(tab)
print("primeira data com >=20 validos por preditor:")
for c in CONT:
    g = P.groupby("t")["v_" + c].count(); ok = g[g >= 20]
    print("  ", c, ok.index.min().date() if len(ok) else None, "meses>=20:", len(ok))
for h in HS:
    g = P.groupby("t")["ex%d" % h].count(); g = g[g >= 20]
    print("h=%d datas de formacao com >=20 retornos validos: %d (%s .. %s); nao sobrepostos ~ %.1f" % (h, len(g), g.index.min().date(), g.index.max().date(), len(g) / h))
print("retorno NaN por falta de preco no fim (fundos parados):", P[P.r1.isna() & (P.t < '2026-09-30')].ticker.value_counts().head())
print(P[["pvp", "dy12", "gap", "dvp3", "mom12", "liq21", "lev", "vol", "score", "saude"]].describe(percentiles=[.01, .5, .99]).T)
print("pvp<0.5 n:", (P.pvp < 0.5).sum(), " pvp>3:", (P.pvp > 3).sum(), " lev<0.9 or >3:", ((P.lev < 0.9) | (P.lev > 3)).sum())
print("destr share:", P.d_destr.mean(), " gravidade:", P.gravidade.value_counts().to_dict())
print("dygap_alto share:", P.d_dygap_alto.mean(), " buy_ep share", P.d_buy_ep.mean(), "sell_ep", P.d_sell_ep.mean())
print("retornos 1m: media %.4f dp %.4f ; max %.3f min %.3f" % (P.r1.mean(), P.r1.std(), P.r1.max(), P.r1.min()))
print(P.sort_values("r1").head(5)[["ticker", "t", "r1"]]); print(P.sort_values("r1").dropna(subset=["r1"]).tail(5)[["ticker", "t", "r1"]])
print("segmento:", P.drop_duplicates("ticker").seg.value_counts().to_dict())
