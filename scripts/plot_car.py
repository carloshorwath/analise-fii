import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sqlalchemy import select

from src.fii_analysis.data.database import Dividendo, PrecoDiario, get_session
from src.fii_analysis.features.dividend_window import get_dividend_windows
from src.fii_analysis.models.statistical import event_study

TICKERS = ["KNIP11", "CPTS11", "HSRE11", "GARE11", "CPSH11", "SNEL11"]
COLORS = {
    "KNIP11": "#1f77b4",
    "CPTS11": "#ff7f0e",
    "HSRE11": "#2ca02c",
    "GARE11": "#d62728",
    "CPSH11": "#9467bd",
    "SNEL11": "#e377c2",
}
OUTPUT = Path(__file__).resolve().parents[1] / "dados" / "car_treino.png"


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    session = get_session()

    fig, ax = plt.subplots(figsize=(14, 8))

    for ticker in TICKERS:
        windows = get_dividend_windows(ticker, session)
        if windows.empty:
            print(f"  {ticker}: sem dados")
            continue

        ev = event_study(windows)
        if ev.empty:
            print(f"  {ticker}: event study vazio")
            continue

        car_pct = ev["retorno_acumulado"] * 100
        dias = ev["dia_relativo"]

        n_eventos = int(ev["n_eventos"].iloc[0])
        ax.plot(dias, car_pct, marker="o", markersize=3, linewidth=1.5,
                color=COLORS.get(ticker, "gray"),
                label=f"{ticker} ({n_eventos} eventos)")

    ax.axvline(x=0, color="black", linestyle="--", linewidth=1.0, alpha=0.7, label="Data-com (dia 0)")
    ax.axhline(y=0, color="gray", linestyle="-", linewidth=0.5, alpha=0.5)

    ax.set_xlabel("Dia Relativo (0 = data-com)", fontsize=12)
    ax.set_ylabel("CAR (%)", fontsize=12)
    ax.set_title("CAR — Cumulative Abnormal Return ao redor da Data-Com\nTreino: 2023-2025 | 5 FIIs", fontsize=14, fontweight="bold")
    ax.set_xticks(range(-10, 11))
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)

    ax.annotate("Run-up\n(compra aqui)", xy=(-5, 0), fontsize=8, color="green",
                ha="center", va="bottom", style="italic")
    ax.annotate("Ex-dividend\ndrop", xy=(1.5, 0), fontsize=8, color="red",
                ha="center", va="bottom", style="italic")

    fig.tight_layout()
    fig.savefig(str(OUTPUT), dpi=150, bbox_inches="tight")
    print(f"Grafico salvo em {OUTPUT}")

    session.close()


if __name__ == "__main__":
    main()
