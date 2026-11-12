# Wrapper do CLI FII Analysis — uso: .\fii diario | .\fii oportunidades | .\fii update-prices ...
$env:PYTHONPATH = "$PSScriptRoot;$PSScriptRoot\src"
$env:PYTHONIOENCODING = "utf-8"
& "C:\ProgramData\anaconda3\python.exe" -m fii_analysis @args
exit $LASTEXITCODE
