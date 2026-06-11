# scripts/run_tests.ps1
# PowerShell script to run pytest with coverage on Windows

$PYTHON_EXE = "C:/ProgramData/anaconda3/python.exe"

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Warning "Anaconda Python interpreter not found at $PYTHON_EXE. Falling back to default 'python'."
    $PYTHON_EXE = "python"
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " Running FII Analysis test suite with coverage..." -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

& $PYTHON_EXE -m pytest --cov=src/fii_analysis tests/
