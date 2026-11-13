from lib import *
c = conn()
D = pd.read_sql("select ticker,data_com,valor_cota from dividendos where data_com>='2022-04-01'", c, parse_dates=["data_com"])
mes = pd.Series(me, index=me)
D["ym"] = D.data_com.dt.to_period("M")
lastday = {pd.Period(d, "M"): d for d in me}
D["is_last"] = D.data_com == D.ym.map(lastday)
D["dias_ate_fim"] = (D.ym.map(lastday) - D.data_com).dt.days
print("dividendos desde 2022-04:", len(D), " data_com == ultimo pregao do mes: %.3f" % D.is_last.mean(), " nos 3 ultimos pregoes do mes (<=4 dias corridos): %.3f" % (D.dias_ate_fim <= 4).mean())
print(D.dias_ate_fim.describe())
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
# predictor defasado 1 mes (stale): x em t-1 formacao, retorno a partir de t
ml = list(me); prev = {ml[i]: ml[i - 1] for i in range(1, len(ml))}
P["t_prev"] = P.t.map(prev)
for k in ["dygap_pct", "dy12", "dvp6"]:
    X = P[["ticker", "t", "x_" + k]].rename(columns={"t": "t_prev", "x_" + k: "xlag_" + k})
    Pm = P.merge(X, on=["ticker", "t_prev"], how="left")
    for h in (1, 3, 6):
        a = fm(Pm, "x_" + k, "ex%d" % h, h); b = fm(Pm, "xlag_" + k, "ex%d" % h, h)
        print("%-10s h=%d  contemporaneo: coef %.2f%% t %.2f T %d | defasado 1 mes: coef %.2f%% t %.2f T %d" % (k, h, a["coef"] * 100, a["t_nw"], a["T"], b["coef"] * 100, b["t_nw"], b["T"]))
# DY excluindo dividendos dos ultimos 5 dias corridos antes de t (nao-anunciados): recalcula dygap_pct simplificado via dy12' = dividendos (t-12m, t-5d]
F_, A_ = F, A
Dv = pd.read_sql("select ticker,data_com,valor_cota d from dividendos where valor_cota is not null", c, parse_dates=["data_com"])
rows = []
for tk, g in Dv.groupby("ticker"):
    g = g.sort_values("data_com"); dd = g.data_com.values; cs = np.concatenate([[0.0], np.cumsum(g.d.values.astype(float))])
    sub = P[P.ticker == tk]
    for r in sub.itertuples():
        i1 = np.searchsorted(dd, (r.t - pd.Timedelta(days=5)).to_datetime64(), side="right"); st = r.t - pd.DateOffset(months=12)
        i0 = np.searchsorted(dd, st.to_datetime64(), side="right")
        rows.append((tk, r.t, (cs[i1] - cs[i0]) / r.preco if (st >= pd.Timestamp("2022-03-31") and st >= r.primeiro_preco) else np.nan))
Q = pd.DataFrame(rows, columns=["ticker", "t", "dy12_ex5d"]); P = P.merge(Q, on=["ticker", "t"])
P["x_dy12_ex5d"] = cs_rank(P, "dy12_ex5d", 20)
for h in (1, 3):
    a = fm(P, "x_dy12", "ex%d" % h, h); b = fm(P, "x_dy12_ex5d", "ex%d" % h, h)
    print("dy12 h=%d: com div ate t: %.2f%% t %.2f | sem div dos ultimos 5 dias: %.2f%% t %.2f" % (h, a["coef"] * 100, a["t_nw"], b["coef"] * 100, b["t_nw"]))
