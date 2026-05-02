"""Camada de decisao — agrega os 3 modos estatisticos + flags de risco
em uma recomendacao acionavel por ticker.

Sinal (estatistico, neutro) -> Acao (derivada, pode ser vetada por Risco).
"""

from src.fii_analysis.decision.portfolio_advisor import (
    AlertaEstrutural,
    HoldingAdvice,
    aconselhar_carteira,
    alertas_estruturais,
    exportar_sugestoes_csv,
    exportar_sugestoes_md,
)
from src.fii_analysis.decision.daily_report import (
    DailyCommandCenter,
    build_daily_command_center,
    export_daily_report_csv,
    export_daily_report_md,
)
from src.fii_analysis.decision.recommender import (
    TickerDecision,
    decidir_ticker,
    decidir_universo,
)

__all__ = [
    "TickerDecision",
    "decidir_ticker",
    "decidir_universo",
    "HoldingAdvice",
    "AlertaEstrutural",
    "DailyCommandCenter",
    "aconselhar_carteira",
    "alertas_estruturais",
    "exportar_sugestoes_md",
    "exportar_sugestoes_csv",
    "build_daily_command_center",
    "export_daily_report_md",
    "export_daily_report_csv",
]
