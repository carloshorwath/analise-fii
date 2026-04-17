import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import func, select

from src.fii_analysis.data.database import Dividendo, PrecoDiario, RelatorioMensal, Ticker, get_session
from src.fii_analysis.features.indicators import get_dy_trailing, get_pvp

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fii-stats")


def _get_cnpj(ticker: str, session) -> str | None:
    return session.execute(
        select(Ticker.cnpj).where(Ticker.ticker == ticker)
    ).scalar_one_or_none()


def _get_pregoes(ticker: str, session) -> list[date]:
    rows = session.execute(
        select(PrecoDiario.data).where(PrecoDiario.ticker == ticker).order_by(PrecoDiario.data.asc())
    ).scalars().all()
    return list(rows)


@mcp.tool()
def validate_split(ticker: str, train_end: str, val_end: str, test_end: str, gap_days: int = 10) -> dict:
    session = get_session()
    try:
        d_train = date.fromisoformat(train_end)
        d_val = date.fromisoformat(val_end)
        d_test = date.fromisoformat(test_end)

        errors = []
        if not (d_train < d_val < d_test):
            errors.append(f"Datas invalidas: train_end ({train_end}) < val_end ({val_end}) < test_end ({test_end})")

        pregoes = _get_pregoes(ticker, session)
        if not pregoes:
            return {"valid": False, "errors": ["Nenhum preco encontrado para o ticker"], "train_events": 0, "val_events": 0, "test_events": 0, "gap_ok": False}

        pregoes_set = set(pregoes)

        def count_uteis(start: date, end: date) -> int:
            return sum(1 for d in pregoes if start < d <= end)

        gap1_uteis = count_uteis(d_train, d_val)
        gap2_uteis = count_uteis(d_val, d_test)
        gap_ok = gap1_uteis >= gap_days and gap2_uteis >= gap_days

        if not gap_ok:
            if gap1_uteis < gap_days:
                errors.append(f"Gap treino->val: {gap1_uteis} dias uteis (minimo: {gap_days})")
            if gap2_uteis < gap_days:
                errors.append(f"Gap val->teste: {gap2_uteis} dias uteis (minimo: {gap_days})")

        dividendos = session.execute(
            select(Dividendo.data_com).where(Dividendo.ticker == ticker).order_by(Dividendo.data_com.asc())
        ).scalars().all()

        train_ev = sum(1 for d in dividendos if d <= d_train)
        val_ev = sum(1 for d in dividendos if d_train < d <= d_val)
        test_ev = sum(1 for d in dividendos if d_val < d <= d_test)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "train_events": train_ev,
            "val_events": val_ev,
            "test_events": test_ev,
            "gap_ok": gap_ok,
        }
    finally:
        session.close()


@mcp.tool()
def detect_leakage(ticker: str, feature_date: str, target_date: str) -> dict:
    session = get_session()
    try:
        d_feature = date.fromisoformat(feature_date)
        d_target = date.fromisoformat(target_date)

        cnpj = _get_cnpj(ticker, session)
        if cnpj is None:
            return {"leakage": False, "vp_data_entrega": None, "vp_data_referencia": None, "message": f"Ticker {ticker} nao encontrado"}

        relatorio = session.execute(
            select(RelatorioMensal.data_entrega, RelatorioMensal.data_referencia)
            .where(
                RelatorioMensal.cnpj == cnpj,
                RelatorioMensal.data_entrega <= d_feature,
            )
            .order_by(RelatorioMensal.data_referencia.desc())
            .limit(1)
        ).first()

        if relatorio is None:
            return {"leakage": False, "vp_data_entrega": None, "vp_data_referencia": None, "message": "Nenhum relatorio CVM encontrado para essa data"}

        vp_entrega = relatorio[0]
        vp_ref = relatorio[1]

        leakage = vp_entrega > d_target

        if leakage:
            msg = f"LEAKAGE: VP entregue em {vp_entrega} (ref: {vp_ref}) usado em feature_date {feature_date} mas target_date e {target_date}"
        else:
            msg = f"OK: VP entregue em {vp_entrega} (ref: {vp_ref}) e anterior ao target {target_date}"

        return {
            "leakage": leakage,
            "vp_data_entrega": str(vp_entrega),
            "vp_data_referencia": str(vp_ref),
            "message": msg,
        }
    finally:
        session.close()


@mcp.tool()
def check_window_overlap(ticker: str) -> dict:
    session = get_session()
    try:
        pregoes = _get_pregoes(ticker, session)
        if not pregoes:
            return {"overlaps": 0, "total_events": 0, "overlap_pairs": []}

        dividendos = session.execute(
            select(Dividendo.data_com).where(Dividendo.ticker == ticker).order_by(Dividendo.data_com.asc())
        ).scalars().all()

        if len(dividendos) < 2:
            return {"overlaps": 0, "total_events": len(dividendos), "overlap_pairs": []}

        pregoes_idx = {d: i for i, d in enumerate(pregoes)}

        def find_dia0(dc: date) -> int | None:
            if dc in pregoes_idx:
                return pregoes_idx[dc]
            idx = None
            for i, d in enumerate(pregoes):
                if d > dc:
                    break
                idx = i
            return idx

        def get_janela_range(dc: date) -> tuple[int, int] | None:
            idx0 = find_dia0(dc)
            if idx0 is None:
                return None
            start = max(0, idx0 - 10)
            end = min(len(pregoes) - 1, idx0 + 10)
            return (start, end)

        janelas = []
        for dc in dividendos:
            r = get_janela_range(dc)
            if r is not None:
                janelas.append((dc, r[0], r[1]))

        overlaps = 0
        overlap_pairs = []
        for i in range(len(janelas)):
            for j in range(i + 1, len(janelas)):
                dc1, s1, e1 = janelas[i]
                dc2, s2, e2 = janelas[j]
                if s1 <= e2 and s2 <= e1:
                    overlaps += 1
                    overlap_pairs.append({"data_com_1": str(dc1), "data_com_2": str(dc2)})

        return {"overlaps": overlaps, "total_events": len(dividendos), "overlap_pairs": overlap_pairs}
    finally:
        session.close()


@mcp.tool()
def summary_report(ticker: str) -> dict:
    session = get_session()
    try:
        preco_range = session.execute(
            select(func.min(PrecoDiario.data), func.max(PrecoDiario.data), func.count())
            .where(PrecoDiario.ticker == ticker)
        ).first()

        n_div = session.execute(
            select(func.count()).select_from(Dividendo).where(Dividendo.ticker == ticker)
        ).scalar_one()

        cnpj = _get_cnpj(ticker, session)
        n_rel = 0
        if cnpj:
            n_rel = session.execute(
                select(func.count()).select_from(RelatorioMensal).where(RelatorioMensal.cnpj == cnpj)
            ).scalar_one()

        data_max = preco_range[1] if preco_range else None
        pvp = get_pvp(ticker, data_max, session) if data_max else None
        dy = get_dy_trailing(ticker, data_max, session) if data_max else None

        return {
            "ticker": ticker,
            "preco_min_data": str(preco_range[0]) if preco_range and preco_range[0] else None,
            "preco_max_data": str(preco_range[1]) if preco_range and preco_range[1] else None,
            "total_precos": preco_range[2] if preco_range else 0,
            "total_dividendos": n_div,
            "total_relatorios_cvm": n_rel,
            "pvp_atual": pvp,
            "dy_atual": dy,
        }
    finally:
        session.close()


if __name__ == "__main__":
    mcp.run()
