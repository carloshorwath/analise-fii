from lib import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 40)
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
print("=== E1. FM multivariado (EXPLORATORIO), alvo ex_h, preditores = rank cs ===")
def fm_multi(df, xs, y, h, minn=30):
    d = df[["t", y] + xs].dropna(); coefs = {}
    for t, g in d.groupby("t"):
        if len(g) < minn: continue
        X = np.column_stack([np.ones(len(g))] + [g[x].values for x in xs]); b = np.linalg.lstsq(X, g[y].values, rcond=None)[0]; coefs[t] = b[1:]
    C = pd.DataFrame(coefs, index=xs).T.sort_index(); T = len(C); neff = max(T // h, 1)
    out = []
    for x in xs:
        se = nw_se(C[x].values, h if h > 1 else 1); t_ = C[x].mean() / se
        out.append(dict(x=x, coef_pct=C[x].mean() * 100, t_nw=t_, p_prim=2 * (1 - stats.t.cdf(abs(t_), max(neff - 1, 1))), T=T))
    return pd.DataFrame(out)
base = ["x_pvp_cs", "x_dvp6", "x_vol", "x_liq", "x_mom3", "x_saude"]
for h in (1, 3, 6):
    print("h=%d (sem dygap_pct)" % h); print(fm_multi(P, base, "ex%d" % h, h).round(3).to_string(index=False))
print("h=1 com dygap_pct + dy12 + base"); print(fm_multi(P, base + ["x_dygap_pct", "x_dy12"], "ex1", 1).round(3).to_string(index=False))
print("\n=== E2. pvp_pct com minimo 63 obs (sistema) em vez de 252 ===")
for h in HS:
    r = fm(P, "x_pvp_pct63", "ex%d" % h, h); print(h, "coef %.2f%% t %.2f p_prim %.3f T %d" % (r["coef"] * 100, r["t_nw"], r["p_prim"], r["T"]))
print("\n=== E3. FM com log(P/VP) padronizado cross-section (nivel) ===")
P["lpvp"] = np.log(P.pvp.where(P.pvp > 0)); g = P.groupby("t").lpvp
P["z_lpvp"] = ((P.lpvp - g.transform("mean")) / g.transform("std")).clip(-3, 3)
for h in HS:
    r = fm(P, "z_lpvp", "ex%d" % h, h); print(h, "coef por 1 DP: %.2f%% t %.2f p_prim %.3f" % (r["coef"] * 100, r["t_nw"], r["p_prim"]))
print("\n=== E4. dy12 (nivel bruto, por 1 pp de DY) ===")
P["dy12pp"] = P.dy12 * 100
for h in HS:
    r = fm(P, "dy12pp", "ex%d" % h, h); print(h, "coef por +1pp DY12m: %.3f%% t %.2f p_prim %.3f T %d" % (r["coef"] * 100, r["t_nw"], r["p_prim"], r["T"]))
print("\n=== E5. composicao: iliquidos (<500k) e idade ===")
P["iliq"] = P.liq21 < 5e5
print("share iliquido por ano:", P.groupby(P.t.dt.year).iliq.mean().round(3).to_dict(), " tickers distintos iliquidos:", P[P.iliq].ticker.nunique(), " obs:", P.iliq.sum())
print("iliquidos: share com idade<730d:", (P[P.iliq].idade_dias < 730).mean().round(3), " | liquidos:", (P[~P.iliq].idade_dias < 730).mean().round(3))
print("top tickers iliquidos:", P[P.iliq].ticker.value_counts().head(10).to_dict())
for h in (3, 6):
    for nm, m in [("iliq", P.iliq), ("jovem<730d", P.idade_dias < 730), ("velho>=730d", P.idade_dias >= 730)]:
        d = P.assign(m=m)[["t", "m", "ex%d" % h]].dropna(); s = d[d.m].groupby("t")["ex%d" % h].mean()
        T = len(s); se = nw_se(s.values, h); print("h=%d %s: excesso medio %.2f%% t_nw %.2f (T=%d)" % (h, nm, s.mean() * 100, s.mean() / se, T))
print("\n=== E6. Vies de sobrevivencia: o que o banco mostra ===")
cen = pd.read_csv(os.path.join(OUT, "censo_por_ticker.csv"), parse_dates=["primeiro", "ultimo"], index_col=0)
print("tickers com preco:", len(cen), " com ultimo preco antes de 2026-11-01:", (cen.ultimo < "2026-11-01").sum(), list(cen[cen.ultimo < "2026-11-01"].index))
print("tickers por ano de entrada (1o preco):", cen.primeiro.dt.year.value_counts().sort_index().to_dict())
h6 = P[P.ticker == "HSRE11"][["t", "r1", "r3", "r6", "ex6"]].dropna(subset=["r1"]).tail(4); print(h6)
print("HSRE11 ultimas linhas com r6 valido:", P[(P.ticker == "HSRE11")].r6.notna().sum(), "de", (P.ticker == "HSRE11").sum())
d = pd.read_sql("select ticker,count(*) n from universo group by 1", conn()); 
print("universo (IFIX 2026-06-11) = 107; tickers no painel que nao estao no universo:", sorted(set(P.ticker) - set(d.ticker)))
print("\n=== E7. Dispersao cross-section (para dimensionar efeito) ===")
for h in HS:
    sd = P.groupby("t")["r%d" % h].std().mean(); print("h=%d: DP cross-section medio do retorno = %.2f%% ; media EW por periodo = %.2f%% ; CDI = %.2f%%" % (h, sd * 100, P.groupby("t")["r%d" % h].mean().mean() * 100, P.groupby("t")["cdi%d" % h].mean().mean() * 100))
print("\n=== E8. Nivel de mercado (NAO inferencial): P/VP medio EW em t vs retorno EW futuro ===")
mk = P.groupby("t").agg(pvp=("pvp", "mean"), r6=("r6", "mean"), r12=("r12", "mean"), r3=("r3", "mean"))
print(mk.corr().round(2).loc["pvp"].to_dict(), " n meses:", len(mk.dropna()), " (6m: ~8 periodos independentes; 12m: ~3,6)")
print("P/VP medio por ano:", P.groupby(P.t.dt.year).pvp.mean().round(3).to_dict())
