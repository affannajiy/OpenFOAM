# OpenFOAM Mesh Utilities — Windows Launcher

**OpenFOAM_UI.exe** is a one-click Windows launcher for the OpenFOAM Mesh
Utilities GUI. It checks your environment, then starts the PyQt5 application
inside WSL2 automatically.

---

## Quick Start

1. **Extract** the ZIP so that `OpenFOAM_UI.exe` is in the same folder as all
   the `.py` files (the `01_utilities` folder).
2. **Double-click** `OpenFOAM_UI.exe`.
3. A startup window appears, runs checks, and opens the GUI. **Done.**

> The first run may take a few extra seconds while WSL wakes up.

---

## What the Launcher Checks

| # | Check | What it does | If missing |
|---|-------|-------------|------------|
| 1 | **WSL2 reachable** | Runs `wsl bash -c "echo ok"` | Install WSL2 via `wsl --install` |
| 2 | **WSLg display** | Verifies `$DISPLAY` or `$WAYLAND_DISPLAY` is set | Update WSL (`wsl --update`) and restart |
| 3 | **OpenFOAM 2506** | Checks `/usr/lib/openfoam/openfoam2506/etc/bashrc` exists | Install OpenFOAM 2506 in WSL |
| 4 | **Python 3** | Runs `python3 --version` in WSL | `sudo apt-get install python3 python3-pip` |
| 5 | **Python packages** | Imports PyQt5, numpy, jinja2, trimesh | Launcher offers auto-install via pip3 |
| 6 | **openfoam_ui.py** | Confirms the file is next to the .exe | Keep all files in the same folder |

Checks run in order and stop at the first failure with a clear error message
and exact fix commands.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Windows 10 Build 21362** or Windows 11 | Required for WSLg (GUI apps from WSL) |
| **WSL2** (not WSL1) | `wsl --install` sets this up; `wsl --status` shows current version |
| **OpenFOAM v2506** inside WSL | See installation guide below |
| **Python 3 + pip** inside WSL | Usually pre-installed on Ubuntu; check with `python3 --version` |
| **PyQt5, numpy, jinja2, trimesh** inside WSL | Launcher can install these automatically on first run |

**OpenFOAM 2506 installation (Ubuntu/Debian inside WSL):**
Follow the precompiled package instructions at:
`https://develop.openfoam.com/Development/openfoam` → Precompiled → Debian/Ubuntu

---

## Folder Structure

All files must remain in the same folder. Do not move `OpenFOAM_UI.exe` out.

```
01_utilities/
├── OpenFOAM_UI.exe                 ← double-click to launch (place here after build)
├── openfoam_ui.py                  ← main PyQt5 GUI application
├── ui_landing.py
├── ui_background_mesh.py
├── ui_snappy_hex.py
├── ui_shared.py
├── ui_log_drawer.py
├── setup_snappy.py
├── auto_refinement.py
├── encoding_utils.py
├── generateBackgroundMesh.py
├── generateSnappyHexMeshDict.py
├── defaults.json
├── requirements.txt
├── templates/
│   ├── blockMeshDict.template
│   └── snappyHexMeshDict.template
│
│   ── Developer files (not needed by end users) ──
├── openfoam_ui_launcher.py         ← launcher source (builds the .exe)
├── openfoam_ui_launcher.spec       ← PyInstaller spec
├── version_info.txt                ← Windows EXE metadata
└── build_exe.bat                   ← build script
```

---

## Troubleshooting

### "WSL Not Found"

`wsl.exe` is not installed on this machine.

**Fix:** Open PowerShell as Administrator and run:
```
wsl --install
```
Restart Windows, then try the launcher again. If WSL is blocked by IT policy,
contact your system administrator.

---

### "WSL Timed Out"

WSL did not respond within 10 seconds. WSL may be starting up or stuck.

**Fix:**
```powershell
wsl --shutdown
```
Wait 10 seconds, then run the launcher again.

---

### "WSL Unreachable"

WSL responded with an unexpected exit code.

**Fix:**
```powershell
wsl --status
wsl --shutdown
```
Then try again. If the error persists, run `wsl --update` and restart.

---

### "No Display Available"

`$DISPLAY` and `$WAYLAND_DISPLAY` are both unset. WSLg is not active.

**Fix:**
```powershell
wsl --update
wsl --shutdown
```
WSLg requires Windows 10 Build 21362+ or Windows 11 with WSL2.
Check your build with `winver`. Contact IT if you cannot update Windows.

---

### "Wrong OpenFOAM Version Installed"

OpenFOAM v2312 was found but v2506 is required.

**Fix:** Install OpenFOAM 2506 inside WSL alongside 2312, or replace it.
Follow the Debian/Ubuntu precompiled package guide at:
`https://develop.openfoam.com/Development/openfoam`

---

### "OpenFOAM Not Found"

No supported OpenFOAM bashrc was found.

**Fix:** Install OpenFOAM 2506 inside your WSL Ubuntu environment.
Installation guide: `https://develop.openfoam.com/Development/openfoam`
→ Precompiled packages → Debian/Ubuntu

---

### "Python 3 Not Found in WSL"

`python3` is not available inside WSL.

**Fix:** Open a WSL terminal and run:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip
```

---

### "Missing Python Packages" (auto-install declined or failed)

One or more of PyQt5, numpy, jinja2, trimesh are missing.

**Fix:** Open a WSL terminal and run:
```bash
pip3 install PyQt5 numpy jinja2 trimesh --break-system-packages
```
Or install the system packages instead:
```bash
sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2
pip3 install trimesh --break-system-packages
```

---

### "Package Installation Failed"

`pip3 install` ran but returned an error.

**Fix:** Open a WSL terminal and run the install command manually so you can
see the full error output. Common causes: no internet access in WSL, or a
corporate proxy blocking pip. Contact your network administrator if needed.

---

### "Application File Missing"

`openfoam_ui.py` is not in the same folder as `OpenFOAM_UI.exe`.

**Fix:** Make sure the `.exe` is inside the `01_utilities` folder alongside
all the `.py` files. Do not distribute the `.exe` alone.

---

### "Launch Failed"

`wsl.exe` was found but the process could not be started.

**Fix:** Open a WSL terminal and launch manually:
```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```
Check the terminal output for Python errors, then contact your administrator.

---

## For Developers — Rebuilding the EXE

Run `build_exe.bat` once on a Windows machine that has Python 3.9+ installed:

```
build_exe.bat
```

The script will:
1. Install / upgrade PyInstaller via pip
2. Delete old `build\` and `dist\` folders
3. Run `pyinstaller openfoam_ui_launcher.spec`
4. Produce `dist\OpenFOAM_UI.exe`

Copy `dist\OpenFOAM_UI.exe` into `01_utilities\`, then zip the entire
`01_utilities\` folder for distribution.

> **Note:** The `.exe` only bundles the Windows launcher (tkinter + stdlib).
> PyQt5, numpy, jinja2, and trimesh are intentionally **not** bundled —
> they run inside WSL and are checked / installed at launch time.
