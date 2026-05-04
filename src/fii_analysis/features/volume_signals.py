from __future__ import annotations

from datetime import date
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.fii_analysis.data.database import PrecoDiario


def get_volume_drop_flag(
    ticker: str,
    target_date: date,
    session: Session,
    queda_min_pct: float = 0.02,
    volume_multiplier: float = 1.5,
    window_days: int = 21,
) -> bool:
    try:
        stmt = (
            select(PrecoDiario.fechamento_aj, PrecoDiario.volume)
            .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= target_date)
            .order_by(PrecoDiario.data.desc())
            .limit(window_days + 1)
        )
        rows = session.execute(stmt).all()

        if len(rows) < window_days + 1:
            return False

        fechamento_aj_0 = rows[0][0]
        fechamento_aj_1 = rows[1][0]
        volume_0 = rows[0][1]

        if fechamento_aj_0 is None or fechamento_aj_1 is None or volume_0 is None:
            return False

        volumes_ref = [row[1] for row in rows[1:]]
        valid_volumes_ref = [v for v in volumes_ref if v is not None]

        if not valid_volumes_ref:
            return False

        retorno_dia = (float(fechamento_aj_0) / float(fechamento_aj_1)) - 1
        media_vol = np.mean(valid_volumes_ref)

        if media_vol == 0:
            return False

        return (
            retorno_dia <= -queda_min_pct
            and float(volume_0) >= volume_multiplier * media_vol
        )

    except Exception:
        return False


def get_vol_ratio_21_63(
    ticker: str,
    target_date: date,
    session: Session,
) -> float | None:
    try:
        stmt = (
            select(PrecoDiario.volume)
            .where(PrecoDiario.ticker == ticker, PrecoDiario.data < target_date)
            .order_by(PrecoDiario.data.desc())
            .limit(63)
        )
        rows = session.execute(stmt).scalars().all()

        if len(rows) < 63:
            return None

        volumes = [v for v in rows if v is not None]
        if not volumes or len(volumes) < 63:
            return None

        vol_21 = np.mean(volumes[:21])
        vol_63 = np.mean(volumes)

        if vol_63 == 0:
            return None

        return float(vol_21 / vol_63)

    except Exception:
        return None


def get_volume_profile(
    ticker: str,
    target_date: date,
    session: Session,
) -> dict:
    profile = {
        "is_high_volume_drop": False,
        "vol_ratio_21_63": None,
        "adtv_21d_brl": None,
        "adtv_63d_brl": None,
    }
    try:
        profile["is_high_volume_drop"] = get_volume_drop_flag(
            ticker, target_date, session
        )
        profile["vol_ratio_21_63"] = get_vol_ratio_21_63(ticker, target_date, session)

        stmt = (
            select(PrecoDiario.fechamento, PrecoDiario.volume)
            .where(PrecoDiario.ticker == ticker, PrecoDiario.data <= target_date)
            .order_by(PrecoDiario.data.desc())
            .limit(63)
        )
        rows = session.execute(stmt).all()

        if rows:
            adtv_list = []
            for row in rows:
                if row.fechamento is not None and row.volume is not None:
                    adtv_list.append(float(row.fechamento) * float(row.volume))
                else:
                    adtv_list.append(None)

            valid_adtv_21 = [v for v in adtv_list[:21] if v is not None]
            if valid_adtv_21:
                profile["adtv_21d_brl"] = float(np.mean(valid_adtv_21))

            valid_adtv_63 = [v for v in adtv_list if v is not None]
            if valid_adtv_63:
                profile["adtv_63d_brl"] = float(np.mean(valid_adtv_63))

    except Exception:
        pass

    return profile
