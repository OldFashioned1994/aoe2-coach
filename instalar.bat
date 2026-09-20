@echo off
REM Instalacion desde cero: entorno virtual, dependencias y descarga de datos.
cd /d "%~dp0"

echo [1/3] Creando el entorno virtual...
python -m venv .venv || goto :error

echo [2/3] Instalando dependencias...
.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt || goto :error

echo [3/3] Descargando los datos (unos 15 MB, tarda un par de minutos)...
set PYTHONPATH=src
.venv\Scripts\python.exe -m aoe2coach.cli ingest || goto :error

echo.
echo Listo. Corre iniciar.bat para usarlo.
pause
exit /b 0

:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1
