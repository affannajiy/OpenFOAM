@echo off
setlocal EnableDelayedExpansion
echo ============================================================
echo  OpenFOAM GUI -- Build Launcher EXE
echo ============================================================
echo.

cd /d "%~dp0"

set /p VERSION="Enter version number (e.g. 1.0.1): "
if "%VERSION%"=="" (
    echo ERROR: Version number cannot be empty.
    pause
    exit /b 1
)
echo Using version: %VERSION%
echo.

echo Checking for icon file...
if not exist "icons\openfoam_ui.ico" (
    echo ERROR: icons\openfoam_ui.ico not found.
    echo Make sure the icons\ folder is present in the deploy directory.
    pause
    exit /b 1
)
echo Icon found.
echo.

echo Updating version_info.txt to version %VERSION%...
:: Convert "1.2.3" to "1, 2, 3, 0" for the filevers / prodvers tuples
for /f "tokens=1,2,3 delims=." %%A in ("%VERSION%") do (
    set V1=%%A
    set V2=%%B
    set V3=%%C
)
set VERTUPLE=%V1%, %V2%, %V3%, 0

> "%TEMP%\patch_version.ps1" echo $f = Get-Content 'version_info.txt' -Raw
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace 'filevers=\([^)]+\)', 'filevers=(%VERTUPLE%)'
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace 'prodvers=\([^)]+\)', 'prodvers=(%VERTUPLE%)'
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace "'FileVersion',\s*'[^']+'" , "'FileVersion', '%VERSION%'"
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace "'ProductVersion',\s*'[^']+'" , "'ProductVersion', '%VERSION%'"
>> "%TEMP%\patch_version.ps1" echo Set-Content 'version_info.txt' $f
powershell -ExecutionPolicy Bypass -File "%TEMP%\patch_version.ps1"
if errorlevel 1 (
    echo ERROR: Failed to update version_info.txt.
    pause
    exit /b 1
)
echo version_info.txt updated.
echo.

echo Updating version label in launcher...
> "%TEMP%\patch_splash.ps1" echo $f = Get-Content '..\app\openfoam_ui_launcher.py' -Raw
>> "%TEMP%\patch_splash.ps1" echo $f = $f -replace "text='v[0-9]+\.[0-9]+\.[0-9]+'", "text='v%VERSION%'"
>> "%TEMP%\patch_splash.ps1" echo Set-Content '..\app\openfoam_ui_launcher.py' $f
powershell -ExecutionPolicy Bypass -File "%TEMP%\patch_splash.ps1"
if errorlevel 1 (
    echo ERROR: Failed to update version label in launcher.
    pause
    exit /b 1
)
echo Launcher version label updated.
echo.

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
echo  Build complete: app\OpenFOAM_UI.exe  [v%VERSION%]
echo  Remember to ZIP the whole app\ folder: icons\, templates\, defaults.json.
echo ============================================================
pause
