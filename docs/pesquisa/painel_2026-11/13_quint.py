from lib import *
P = pd.read_pickle(os.path.join(OUT, "painel_final.pkl"))
for k, h in [("dvp6", 6), ("dvp6", 3), ("pvp_pct", 6), ("pvp_cs", 6), ("pvp_cs", 12), ("dygap_pct", 3), ("dy12", 6), ("score", 6), ("saude", 6)]:
    sp = sorted_ports(P, "x_" + k, "ex%d" % h, h); print("%-9s h=%2d excesso medio por quintil (%%): %s | Q1-Q5 %.2f%% t %.2f hit(Q1>Q5) %.2f pior seq neg %d T=%d" % (k, h, (sp["Q"].mean() * 100).round(2).tolist(), sp["mean"] * 100, sp["t_nw"], sp["hit"], sp["worst_run"], sp["T"]))
