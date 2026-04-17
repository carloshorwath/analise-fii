from datetime import date, timedelta

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay


def make_splits(
    events: pd.DataFrame,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
    gap_days: int = 10,
) -> dict:
    df = events.sort_values("data_com").reset_index(drop=True)
    n = len(df)
    if n == 0:
        return {
            "train": pd.DataFrame(columns=events.columns),
            "val": pd.DataFrame(columns=events.columns),
            "test": pd.DataFrame(columns=events.columns),
            "train_end": None,
            "val_start": None,
            "val_end": None,
            "test_start": None,
            "n_train": 0,
            "n_val": 0,
            "n_test": 0,
        }

    n_train = max(1, int(n * train_frac))
    n_val = max(1, int(n * val_frac))
    n_test = max(1, n - n_train - n_val)

    while n_train + n_val + n_test > n:
        if n_test > 1:
            n_test -= 1
        elif n_val > 1:
            n_val -= 1
        else:
            n_train -= 1

    train_df = df.iloc[:n_train].copy()
    val_df = df.iloc[n_train : n_train + n_val].copy()
    test_df = df.iloc[n_train + n_val : n_train + n_val + n_test].copy()

    gap_bday = BDay(30)

    train_end = train_df["data_com"].max()
    val_start_raw = val_df["data_com"].min()
    val_end = val_df["data_com"].max()
    test_start_raw = test_df["data_com"].min()

    train_end_ts = pd.Timestamp(train_end)
    val_df = val_df[val_df["data_com"] >= (train_end_ts + gap_bday).date()].copy()
    if len(val_df) > 0:
        val_end_ts = pd.Timestamp(val_df["data_com"].max())
        test_df = test_df[test_df["data_com"] >= (val_end_ts + gap_bday).date()].copy()
    else:
        test_df = pd.DataFrame(columns=events.columns)

    val_start = val_df["data_com"].min() if len(val_df) > 0 else None
    test_start = test_df["data_com"].min() if len(test_df) > 0 else None

    return {
        "train": train_df,
        "val": val_df,
        "test": test_df,
        "train_end": train_end,
        "val_start": val_start,
        "val_end": val_end if len(val_df) > 0 else None,
        "test_start": test_start,
        "n_train": len(train_df),
        "n_val": len(val_df),
        "n_test": len(test_df),
    }


def validate_no_leakage(splits: dict, all_windows: pd.DataFrame) -> list[str]:
    errors = []
    if all_windows.empty:
        return errors

    train_events = set(splits["train"]["data_com"].tolist()) if not splits["train"].empty else set()
    val_events = set(splits["val"]["data_com"].tolist()) if not splits["val"].empty else set()
    test_events = set(splits["test"]["data_com"].tolist()) if not splits["test"].empty else set()

    def get_dates(event_set: set) -> set:
        return set(
            all_windows[all_windows["data_com"].isin(event_set)]["data"].tolist()
        )

    train_dates = get_dates(train_events)
    val_dates = get_dates(val_events)
    test_dates = get_dates(test_events)

    overlap_tv = train_dates & val_dates
    if overlap_tv:
        errors.append(f"Sobreposição treino/validação: {len(overlap_tv)} pregões compartilhados")

    overlap_tt = train_dates & test_dates
    if overlap_tt:
        errors.append(f"Sobreposição treino/teste: {len(overlap_tt)} pregões compartilhados")

    overlap_vt = val_dates & test_dates
    if overlap_vt:
        errors.append(f"Sobreposição validação/teste: {len(overlap_vt)} pregões compartilhados")

    return errors


def print_splits_summary(splits: dict) -> None:
    print("=" * 60)
    print("  WALK-FORWARD SPLIT SUMMARY")
    print("=" * 60)

    for name in ["train", "val", "test"]:
        df = splits[name]
        n = len(df)
        label = {"train": "TREINO", "val": "VALIDACAO", "test": "TESTE"}[name]

        if n > 0:
            min_d = df["data_com"].min()
            max_d = df["data_com"].max()
            print(f"\n  {label}:")
            print(f"    Periodo:    {min_d} a {max_d}")
            print(f"    Eventos:    {n}")
        else:
            print(f"\n  {label}:")
            print(f"    Eventos:    0 (vazio)")

        if n < 5:
            print(f"    ** AVISO: menos de 5 eventos em {label} **")

    train_end = splits["train_end"]
    val_start = splits["val_start"]
    val_end = splits.get("val_end")
    test_start = splits["test_start"]

    if train_end and val_start:
        gap_tv = (val_start - train_end).days
        print(f"\n  Gap treino->val:     {gap_tv} dias")
    else:
        print(f"\n  Gap treino->val:     N/A")

    if val_end and test_start:
        gap_vt = (test_start - val_end).days
        print(f"  Gap val->teste:      {gap_vt} dias")
    else:
        print(f"  Gap val->teste:      N/A")

    print(f"\n  Total eventos: {splits['n_train'] + splits['n_val'] + splits['n_test']}")
    print("=" * 60)
