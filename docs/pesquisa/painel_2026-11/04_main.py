from lib import *
pd.set_option('display.width', 280); pd.set_option('display.max_rows', 400); pd.set_option('display.max_columns', 40)
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
CONT = ["pvp_pct", "pvp_cs", "pvp_seg", "dy12", "dygap_pct", "dvp3", "dvp6", "mom1", "mom3", "mom6", "mom12", "liq", "lev", "vol", "score", "saude"]
DISC = ["buy_ep", "sell_ep", "destr", "pvp_baixo", "dygap_alto", "liq_ok", "vistos", "pvp_lt05", "vistos4"]
HYP = {"pvp_pct": "baixo=bom", "pvp_cs": "baixo=bom", "pvp_seg": "baixo=bom", "dy12": "alto=bom", "dygap_pct": "alto=bom", "dvp3": "alto=bom", "dvp6": "alto=bom",
       "mom1": "-", "mom3": "-", "mom6": "-", "mom12": "-", "liq": "alto=bom", "lev": "baixo=bom", "vol": "baixo=bom", "score": "alto=bom", "saude": "alto=bom",
       "buy_ep": "+ (BUY)", "sell_ep": "- (SELL)", "destr": "- (SAIR)", "pvp_baixo": "+", "dygap_alto": "+", "liq_ok": "+", "vistos": "+", "pvp_lt05": "? (oportunidade vs armadilha)", "vistos4": "+"}
rows = []; series = {}
for h in HS:
    y = "ex%d" % h
    for k in CONT + DISC:
        if k in CONT:
            res = fm(P, "x_" + k, y, h); sp = sorted_ports(P, "x_" + k, y, h, 5)
        else:
            res = fm(P, "d_" + k, y, h, min_each=5 if k not in ("vistos",) else None); sp = None
            if k == "vistos":
                res = fm(P, "d_vistos", y, h)
        series[(k, h)] = res["series"]
        row = dict(pred=k, tipo="cont" if k in CONT else "disc", h=h, hip_sistema=HYP[k], n_datas=res["T"], n_efetivo=res["neff"], coef=res["coef"], se_nw=res["se"], t_nw=res["t_nw"],
                   p_norm=res["p_norm"], p_prim=res["p_prim"], de=res.get("first"), ate=res.get("last"), n_obs=res.get("n_obs"))
        if sp is not None:
            row.update(spread_Q1mQ5=sp["mean"], t_spread=sp["t_nw"], hit=sp["hit"], pior_seq_neg=sp["worst_run"], Q1=sp["Q"]["Q1"].mean(), Q5=sp["Q"]["Q5"].mean(), n_datas_sp=sp["T"])
        rows.append(row)
T = pd.DataFrame(rows)
ok = T.p_prim.notna()
T["p_bh"] = np.nan; T["p_bonf"] = np.nan; T["p_bh_norm"] = np.nan
T.loc[ok, "p_bh"] = bh(T.loc[ok, "p_prim"].values); T.loc[ok, "p_bonf"] = np.minimum(T.loc[ok, "p_prim"] * 100, 1)
T.loc[ok, "p_bh_norm"] = bh(T.loc[ok, "p_norm"].values)
T["p_bonf_norm"] = np.minimum(T.p_norm * 100, 1)
T["sinal_ok"] = np.where(T.tipo == "cont", np.sign(T.coef) == np.sign(T.spread_Q1mQ5) * -1 * -1, True)  # coef (rank alto - baixo) vs Q1-Q5 (baixo - alto): sinais opostos esperados
T["sinal_ok"] = np.where(T.tipo == "cont", np.sign(T.coef) == -np.sign(T.spread_Q1mQ5), True)
T["sobrevive_BH"] = (T.p_bh < 0.05) & T.sinal_ok
T["sobrevive_Bonf"] = (T.p_bonf < 0.05) & T.sinal_ok
T["sobrevive_BH_leniente"] = (T.p_bh_norm < 0.05) & T.sinal_ok
T["p_bruto_lt05"] = T.p_prim < 0.05
print("familia:", len(T), " com p:", ok.sum())
T.to_csv(os.path.join(OUT, "tabela_prereg.csv"), index=False)
pickle.dump(series, open(os.path.join(OUT, "series_fm.pkl"), "wb"))
cols = ["pred", "h", "n_datas", "n_efetivo", "coef", "se_nw", "t_nw", "p_norm", "p_prim", "p_bh", "p_bonf", "spread_Q1mQ5", "t_spread", "hit", "pior_seq_neg", "sobrevive_BH", "sobrevive_BH_leniente"]
fmt = T[cols].copy()
for c_ in ["coef", "se_nw", "spread_Q1mQ5"]: fmt[c_] = (fmt[c_] * 100).round(2)
for c_ in ["t_nw", "t_spread", "hit"]: fmt[c_] = fmt[c_].round(2)
for c_ in ["p_norm", "p_prim", "p_bh", "p_bonf"]: fmt[c_] = fmt[c_].round(3)
print(fmt.to_string())
print("\nSOBREVIVEM BH:", T[T.sobrevive_BH][["pred", "h"]].values.tolist())
print("SOBREVIVEM Bonf:", T[T.sobrevive_Bonf][["pred", "h"]].values.tolist())
print("SOBREVIVEM BH leniente (p NW normal):", T[T.sobrevive_BH_leniente][["pred", "h"]].values.tolist())
print("p_prim<0.05 bruto:", T[T.p_bruto_lt05][["pred", "h", "coef", "p_prim"]].values.tolist())
print("n com p_norm<0.05:", (T.p_norm < 0.05).sum(), "de", ok.sum(), "(esperado sob H0 ~", round(0.05 * ok.sum(), 1), ")")
