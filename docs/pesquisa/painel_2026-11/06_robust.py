from lib import *
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 300); pd.set_option('display.max_columns', 40)
P0 = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
SRC = {"dygap_pct": "v_dygap_pct", "dvp6": "v_dvp6", "liq": "v_liq", "dvp3": "v_dvp3"}
CAND = [("dygap_pct", 1, "cont"), ("dvp6", 3, "cont"), ("dvp6", 6, "cont"), ("liq_ok", 3, "disc"), ("liq_ok", 6, "disc"), ("liq", 6, "cont")]

def prep(df, k):
    df = df.copy()
    if k in SRC: df["x_" + k] = cs_rank(df, SRC[k], 10)
    return df
def run(df, k, h, kind, y=None, minn=20, rerank=True):
    y = y or "ex%d" % h
    d = prep(df, k) if (kind == "cont" and rerank) else df
    if kind == "cont":
        r = fm(d, "x_" + k, y, h, minn=minn); sp = sorted_ports(d, "x_" + k, y, h, 5, minn=minn)
        return dict(T=r["T"], coef_pct=r["coef"] * 100, t=r["t_nw"], p_norm=r["p_norm"], spread_pct=(sp["mean"] * 100 if sp else np.nan), t_sp=(sp["t_nw"] if sp else np.nan))
    r = fm(d, "d_" + k, y, h, min_each=3, minn=minn)
    return dict(T=r["T"], coef_pct=r["coef"] * 100, t=r["t_nw"], p_norm=r["p_norm"], spread_pct=np.nan, t_sp=np.nan)

allrows = []
for (k, h, kind) in CAND:
    print("\n" + "=" * 100); print("CANDIDATO (EXPLORATORIO: nao sobrevive a BH pre-registrado):", k, "h=%d" % h)
    rows = []
    def add(name, res): rows.append(dict(variante=name, **res)); allrows.append(dict(pred=k, h=h, variante=name, **res))
    add("base", run(P0, k, h, kind, rerank=False))
    # (i) metades e anos
    dts = sorted(P0.loc[P0["x_" + k if kind == "cont" else "d_" + k].notna() & P0["ex%d" % h].notna(), "t"].unique()); mid = dts[len(dts) // 2]
    add("(i) metade inicial (<=%s)" % pd.Timestamp(mid).date(), run(P0[P0.t <= mid], k, h, kind, rerank=False))
    add("(i) metade final", run(P0[P0.t > mid], k, h, kind, rerank=False))
    for yr in (2022, 2023, 2024, 2025, 2026):
        add("(i) formacao em %d" % yr, run(P0[P0.t.dt.year == yr], k, h, kind, rerank=False))
    # (ii) segmento
    for sg in ("Tijolo", "Papel", "Hibrido"):
        add("(ii) seg %s" % sg, run(P0[P0.seg == sg], k, h, kind, minn=10))
    # (iii) liquidez
    if k != "liq_ok" and k != "liq":
        add("(iii) liq21>=500k", run(P0[P0.liq21 >= 5e5], k, h, kind)); add("(iii) liq21>=1M", run(P0[P0.liq21 >= 1e6], k, h, kind))
    else:
        add("(iii) liq: degenerado (a variavel e a propria liquidez)", dict(T=0, coef_pct=np.nan, t=np.nan, p_norm=np.nan, spread_pct=np.nan, t_sp=np.nan))
    # (iv) eventos estranhos
    weird = ["CACR11", "MFII11", "HCTR11", "DEVA11", "TGAR11", "URPR11"]
    add("(iv) sem 6 tickers estranhos (+queda>40%)", run(P0[~P0.ticker.isin(weird)], k, h, kind))
    # (v) lag 1
    add("(v) entrada em t+1 pregao", run(P0, k, h, kind, y="ex%d_lag1" % h, rerank=False))
    # (vii) sobrevivencia
    add("(vii) listado >=730d antes de t", run(P0[P0.idade_dias >= 730], k, h, kind))
    add("(vii) listado antes de 2022-04-29", run(P0[P0.primeiro_preco <= "2022-04-29"], k, h, kind))
    add("(vii) listado <730d (jovens)", run(P0[P0.idade_dias < 730], k, h, kind, minn=10))
    add("(exp) pvp_pct63? n/a", dict(T=0, coef_pct=np.nan, t=np.nan, p_norm=np.nan, spread_pct=np.nan, t_sp=np.nan)) if False else None
    print(pd.DataFrame(rows).round(3).to_string(index=False))
pd.DataFrame(allrows).to_csv(os.path.join(OUT, "robustez_candidatos.csv"), index=False)
