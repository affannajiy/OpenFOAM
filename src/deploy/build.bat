@echo off
setlocal EnableDelayedExpansion
echo ============================================================
echo  OpenFOAM GUI -- Build EXE + One-File Installer
echo ============================================================
echo.
:: Single build entry point: version prompt -> patch version_info.txt +
:: launcher splash label -> PyInstaller EXE -> compile installer.iss.
:: Always the full chain -- the splash label is baked into the EXE, so a
:: partial build could ship an installer whose version disagrees with it.

cd /d "%~dp0"

:: Current version from version_info.txt as the prompt default (Enter reuses).
set "CURVER="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "if ((Get-Content 'version_info.txt' -Raw) -match 'FileVersion\D+([\d.]+)') { $Matches[1] }"`) do set "CURVER=%%V"

if "%CURVER%"=="" (
    set /p VERSION="Enter version number (e.g. 1.1.0): "
) else (
    set /p VERSION="Enter version number [%CURVER%]: "
)
if "%VERSION%"=="" set "VERSION=%CURVER%"
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

:: Read/write via [IO.File] -- Get-Content -Raw keeps the file's trailing
:: newline and Set-Content then appended ANOTHER, so every build grew the file
:: by one blank line. TrimEnd() (no added newline) matches the committed file
:: exactly, so a build with an unchanged version leaves no git diff here.
> "%TEMP%\patch_version.ps1" echo $enc = New-Object System.Text.UTF8Encoding($false)
>> "%TEMP%\patch_version.ps1" echo $f = [IO.File]::ReadAllText('version_info.txt', $enc)
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace 'filevers=\([^)]+\)', 'filevers=(%VERTUPLE%)'
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace 'prodvers=\([^)]+\)', 'prodvers=(%VERTUPLE%)'
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace "'FileVersion',\s*'[^']+'" , "'FileVersion', '%VERSION%'"
>> "%TEMP%\patch_version.ps1" echo $f = $f -replace "'ProductVersion',\s*'[^']+'" , "'ProductVersion', '%VERSION%'"
>> "%TEMP%\patch_version.ps1" echo $f = $f.TrimEnd()
>> "%TEMP%\patch_version.ps1" echo [IO.File]::WriteAllText('version_info.txt', $f, $enc)
powershell -ExecutionPolicy Bypass -File "%TEMP%\patch_version.ps1"
if errorlevel 1 (
    echo ERROR: Failed to update version_info.txt.
    pause
    exit /b 1
)
echo version_info.txt updated.
echo.

echo Updating version label in launcher...
:: UTF-8 read/write via [IO.File] -- Get-Content/Set-Content misread the
:: BOM-less UTF-8 source as ANSI and corrupt every non-ASCII character.
> "%TEMP%\patch_splash.ps1" echo $enc = New-Object System.Text.UTF8Encoding($false)
>> "%TEMP%\patch_splash.ps1" echo $f = [IO.File]::ReadAllText('..\app\openfoam_ui_launcher.py', $enc)
>> "%TEMP%\patch_splash.ps1" echo $f = $f -replace "text='v[0-9]+\.[0-9]+\.[0-9]+'", "text='v%VERSION%'"
>> "%TEMP%\patch_splash.ps1" echo [IO.File]::WriteAllText('..\app\openfoam_ui_launcher.py', $f, $enc)
powershell -ExecutionPolicy Bypass -File "%TEMP%\patch_splash.ps1"
if errorlevel 1 (
    echo ERROR: Failed to update version label in launcher.
    pause
    exit /b 1
)
echo Launcher version label updated.
echo.

echo [1/5] Checking PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found -- installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller. Check your Python installation.
        pause
        exit /b 1
    )
) else (
    echo PyInstaller present.
)
echo.

echo [2/5] Cleaning old build artefacts...
if exist build              rmdir /s /q build
if exist dist               rmdir /s /q dist
if exist ..\app\OpenFOAM_UI.exe  del /f /q ..\app\OpenFOAM_UI.exe
if exist ..\app\_internal        rmdir /s /q ..\app\_internal
echo.

echo [3/5] Building EXE...
pyinstaller openfoam_ui_launcher.spec
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. See output above for details.
    pause
    exit /b 1
)
echo.

echo [4/5] Copying EXE + support files to app\...
:: One-dir build: dist\OpenFOAM_UI\ holds OpenFOAM_UI.exe + _internal\.
:: Both must land in app\ together -- the exe cannot run without _internal.
xcopy /e /i /y /q dist\OpenFOAM_UI ..\app
if errorlevel 1 (
    echo ERROR: Could not copy dist\OpenFOAM_UI to app\ -- copy it manually.
    pause
    exit /b 1
)
echo.

echo [5/5] Building one-file installer...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
    echo WARNING: Inno Setup 6 not found -- skipping installer build.
    echo Install it with:  winget install JRSoftware.InnoSetup
    echo Then re-run build.bat to create the Setup EXE.
) else (
    "%ISCC%" /DMyAppVersion=%VERSION% installer.iss
    if errorlevel 1 (
        echo ERROR: Installer compile failed. See output above.
        pause
        exit /b 1
    )
)
echo.

echo ============================================================
echo  Build complete: app\OpenFOAM_UI.exe  [v%VERSION%]
if exist "dist\OpenFOAM_UI_Setup_%VERSION%.exe" echo  Installer: dist\OpenFOAM_UI_Setup_%VERSION%.exe  ^<-- distribute this one file
echo ============================================================
pause
