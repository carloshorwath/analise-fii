import pytest
from datetime import date
from unittest.mock import patch
from sqlalchemy import select
from src.fii_analysis.data.database import SnapshotRun
from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot

def test_generate_daily_snapshot_idempotency(db_session):
    # Setup: mock fetch_focus_selic to avoid external API calls during testing
    with patch('src.fii_analysis.evaluation.daily_snapshots.fetch_focus_selic') as mock_focus:
        mock_focus.return_value = MagicMock(
            focus_data_referencia=date.today(),
            focus_coletado_em=None,
            focus_selic_3m=10.0,
            focus_selic_6m=10.0,
            focus_selic_12m=10.0,
            focus_status="ready"
        )
        
        # We need to mock build_optimizer_params_map or walk_forward_roll inside build_snapshot_decisions
        # to avoid long execution of optimizer and backtests.
        with patch('src.fii_analysis.evaluation.daily_snapshots._build_optimizer_params_map') as mock_opt_map, \
             patch('src.fii_analysis.decision.recommender.walk_forward_roll') as mock_wf:
            
            mock_opt_map.return_value = {"MOCK11": {"some": "param"}}
            mock_wf.return_value = {
                "sinal_hoje": {"sinal": "BUY", "data_ultimo_sinal_oos": date(2025, 4, 1)},
                "n_steps": 10,
                "summary": {"BUY": {"p_value": 0.01}}
            }

            # 1. First run: should create a new snapshot ready
            res = generate_daily_snapshot(db_session, scope="curado", tickers=["MOCK11"], force=True)
            assert res["status"] == "ready"
            run_id = res["run_id"]
            
            # Check db record status
            run_rec = db_session.get(SnapshotRun, run_id)
            assert run_rec is not None
            assert run_rec.status == "ready"

            # 2. Second run with force=False (default): should return already_ready and reuse run_id
            res2 = generate_daily_snapshot(db_session, scope="curado", tickers=["MOCK11"], force=False)
            assert res2["status"] == "already_ready"
            assert res2["run_id"] == run_id

def test_generate_daily_snapshot_failure(db_session):
    # Force failure by raising exception inside generate_base_snapshots
    with patch('src.fii_analysis.evaluation.daily_snapshots.generate_base_snapshots') as mock_base:
        mock_base.side_effect = RuntimeError("Forced simulation error")
        
        res = generate_daily_snapshot(db_session, scope="curado", tickers=["MOCK11"], force=True)
        assert res["status"] == "failed"
        run_id = res["run_id"]
        
        # Check database record is marked as failed and has message
        run_rec = db_session.get(SnapshotRun, run_id)
        assert run_rec is not None
        assert run_rec.status == "failed"
        assert "Forced simulation error" in run_rec.mensagem_erro

# Helper to mock focus result in patch
from unittest.mock import MagicMock
