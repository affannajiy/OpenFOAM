@echo off
setlocal EnableDelayedExpansion
echo ============================================================
echo  OpenFOAM GUI -- Build Launcher EXE
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/4] Installing / upgrading PyInstaller...
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller. Check your Python installation.
    pause
    exit /b 1
)
echo.

echo [2/4] Cleaning old build artefacts...
if exist build              rmdir /s /q build
if exist dist               rmdir /s /q dist
if exist ..\app\OpenFOAM_UI.exe  del /f /q ..\app\OpenFOAM_UI.exe
echo.

echo [3/4] Building EXE...
pyinstaller openfoam_ui_launcher.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. See output above for details.
    pause
    exit /b 1
)
echo.

echo [4/4] Copying EXE to app\...
copy /y dist\OpenFOAM_UI.exe ..\app\OpenFOAM_UI.exe
if errorlevel 1 (
    echo ERROR: Could not copy EXE to app\ -- copy it manually from dist\.
    pause
    exit /b 1
)
echo.

echo ============================================================
echo  Build complete: app\OpenFOAM_UI.exe
echo  Remember to include the app\icons\ folder in the distribution ZIP.
echo ============================================================
pause
