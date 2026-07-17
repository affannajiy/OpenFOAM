@echo off
setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo   OpenFOAM Mesh Utilities -- Build Windows Launcher EXE
echo   Keysight Technologies
echo ============================================================
echo.
echo  This script builds OpenFOAM_UI.exe from openfoam_ui_launcher.py
echo  using PyInstaller. Run it once on a Windows dev machine.
echo.

:: ── Check python is on PATH ──────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python.exe was not found on PATH.
    echo.
    echo  Fix: Install Python 3.9+ for Windows from https://python.org
    echo  Tick "Add Python to PATH" during installation, then reopen this window.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Python found: %PY_VER%
echo.

:: ── Step 1: Install / upgrade PyInstaller ────────────────────────────────────
echo [1/4] Installing / upgrading PyInstaller...
pip install pyinstaller --quiet --upgrade
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install PyInstaller.
    echo  Try running manually:  pip install pyinstaller
    echo.
    pause
    exit /b 1
)
echo  PyInstaller ready.
echo.

:: ── Step 2: Clean previous build artefacts ───────────────────────────────────
echo [2/4] Cleaning previous build artefacts...
if exist build\ (
    rmdir /s /q build\
    echo  Removed: build\
)
if exist dist\ (
    rmdir /s /q dist\
    echo  Removed: dist\
)
echo  Clean done.
echo.

:: ── Step 3: Run PyInstaller ───────────────────────────────────────────────────
echo [3/4] Running PyInstaller (this takes 30-60 seconds)...
echo.
pyinstaller openfoam_ui_launcher.spec
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller failed. See the output above for details.
    echo.
    pause
    exit /b 1
)

:: ── Step 4: Done ──────────────────────────────────────────────────────────────
echo.
echo [4/4] Build complete!
echo.
echo ============================================================
echo  SUCCESS:  dist\OpenFOAM_UI.exe
echo.
echo  Next steps:
echo    1. Copy  dist\OpenFOAM_UI.exe  into this folder (01_utilities\)
echo       so it sits alongside openfoam_ui.py and the other .py files.
echo.
echo    2. Zip the entire 01_utilities\ folder.
echo.
echo    3. Distribute the ZIP to engineers.
echo       They extract it, double-click OpenFOAM_UI.exe, and are done.
echo ============================================================
echo.
pause
