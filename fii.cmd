@echo off
rem Wrapper do CLI FII Analysis - uso: fii diario | fii oportunidades | fii update-prices ...
set "PYTHONPATH=%~dp0;%~dp0src"
set "PYTHONIOENCODING=utf-8"
C:\ProgramData\anaconda3\python.exe -m fii_analysis %*
