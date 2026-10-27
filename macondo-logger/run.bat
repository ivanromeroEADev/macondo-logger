@echo off
REM Abre Macondo Logger en el navegador. Doble clic sobre este archivo.
REM Para cerrarlo, cierra esta ventana negra.
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo No encontre Python. Instalalo desde python.org y marca "Add python.exe to PATH".
    pause
    exit /b 1
)

echo Revisando dependencias (la primera vez tarda unos minutos)...
%PY% -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo No se pudieron instalar las dependencias. Revisa el mensaje de arriba.
    pause
    exit /b 1
)

echo Abriendo Macondo Logger...
%PY% -m streamlit run macondo_app.py
pause
