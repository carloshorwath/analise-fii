from lib import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 40)
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
rng = np.random.default_rng(12345)
SRC = {"dygap_pct": "v_dygap_pct", "dvp6": "v_dvp6", "dvp3": "v_dvp3", "liq": "v_liq"}

def quint_members(df, xcol, ycol, top=True):
    d = df[["t", "ticker", xcol, ycol]].dropna(); mem = {}
    for t, g in d.groupby("t"):
        if len(g) < 20: continue
        q = np.minimum(np.floor(g[xcol].values * 5), 4)
        mem[t] = set(g.ticker[q == (4 if top else 0)])
    return mem
def block_boot(s, blk, B=5000):
    s = s.values; n = len(s); nb = int(np.ceil(n / blk)); out = np.empty(B)
    for b in range(B):
        st = rng.integers(0, n - blk + 1, nb); idx = (st[:, None] + np.arange(blk)).ravel()[:n]; out[b] = s[idx].mean()
    return np.percentile(out, [2.5, 97.5])
def econ(k, h, top=True, cs=0.001):
    xcol = "x_" + k; y = "ex%d" % h
    sp = sorted_ports(P, xcol, y, h, 5); Q = sp["Q"]
    fav = Q["Q5"] if top else Q["Q1"]; 
    ew = P.groupby("t")["r%d" % h].mean().reindex(Q.index)
    cdi_ = P.groupby("t")["cdi%d" % h].mean().reindex(Q.index); xf_ = P.groupby("t")["xf%d" % h].mean().reindex(Q.index)
    mem = quint_members(P, xcol, y, top)
    dts = sorted(mem); to = []
    for t in dts:
        # data h meses depois na lista de formacoes
        i = list(me).index(t)
        if i + h < len(me) and me[i + h] in mem:
            a, b = mem[t], mem[me[i + h]]; to.append(1 - len(a & b) / max(len(b), 1))
    to = float(np.mean(to)) if to else np.nan
    per = 12 / h
    res = dict(pred=k, h=h, lado="Q5(alto)" if top else "Q1(baixo)", n_datas=len(Q), turnover_h=to)
    act = fav
    lo, hi = block_boot(act, h)
    res.update(ativo_h_pct=act.mean() * 100, ativo_ano_pct=((1 + act.mean()) ** per - 1) * 100, ic95_h_pct=(lo * 100, hi * 100), ic95_ano_pct=(((1 + lo) ** per - 1) * 100, ((1 + hi) ** per - 1) * 100),
               TE_h_pct=act.std() * 100, IR_anual=(act.mean() / act.std()) * np.sqrt(per) if act.std() > 0 else np.nan,
               Q_bruto_h_pct=(ew + fav).mean() * 100, EW_h_pct=ew.mean() * 100, CDI_h_pct=cdi_.mean() * 100, XFIX_h_pct=xf_.mean() * 100,
               hit_Q_vs_EW=float((act > 0).mean()))
    for c in (0.001, 0.003):
        net = act - to * c
        res["liq_ativo_ano_pct_c%.3f" % c] = ((1 + net.mean()) ** per - 1) * 100
    res["spread_LS_h_pct"] = (Q["Q5"] - Q["Q1"]).mean() * 100 * (1 if top else -1)
    return res
rows = []
for k, h, top in [("dygap_pct", 1, True), ("dvp6", 3, True), ("dvp6", 6, True), ("dvp6", 12, True), ("dygap_pct", 3, True), ("dygap_pct", 6, True), ("pvp_pct", 6, False), ("pvp_cs", 6, False), ("pvp_cs", 12, False), ("pvp_pct", 12, False), ("saude", 6, True), ("score", 6, True)]:
    rows.append(econ(k, h, top))
E = pd.DataFrame(rows); E.to_csv(os.path.join(OUT, "economia_quintis.csv"), index=False)
print(E.round(3).to_string())

# ---- placebo within-date + circular time-shift
def fm_mean_fast(arr_x, arr_y):
    out = []
    for x, y in zip(arr_x, arr_y):
        xv = x - x.mean(); den = (xv ** 2).sum()
        out.append((xv * (y - y.mean())).sum() / den if den > 0 else np.nan)
    return np.nanmean(out)
def placebo(k, h, kind, N=2000, Ns=1000):
    xcol = ("x_" + k) if kind == "cont" else ("d_" + k); y = "ex%d" % h
    d = P[["t", "ticker", xcol, y] + ([SRC[k]] if k in SRC else [])].dropna(subset=[xcol, y]).copy()
    groups = [g for _, g in d.groupby("t") if len(g) >= 20]
    xs = [g[xcol].values for g in groups]; ys = [g[y].values for g in groups]
    obs = fm_mean_fast(xs, ys)
    null = np.empty(N)
    for i in range(N):
        null[i] = fm_mean_fast([rng.permutation(x) for x in xs], ys)
    p_perm = (1 + (np.abs(null) >= abs(obs)).sum()) / (N + 1)
    # circular time shift dentro do ticker (preserva persistencia do preditor e a estrutura de retornos)
    base = P[["t", "ticker", y, SRC[k] if k in SRC else ("liq21" if k == "liq_ok" else xcol)]].copy()
    src = base.columns[-1]; piv = base.pivot(index="t", columns="ticker", values=src); T_ = len(piv)
    yy = base.pivot(index="t", columns="ticker", values=y)
    nulls = []
    for i in range(Ns):
        sh = piv.copy()
        for c in sh.columns:
            kk = rng.integers(max(3, h), T_ - max(3, h)); sh[c] = np.roll(piv[c].values, kk)
        if kind == "cont":
            xr = sh.rank(axis=1, method="average", na_option="keep"); n = sh.count(axis=1)
            xr = xr.sub(1).div((n - 1).replace(0, np.nan), axis=0); xr[n < 20] = np.nan
        else:
            xr = (sh >= 5e5).astype(float).where(sh.notna())
        cs = []
        for t in piv.index:
            xv = xr.loc[t]; yv = yy.loc[t]; ok = xv.notna() & yv.notna()
            if ok.sum() < 20: continue
            a = xv[ok].values; b = yv[ok].values; a = a - a.mean(); den = (a ** 2).sum()
            if den > 0: cs.append((a * (b - b.mean())).sum() / den)
        nulls.append(np.mean(cs))
    nulls = np.array(nulls); p_shift = (1 + (np.abs(nulls) >= abs(obs)).sum()) / (Ns + 1)
    return dict(pred=k, h=h, obs_coef_pct=obs * 100, null_sd_within_pct=null.std() * 100, p_within=p_perm, pct_rank_within=float((null < obs).mean() * 100),
                null_sd_shift_pct=nulls.std() * 100, p_shift=p_shift, pct_rank_shift=float((nulls < obs).mean() * 100))
rows = []
for k, h, kind in [("dygap_pct", 1, "cont"), ("dvp6", 3, "cont"), ("dvp6", 6, "cont"), ("liq_ok", 3, "disc"), ("liq_ok", 6, "disc"), ("pvp_pct", 6, "cont"), ("pvp_cs", 6, "cont")]:
    if k == "liq_ok": P["d_liq_ok"] = (P.liq21 >= 5e5).astype(float).where(P.liq21.notna())
    rows.append(placebo(k, h, kind)); print(rows[-1], flush=True)
pd.DataFrame(rows).to_csv(os.path.join(OUT, "placebo.csv"), index=False)
print(pd.DataFrame(rows).round(4).to_string())
