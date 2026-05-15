# openfoam_ui_launcher.spec — PyInstaller spec for OpenFOAM GUI launcher
#
# Run from the deploy directory:
#   pyinstaller openfoam_ui_launcher.spec
#
# Or use build_exe.bat which handles icon generation and cleanup automatically.
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='OpenFOAM_UI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/openfoam_ui.ico',
    version='version_info.txt',
)
