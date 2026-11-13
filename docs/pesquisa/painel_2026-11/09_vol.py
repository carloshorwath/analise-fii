from lib import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300)
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
def fm_multi(df, xs, y, h, minn=30):
    d = df[["t", y] + xs].dropna(); coefs = {}
    for t, g in d.groupby("t"):
        if len(g) < minn: continue
        X = np.column_stack([np.ones(len(g))] + [g[x].values for x in xs]); coefs[t] = np.linalg.lstsq(X, g[y].values, rcond=None)[0][1:]
    C = pd.DataFrame(coefs, index=xs).T.sort_index(); T = len(C); neff = max(T // h, 1); out = {}
    for x in xs:
        se = nw_se(C[x].values, h if h > 1 else 1); t_ = C[x].mean() / se; out[x] = (C[x].mean() * 100, t_, 2 * (1 - stats.t.cdf(abs(t_), max(neff - 1, 1))))
    return out, T
print("corr cross-section media (rank) vol x liq, vol x pvp_cs, liq x pvp:")
cc = P.groupby("t").apply(lambda g: g[["x_vol", "x_liq", "x_pvp_cs", "x_dvp6", "x_mom3"]].corr()).groupby(level=1).mean().round(2); print(cc)
print("\n-- vol sozinha vs vol+liq vs vol+liq+pvp (coef vol, t, p_prim)")
for h in (1, 3, 6):
    for nm, xs in [("vol", ["x_vol"]), ("vol+liq", ["x_vol", "x_liq"]), ("vol+pvp_cs", ["x_vol", "x_pvp_cs"]), ("vol+liq+pvp+dvp6+mom3+saude", ["x_vol", "x_liq", "x_pvp_cs", "x_dvp6", "x_mom3", "x_saude"])]:
        o, T = fm_multi(P, xs, "ex%d" % h, h); print("h=%d %-30s T=%d vol: %.2f%% t=%.2f p=%.3f | " % (h, nm, T, *o["x_vol"]), {k: round(v[0], 2) for k, v in o.items() if k != "x_vol"})
print("\n-- robustez da vol no modelo vol+liq (h=3):")
def rr(df, nm, h=3, y=None):
    o, T = fm_multi(df, ["x_vol", "x_liq"], y or "ex%d" % h, h, minn=20); print("  %-40s T=%d vol coef %.2f%% t=%.2f p_prim=%.3f ; liq coef %.2f%% t=%.2f" % (nm, T, *o["x_vol"], o["x_liq"][0], o["x_liq"][1]))
mid = pd.Timestamp("2024-06-28")
rr(P, "base"); rr(P[P.t <= mid], "metade inicial"); rr(P[P.t > mid], "metade final")
rr(P[~P.weird], "sem 6 tickers estranhos"); rr(P, "lag1", y="ex3_lag1"); rr(P[P.liq21 >= 5e5], "liq>=500k"); rr(P[P.liq21 >= 1e6], "liq>=1M")
rr(P[P.idade_dias >= 730], "idade>=730d")
for sg in ("Tijolo", "Papel", "Hibrido"): rr(P[P.seg == sg], "seg " + sg)
for yr in (2022, 2023, 2024, 2025, 2026): rr(P[P.t.dt.year == yr], "formacao %d" % yr)
print("\n-- vol (univariada) tercis de vol dentro de liquidos (>=1M): excesso medio por tercil, h=3 e 6")
for h in (1, 3, 6):
    d = P[(P.liq21 >= 1e6)].dropna(subset=["vol", "ex%d" % h]).copy()
    d["q"] = d.groupby("t").vol.transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False) if len(s) >= 30 else np.nan)
    m = d.groupby(["t", "q"])["ex%d" % h].mean().unstack(); sp = m[0] - m[2]
    print("h=%d  T1(baixa vol) %.2f%%  T3(alta vol) %.2f%%  spread %.2f%% t_nw %.2f T=%d neff=%d" % (h, m[0].mean() * 100, m[2].mean() * 100, sp.mean() * 100, sp.mean() / nw_se(sp.values, max(h, 1)), len(sp), len(sp) // h))
print("\n-- vol: quintis univariados, retorno medio por quintil (excesso %), h=1,3,6")
for h in (1, 3, 6):
    sp = sorted_ports(P, "x_vol", "ex%d" % h, h); print(h, (sp["Q"].mean() * 100).round(2).to_dict(), "hit Q1-Q5<0:", round(float((sp["spread"] < 0).mean()), 2))
print("\n-- vol bruta media por quintil de vol (anual) -> magnitude:", P.groupby(pd.qcut(P.vol, 5, labels=False)).vol.mean().round(3).to_dict())
print("-- corr(vol, mdd) etc ok")
