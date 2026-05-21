@echo off
setlocal

set "GR_ROOT=C:\GNURadio-3.10"
set "GTKFIX_ENV=C:\Users\mstef\anaconda3\envs\gtkfix"
set "PYTHON_EXE=%GTKFIX_ENV%\python.exe"
set "GRC_SCRIPT=%GR_ROOT%\bin\gnuradio-companion.py"

if not exist "%PYTHON_EXE%" (
  echo No se encontro el entorno gtkfix en "%GTKFIX_ENV%".
  echo Ejecuta de nuevo la reparacion o revisa la ruta.
  exit /b 1
)

if not exist "%GRC_SCRIPT%" (
  echo No se encontro GNU Radio en "%GR_ROOT%".
  echo Revisa la ruta de instalacion.
  exit /b 1
)

set "PYTHONHOME="
set "PYTHONEXECUTABLE="
set "PYTHONUSERBASE="
set "PYTHONPATH=%GR_ROOT%\lib\site-packages;%GR_ROOT%\lib\site-packages\gnuradio;%GR_ROOT%\lib\site-packages\gnuradio\analog;%GR_ROOT%\lib\site-packages\pmt"
set "PATH=%GTKFIX_ENV%;%GTKFIX_ENV%\Library\bin;%GTKFIX_ENV%\Scripts;%GR_ROOT%\bin;%PATH%"
set "GI_TYPELIB_PATH=%GTKFIX_ENV%\Library\lib\girepository-1.0"
set "GRC_BLOCKS_PATH=%GR_ROOT%\share\gnuradio\grc\blocks"

echo Abriendo GNU Radio Companion con runtime GTK reparado...
call "%PYTHON_EXE%" "%GRC_SCRIPT%"
