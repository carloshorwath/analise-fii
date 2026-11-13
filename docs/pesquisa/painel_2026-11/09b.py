from lib import *
exec(open('09_vol.py').read().split("print(\"corr cross-section")[0])
for h in (1,3,6):
    for nm,df in [("todos",P),("sem 6 estranhos",P[~P.weird]),("sem estranhos, liq>=1M",P[(~P.weird)&(P.liq21>=1e6)])]:
        d=df.copy()
        for c_ in ("vol","pvp_cs","liq"): d["x_"+c_]=cs_rank(d,"v_"+c_,20)
        o,T=fm_multi(d,["x_vol","x_pvp_cs"],"ex%d"%h,h,minn=20); print("h=%d %-26s T=%d vol %.2f%% t=%.2f p=%.3f | pvp_cs %.2f%% t=%.2f"%(h,nm,T,*o["x_vol"],o["x_pvp_cs"][0],o["x_pvp_cs"][1]))
# vol univariada sem estranhos
for h in (1,3,6):
    d=P[~P.weird].copy(); d["x_vol"]=cs_rank(d,"v_vol",20); r=fm(d,"x_vol","ex%d"%h,h); print("vol univ sem estranhos h=%d coef %.2f%% t %.2f p_prim %.3f"%(h,r["coef"]*100,r["t_nw"],r["p_prim"]))
# peso dos 6 estranhos no Q5 de vol
d=P.dropna(subset=["x_vol"]); q5=d[d.x_vol>=0.8]; print("share de obs Q5 vol que sao dos 6 estranhos: %.3f ; share deles no painel %.3f"%(q5.weird.mean(),d.weird.mean()))
print("retorno 6m medio dos 6 estranhos (ex6): %.2f%% ; demais %.2f%%"%(P[P.weird].ex6.mean()*100,P[~P.weird].ex6.mean()*100), " n obs estranhos", P.weird.sum())
