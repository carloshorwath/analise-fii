"""
CAR Ajustado por Dividendo — separa o ajuste mecânico do sinal real.

Para cada evento, no dia +1 (ex-date) o preço cai ~dividendo/cota.
Isso é mecânico, não é sinal de mercado.

Ajuste: adiciona div_yield_day1 = dividendo / fechamento_dia0 no retorno do dia +1
→ CAR ajustado mostra o que o mercado faria "sem" o ajuste de dividendo
→ Identifica o janelo teórico correto para a estratégia
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.fii_analysis.data.database import get_session
from src.fii_analysis.features.dividend_window import get_dividend_windows

TICKERS = ["KNIP11", "CPTS11", "HSRE11", "GARE11", "CPSH11", "SNEL11"]
COLORS = {
    "KNIP11": "#1f77b4",
    "CPTS11": "#ff7f0e",
    "HSRE11": "#2ca02c",
    "GARE11": "#d62728",
    "CPSH11": "#9467bd",
    "SNEL11": "#e377c2",
}
OUTPUT_COMP = Path(__file__).resolve().parents[1] / "dados" / "car_comparado.png"
OUTPUT_ADJ = Path(__file__).resolve().parents[1] / "dados" / "car_ajustado.png"


def compute_car_raw(windows: pd.DataFrame) -> pd.DataFrame:
    """CAR bruto: média dos retornos diários por dia relativo, acumulados."""
    if windows.empty:
        return pd.DataFrame()
    med = (
        windows.groupby("dia_relativo")["retorno"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "ret_medio", "count": "n"})
        .sort_values("dia_relativo")
    )
    med["car"] = med["ret_medio"].cumsum()
    return med


def compute_car_adjusted(windows: pd.DataFrame) -> pd.DataFrame:
    """
    CAR ajustado: no dia +1, adiciona div_yield_day1 para remover ajuste mecânico.
    div_yield = valor_cota / fechamento_dia0
    """
    if windows.empty:
        return pd.DataFrame()

    df = windows.copy()

    # Para cada evento, pegar fechamento_dia0 (dia_relativo == 0)
    day0 = (
        df[df["dia_relativo"] == 0][["data_com", "fechamento", "valor_cota"]]
        .rename(columns={"fechamento": "fech_dia0"})
        .copy()
    )
    day0["div_yield"] = day0["valor_cota"] / day0["fech_dia0"].replace(0, np.nan)
    day0 = day0[["data_com", "div_yield"]]

    df = df.merge(day0, on="data_com", how="left")

    # Ajuste: no dia +1, somar div_yield ao retorno bruto
    mask_day1 = df["dia_relativo"] == 1
    df.loc[mask_day1, "retorno_adj"] = df.loc[mask_day1, "retorno"] + df.loc[mask_day1, "div_yield"]
    df.loc[~mask_day1, "retorno_adj"] = df.loc[~mask_day1, "retorno"]

    med = (
        df.groupby("dia_relativo")["retorno_adj"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "ret_medio", "count": "n"})
        .sort_values("dia_relativo")
    )
    med["car"] = med["ret_medio"].cumsum()
    return med


def print_analysis(ticker: str, raw: pd.DataFrame, adj: pd.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"  {ticker}")
    print(f"{'='*60}")
    print(f"  {'Dia':>4}  {'CAR_raw%':>9}  {'CAR_adj%':>9}  {'diff%':>8}")
    for _, r in raw.iterrows():
        dia = int(r["dia_relativo"])
        car_r = r["car"] * 100
        adj_row = adj[adj["dia_relativo"] == dia]
        if adj_row.empty:
            continue
        car_a = float(adj_row["car"].values[0]) * 100
        diff = car_a - car_r
        marker = " <-- ex-div" if dia == 1 else ""
        print(f"  {dia:>4}  {car_r:>9.4f}  {car_a:>9.4f}  {diff:>8.4f}{marker}")

    # Pico pré-ex-date e recuperação pós
    pre_peak = raw[raw["dia_relativo"] <= 0]["car"].max() if not raw.empty else None
    adj_at_day5 = adj[adj["dia_relativo"] == 5]["car"].values
    adj_at_day10 = adj[adj["dia_relativo"] == 10]["car"].values

    if pre_peak is not None:
        print(f"\n  CAR máx pré-data-com:     {pre_peak*100:.4f}%")
    if len(adj_at_day5):
        print(f"  CAR ajustado dia +5:      {adj_at_day5[0]*100:.4f}%")
    if len(adj_at_day10):
        print(f"  CAR ajustado dia +10:     {adj_at_day10[0]*100:.4f}%")


def plot_comparison(results: dict) -> None:
    """Figura 1: raw vs ajustado por ticker."""
    n = len(results)
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.flatten()

    for i, (ticker, (raw, adj)) in enumerate(results.items()):
        ax = axes[i]
        if not raw.empty:
            ax.plot(raw["dia_relativo"], raw["car"] * 100, "o-", markersize=3,
                    linewidth=1.5, color=COLORS.get(ticker, "gray"), label="CAR bruto", alpha=0.7)
        if not adj.empty:
            ax.plot(adj["dia_relativo"], adj["car"] * 100, "s--", markersize=3,
                    linewidth=1.5, color=COLORS.get(ticker, "gray"), label="CAR ajustado (sem div)", alpha=1.0)
        ax.axvline(x=0, color="black", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.axhline(y=0, color="gray", linestyle="-", linewidth=0.4, alpha=0.4)
        ax.set_title(ticker, fontsize=11, fontweight="bold")
        ax.set_xlabel("Dia relativo", fontsize=9)
        ax.set_ylabel("CAR (%)", fontsize=9)
        ax.set_xticks(range(-10, 11, 2))
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.25)

    # Esconder eixo extra
    for j in range(len(results), len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("CAR bruto vs Ajustado por Dividendo\n(ajustado remove o efeito mecânico do ex-dividend no dia +1)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(str(OUTPUT_COMP), dpi=150, bbox_inches="tight")
    print(f"\nGráfico comparativo salvo em {OUTPUT_COMP}")


def plot_adjusted_all(results: dict) -> None:
    """Figura 2: todos os CARs ajustados no mesmo gráfico."""
    fig, ax = plt.subplots(figsize=(14, 8))

    for ticker, (raw, adj) in results.items():
        if adj.empty:
            continue
        n_eventos = int(adj["n"].iloc[0]) if "n" in adj.columns else "?"
        ax.plot(adj["dia_relativo"], adj["car"] * 100, marker="o", markersize=3,
                linewidth=1.5, color=COLORS.get(ticker, "gray"),
                label=f"{ticker} ({n_eventos} ev.)")

    ax.axvline(x=0, color="black", linestyle="--", linewidth=1.0, alpha=0.7, label="Data-com (dia 0)")
    ax.axhline(y=0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)

    ax.set_xlabel("Dia Relativo (0 = data-com)", fontsize=12)
    ax.set_ylabel("CAR Ajustado (%)", fontsize=12)
    ax.set_title("CAR Ajustado por Dividendo — Sinal Real sem Ajuste Mecânico\n"
                 "Treino: 2023-2025 | 5 FIIs", fontsize=14, fontweight="bold")
    ax.set_xticks(range(-10, 11))
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)

    # Anotar regiões
    ax.annotate("run-up", xy=(-4, ax.get_ylim()[0] if ax.get_ylim()[0] != 0 else 0),
                fontsize=9, color="green", ha="center", style="italic",
                xytext=(-4, 0), arrowprops=None)
    ax.annotate("data-com", xy=(0, 0), fontsize=8, color="black",
                ha="left", va="bottom", xytext=(0.2, 0), style="italic")

    fig.tight_layout()
    fig.savefig(str(OUTPUT_ADJ), dpi=150, bbox_inches="tight")
    print(f"Gráfico ajustado salvo em {OUTPUT_ADJ}")


def main():
    OUTPUT_COMP.parent.mkdir(parents=True, exist_ok=True)

    session = get_session()
    results = {}

    for ticker in TICKERS:
        windows = get_dividend_windows(ticker, session)
        if windows.empty:
            print(f"  {ticker}: sem dados")
            continue

        raw = compute_car_raw(windows)
        adj = compute_car_adjusted(windows)
        results[ticker] = (raw, adj)
        print_analysis(ticker, raw, adj)

    print("\n" + "=" * 60)
    print("  RESUMO — JANELA TEÓRICA SUGERIDA")
    print("=" * 60)
    print("  Com o CAR ajustado:")
    print("  - Se CAR_adj cai apos dia 0: sinal real de venda apos data-com")
    print("  - Se CAR_adj sobe/estavel: queda bruta era so mecanica; segurar pode ser melhor")
    print("  - Olhe onde o CAR_adj para de subir = onde encerrar a posicao")
    print("  - Olhe onde o CAR_adj comeca a subir = onde entrar")

    plot_comparison(results)
    plot_adjusted_all(results)

    session.close()


if __name__ == "__main__":
    main()
