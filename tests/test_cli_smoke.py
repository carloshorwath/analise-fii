import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from src.fii_analysis.cli import app
from src.fii_analysis.evaluation.daily_snapshots import generate_daily_snapshot

runner = CliRunner()

@pytest.fixture
def clean_snapshot(db_session):
    # Mock dependencies to generate a fast snapshot for smoke testing
    with patch('src.fii_analysis.evaluation.daily_snapshots.fetch_focus_selic') as mock_focus:
        mock_focus.return_value = MagicMock(
            focus_data_referencia=date.today(),
            focus_coletado_em=None,
            focus_selic_3m=10.0,
            focus_selic_6m=10.0,
            focus_selic_12m=10.0,
            focus_status="ready"
        )
        
        with patch('src.fii_analysis.evaluation.daily_snapshots._build_optimizer_params_map') as mock_opt_map, \
             patch('src.fii_analysis.decision.recommender.walk_forward_roll') as mock_wf:
            
            mock_opt_map.return_value = {"MOCK11": {"some": "param"}, "MOCK12": {"some": "param"}}
            mock_wf.return_value = {
                "sinal_hoje": {"sinal": "BUY", "data_ultimo_sinal_oos": date(2025, 4, 1)},
                "n_steps": 10,
                "summary": {"BUY": {"p_value": 0.01}}
            }
            
            # Generate the snapshot
            generate_daily_snapshot(db_session, scope="curado", tickers=["MOCK11", "MOCK12"], force=True)
            yield

def test_cli_diario_smoke(clean_snapshot):
    result = runner.invoke(app, ["diario"])
    assert result.exit_code == 0
    assert "MOCK" in result.stdout
    assert "Cockpit do Dia" in result.stdout

def test_cli_panorama_smoke(clean_snapshot):
    # Test panorama command
    result = runner.invoke(app, ["panorama"])
    assert result.exit_code == 0
    assert "MOCK" in result.stdout

def test_cli_carteira_smoke(clean_snapshot):
    # Test carteira command
    result = runner.invoke(app, ["carteira"])
    assert result.exit_code == 0

def test_cli_radar_smoke(clean_snapshot):
    # Test radar command
    result = runner.invoke(app, ["radar"])
    assert result.exit_code == 0
    assert "MOCK" in result.stdout

def test_cli_alertas_smoke(clean_snapshot):
    # Test alertas command
    result = runner.invoke(app, ["alertas"])
    assert result.exit_code == 0
