from lib import *
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
v0 = V.reindex(P.t).values  # placeholder
P["vol_t"] = [V.at[t, tk] for t, tk in zip(P.t, P.ticker)]
print("obs com volume==0 no dia de formacao:", (P.vol_t == 0).sum(), " tickers:", P[P.vol_t == 0].ticker.value_counts().head(8).to_dict())
print("obs liq21==0:", (P.liq21 == 0).sum(), " liq21<50k:", (P.liq21 < 5e4).sum(), " de", len(P))
print("SNFF11 obs apos liquidacao (t>=2026-04-16):", ((P.ticker == "SNFF11") & (P.t >= "2026-04-16")).sum())
stale = (P.vol_t == 0) | ((P.ticker == "SNFF11") & (P.t >= "2026-04-16"))
for nm, df in [("base", P), ("sem SNFF11 pos-liquidacao e sem volume==0 em t", P[~stale]), ("sem SNFF11 total", P[P.ticker != "SNFF11"]), ("liq21>=50k apenas", P[P.liq21 >= 5e4])]:
    d = df.copy(); d["d_liq_ok"] = (d.liq21 >= 5e5).astype(float)
    out = []
    for h in (3, 6):
        r = fm(d, "d_liq_ok", "ex%d" % h, h, min_each=3); out.append("h=%d coef %.2f%% t %.2f p_prim %.3f" % (h, r["coef"] * 100, r["t_nw"], r["p_prim"]))
    print("%-48s" % nm, " | ".join(out))
