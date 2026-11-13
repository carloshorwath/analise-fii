out = []
t0 = time.time()
xr_all = None
for tk in tickers:
    cnpj = t2c[tk]
    f = F[tk].dropna(); a = A[tk].dropna(); v = V[tk]
    first_px = f.index.min()
    rel = rel_cached(tk, S)
    rel = rel[rel.vp_aj.notna() & (rel.vp_aj > 0)].copy()
    rs = rel.sort_values("data_entrega")
    cur_ref = pd.Timestamp.min; cur_vp = np.nan; vv = []
    for r_ in rs.itertuples():
        if r_.data_referencia >= cur_ref:
            cur_ref = r_.data_referencia; cur_vp = r_.vp_aj
        vv.append(cur_vp)
    rs = rs.assign(vp_vig=vv)
    rsd = rs[["data_entrega", "vp_vig"]].copy()
    rsd["data_entrega"] = pd.to_datetime(rsd["data_entrega"])
    rsd = rsd.sort_values("data_entrega").drop_duplicates("data_entrega", keep="last")
    fd = pd.DataFrame({"data": f.index, "preco": f.values})
    fd = pd.merge_asof(fd, rsd, left_on="data", right_on="data_entrega", direction="backward").dropna(subset=["vp_vig"])
    fd["pvp"] = fd.preco / fd.vp_vig
    fd["pvp_pct"] = pvp_percentil_ate_t_menos_1(fd["pvp"].values, 504, 63)
    fd["n_prev"] = np.minimum(np.arange(len(fd)), 504)
    fd = fd.set_index("data")
    dv = divs.get(tk)
    dyd = pd.Series(np.nan, index=f.index)
    if dv is not None:
        dd = dv.data_com.values; cs = np.concatenate([[0.0], np.cumsum(dv.d.values.astype(float))])
        idx_t = np.searchsorted(dd, f.index.values, side="right")
        starts = (f.index - pd.DateOffset(months=12))
        idx_s = np.searchsorted(dd, starts.values, side="right")
        soma = cs[idx_t] - cs[idx_s]
        ok = (starts >= COV_START) & (starts >= first_px) & (soma > 0)
        dyd[:] = np.where(ok, soma / f.values, np.nan)
    gap = dyd - cdi12.reindex(dyd.index)
    liq21 = (f * v.reindex(f.index)).rolling(21, min_periods=1).mean()
    inf_r = R[R.cnpj == cnpj].sort_values("data_referencia")
    ap_r = AP[AP.cnpj == cnpj]
    for t in forms:
        if t not in f.index: continue
        o = {"ticker": tk, "t": t, "preco": f[t], "seg": segmento[tk], "primeiro_preco": first_px}
        if t in fd.index:
            o["pvp"] = fd.at[t, "pvp"]; o["pvp_pct"] = fd.at[t, "pvp_pct"]; o["n_prev"] = fd.at[t, "n_prev"]
        o["dy12"] = dyd.get(t, np.nan); o["gap"] = gap.get(t, np.nan)
        if not np.isnan(o["gap"]):
            pos = f.index.get_loc(t)
            w = gap.iloc[max(0, pos - 252):pos].dropna(); n = len(w)
            if n >= 50:
                o["dygap_pct"] = float((w <= o["gap"]).sum() / n * 100); o["dygap_n"] = n
        for k in (1, 3, 6, 12):
            t_k = t - pd.DateOffset(months=k)
            if t_k >= pd.Timestamp("2022-04-01"):
                ak = a[a.index <= t_k]
                if len(ak) and (t_k - ak.index[-1]).days <= 7:
                    o["mom%d" % k] = a[t] / ak.iloc[-1] - 1
        o["liq21"] = liq21.get(t, np.nan)
        pos_a = a.index.get_loc(t)
        w252 = a.iloc[max(0, pos_a - 251):pos_a + 1]
        if len(w252) >= 63:
            r_ = np.log(w252).diff().dropna(); o["vol"] = float(r_.std(ddof=1) * np.sqrt(252))
            xx = xf.reindex(w252.index); ok = xx.notna()
            if ok.sum() >= 63:
                ra = np.log(w252[ok]).diff().dropna(); rx = np.log(xx[ok]).diff().dropna()
                if rx.var() > 0: o["beta"] = float(np.cov(ra, rx)[0, 1] / rx.var())
        w504 = a.iloc[max(0, pos_a - 503):pos_a + 1]
        if len(w504) >= 63:
            o["mdd"] = float((w504 / w504.cummax() - 1).min())
        pit = inf_r[inf_r.data_entrega <= t]
        if len(pit):
            dyv = pit.tail(24).dy_mes_pct.dropna(); dyv = dyv[dyv > 0]
            if len(dyv) >= 6 and dyv.mean() > 0:
                cv = dyv.std(ddof=0) / dyv.mean(); o["score_hist"] = max(0, min(100, round((1 - min(cv / 0.5, 1)) * 100)))
            else: o["score_hist"] = 50
        rr = rel[pd.to_datetime(rel.data_entrega) <= t].sort_values("data_referencia")
        if len(rr):
            vp0 = rr.iloc[-1]; ref0 = vp0.data_referencia
            for k in (3, 6):
                prev = rr[rr.data_referencia == ref0 - pd.DateOffset(months=k)]
                if len(prev): o["dvp%d" % k] = vp0.vp_aj / prev.iloc[0].vp_aj - 1
            o["pl"] = vp0.patrimonio_liq; o["ref_vp"] = ref0
            ap_p = ap_r[(ap_r.data_entrega <= t) & (ap_r.data_referencia == ref0)]
            if len(ap_p) and pd.notna(ap_p.iloc[-1].ativo_total) and vp0.patrimonio_liq and vp0.patrimonio_liq > 0:
                o["lev"] = float(ap_p.iloc[-1].ativo_total) / float(vp0.patrimonio_liq)
        out.append(o)
P = pd.DataFrame(out)
print("painel base", P.shape, time.time() - t0)
t0 = time.time()
sc = []
for r_ in P[["ticker", "t"]].itertuples():
    try:
        fl = saude_mod.flag_destruicao_capital(r_.ticker, S, t=r_.t.date())
        sc.append((fl["destruicao"], fl["gravidade"], fl["score_saude"], fl["pct_3m"], fl["pct_6m"], fl["motivo"][:30]))
    except Exception as e:
        sc.append((None, None, None, None, None, "ERR " + str(e)[:30]))
P[["destr", "gravidade", "saude", "saude_pct3m", "saude_pct6m", "saude_motivo"]] = pd.DataFrame(sc, index=P.index)
print("saude", time.time() - t0, P.saude_motivo.str.startswith("ERR").sum())
P.to_pickle(os.path.join(OUT, "painel_base.pkl"))
pickle.dump({"F": F, "A": A, "V": V, "cal": cal, "forms": forms, "me": me, "cdi": cdi, "xf": xf, "segmento": segmento}, open(os.path.join(OUT, "wide.pkl"), "wb"))
