"""
Diagnóstico: identificar qual indicador retorna None para cada relatório
descartado pelo dropna() no ThresholdOptimizer.optimize() para KNIP11.
"""
import sys
sys.path.insert(0, r"D:\analise-de-acoes")

from collections import Counter
from datetime import date

import pandas as pd
from sqlalchemy import select

from src.fii_analysis.data.database import (
    PrecoDiario,
    RelatorioMensal,
    get_cnpj_by_ticker,
    get_session,
)
from src.fii_analysis.features.valuation import get_dy_gap_percentil, get_pvp_percentil
from src.fii_analysis.models.threshold_optimizer import ThresholdOptimizer

TICKER = "KNIP11"

def main():
    session = get_session()
    opt = ThresholdOptimizer()

    cnpj = get_cnpj_by_ticker(TICKER, session)
    print(f"Ticker: {TICKER}  CNPJ: {cnpj}\n")

    # --- Load reports (same query as optimize()) ---
    reports_db = session.execute(
        select(RelatorioMensal.data_referencia, RelatorioMensal.data_entrega)
        .where(RelatorioMensal.cnpj == cnpj, RelatorioMensal.data_entrega.isnot(None))
        .order_by(RelatorioMensal.data_entrega.asc())
    ).all()
    print(f"Total de relatórios com data_entrega: {len(reports_db)}")

    # --- Load prices (same query as optimize()) ---
    prices_db = session.execute(
        select(PrecoDiario.data, PrecoDiario.fechamento_aj)
        .where(PrecoDiario.ticker == TICKER)
        .order_by(PrecoDiario.data.asc())
    ).all()
    prices_df = pd.DataFrame([{"data": p.data, "fechamento_aj": p.fechamento_aj} for p in prices_db])
    print(f"Total de preços diários: {len(prices_df)}")
    if not prices_df.empty:
        print(f"  Primeiro preço: {prices_df['data'].iloc[0]}  Último: {prices_df['data'].iloc[-1]}")

    # --- Check each report ---
    results = []
    for i, r in enumerate(reports_db):
        t = r.data_entrega
        data_ref = r.data_referencia

        pvp_pct, pvp_janela = get_pvp_percentil(TICKER, t, session=session)
        dy_gap_pct = get_dy_gap_percentil(TICKER, t, session=session)
        meses_alerta = opt._get_point_in_time_fundamentos(TICKER, t, session)
        fwd_ret = opt._get_forward_return(TICKER, t, opt.forward_days, prices_df)

        pvp_none = pvp_pct is None
        dy_none = dy_gap_pct is None
        fwd_none = fwd_ret is None
        discarded = pvp_none or dy_none or fwd_none

        results.append({
            "idx": i,
            "data_ref": data_ref,
            "data_entrega": t,
            "pvp_pct": pvp_pct,
            "pvp_janela": pvp_janela,
            "dy_gap_pct": dy_gap_pct,
            "meses_alerta": meses_alerta,
            "fwd_ret": fwd_ret,
            "discarded": discarded,
            "pvp_none": pvp_none,
            "dy_none": dy_none,
            "fwd_none": fwd_none,
        })

    df = pd.DataFrame(results)
    n_total = len(df)
    n_discarded = df["discarded"].sum()
    n_kept = n_total - n_discarded

    print(f"\n{'='*70}")
    print(f"RESUMO: {n_total} relatórios | {n_kept} mantidos | {n_discarded} descartados")
    print(f"{'='*70}")

    # --- Breakdown by cause ---
    disc = df[df["discarded"]]
    causes = Counter()
    for _, row in disc.iterrows():
        parts = []
        if row["pvp_none"]:
            parts.append("pvp_pct=None")
        if row["dy_none"]:
            parts.append("dy_gap_pct=None")
        if row["fwd_none"]:
            parts.append("fwd_ret=None")
        causes[" + ".join(parts)] += 1

    print(f"\nBreakdown por causa:")
    for cause, count in causes.most_common():
        print(f"  {cause}: {count}")

    # --- Show discarded reports detail ---
    print(f"\n--- Relatórios descartados (detalhe) ---")
    for _, row in disc.iterrows():
        reasons = []
        if row["pvp_none"]:
            reasons.append(f"pvp_pct=None (janela={row['pvp_janela']})")
        if row["dy_none"]:
            reasons.append("dy_gap_pct=None")
        if row["fwd_none"]:
            reasons.append("fwd_ret=None")
        print(f"  [{row['idx']:3d}] ref={row['data_ref']}  entrega={row['data_entrega']}  "
              f"| {' | '.join(reasons)}")

    # --- Check earliest kept vs latest discarded ---
    if n_kept > 0:
        kept = df[~df["discarded"]]
        print(f"\nPrimeiro mantido: ref={kept['data_ref'].iloc[0]} entrega={kept['data_entrega'].iloc[0]}")
        print(f"Último mantido:   ref={kept['data_ref'].iloc[-1]} entrega={kept['data_entrega'].iloc[-1]}")

    # --- Additional diagnostics: why pvp_pct is None for early reports ---
    pvp_disc = disc[disc["pvp_none"]]
    if not pvp_disc.empty:
        print(f"\n--- Diagnóstico pvp_pct=None ({len(pvp_disc)} casos) ---")
        # Check price data before first discarded
        for _, row in pvp_disc.head(5).iterrows():
            t = row["data_entrega"]
            n_precos_antes = len(prices_df[prices_df["data"] <= t])
            # Check VP availability
            vp_rows = session.execute(
                select(RelatorioMensal.data_referencia, RelatorioMensal.data_entrega, RelatorioMensal.vp_por_cota)
                .where(
                    RelatorioMensal.cnpj == cnpj,
                    RelatorioMensal.data_entrega <= t,
                    RelatorioMensal.vp_por_cota.isnot(None),
                )
                .order_by(RelatorioMensal.data_entrega.desc())
                .limit(5)
            ).all()
            print(f"  ref={row['data_ref']} entrega={t} -> preços até t: {n_precos_antes}, "
                  f"VP reports <= t: {len(vp_rows)}")
            for vr in vp_rows[:3]:
                print(f"    VP ref={vr.data_referencia} entrega={vr.data_entrega} vp={vr.vp_por_cota}")

    # --- Diagnostics: why dy_gap_pct is None ---
    dy_disc = disc[disc["dy_none"]]
    if not dy_disc.empty:
        print(f"\n--- Diagnóstico dy_gap_pct=None ({len(dy_disc)} casos) ---")
        for _, row in dy_disc.head(5).iterrows():
            t = row["data_entrega"]
            n_precos_antes = len(prices_df[prices_df["data"] <= t])
            print(f"  ref={row['data_ref']} entrega={t} -> preços até t: {n_precos_antes} (need >= 252)")

    # --- Diagnostics: why fwd_ret is None ---
    fwd_disc = disc[disc["fwd_none"]]
    if not fwd_disc.empty:
        print(f"\n--- Diagnóstico fwd_ret=None ({len(fwd_disc)} casos) ---")
        for _, row in fwd_disc.head(5).iterrows():
            t = row["data_entrega"]
            subset = prices_df[prices_df["data"] >= t].head(opt.forward_days + 1)
            last_price_date = prices_df["data"].iloc[-1] if not prices_df.empty else "N/A"
            print(f"  ref={row['data_ref']} entrega={t} -> preços futuros disponíveis: {len(subset)}/{opt.forward_days+1} "
                  f"(need {opt.forward_days+1}), último preço em BD: {last_price_date}")

    session.close()


if __name__ == "__main__":
    main()
