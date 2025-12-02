@echo off
REM RB Terminal - Windows Build Script
REM Execute este script no Windows para gerar o .exe

echo === RB Terminal Build ===
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale Python 3.11+
    pause
    exit /b 1
)

REM Instalar dependencias
echo Instalando dependencias...
pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias
    pause
    exit /b 1
)

echo.
echo Compilando executavel...
pyinstaller build.spec --clean
if errorlevel 1 (
    echo ERRO: Falha na compilacao
    pause
    exit /b 1
)

echo.
echo === BUILD CONCLUIDO ===
echo Executavel gerado em: dist\RB-Terminal.exe
echo.
pause
