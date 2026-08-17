@echo off
title Compilador do Instalador - Paradox2Firebird Studio v2.0
echo ======================================================================
echo    PARADOX 2 FIREBIRD CONVERSION STUDIO - BUILD DO INSTALADOR
echo ======================================================================
echo.

echo [1/2] Compilando executavel standalone com PyInstaller...
python -m PyInstaller Paradox2Firebird.spec --noconfirm --clean
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao compilar com PyInstaller!
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] Gerando instalador com Inno Setup 6 (ISCC.exe)...
set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

"%ISCC_PATH%" installer.iss
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao compilar o instalador Inno Setup!
    pause
    exit /b %errorlevel%
)

echo.
echo ======================================================================
echo [SUCESSO] Instalador gerado com sucesso em:
echo   .\installer_output\Paradox2Firebird_Setup_v2.0.exe
echo ======================================================================
echo.
pause
