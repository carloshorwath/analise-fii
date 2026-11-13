from lib import *
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl")); rng = np.random.default_rng(1)
k, h = "pvp_pct", 6; y = "ex6"
piv = P.pivot(index="t", columns="ticker", values="x_pvp_pct"); yy = P.pivot(index="t", columns="ticker", values=y); T_ = len(piv)
def coefmean(xr):
    cs = []
    for t in piv.index:
        xv = xr.loc[t]; yv = yy.loc[t]; ok = xv.notna() & yv.notna()
        if ok.sum() < 20: continue
        a = xv[ok].values; b = yv[ok].values; a = a - a.mean(); den = (a ** 2).sum()
        if den > 0: cs.append((a * (b - b.mean())).sum() / den)
    return np.mean(cs)
print("obs (ranks originais):", coefmean(piv) * 100)
vals = []
for i in range(40):
    sh = piv.copy()
    for c in sh.columns: sh[c] = np.roll(piv[c].values, rng.integers(6, T_ - 6))
    n = sh.count(axis=1); xr = sh.rank(axis=1, method="average", na_option="keep").sub(1).div((n - 1).replace(0, np.nan), axis=0)
    vals.append(coefmean(xr) * 100)
print("null shift: media %.2f sd %.2f min %.2f max %.2f" % (np.mean(vals), np.std(vals), np.min(vals), np.max(vals)))
print("share NaN no pivot:", piv.isna().mean().mean())
