# openfoam_ui_launcher.spec — PyInstaller spec for OpenFOAM GUI launcher
#
# Run from the deploy directory:
#   pyinstaller openfoam_ui_launcher.spec
#
# Or use build.bat which handles versioning, cleanup, and the installer.
#
# The launcher uses only: tkinter, subprocess, sys, os, time.
#
# NOTE: Do NOT exclude stdlib modules here. PyInstaller's own bootloader and
# runtime hooks (pyi_rth_inspect, etc.) depend on stdlib internals in ways
# that are not visible from the launcher source. PyInstaller's static analysis
# already prunes unused stdlib modules automatically. Only exclude third-party
# packages that the analysis phase might accidentally pull in from the env.

block_cipher = None

_EXCLUDES = [
    'numpy', 'PyQt5', 'PIL', 'setuptools', 'pkg_resources',
]

a = Analysis(
    ['../app/openfoam_ui_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One-dir build (EXE + COLLECT), upx off:
#  - one-file self-extracted ~10 MB to %TEMP%\_MEIxxxx on EVERY launch and
#    made Defender re-scan the payload — the "slow first run" users noticed;
#  - UPX-compressed exes decompress at each start and get extra AV scrutiny.
# The app already ships as a folder (installer copies app\* wholesale), so
# one-dir costs nothing: the exe's support files live in app\_internal\.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OpenFOAM_UI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/openfoam_ui.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OpenFOAM_UI',
)