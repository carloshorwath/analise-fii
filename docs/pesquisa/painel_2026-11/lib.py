from common import *
import pickle, warnings
from scipy import stats
warnings.filterwarnings("ignore")
HS = [1, 3, 6, 12]
W = pickle.load(open(os.path.join(OUT, "wide.pkl"), "rb"))
F, A, V, cal, forms, me, cdi, xf = W["F"], W["A"], W["V"], W["cal"], W["forms"], W["me"], W["cdi"], W["xf"]
LAST_COMPLETE = pd.Timestamp("2026-11-01")

def add_returns(P):
    """retorno futuro TR (entrada em t e em t+1 pregao), CDI e XFIX11 por horizonte."""
    me_list = list(me); pos_me = {d: i for i, d in enumerate(me_list)}
    Aff = A.ffill(limit=5); Ff = F.ffill(limit=5)
    lcdi = np.log1p(cdi / 1.0).cumsum() if cdi.max() < 1 else None
    out = {}
    cal_pos = {d: i for i, d in enumerate(cal)}
    for h in HS:
        r0 = []; r1 = []; rc = []; rx = []; rtp = []
        for t, tk in zip(P.t, P.ticker):
            i = pos_me[t]
            if i + h >= len(me_list) or me_list[i + h] >= LAST_COMPLETE:
                r0.append(np.nan); r1.append(np.nan); rc.append(np.nan); rx.append(np.nan); continue
            T = me_list[i + h]
            a_t = Aff.at[t, tk]; a_T = Aff.at[T, tk]
            # fundo que parou de negociar: ultimo preco valido antes de T conta apenas se ffill alcanca; senao NaN
            r0.append(a_T / a_t - 1 if (pd.notna(a_t) and pd.notna(a_T)) else np.nan)
            j = cal_pos[t] + 1
            if j < len(cal):
                a1 = Aff.at[cal[j], tk]
                r1.append(a_T / a1 - 1 if (pd.notna(a1) and pd.notna(a_T)) else np.nan)
            else: r1.append(np.nan)
            c_ = cdi[(cdi.index > t) & (cdi.index <= T)]
            rc.append(float(np.prod(1 + c_.values) - 1))
            x0 = xf.get(t, np.nan); x1 = xf.get(T, np.nan)
            rx.append(x1 / x0 - 1 if pd.notna(x0) and pd.notna(x1) else np.nan)
        out[h] = (r0, r1, rc, rx)
    for h in HS:
        P["r%d" % h], P["r%d_lag1" % h], P["cdi%d" % h], P["xf%d" % h] = out[h]
    return P

def cs_rank(df, col, minn=20, by=None):
    """rank cross-sectional em [0,1] por data (ou por data x grupo)."""
    keys = ["t"] if by is None else ["t", by]
    g = df.groupby(keys)[col]
    n = g.transform("count"); r = g.rank(method="average")
    x = (r - 1) / (n - 1).replace(0, np.nan)
    x[n < (minn if by is None else 5)] = np.nan
    return x

def nw_se(x, L):
    x = np.asarray(x, float); T = len(x); xc = x - x.mean()
    g0 = (xc @ xc) / T; v = g0
    for l in range(1, min(L, T - 1) + 1):
        gl = (xc[l:] @ xc[:-l]) / T; v += 2 * (1 - l / (L + 1)) * gl
    return np.sqrt(max(v, 1e-30) / T)

def fm(df, xcol, ycol, h, min_each=None, minn=20):
    """Fama-MacBeth univariado. xcol numerica; retorna dict + serie de coeficientes."""
    d = df[["t", xcol, ycol]].dropna()
    coefs = {}
    for t, g in d.groupby("t"):
        x = g[xcol].values; y = g[ycol].values
        if len(g) < minn: continue
        if min_each is not None:
            n1 = (x == 1).sum(); n0 = (x == 0).sum()
            if n1 < min_each or n0 < min_each: continue
        xv = x - x.mean()
        den = (xv ** 2).sum()
        if den <= 0: continue
        coefs[t] = (xv * (y - y.mean())).sum() / den
    s = pd.Series(coefs).sort_index()
    T = len(s)
    if T < 5: return {"T": T, "coef": np.nan, "se": np.nan, "t_nw": np.nan, "p_norm": np.nan, "p_prim": np.nan, "neff": 0, "series": s}
    L = h if h > 1 else 1
    se = nw_se(s.values, L); tt = s.mean() / se
    neff = max(int(T // h), 1)
    return {"T": T, "coef": s.mean(), "se": se, "t_nw": tt, "p_norm": 2 * (1 - stats.norm.cdf(abs(tt))),
            "p_prim": 2 * (1 - stats.t.cdf(abs(tt), max(neff - 1, 1))), "neff": neff, "series": s,
            "first": s.index.min(), "last": s.index.max(), "n_obs": len(d)}

def sorted_ports(df, xcol, ycol, h, nq=5, minn=20):
    d = df[["t", xcol, ycol]].dropna()
    rows = {}
    for t, g in d.groupby("t"):
        if len(g) < minn: continue
        n = len(g)
        q = np.minimum(np.floor(g[xcol].values * nq), nq - 1).astype(int); q = pd.Series(q, index=g.index)
        m = g.groupby(q.values)[ycol].mean()
        if len(m) == nq: rows[t] = m.values
    if not rows: return None
    Q = pd.DataFrame(rows, index=["Q%d" % (i + 1) for i in range(nq)]).T.sort_index()
    sp = Q["Q1"] - Q["Q%d" % nq]
    neg = (sp < 0).astype(int); run = best = 0
    for v in neg.values:
        run = run + 1 if v else 0; best = max(best, run)
    se = nw_se(sp.values, h if h > 1 else 1)
    return {"Q": Q, "spread": sp, "mean": sp.mean(), "t_nw": sp.mean() / se, "hit": float((sp > 0).mean()), "worst_run": best, "T": len(sp)}

def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p); r = np.empty(n)
    adj = p[o] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    r[o] = np.minimum(adj, 1); return r
