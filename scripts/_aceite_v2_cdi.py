"""[PESQUISA — não operacional] Teste de aceite V2 CDI — Fase 1 (diagnóstico) + Fase 2 (OOS) + Veredito.

EXPERIMENTO ENCERRADO (29/04/2026). Veredito: RESIDUO_PIORA.
A hipótese de substituir P/VP bruto por resíduo CDI-ajustado foi rejeitada em OOS.
Este script é mantido apenas como registro de pesquisa. Não usar no fluxo operacional.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8')

import time
from datetime import date

TICKERS = ["KNIP11", "HSRE11", "CPSH11", "GARE11"]

from src.fii_analysis.data.database import get_session_ctx

# ═══════════════════════════════════════════════════════════════════
# FASE 1 — DIAGNÓSTICO
# ═══════════════════════════════════════════════════════════════════
print("=" * 78)
print("FASE 1 — DIAGNÓSTICO: P/VP Bruto vs Resíduo CDI-Ajustado")
print("=" * 78)

from src.fii_analysis.models.cdi_comparison import (
    compute_diagnostic_batch,
    build_daily_residual_series,
)

t0 = time.time()
with get_session_ctx() as session:
    diagnostics = compute_diagnostic_batch(TICKERS, session, low_pct=20, high_pct=80)

# Tabela
hdr = (f"{'Ticker':<10} {'Status':<20} {'N_obs':>7} {'Corr':>7} "
       f"{'%Discord':>9} {'Br→Nt':>7} {'Nt→Ex':>7} {'Ambos':>7}")
print(hdr)
print("-" * len(hdr))

for d in diagnostics:
    if d.get("status") != "OK":
        print(f"{d['ticker']:<10} {d['status']:<20}")
        continue

    print(f"{d['ticker']:<10} {'OK':<20} {d['n_obs']:>7} {d['corr']:>7.3f} "
          f"{d['pct_discordancia']:>8.1f}% "
          f"{d['bruto_extremo_residuo_neutro']:>7} "
          f"{d['bruto_neutro_residuo_extremo']:>7} "
          f"{d['ambos_concordam']:>7}")

print()
print("Observações de plausibilidade:")
for d in diagnostics:
    if d.get("status") == "OK":
        print(f"  {d['ticker']}: {d['observacao']}")

# Exemplos de discordância
print()
print("Exemplos de discordância (top 3 por ticker):")
for d in diagnostics:
    if d.get("status") != "OK":
        continue
    print(f"\n  {d['ticker']}:")
    for ex in d.get("exemplos_discordancia", [])[:3]:
        print(f"    {ex['data']} | Bruto={ex['pvp_pct']:.1f}% [{ex['regime_bruto']}] "
              f"| Resíduo={ex['residuo_pct']:.1f}% [{ex['regime_residuo']}]")

elapsed_f1 = time.time() - t0
print(f"\nTempo Fase 1: {elapsed_f1:.1f}s")

# ═══════════════════════════════════════════════════════════════════
# FASE 2 — TESTE OOS
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("FASE 2 — TESTE OOS: Baseline (P/VP) vs Experimental (Resíduo CDI)")
print("=" * 78)

from src.fii_analysis.models.cdi_oos_evaluation import (
    compare_oos_batch,
    verdict,
)

t0 = time.time()
with get_session_ctx() as session:
    batch = compare_oos_batch(TICKERS, session)

elapsed_f2 = time.time() - t0
print(f"Tempo Fase 2: {elapsed_f2:.1f}s")

# ─── 2a. Episódios ────────────────────────────────────────────────
print("\n--- Episódios ---")
print(f"{'Ticker':<10} {'Status':<16} "
      f"{'BL_WR':>7} {'EX_WR':>7} {'ΔWR':>7} "
      f"{'BL_Ret':>8} {'EX_Ret':>8} {'ΔRet':>8} "
      f"{'BL_N':>5} {'EX_N':>5}")
print("-" * 105)

for r in batch.get("episodes", []):
    tkr = r["ticker"]
    st = r.get("status", "?")
    if st != "OK":
        print(f"{tkr:<10} {st:<16}")
        continue

    bl = r.get("baseline", {})
    ex = r.get("experimental", {})

    def _s(d, k, fmt=".3f"):
        v = d.get(k)
        return format(v, fmt) if v is not None else "n/d"

    wr_bl = bl.get("win_rate_buy")
    wr_ex = ex.get("win_rate_buy")
    m_bl = bl.get("mean_buy")
    m_ex = ex.get("mean_buy")

    d_wr = f"{(wr_ex or 0) - (wr_bl or 0):+.3f}" if wr_bl is not None and wr_ex is not None else "n/d"
    d_ret = f"{(m_ex or 0) - (m_bl or 0):+.4f}" if m_bl is not None and m_ex is not None else "n/d"

    print(f"{tkr:<10} {'OK':<16} "
          f"{_s(bl,'win_rate_buy'):>7} {_s(ex,'win_rate_buy'):>7} {d_wr:>7} "
          f"{_s(bl,'mean_buy','.4f'):>8} {_s(ex,'mean_buy','.4f'):>8} {d_ret:>8} "
          f"{bl.get('n_buy',0):>5} {ex.get('n_buy',0):>5}")

# ─── 2b. Walk-Forward ────────────────────────────────────────────
print("\n--- Walk-Forward Rolling ---")
print(f"{'Ticker':<10} {'Status':<16} "
      f"{'BL_WR':>7} {'EX_WR':>7} {'ΔWR':>7} "
      f"{'BL_Ret':>8} {'EX_Ret':>8} {'ΔRet':>8} "
      f"{'BL_Neff':>8} {'EX_Neff':>8} {'Steps':>6}")
print("-" * 115)

for r in batch.get("walk_forward", []):
    tkr = r["ticker"]
    st = r.get("status", "?")
    if st != "OK":
        print(f"{tkr:<10} {st:<16}")
        continue

    bl = r.get("baseline", {})
    ex = r.get("experimental", {})

    if "error" in bl:
        print(f"{tkr:<10} {'BL_ERR':<16} {bl['error'][:60]}")
        continue
    if "error" in ex:
        print(f"{tkr:<10} {'EX_ERR':<16} {ex['error'][:60]}")
        continue

    def _s(d, k, fmt=".3f"):
        v = d.get(k)
        return format(v, fmt) if v is not None else "n/d"

    wr_bl = bl.get("win_rate_buy")
    wr_ex = ex.get("win_rate_buy")
    m_bl = bl.get("mean_buy")
    m_ex = ex.get("mean_buy")

    d_wr = f"{(wr_ex or 0) - (wr_bl or 0):+.3f}" if wr_bl is not None and wr_ex is not None else "n/d"
    d_ret = f"{(m_ex or 0) - (m_bl or 0):+.4f}" if m_bl is not None and m_ex is not None else "n/d"

    print(f"{tkr:<10} {'OK':<16} "
          f"{_s(bl,'win_rate_buy'):>7} {_s(ex,'win_rate_buy'):>7} {d_wr:>7} "
          f"{_s(bl,'mean_buy','.4f'):>8} {_s(ex,'mean_buy','.4f'):>8} {d_ret:>8} "
          f"{bl.get('n_effective_buy',0):>8} {ex.get('n_effective_buy',0):>8} "
          f"{bl.get('n_steps',0):>6}")


# ═══════════════════════════════════════════════════════════════════
# VEREDITO FINAL
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("VEREDITO FINAL")
print("=" * 78)

v = verdict(batch)

print(f"\nClassificação: {v['classificacao']}")
print(f"  Melhora: {v['n_melhora']} | Empata: {v['n_empata']} | "
      f"Piora: {v['n_piora']} | Inconclusivo: {v['n_inconclusivo']}")

print("\nDetalhes:")
for d in v["detalhes"]:
    print(d)

print()
if v["classificacao"] == "RESIDUO_MELHORA":
    print("→ O resíduo CDI-ajustado mostra ganho OOS real.")
    print("→ Recomendação: seguir para Fase 3 shadow mode.")
elif v["classificacao"] == "RESIDUO_EMPATA":
    print("→ O resíduo CDI-ajustado não piora nem melhora significativamente.")
    print("→ Pode seguir para Fase 3 shadow como narrativa complementar, sem ganho estatístico.")
elif v["classificacao"] == "RESIDUO_PIORA":
    print("→ O resíduo CDI-ajustado piora o sinal OOS.")
    print("→ Recomendação: NÃO seguir para Fase 3. Parar por aqui.")
else:
    print("→ Resultado inconclusivo — dados insuficientes ou misto.")
    print("→ Recomendação: coletar mais dados antes de decidir.")

print(f"\nTempo total: {elapsed_f1 + elapsed_f2:.1f}s")