# OpenFOAM Mesh Generation Utilities

Python utilities for automating snappyHexMesh setup in ESI OpenFOAM v2506, with a PyQt5 GUI and CLI fallbacks.

---

# User Guide

For engineers and simulation runners using the tool day-to-day.

## Quick Start

1. Navigate to the `01_utilities\` folder.
2. Double-click **`OpenFOAM_UI.exe`**.
3. A startup window appears, runs environment checks, and opens the GUI automatically.

> The first run may take a few extra seconds while WSL wakes up.

---

## Fresh Installation (Windows + WSL + OpenFOAM)

> Skip this section if WSL and OpenFOAM are already installed on the machine.

### Step 1 — Install WSL

1. Open **PowerShell as Administrator**.
2. Run:
   ```powershell
   wsl --install
   ```
3. **Restart** your device.

### Step 2 — Install Ubuntu

1. Open **PowerShell as Administrator**.
2. Run:
   ```powershell
   wsl --install Ubuntu
   ```
3. **Restart** your device.

### Step 3 — Open WSL

**Option A — via Terminal UI:**
1. Open **Terminal**.
2. Click the **down arrow (⌄)** next to the tab bar.
3. Select **Ubuntu**.

**Option B — via command:**
1. Open **Terminal**.
2. Run:
   ```powershell
   wsl -d Ubuntu
   ```

### Step 4 — Install OpenFOAM

From the **Ubuntu terminal**, run the following in order:

```bash
curl -s https://dl.openfoam.com/add-debian-repo.sh | sudo bash
```

```bash
sudo apt-get update
sudo apt-get upgrade
```

```bash
sudo apt-get install openfoam2506-default
```

---

## Tool Setup

### Step 5 — Get the Tool Files

Obtain the `01_utilities\` ZIP from the project maintainer.

The ZIP must contain all of the following files — do not omit any:

```
openfoam_ui.py                   ← GUI entry point
ui_background_mesh.py
ui_snappy_hex.py
ui_log_drawer.py
ui_landing.py
ui_shared.py
snappy_generator.py
generateBackgroundMesh.py        ← standalone CLI
generateSnappyHexMeshDict.py     ← standalone CLI
defaults.json
requirements.txt
OpenFOAM_UI.exe                  ← Windows launcher
```

Do **not** include `__pycache__\` — it is machine-specific and regenerates automatically.

### Step 6 — Place the Files

Extract the ZIP anywhere on Windows. The path must be reachable under `/mnt/` from WSL. Recommended location:

```
C:\OpenFOAM\
└── 01_utilities\
```

WSL equivalent: `/mnt/c/OpenFOAM/01_utilities/`

### Step 7 — Install Python Dependencies

From the **Ubuntu terminal**:

**Recommended (system packages, no venv needed):**

```bash
sudo apt-get install python3-pip
sudo apt-get install python3-pyqt5 python3-numpy
```

**Alternative (pip):**

```bash
pip3 install -r /mnt/c/OpenFOAM/01_utilities/requirements.txt --break-system-packages
```

| Package | Required | Purpose |
|---------|----------|---------|
| `PyQt5` | Yes | GUI framework |
| `numpy` | Yes | Bounding box arithmetic |

### Step 8 — Set Up Aliases (optional but recommended)

1. Open the aliases file:
   ```bash
   vi ~/.bash_aliases
   ```

2. Press `i` to enter insert mode and add:
   ```bash
   alias myDir="cd /mnt/c/OpenFOAM"
   alias of2506="source /usr/lib/openfoam/openfoam2506/etc/bashrc"
   alias generateBackgroundMesh="python3 /mnt/c/OpenFOAM/01_utilities/app/generateBackgroundMesh.py"
   alias generateSnappyHexMeshDict="python3 /mnt/c/OpenFOAM/01_utilities/app/generateSnappyHexMeshDict.py"
   alias openfoamUI="python3 /mnt/c/OpenFOAM/01_utilities/app/openfoam_ui.py"
   ```

3. Press `Esc`, then save and quit:
   ```
   :wq
   ```

   | vi command | Action |
   |------------|--------|
   | `i` | Enter insert mode |
   | `Esc` | Exit insert mode |
   | `:wq` | Save and quit |
   | `:q!` | Force quit, discard changes |

4. Apply the aliases:
   ```bash
   source ~/.bash_aliases
   ```

### Step 9 — Source the OpenFOAM Environment

Add to `~/.bashrc` to activate automatically, or run manually before each session:

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
```

With the alias from Step 8:

```bash
of2506
```

---

## Prerequisites Summary

| Requirement | Notes |
|-------------|-------|
| **Windows 10 Build 21362** or Windows 11 | Required for WSLg (GUI apps from WSL) |
| **WSL2** (not WSL1) | `wsl --install` sets this up; `wsl --status` shows current version |
| **OpenFOAM v2506** inside WSL | See Steps 1–4 above |
| **Python 3 + pip** inside WSL | Usually pre-installed on Ubuntu; check with `python3 --version` |
| **PyQt5, numpy** inside WSL | See Step 7; launcher can also install these automatically on first run |

## What the Launcher Checks

The startup window runs six checks in order and stops at the first failure with a clear error message and fix instructions.

| # | Check | If missing |
|---|-------|------------|
| 1 | **WSL2 reachable** | Install WSL2: `wsl --install` (PowerShell as Administrator), restart Windows |
| 2 | **WSLg display** | `wsl --update` then `wsl --shutdown` |
| 3 | **OpenFOAM 2506** | Install OpenFOAM 2506 in WSL — see Steps 1–4 above |
| 4 | **Python 3** | `sudo apt-get install -y python3 python3-pip` inside WSL |
| 5 | **Python packages** | Launcher offers auto-install; or see Step 7 |
| 6 | **openfoam_ui.py present** | Keep all files in the same `01_utilities\` folder — do not move the `.exe` |

---

## Using the GUI

The GUI requires a display. On **Windows 11** this works automatically via WSLg. On **Windows 10** start an X server (VcXsrv or MobaXterm) first.

### Landing Page

On launch the GUI shows a landing page where you:

- **New project** — enter a name and location; the tool creates the folder structure (`constant/triSurface/`, `system/`, `0/`) and stub dictionaries (`controlDict`, `fvSchemes`, `fvSolution`).
- **Open existing** — browse to or pick from the recent-projects list (max 10; each has a × button to remove it). Validates that `system/controlDict` exists.

Choose a utility (Background Mesh or SnappyHexMesh Dict) and click **Continue →**. The **← Home** button in the header bar returns to the landing page at any time.

> The working directory does not need to be set before launching — the landing page handles it.

### Tab 1 — Background Mesh

Generates `system/blockMeshDict` from an STL bounding box and runs `blockMesh`.

1. **STL file** — browse or paste path; auto-detects the case root from `constant/` in the path (works regardless of the geometry subfolder name).
2. **Grid resolution** — DX / DY / DZ cell sizes in metres.
3. Click **Generate Background Mesh** — runs `surfaceCheck`, writes `blockMeshDict`, runs `blockMesh`, creates `<case>.foam`.
4. **Cancel** — stops a running job and clears all input fields.

### Tab 2 — SnappyHexMesh Dict

Five-section card form that writes `system/snappyHexMeshDict` via `foamDictionary` calls and runs `snappyHexMesh`.

| Section | Content |
|---------|---------|
| **01 Geometry** | File table listing all `.stl`/`.obj` files found under `constant/` (any subfolder); set Surface Type (None / Boundary / FaceZone / FaceZone+CellZone), min/max refinement levels, and Volume Direction + level per file; plus a spinbox to add standard analytical shapes (Box, Cylinder, Sphere) with inline coordinate inputs |
| **02 Castellation** | Geometry unit (mm / m / cm / µm / in / ft), nCellsBetweenLevels, location-in-mesh X Y Z |
| **03 Snap controls** | Implicit feature snapping toggle |
| **04 Layer addition** | Enable boundary layers; per-patch nSurfaceLayers spinboxes (auto-populated from Section 01 surface selections) |
| **05 Generate & Run** | Single **Generate Dict & Run snappyHexMesh** button: writes `system/snappyHexMeshDict` (plus `fvSchemes`/`fvSolution` when layers are on), streams the solver to the log, removes numeric time directories (except `0`), and refreshes the `.foam` file |

### Output Log

The **Output Log** at the bottom of the window starts expanded and streams all subprocess output with colour-coded tags (`error` → red, `warn` → amber, `info` → blue, `cmd` → grey). Drag its bottom grip upward to resize it, or click the chevron to collapse/expand.

---

## Case Directory Requirements

A valid working directory must contain:

```
<case-root>/
├── constant/           ← required; geometry files go in any subfolder here
│   └── <any-name>/    ← e.g. triSurface/, geometry/, surfaces/ — name is flexible
│       └── *.stl / *.obj
└── system/             ← required; generated dicts are written here
```

The GUI scans **all of `constant/`** recursively for `.stl` and `.obj` files — the subfolder name does not matter.

To use your own case:
1. Ensure the case has both `constant/` and `system/` folders.
2. Place STL/OBJ geometry files inside any subfolder of `constant/`.
3. Use the landing page to browse to or create the case, or use the **Change** button in Tab 2 to switch while the GUI is running.

---

## Typical Workflow

```bash
# 1. Source the OpenFOAM environment
source /usr/lib/openfoam/openfoam2506/etc/bashrc

# 2. Launch the GUI (double-click the .exe, or from WSL terminal:)
python3 /mnt/c/OpenFOAM/01_utilities/app/openfoam_ui.py
# With alias: of2506 && openfoamUI

# Landing page: create a new project or open an existing one → choose utility → Continue →

# 3. Tab 1 — select STL, set DX/DY/DZ, click Generate Background Mesh

# 4. Tab 2 — configure Sections 01–04, click Generate snappyHexMeshDict, then Run snappyHexMesh

# 5. Click Open ParaView in the header bar to inspect the mesh
```

---

## CLI Tools

For power users who prefer the terminal. All commands must be run inside WSL with the OpenFOAM environment sourced.

### generateBackgroundMesh.py

Reads an STL bounding box via `surfaceCheck`, writes `system/blockMeshDict`, and runs `blockMesh`.

```bash
cd /mnt/c/OpenFOAM/03_mesh_session
source /usr/lib/openfoam/openfoam2506/etc/bashrc

python3 /mnt/c/OpenFOAM/01_utilities/app/generateBackgroundMesh.py \
  -stlPath constant/triSurface/geometry.stl \
  -dx 0.05 -dy 0.05 -dz 0.05
```

| Argument | Description |
|----------|-------------|
| `-stlPath` | Path to the STL file |
| `-dx` | Cell size in x (metres) |
| `-dy` | Cell size in y (metres) |
| `-dz` | Cell size in z (metres) |

Logs are written to `programOutputs/`.

### generateSnappyHexMeshDict.py

Interactive CLI that builds `system/snappyHexMeshDict` through prompts. Also generates `system/fvSchemes` and `system/fvSolution` when boundary layer addition is enabled.

```bash
cd /mnt/c/OpenFOAM/03_mesh_session
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/app/generateSnappyHexMeshDict.py
```

Requires `system/controlDict` and a `constant/` directory to exist in the case root.

---

## Troubleshooting

### Launcher error messages

#### "WSL Not Found"
`wsl.exe` is not installed on this machine.

**Fix:** Open PowerShell as Administrator and run:
```powershell
wsl --install
```
Restart Windows, then try the launcher again. Contact IT if WSL is blocked by policy.

---

#### "WSL Timed Out"
WSL did not respond within 10 seconds.

**Fix:**
```powershell
wsl --shutdown
```
Wait 10 seconds, then run the launcher again.

---

#### "WSL Unreachable"
WSL responded with an unexpected exit code.

**Fix:**
```powershell
wsl --status
wsl --shutdown
```
Then try again. If the error persists, run `wsl --update` and restart.

---

#### "No Display Available"
`$DISPLAY` and `$WAYLAND_DISPLAY` are both unset — WSLg is not active.

**Fix:**
```powershell
wsl --update
wsl --shutdown
```
WSLg requires Windows 10 Build 21362+ or Windows 11 with WSL2. Check your build with `winver`.

---

#### "Wrong OpenFOAM Version Installed"
OpenFOAM v2312 was found but v2506 is required.

**Fix:** Install OpenFOAM 2506 inside WSL alongside 2312, or replace it. Follow the Debian/Ubuntu precompiled package guide at `https://develop.openfoam.com/Development/openfoam`.

---

#### "OpenFOAM Not Found"
No supported OpenFOAM bashrc was found.

**Fix:** Install OpenFOAM 2506 inside your WSL Ubuntu environment — see Steps 1–4 above.

---

#### "Python 3 Not Found in WSL"
`python3` is not available inside WSL.

**Fix:**
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip
```

---

#### "Missing Python Packages"
One or more of PyQt5, numpy are missing.

**Fix:**
```bash
pip3 install PyQt5 numpy --break-system-packages
```
Or use system packages:
```bash
sudo apt-get install -y python3-pyqt5 python3-numpy
```

---

#### "Package Installation Failed"
`pip3 install` ran but returned an error.

**Fix:** Open a WSL terminal and run the install command manually to see the full error. Common causes: no internet access in WSL, or a corporate proxy blocking pip.

---

#### "Application File Missing"
`openfoam_ui.py` is not in the same folder as `OpenFOAM_UI.exe`.

**Fix:** Keep the `.exe` inside the `01_utilities` folder alongside all the `.py` files. Do not distribute the `.exe` alone.

---

#### "Launch Failed"
`wsl.exe` was found but the process could not be started.

**Fix:** Open a WSL terminal and launch manually:
```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```
Check terminal output for Python errors.

---

### General issues

| Problem | Fix |
|---------|-----|
| `python3: command not found` | `sudo apt-get install python3` |
| `No module named 'PyQt5'` | `sudo apt-get install python3-pyqt5` |
| `blockMesh: command not found` | Source the OpenFOAM environment first: `source /usr/lib/openfoam/openfoam2506/etc/bashrc` |
| Blank window / no display | Windows 10: start VcXsrv or MobaXterm; Windows 11: WSLg should work out of the box |
| `Not found: .../constant` | The selected directory is not a valid case root — it must contain both `constant/` and `system/` |
| No files in Tab 2 geometry table | No `.stl` or `.obj` files found under `constant/`; check file placement |
| ParaView button does nothing | Install ParaView on Windows under `C:\Program Files\ParaView*\` |
| `Could not parse stylesheet` in terminal | Harmless Qt5 warning on Linux/WSL — the GUI suppresses these automatically; no action needed |

### Installing additional Python libraries

```bash
sudo apt-get install python3-<library_name>
```

Or with pip:

```bash
pip3 install <library_name> --break-system-packages
```

---

---

# Developer Guide

For developers maintaining, extending, or deploying the tool.

## Repository Layout

```
C:\OpenFOAM\
├── 01_utilities\
│   ├── app\                            # Distribution ZIP — all end-user files
│   │   ├── openfoam_ui.py              # PyQt5 GUI entry point
│   │   ├── ui_shared.py                # Colour tokens, styles, shared helpers
│   │   ├── ui_landing.py               # Landing page widget
│   │   ├── ui_log_drawer.py            # Collapsible/resizable log drawer widget
│   │   ├── ui_background_mesh.py       # Background Mesh tab widget
│   │   ├── ui_snappy_hex.py            # SnappyHexMesh Dict tab widget
│   │   ├── snappy_generator.py         # Tab 2 backend: foamDictionary calls + snappyHexMesh run
│   │   ├── defaults.json               # Default OpenFOAM solver parameters
│   │   ├── generateBackgroundMesh.py   # CLI: blockMesh from STL bbox (do not modify)
│   │   ├── generateSnappyHexMeshDict.py # CLI: interactive snappyHexMeshDict (do not modify)
│   │   ├── requirements.txt            # Python dependencies
│   │   ├── openfoam_ui_launcher.py     # Windows launcher source (builds the .exe)
│   │   ├── OpenFOAM_UI.exe             # Windows launcher binary
│   │   ├── icons\                      # App icon PNGs
│   │   │   ├── icon_16.png  …  icon_256.png
│   │   │   └── openfoam_ui.ico
│   │   └── templates\                  # OpenFOAM dict templates
│   └── deploy\                         # Build tools — not in the distribution zip
│       ├── generate_icon.py            # Generates SVG → PNG → ICO icon pipeline
│       ├── icon_source.svg             # Generated SVG source (output of generate_icon.py)
│       ├── openfoam_ui_launcher.spec   # PyInstaller spec
│       ├── version_info.txt            # Windows EXE metadata (file version, product name)
│       ├── build_exe.bat               # One-click build script (runs icon gen + pyinstaller)
│       ├── build\                      # PyInstaller intermediate artefacts
│       └── dist\                       # Built OpenFOAM_UI.exe output
├── 03_mesh_session\                    # Example OpenFOAM case
│   ├── constant\<geometry>\            # Input STL geometry files (any subfolder name)
│   ├── constant\polyMesh\              # Generated mesh (blockMesh output)
│   ├── system\                         # Dictionaries (blockMeshDict, snappyHexMeshDict, …)
│   └── programOutputs\                 # Captured log files
├── agents\                             # Scoped subagent definitions (see CLAUDE.md)
│   ├── foam-docs.md
│   ├── foam-ui.md
│   ├── foam-snappymesh.md
│   ├── foam-backgroundmesh.md
│   └── foam-git.md
├── documentation\
│   └── OpenFOAMSetup.md                # WSL/OpenFOAM setup and troubleshooting guide
└── CLAUDE.md                           # AI assistant guidance (architecture, design patterns)
```

## Python Dependencies

Install inside WSL:

```bash
sudo apt-get install -y python3-pyqt5 python3-numpy
```

Or via pip (Ubuntu 24.04+):

```bash
pip3 install -r 01_utilities/requirements.txt --break-system-packages
```

| Package | Required | Purpose |
|---------|----------|---------|
| `PyQt5` | Yes | GUI framework |
| `numpy` | Yes | Bounding box scaling and cell-count arithmetic |

## Architecture Overview

The tool has two layers: the **Windows launcher** (`.exe`) and the **Python application** (WSL).

**Windows launcher (`openfoam_ui_launcher.py` → `OpenFOAM_UI.exe`)**
- Stdlib only (`tkinter`, `subprocess`, `sys`, `os`, `time`) — no PyQt5 or OpenFOAM dependencies bundled.
- Shows a branded splash, runs six pre-flight checks, then calls `python3 openfoam_ui.py` inside WSL via `subprocess.Popen` and immediately closes.
- PyInstaller bundles only this file; all application logic runs live from `.py` files in WSL.

**Python application (WSL)**
- `openfoam_ui.py` — `QMainWindow` entry point; tab switching, header bar, LogDrawer, ParaView launcher.
- `ui_landing.py` — new/open project landing page; recents stored in `~/.openfoam_ui_recents.json`.
- `ui_background_mesh.py` — Tab 1; `_BgMeshWorker(QThread)` runs `surfaceCheck` → `blockMesh`.
- `ui_snappy_hex.py` — Tab 2; `_SnappyWorker(QThread)` calls `snappy_generator.generate_and_run()`.
- `snappy_generator.py` — Tab 2 backend; writes `snappyHexMeshDict` via a `foamDictionary` call sequence (mirroring the reference CLI), then streams `snappyHexMesh -overwrite`. All subprocess calls use `bash -c 'source <OF_bashrc> && ...'` with `cwd=case_dir`; never uses `os.chdir()`.

See `CLAUDE.md` for full architecture detail and design patterns.

## Rebuilding the EXE

Only needed when `openfoam_ui_launcher.py` itself changes. Edits to any other `.py` file take effect immediately on next launch — no rebuild required.

**Requirements (Windows only):**
- Python 3.9+ installed on Windows (not WSL)
- PyInstaller will be installed automatically by the build script

**Steps:**

```bat
cd C:\OpenFOAM\01_utilities\deploy
build_exe.bat
```

The script:
1. Installs/upgrades PyInstaller via pip
2. Deletes old `build\` and `dist\` folders
3. Runs `pyinstaller openfoam_ui_launcher.spec`
4. Produces `dist\OpenFOAM_UI.exe`

Copy `dist\OpenFOAM_UI.exe` into `01_utilities\` to replace the existing launcher.

## Deployment Checklist

Run through this list for every release distributed to end users.

### Before building

- [ ] All changes committed and on `main`
- [ ] `version_info.txt` updated with the new version number
- [ ] `_Splash` label in `openfoam_ui_launcher.py` (`v1.0.0`) updated to match
- [ ] Tested the GUI end-to-end in WSL: landing page → Tab 1 → Tab 2 → ParaView
- [ ] Confirmed `defaults.json` and both Jinja2 templates are correct
- [ ] `requirements.txt` matches the packages actually imported

### Building the EXE

- [ ] Run `build_exe.bat` on a clean Windows machine (Python 3.9+, no stale `build\`/`dist\`)
- [ ] Confirm `dist\OpenFOAM_UI.exe` was produced with no PyInstaller errors
- [ ] Copy `dist\OpenFOAM_UI.exe` → `01_utilities\OpenFOAM_UI.exe`

### Packaging

- [ ] ZIP the `01_utilities\app\` folder (include `.exe`, all `.py`, `icons\`, `defaults.json`, `requirements.txt`, `templates\`)
- [ ] Confirm `icons\` folder is present and contains at minimum `icon_256.png` (run `deploy\build_exe.bat` to regenerate)
- [ ] Verify the ZIP does **not** include `deploy\`, `__pycache__\`, or any `.pyc` files
- [ ] Smoke-test the ZIP: extract to a clean folder, double-click the `.exe`, confirm all pre-flight checks pass and the GUI opens

### What is and is not bundled in the EXE

The `.exe` bundles only the launcher (`tkinter` + stdlib). The following run live from the extracted `.py` files inside WSL — **they are not in the `.exe`**:

| Bundled in EXE | Not bundled (runs from .py files) |
|----------------|-----------------------------------|
| `openfoam_ui_launcher.py` | `openfoam_ui.py` and all `ui_*.py` |
| tkinter, stdlib | `snappy_generator.py` |
| | PyQt5, numpy |
| | `defaults.json` |

## Platform Notes

- Windows path `C:\OpenFOAM` maps to WSL path `/mnt/c/OpenFOAM`
- Target OpenFOAM version: **2506** (also compatible with 2312)
- ParaView is detected at runtime by scanning `/mnt/c/Program Files/ParaView*/bin/paraview.exe` (newest version wins); converted to Windows UNC format via `wslpath -w` before launching
- The GUI window is 1100×760, centered on the primary screen; requires WSLg or an X server
- Qt5 on Linux/WSL prints harmless `Could not parse stylesheet` messages for some `QFrame` widgets; a `qInstallMessageHandler` in `openfoam_ui.py` silences these — only genuine Qt warnings reach stderr
