# OpenFOAM Mesh Generation Utilities

Python utilities for automating snappyHexMesh setup in ESI OpenFOAM v2506, with a PyQt5 GUI and CLI fallbacks.

---

# User Guide

## Quick Start

1. Go to `src\app\`.
2. Double-click **`OpenFOAM_UI.exe`**.
3. Startup window runs environment checks, then opens the GUI.

> First run may take a few extra seconds while WSL wakes up.

---

## Fresh Installation (Windows + WSL + OpenFOAM)

> Skip if WSL and OpenFOAM are already installed.

1. **Install WSL** — PowerShell as Administrator: `wsl --install`, then restart.
2. **Install Ubuntu** — PowerShell as Administrator: `wsl --install Ubuntu`, then restart.
3. **Open WSL** — Terminal → down arrow (⌄) next to tab bar → Ubuntu, or run `wsl -d Ubuntu`.
4. **Install OpenFOAM** — from the Ubuntu terminal, in order:
   ```bash
   curl -s https://dl.openfoam.com/add-debian-repo.sh | sudo bash
   sudo apt-get update && sudo apt-get upgrade
   sudo apt-get install openfoam2506-default
   ```

---

## Tool Setup

### Get the files

Obtain the `src\` ZIP. It must contain every `.py` file, `defaults.json`, `requirements.txt`, `OpenFOAM_UI.exe`, and `templates\`. Do **not** include `__pycache__\`.

### Place the files

Extract anywhere Windows-reachable under `/mnt/` from WSL. Recommended: `C:\OpenFOAM\src\` (WSL: `/mnt/c/OpenFOAM/src/`).

### Install Python dependencies

From the Ubuntu terminal:

```bash
sudo apt-get install python3-pip python3-pyqt5 python3-numpy python3-jinja2
```

Or with pip: `pip3 install -r /mnt/c/OpenFOAM/src/requirements.txt --break-system-packages`

| Package | Purpose |
|---------|---------|
| `PyQt5` | GUI framework |
| `numpy` | Bounding box arithmetic |
| `jinja2` | snappyHexMeshDict template rendering |

### Aliases (optional)

```bash
vi ~/.bash_aliases
```
Insert (`i`), add, save (`Esc` then `:wq`):
```bash
alias myDir="cd /mnt/c/OpenFOAM"
alias of2506="source /usr/lib/openfoam/openfoam2506/etc/bashrc"
alias openfoamUI="python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py"
```
Apply: `source ~/.bash_aliases`

### Source the OpenFOAM environment

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
```
Add to `~/.bashrc` to run automatically, or use the `of2506` alias.

---

## Prerequisites Summary

| Requirement | Notes |
|-------------|-------|
| Windows 10 Build 21362+ or Windows 11 | Needed for WSLg |
| WSL2 (not WSL1) | `wsl --install` sets this up |
| OpenFOAM v2506 inside WSL | See installation steps above |
| Python 3 + PyQt5, numpy, jinja2 inside WSL | Launcher installs via apt automatically on first run |

## What the Launcher Checks (and Fixes Itself)

Pre-flight steps run in order; most failures are **self-healing** — the launcher offers a one-click fix instead of just an error:

| # | Step | If missing — what the launcher does |
|---|------|------------|
| 0 | Windows build ≥ 21362 (WSLg) | Clear "Windows too old" message up front |
| 1 | WSL installed | **[Install WSL]** button — UAC prompt, then optional one-time **Restart Now** |
| 2 | Ubuntu distro exists | **[Install Ubuntu]** button — downloads it, then opens a guided terminal to create your username/password |
| 3 | Patient WSL boot (90s) | Click **Try Again** — VM still booting |
| 4 | Distro is WSL2 (not WSL1) | **[Convert to WSL2]** button |
| 5 | WSLg display + compositor | **[Update WSL]** button (`wsl --update` + restart WSL) |
| 6 | OpenFOAM bashrc (2506, or 2312) | Included in the setup consent below |
| 7 | Network + disk-space probes | Warns before setup if download servers are unreachable (corporate proxy) or disk is low |
| 8 | Python packages + setup gate | Single consent dialog; apt-only install of Qt libs + PyQt5/numpy/jinja2 (+ OpenFOAM if missing) |
| 9 | `openfoam_ui.py` present | Keep all files together in `src\app\` |

If an automatic install can't run (admin permission declined / blocked by policy), the launcher shows numbered manual steps with a **Copy Command** button, and continues automatically on the next run once the install is done. Every error dialog has **Copy Details** — a full diagnostics report for IT tickets.

---

## Using the GUI

Needs a display — automatic via WSLg on Windows 11; start an X server (VcXsrv/MobaXterm) on Windows 10.

### Landing Page

- **New project** — enter name/location; creates `constant/triSurface/`, `system/`, `0/` and stub dicts. Name is auto-cleaned as you type (spaces/punctuation → `_`); `C:\…` locations are auto-converted to WSL `/mnt/…`.
- **Template** — *Empty case*, or *From STL* (pick one or more `.stl`/`.obj` files, copied into `constant/triSurface/`).
- **Open existing** — browse or pick from recents (max 10). Validates `system/controlDict` exists. Removing a recent entry (×) asks for confirmation first — the project folder itself is never deleted.
- **Environment card** — shows the *detected* versions of OpenFOAM, ParaView, Ubuntu, and Python on this machine (green dot = found, grey = not found). Nothing is hardcoded — a different install (e.g. OpenFOAM 2312) shows its real version and is used automatically.

Pick a utility, then click the footer **Open →** (enabled once a project and utility are both chosen; double-click a utility card also opens). **← Home** returns anytime.

### Tab 1 — Background Mesh

Generates `system/blockMeshDict` from an STL bounding box and runs `blockMesh`.

1. **STL file** — browse or paste path; case root auto-detected from `constant/`.
2. **Grid resolution** — DX/DY/DZ cell sizes (metres).
3. **Generate Background Mesh** — runs `surfaceCheck` → writes dict → runs `blockMesh` → creates `.foam`.
4. **Cancel** stops the job and clears inputs.

On success a green banner offers **Continue to Snappy Hex Mesh →**; on failure a red banner shows a plain-language cause and fix (see [Error messages](#error-messages)).

### Tab 2 — SnappyHexMesh Dict

Renders `system/snappyHexMeshDict` in one pass, records inputs to `snappy_inputs.json`, runs `snappyHexMesh`.

**Surface Type, plain words:** *Boundary* = outer shell, mesh stops there. *FaceZone + Cell Zone* = a solid part **inside** the domain — its cells are kept and tagged as a named group. Skip Cell Zone and the inner part's cells get thrown away (invisible in the mesh). A Boundary shell should never carry a Vol Dir — the GUI locks this to None automatically.

| Section | Content |
|---------|---------|
| **01 Geometry** | File table (`.stl`/`.obj` under `constant/`): **Use** checkbox (untick to leave a file out of the mesh entirely — it stays on disk), Surface Type, refinement Min/Max (independent, default 0/0), Vol Dir + Vol Level (independent, default 0). Plus standard shapes (Box/Cylinder/Sphere). **Smart defaults**: largest file → Boundary; rest → FaceZone+CellZone+Inside. **Refresh file list** rescans and preserves your settings |
| **02 Castellation** | Geometry unit, nCellsBetweenLevels, location-in-mesh X/Y/Z; **Suggest point** places it 60% from the largest boundary STL's centroid toward its max corner — verify it lands in fluid, outside any inner solid |
| **03 Snap controls** | Implicit feature snapping always on — no `.eMesh`/`surfaceFeatureExtract` step |
| **04 Layer addition** | Enable boundary layers; per-patch nSurfaceLayers, auto-populated from Section 01 |
| **05 Generate & Run** | **Pre-flight check** (live ✓/✗ list: background mesh exists, a Boundary file is set, FaceZone files have Cell Zone, location-in-mesh set), then renders the dict, writes `snappy_inputs.json`, streams the solver log, cleans up numeric time dirs, refreshes `.foam` |

> Every input has a hover tooltip explaining valid choices and pitfalls — hover column headers for column-level help. Tooltips share one look across the whole app (white background, black text, red rounded border).

### Output Log

Bottom drawer, colour-coded tags (`error` red, `warn` amber, `info` blue, `cmd` grey). Drag to resize, click chevron to collapse. During a snappyHexMesh run the header shows a live **Step X/3** label (Castellating → Snapping → Adding layers) parsed from the solver's own output.

### Error messages

When a run fails, a red banner above the log translates the raw OpenFOAM output into a plain-language cause and fix — covering common cases like a bad location-in-mesh point, an empty mesh (`selected 0 cells`), a missing background mesh, a non-watertight STL, or a missing `jinja2`. The full log stays below for detail.

---

## Case Directory Requirements

```
<case-root>/
├── constant/           ← required; geometry in any subfolder
│   └── <any-name>/
│       └── *.stl / *.obj
└── system/             ← required; generated dicts go here
```

GUI scans all of `constant/` recursively — subfolder name doesn't matter.

---

## Typical Workflow

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py
# Landing page → new/open project → choose utility → Continue →
# Tab 1: select STL, set DX/DY/DZ, Generate Background Mesh
# Tab 2: configure Sections 01-04, Generate + Run snappyHexMesh
# Open ParaView from the header bar to inspect the mesh
```

---

## CLI Tools

Run inside WSL with the OpenFOAM environment sourced.

**generateBackgroundMesh.py** — STL bbox → `blockMeshDict` → `blockMesh`:
```bash
python3 /mnt/c/OpenFOAM/src/app/generateBackgroundMesh.py \
  -stlPath constant/triSurface/geometry.stl -dx 0.05 -dy 0.05 -dz 0.05
```

**generateSnappyHexMeshDict.py** — interactive prompts, also writes `fvSchemes`/`fvSolution` when layers are enabled:
```bash
python3 /mnt/c/OpenFOAM/src/app/generateSnappyHexMeshDict.py
```
Requires `system/controlDict` and `constant/` in the case root.

---

## Troubleshooting

| Launcher error | Fix |
|---|---|
| WSL Not Installed | Click **Install WSL** (needs admin approval); or `wsl --install` in admin PowerShell, restart |
| No Linux Distribution Found | Click **Install Ubuntu** and follow the terminal; or `wsl --install -d Ubuntu` |
| Distro is WSL1 | Click **Convert to WSL2**; or `wsl --set-version <distro> 2` |
| Administrator Permission Needed | Follow the numbered steps in the dialog (**Copy Command** copies the exact command); ask IT if you lack admin rights |
| Download Servers Unreachable | Corporate proxy/firewall — connect to an open network or ask IT to allow archive.ubuntu.com and dl.openfoam.com |
| Low Disk Space | Free space on C: and inside WSL, then retry |
| WSL Timed Out | Click **Try Again** — VM still booting |
| WSL Unreachable | `wsl --status`, `wsl --shutdown`, retry; else `wsl --update` |
| No Display Available | `wsl --update`, `wsl --shutdown`; needs Win10 21362+/Win11 |
| Wrong OpenFOAM Version | Install 2506 alongside/instead of 2312 |
| OpenFOAM Not Found | Install OpenFOAM 2506 in WSL |
| Python 3 Not Found | `sudo apt-get install -y python3` |
| Missing Python Packages | `sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2`, or accept the setup prompt |
| Package Installation Failed | Dialog names the failing component; check `%TEMP%\openfoam_ui_launcher.log` |
| Application File Missing | Keep `.exe` inside `src\app\` with all `.py` files |
| Launch Failed | Run manually in WSL and check Python errors |

| General issue | Fix |
|---|---|
| `python3: command not found` | `sudo apt-get install python3` |
| `No module named 'PyQt5'` | `sudo apt-get install python3-pyqt5` |
| `blockMesh: command not found` | Source the OpenFOAM environment first |
| Blank window | Win10: start VcXsrv/MobaXterm; Win11: should work out of the box |
| `Not found: .../constant` | Directory needs both `constant/` and `system/` |
| No files in Tab 2 table | No `.stl`/`.obj` under `constant/` |
| ParaView button does nothing | Install ParaView under `C:\Program Files\ParaView*\` |
| `Could not parse stylesheet` | Harmless Qt5 warning, suppressed automatically |

Install extra libraries: `sudo apt-get install python3-<name>` or `pip3 install <name> --break-system-packages`.

---

# Developer Guide

## Repository Layout

```
C:\OpenFOAM\
├── src\
│   ├── app\                            # Distribution ZIP — all end-user files
│   │   ├── openfoam_ui.py              # PyQt5 GUI entry point
│   │   ├── ui_shared.py                # Colour tokens, styles, shared helpers
│   │   ├── ui_landing.py                # Landing page widget
│   │   ├── ui_log_drawer.py             # Collapsible/resizable log drawer
│   │   ├── ui_background_mesh.py        # Background Mesh tab
│   │   ├── ui_snappy_hex.py             # SnappyHexMesh Dict tab
│   │   ├── snappy_generator.py          # Tab 2 backend: dict render + run
│   │   ├── defaults.json                # Default solver parameters
│   │   ├── generateBackgroundMesh.py    # CLI (do not modify)
│   │   ├── generateSnappyHexMeshDict.py # CLI (do not modify)
│   │   ├── requirements.txt
│   │   ├── openfoam_ui_launcher.py      # Launcher source
│   │   ├── OpenFOAM_UI.exe              # Launcher binary
│   │   ├── icons\
│   │   └── templates\                   # OpenFOAM dict templates
│   └── deploy\                          # Build tools — not shipped
│       ├── generate_icon.py
│       ├── openfoam_ui_launcher.spec
│       ├── version_info.txt
│       └── build_exe.bat
├── 03_mesh_session\                     # Example OpenFOAM case
├── agents\                              # Scoped subagent definitions
├── documentation\
└── CLAUDE.md                            # AI assistant guidance
```

## Architecture Overview

**Windows launcher** (`openfoam_ui_launcher.py` → `OpenFOAM_UI.exe`) — stdlib only, no bundled PyQt5/OpenFOAM. Shows splash, runs six pre-flight steps, then `python3 openfoam_ui.py` inside WSL and closes when the GUI is ready. Setup gate writes an apt-only script for missing packages. All commands target the detected distro via `wsl -d <name>`; logs to `%TEMP%\openfoam_ui_launcher.log`.

**Python application (WSL)**:
- `openfoam_ui.py` — `QMainWindow` shell: tabs, header, LogDrawer, ParaView launcher.
- `ui_shared.py` — colour/style tokens, custom widgets (`PlusMinusSpinBox`, `ChevronComboBox`), `MessageBanner` (shared red-error / green-success strip), and `scan_log_for_fix()` (maps raw OpenFOAM log signatures → plain fixes).
- `ui_landing.py` — new/open project page; recents in `~/.openfoam_ui_recents.json`; live name-sanitize, `/mnt` path conversion, From-STL template, gated footer **Open →**.
- `ui_background_mesh.py` — Tab 1; `_BgMeshWorker(QThread)` runs `surfaceCheck` → `blockMesh`. Emits `request_snappy` from its success banner to hand off to Tab 2.
- `ui_snappy_hex.py` — Tab 2; `_SnappyWorker(QThread)` calls `snappy_generator.generate_and_run()`.
- `snappy_generator.py` — renders `snappyHexMeshDict` from `templates/snappyHexMeshDict.template` (Jinja2), records inputs to `snappy_inputs.json`, streams `snappyHexMesh -overwrite`. Inner solids become faceZone + cellZone so cells are kept and named; keep-point nudged by 1e-6 off cell faces. All subprocess calls use `cwd=case_dir`, never `os.chdir()`.

See `CLAUDE.md` for full detail.

## Rebuilding the EXE

Only needed when `openfoam_ui_launcher.py` changes — other `.py` edits take effect on next launch.

```bat
cd C:\OpenFOAM\src\deploy
build_exe.bat
```

Prompts for a version number, patches `version_info.txt` + the splash label, runs PyInstaller, copies the result to `..\app\OpenFOAM_UI.exe`. Requires Python 3.9+ on Windows; PyInstaller installs automatically.

## Deployment Checklist

**Before building:** changes committed on `main`; GUI tested end-to-end (landing → Tab 1 → Tab 2 → ParaView); `defaults.json`/templates correct; `requirements.txt` matches imports; `deploy\icons\openfoam_ui.ico` present.

**Building:** run `build_exe.bat` on a clean machine; confirm `dist\OpenFOAM_UI.exe` built with no errors and was copied to `app\`.

**Packaging:** ZIP `src\app\` (exe, all `.py`, `icons\`, `defaults.json`, `requirements.txt`, `templates\`); exclude `deploy\`, `__pycache__\`, `.pyc`; smoke-test from a clean extract.

**What's bundled in the EXE:** only `openfoam_ui_launcher.py` + stdlib/tkinter. Everything else (`openfoam_ui.py`, `ui_*.py`, `snappy_generator.py`, PyQt5/numpy/jinja2, `defaults.json`) runs live from `.py` files in WSL.

## Platform Notes

- `C:\OpenFOAM` ↔ WSL `/mnt/c/OpenFOAM`
- Target OpenFOAM: **2506** (also 2312). The GUI sources whichever install it was launched under (`$WM_PROJECT_DIR`), else the newest under `/usr/lib/openfoam/` — no hardcoded version
- ParaView auto-detected at `/mnt/c/Program Files/ParaView*/bin/paraview.exe` (newest wins), path converted via `wslpath -w`
- GUI window 1100×760, centered; needs WSLg or X server
- `qInstallMessageHandler` in `openfoam_ui.py` silences harmless Qt5 stylesheet warnings
