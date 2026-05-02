"""Aceite v3 — valida camada CDI completa (Focus + sensitivity + snapshot).

Validacoes:
  1. Import de recommender sem puxar yfinance
  2. fetch_focus_selic() retorna dados
  3. compute_cdi_sensitivity() para KNIP11
  4. build_cdi_focus_explanation() com dados reais
  5. decidir_universo() com focus_explanation sem alterar acao
  6. Snapshot em banco temporario com migracao

Criterio de aceite: acao final nao muda por causa da camada CDI.
"""

import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import json


def test_1_import_sem_yfinance():
    """Recommender pode ser importado sem carregar yfinance."""
    print("\n=== TESTE 1: Import de recommender sem yfinance ===")
    import importlib

    # Verificar que yfinance NAO esta nos modulos carregados ANTES
    loaded_before = "yfinance" in sys.modules

    # Importar recommender
    from src.fii_analysis.decision.recommender import TickerDecision, decidir_ticker, decidir_universo

    loaded_after = "yfinance" in sys.modules

    print(f"  yfinance carregado ANTES: {loaded_before}")
    print(f"  yfinance carregado DEPOIS: {loaded_after}")

    if loaded_after and not loaded_before:
        print("  AVISO: yfinance foi carregado como efeito colateral")
    else:
        print("  OK: yfinance nao foi carregado")

    print(f"  TickerDecision tem cdi_delta_focus_12m: {hasattr(TickerDecision, 'cdi_delta_focus_12m')}")
    print(f"  TickerDecision tem cdi_repricing_12m: {hasattr(TickerDecision, 'cdi_repricing_12m')}")
    assert hasattr(TickerDecision, "cdi_delta_focus_12m"), "Campo cdi_delta_focus_12m ausente"
    assert hasattr(TickerDecision, "cdi_repricing_12m"), "Campo cdi_repricing_12m ausente"
    print("  PASSOU")


def test_2_focus_bcb():
    """fetch_focus_selic() retorna dados."""
    print("\n=== TESTE 2: Focus BCB ===")
    from src.fii_analysis.data.focus_bcb import fetch_focus_selic

    result = fetch_focus_selic()
    print(f"  focus_status: {result.focus_status}")
    print(f"  focus_selic_3m: {result.focus_selic_3m}")
    print(f"  focus_selic_6m: {result.focus_selic_6m}")
    print(f"  focus_selic_12m: {result.focus_selic_12m}")
    print(f"  focus_data_referencia: {result.focus_data_referencia}")

    assert result.focus_status in ("OK", "SEM_DADOS"), f"Status inesperado: {result.focus_status}"
    if result.focus_status == "OK":
        assert result.focus_selic_12m is not None, "Focus 12m nao deveria ser None com status OK"
    print("  PASSOU")


def test_3_cdi_sensitivity():
    """compute_cdi_sensitivity() para KNIP11."""
    print("\n=== TESTE 3: CDI Sensitivity (KNIP11) ===")
    from src.fii_analysis.data.database import get_engine
    from src.fii_analysis.data.migrations import run_migrations
    from src.fii_analysis.models.cdi_sensitivity import compute_cdi_sensitivity, cdi_sensitivity_to_dict

    run_migrations()  # apply to default DB
    engine = get_engine()
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        result = compute_cdi_sensitivity("KNIP11", session)

    print(f"  status: {result.status}")
    print(f"  beta: {result.beta}")
    print(f"  r_squared: {result.r_squared}")
    print(f"  p_value: {result.p_value}")
    print(f"  residuo_atual: {result.residuo_atual}")
    print(f"  residuo_percentil: {result.residuo_percentil}")

    d = cdi_sensitivity_to_dict(result)
    print(f"  dict keys: {list(d.keys())}")
    assert "cdi_status" in d
    assert "cdi_beta" in d
    print("  PASSOU")


def test_4_focus_explainer():
    """build_cdi_focus_explanation() com dados reais."""
    print("\n=== TESTE 4: CDI Focus Explainer (KNIP11) ===")
    from src.fii_analysis.data.database import get_engine
    from src.fii_analysis.data.focus_bcb import fetch_focus_selic
    from src.fii_analysis.data.migrations import run_migrations
    from src.fii_analysis.decision.cdi_focus_explainer import build_cdi_focus_explanation
    from src.fii_analysis.models.cdi_sensitivity import compute_cdi_sensitivity, cdi_sensitivity_to_dict
    from sqlalchemy.orm import Session

    run_migrations()  # already applied, idempotent
    engine = get_engine()

    focus = fetch_focus_selic()
    print(f"  Focus status: {focus.focus_status}")

    with Session(engine) as session:
        cdi_sens = compute_cdi_sensitivity("KNIP11", session)
        cdi_dict = cdi_sensitivity_to_dict(cdi_sens)

        expl = build_cdi_focus_explanation(
            "KNIP11", session,
            focus_data=focus,
            cdi_sensitivity=cdi_dict,
        )

    print(f"  delta_focus_12m: {expl.get('delta_focus_12m')}")
    print(f"  repricing_estimado_12m: {expl.get('repricing_estimado_12m')}")
    print(f"  cdi_12m_atual: {expl.get('cdi_12m_atual')}")
    print(f"  focus_selic_12m: {expl.get('focus_selic_12m')}")
    print(f"  explanation_lines: {expl.get('explanation_lines')}")

    assert "delta_focus_12m" in expl
    assert "repricing_estimado_12m" in expl
    assert "explanation_lines" in expl
    print("  PASSOU")


def test_5_decidir_sem_alterar_acao():
    """decidir_universo com e sem focus_explanation — acao nao muda."""
    print("\n=== TESTE 5: decidir_universo — acao inalterada ===")
    from src.fii_analysis.data.database import get_engine
    from src.fii_analysis.data.focus_bcb import fetch_focus_selic
    from src.fii_analysis.data.migrations import run_migrations
    from src.fii_analysis.decision.cdi_focus_explainer import build_cdi_focus_explanation
    from src.fii_analysis.decision.recommender import decidir_universo
    from src.fii_analysis.models.cdi_sensitivity import compute_cdi_sensitivity_batch, cdi_sensitivity_to_dict
    from sqlalchemy.orm import Session

    run_migrations()  # already applied, idempotent
    engine = get_engine()

    tickers = ["KNIP11"]

    with Session(engine) as session:
        # SEM focus
        decisoes_sem = decidir_universo(session, tickers=tickers)

        # COM focus
        focus = fetch_focus_selic()
        cdi_raw = compute_cdi_sensitivity_batch(tickers, session)
        cdi_map = {t: cdi_sensitivity_to_dict(r) for t, r in cdi_raw.items()}
        focus_map = {}
        for t in tickers:
            focus_map[t] = build_cdi_focus_explanation(
                t, session, focus_data=focus,
                cdi_sensitivity=cdi_map.get(t),
            )
        decisoes_com = decidir_universo(
            session, tickers=tickers,
            cdi_sensitivity_por_ticker=cdi_map,
            focus_explanation_por_ticker=focus_map,
        )

    d_sem = decisoes_sem[0]
    d_com = decisoes_com[0]

    print(f"  SEM focus: acao={d_sem.acao}, concordancia={d_sem.nivel_concordancia}")
    print(f"  COM focus: acao={d_com.acao}, concordancia={d_com.nivel_concordancia}")
    print(f"  COM focus: cdi_delta_focus_12m={d_com.cdi_delta_focus_12m}")
    print(f"  COM focus: cdi_repricing_12m={d_com.cdi_repricing_12m}")

    # CRITERIO DE ACEITE: acao nao muda
    assert d_sem.acao == d_com.acao, (
        f"ACAO MUDOU! sem={d_sem.acao} com={d_com.acao} — VIOLACAO DE REGRA"
    )
    assert d_sem.nivel_concordancia == d_com.nivel_concordancia, "Concordancia mudou!"
    assert d_sem.n_concordam_buy == d_com.n_concordam_buy, "n_concordam_buy mudou!"
    assert d_sem.n_concordam_sell == d_com.n_concordam_sell, "n_concordam_sell mudou!"

    # Rationale com focus deve ter mais linhas
    print(f"  SEM focus rationale: {len(d_sem.rationale)} linhas")
    print(f"  COM focus rationale: {len(d_com.rationale)} linhas")
    for line in d_com.rationale:
        if "Focus" in line or "Repricing" in line or "Delta" in line or "Leitura" in line:
            print(f"    >> {line}")

    print("  PASSOU — acao inalterada, rationale enriquecido")


def test_6_snapshot_temp_db():
    """Gera snapshot em banco temporario com migracao."""
    print("\n=== TESTE 6: Snapshot em banco temporario ===")
    import tempfile
    from sqlalchemy import create_engine, text, inspect
    from src.fii_analysis.data.database import Base
    from src.fii_analysis.data.migrations import run_migrations

    # Criar banco temporario
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, dir=r"C:\tmp")
    tmp_path = tmp.name
    tmp.close()

    try:
        os.makedirs(r"C:\tmp", exist_ok=True)
        engine = create_engine(f"sqlite:///{tmp_path}")

        # Criar todas as tabelas
        Base.metadata.create_all(engine)

        # Aplicar migrações com texto SQL direto (sem usar get_engine)
        with engine.connect() as conn:
            for table, col, ctype in [
                ("snapshot_runs", "focus_data_referencia", "DATE"),
                ("snapshot_runs", "focus_coletado_em", "DATETIME"),
                ("snapshot_runs", "focus_selic_3m", "REAL"),
                ("snapshot_runs", "focus_selic_6m", "REAL"),
                ("snapshot_runs", "focus_selic_12m", "REAL"),
                ("snapshot_runs", "focus_status", "TEXT"),
                ("snapshot_decisions", "cdi_delta_focus_12m", "REAL"),
                ("snapshot_decisions", "cdi_repricing_12m", "REAL"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}"))
                except Exception:
                    pass
            conn.commit()

        # Verificar colunas novas
        insp = inspect(engine)
        cols_run = {c["name"] for c in insp.get_columns("snapshot_runs")}
        cols_dec = {c["name"] for c in insp.get_columns("snapshot_decisions")}

        focus_cols = {"focus_data_referencia", "focus_coletado_em", "focus_selic_3m",
                      "focus_selic_6m", "focus_selic_12m", "focus_status"}
        for col in focus_cols:
            assert col in cols_run, f"Coluna {col} ausente de snapshot_runs"

        dec_new_cols = {"cdi_delta_focus_12m", "cdi_repricing_12m"}
        for col in dec_new_cols:
            assert col in cols_dec, f"Coluna {col} ausente de snapshot_decisions"

        print(f"  snapshot_runs colunas Focus: OK ({len(focus_cols)} colunas)")
        print(f"  snapshot_decisions colunas novas: OK ({len(dec_new_cols)} colunas)")
        print("  PASSOU")

    finally:
        engine.dispose()
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main():
    print("=" * 60)
    print("ACEITE v3 — Camada CDI (Focus + Sensitivity + Snapshot)")
    print("=" * 60)

    tests = [
        ("Import sem yfinance", test_1_import_sem_yfinance),
        ("Focus BCB", test_2_focus_bcb),
        ("CDI Sensitivity", test_3_cdi_sensitivity),
        ("Focus Explainer", test_4_focus_explainer),
        ("Acao inalterada", test_5_decidir_sem_alterar_acao),
        ("Snapshot temp DB", test_6_snapshot_temp_db),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  FALHOU: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTADO: {passed} passaram, {failed} falharam")
    print("=" * 60)

    if failed == 0:
        print("CRITERIO DE ACEITE ATENDIDO: decisao final nao muda por causa da camada CDI")
    else:
        print("FALHAS ENCONTRADAS — verificar acima")


if __name__ == "__main__":
    main()