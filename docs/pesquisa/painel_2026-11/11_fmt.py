import pandas as pd, numpy as np
T = pd.read_csv("tabela_prereg.csv")
for h in (1, 3, 6, 12):
    s = T[T.h == h]
    print("h=%d (Neff por teste: %s) | SE NW mediano cont: %.2f%% -> MDE80 ~ %.1f%% (topo-menos-base de rank)" % (h, sorted(set(s.n_efetivo.astype(int)))[:3] + ["..."] if False else str(s.n_efetivo.min()) + "-" + str(s.n_efetivo.max()), s[s.tipo == "cont"].se_nw.median() * 100, 2.8 * s[s.tipo == "cont"].se_nw.median() * 100))
print()
print("pred h coef% t_nw p_prim pBH pBonf spread% hit surv")
for r in T.itertuples():
    sp = "" if pd.isna(r.spread_Q1mQ5) else "%+.2f" % (r.spread_Q1mQ5 * 100)
    ht = "" if pd.isna(r.hit) else "%.2f" % r.hit
    print("%-10s %2d %+6.2f %+5.2f %.3f %.2f %.2f N=%d/%d %s %s %s" % (r.pred, r.h, r.coef * 100, r.t_nw, r.p_prim, r.p_bh, r.p_bonf, r.n_efetivo, r.n_datas, sp, ht, "SIM" if r.sobrevive_BH else "nao"))
print("menor p_prim:", T.sort_values("p_prim").head(8)[["pred", "h", "coef", "t_nw", "p_prim", "p_bh"]].to_string())
print("n_efetivo<30 em", (T.n_efetivo < 30).sum(), "de 100")
