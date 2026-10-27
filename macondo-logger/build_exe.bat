@echo off
REM Compila Macondo Logger como un .exe. Doble clic sobre este archivo.
REM Resultado: dist\MacondoLogger.exe
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>nul
if errorlevel 1 (
    echo No encontre Python. Instala Python 3.11+ desde python.org marcando "Add python.exe to PATH".
    pause
    exit /b 1
)

echo [1/3] Instalando dependencias...
%PY% -m pip install --upgrade -r requirements.txt pyinstaller || goto :error

echo [2/3] Limpiando compilacion anterior...
if exist build rmdir /s /q build

echo [3/3] Compilando MacondoLogger.exe (tarda unos minutos)...
%PY% -m PyInstaller MacondoLogger.spec --noconfirm || goto :error

echo.
echo Listo: dist\MacondoLogger.exe
pause
exit /b 0

:error
echo.
echo La compilacion fallo. Revisa el mensaje de arriba.
pause
exit /b 1
