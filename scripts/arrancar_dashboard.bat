@echo off
REM =============================================================
REM Dashboard STRAND-1 (Windows)
REM Arranca el backend FastAPI + el frontend Vite.
REM
REM Uso:  arrancar_dashboard.bat
REM =============================================================
setlocal
cd /d "%~dp0\.."

set BACKEND_PORT=8150
set FRONTEND_PORT=4175

REM Usar el venv del proyecto si existe (..\strand\Scripts\python.exe)
if exist "..\strand\Scripts\python.exe" (
    set PYTHON_BIN=..\strand\Scripts\python.exe
) else (
    set PYTHON_BIN=python
)

echo ==^> Arrancando backend FastAPI en http://127.0.0.1:%BACKEND_PORT%
start "STRAND-1 Backend" /min cmd /c ""%PYTHON_BIN%" -m uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

REM Esperar a que el backend arranque
timeout /t 3 /nobreak >nul

REM Nota: el proxy de Vite (/api y /ws) apunta a 127.0.0.1:8150 en dashboard\vite.config.js.
if not exist "dashboard\node_modules" (
    echo dashboard\node_modules no existe; ejecutando npm install...
    pushd dashboard
    call npm install
    popd
)

echo ==^> Arrancando frontend Vite en http://localhost:%FRONTEND_PORT%
pushd dashboard
call npm run preview -- --port %FRONTEND_PORT% --strictPort
popd

endlocal