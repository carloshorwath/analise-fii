import numpy as np
import pandas as pd


def _is_empty(val) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    return False


def format_currency(val) -> str:
    if _is_empty(val):
        return "n/d"
    return f"R$ {float(val):,.2f}"


def format_pct(val) -> str:
    if _is_empty(val):
        return "n/d"
    return f"{float(val):.2%}"


def format_number(val, decimals: int = 2) -> str:
    if _is_empty(val):
        return "n/d"
    return f"{float(val):,.{decimals}f}"


def radar_cell(val: bool) -> str:
    return "PASSOU" if val else "FALHOU"


def render_panorama_table(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    if "preco" in display.columns:
        display["preco"] = display["preco"].apply(format_currency)
    if "pvp" in display.columns:
        display["pvp"] = display["pvp"].apply(lambda x: format_number(x) if x else "n/d")
    if "dy_12m" in display.columns:
        display["dy_12m"] = display["dy_12m"].apply(format_pct)
    if "dy_24m" in display.columns:
        display["dy_24m"] = display["dy_24m"].apply(format_pct)
    if "dy_mes" in display.columns:
        display["dy_mes"] = display["dy_mes"].apply(format_pct)
    if "rent_acum" in display.columns:
        display["rent_acum"] = display["rent_acum"].apply(format_pct)
    if "vp" in display.columns:
        display["vp"] = display["vp"].apply(format_currency)
    if "volume_medio_21d" in display.columns:
        display["volume_medio_21d"] = display["volume_medio_21d"].apply(format_currency)
    return display


def render_radar_matriz(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    for col in ["pvp_baixo", "dy_gap_alto", "saude_ok", "liquidez_ok"]:
        if col in display.columns:
            display[col] = display[col].apply(lambda x: "PASSOU" if x else "FALHOU")
    return display
