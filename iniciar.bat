@echo off
REM Levanta AoE2 Coach y abre el navegador. Doble click y listo.
REM Sin acentos a proposito: la consola de Windows los rompe.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No esta instalado todavia. Corriendo instalar.bat...
  call instalar.bat
)

if not exist "data\aoe2coach.duckdb" (
  echo Falta la base de datos. Descargando las fuentes, esto tarda unos minutos...
  set PYTHONPATH=src
  .venv\Scripts\python.exe -m aoe2coach.cli ingest
)

echo.
echo   AoE2 Coach -^> http://127.0.0.1:8000
echo   (cerra esta ventana para apagarlo)
echo.
start "" http://127.0.0.1:8000
set PYTHONPATH=src
.venv\Scripts\python.exe -m aoe2coach.cli web
pause
