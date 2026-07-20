# OpenFOAM Mesh Generation Utilities

A point-and-click GUI (plus CLI fallbacks) for setting up `blockMesh` and `snappyHexMesh` in ESI OpenFOAM v2506. Runs on Windows via WSL.

> **About OpenFOAM** — two independent official variants exist:
> - **ESI-OpenCFD / [openfoam.com](https://www.openfoam.com)** — source at [develop.openfoam.com](https://develop.openfoam.com/Development/openfoam). Versions like **v2506** — *this is the variant this tool targets*.
> - **OpenFOAM Foundation / [openfoam.org](https://openfoam.org)** — source at [github.com/OpenFOAM/OpenFOAM-dev](https://github.com/OpenFOAM/OpenFOAM-dev).
>
> This project is an independent tool and is not affiliated with or endorsed by either organisation.

---

# User Guide

## Quick Start

Run the installer **`OpenFOAM_UI_Setup_<version>.exe`**, then double-click the desktop shortcut. The startup window checks your environment (and fixes most problems itself), then opens the GUI.

> First run may take longer while WSL wakes up and missing pieces are installed.

**What you need:** Windows 11 (or Windows 10 build 21362+). Everything else — WSL, Ubuntu, OpenFOAM, Python packages — the launcher can detect and install for you with one click.

## Installing by Hand (optional)

Only needed if you prefer manual setup or the automatic installs are blocked:

1. **WSL + Ubuntu** — admin PowerShell: `wsl --install`, restart, then `wsl --install Ubuntu`, restart.
2. **OpenFOAM** — in the Ubuntu terminal (`wsl -d Ubuntu`):
   ```bash
   curl -s https://dl.openfoam.com/add-debian-repo.sh | sudo bash
   sudo apt-get update && sudo apt-get upgrade
   sudo apt-get install openfoam2506-default
   ```
3. **Python packages** — `sudo apt-get install python3-pyqt5 python3-numpy python3-jinja2`
   (PyQt5 = GUI, numpy = bounding-box math, jinja2 = dict templates).

**ZIP fallback** (no installer): extract the `app\` folder anywhere on a Windows drive, e.g. `C:\OpenFOAM\src\app\`. Keep all files together (`.py`, `defaults.json`, `OpenFOAM_UI.exe`, `_internal\`, `templates\`); don't include `__pycache__\`.

**Handy aliases** — add to `~/.bash_aliases` in WSL:
```bash
alias of2506="source /usr/lib/openfoam/openfoam2506/etc/bashrc"
alias openfoamUI="python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py"
```

## What the Launcher Checks

The startup window runs these in order. Most failures come with a one-click fix button:

| Check | If missing |
|---|---|
| Windows build ≥ 21362 (WSLg) | Clear "Windows too old" message |
| WSL installed | **Install WSL** button (admin prompt, optional restart) |
| Ubuntu exists | **Install Ubuntu** button + guided first-run terminal |
| WSL boots (waits up to 90 s) | **Try Again** |
| WSL2 (not WSL1) | **Convert to WSL2** button |
| WSLg display works | **Update WSL** button |
| OpenFOAM + Python packages | One consent dialog, installed via apt |
| Network / disk space | Warns before installing if blocked or low |

If an install needs admin rights you don't have, the launcher shows numbered manual steps with a **Copy Command** button — do them (or ask IT), relaunch, and it continues where it left off. Every error dialog has **Copy Details** for IT tickets. Log: `%TEMP%\openfoam_ui_launcher.log`.

---

## Using the GUI

### Landing Page

- **New project** — name + location; creates the case folders and stub dicts. Names are auto-cleaned as you type; `C:\…` paths auto-convert to WSL form. Template: *Empty case* or *From STL* (picked files are copied into `constant/triSurface/`).
- **Open existing** — browse or use recents. Removing a recent (×) asks first and never deletes the folder.
- **Environment card** — live-detected versions of OpenFOAM, ParaView, Ubuntu, Python (green = found).

Choose a utility, then click **Open →** (or double-click the utility card). **← Home** returns anytime.

### Tab 1 — Background Mesh

Builds the base grid: pick an STL, set DX/DY/DZ cell sizes (metres), click **Generate Background Mesh**. It runs `surfaceCheck`, writes `blockMeshDict`, runs `blockMesh`. Success shows a green banner with **Continue to Snappy Hex Mesh →**; failure shows a plain-language cause and fix.

### Tab 2 — SnappyHexMesh Dict

Carves your geometry out of the background mesh.

**Surface Type in plain words:**
- *Boundary* = the outer shell — the mesh stops there.
- *FaceZone + Cell Zone* = a solid part **inside** the domain — its cells are kept and named. Skip Cell Zone and those cells are thrown away (part becomes invisible). A Boundary never takes a Vol Dir — the GUI locks it.

| Section | What you set |
|---|---|
| **01 Geometry** | Table of every `.stl`/`.obj` under `constant/` + standard shapes. Per file: Use (untick to exclude), Surface Type, refinement Min/Max, Vol Dir + level. Smart defaults: biggest file → Boundary, rest → FaceZone+CellZone. **The table refreshes itself** when you add or remove files (a manual **Refresh file list** button is there too); your existing settings are kept |
| **02 Castellation** | Unit, nCellsBetweenLevels, location-in-mesh point. **Suggest point** picks one for you — verify it's in fluid, not inside a solid |
| **03 Snap** | Automatic (implicit feature snapping, nothing to configure) |
| **04 Layers** | Optional boundary layers, per-patch counts |
| **05 Generate & Run** | Live pre-flight ✓/✗ list, then renders the dict and streams the run |

> Hover anything for a tooltip — they are the built-in help.

### Log & Errors

Bottom drawer: colour-coded log, drag to resize, chevron to collapse. During snappy runs the header shows **Step X/3** (Castellating → Snapping → Adding layers). On failure, a red banner translates the raw OpenFOAM error into a plain cause and fix (bad location point, empty mesh, missing background mesh, non-watertight STL, …); the full log stays below.

### Closing While Meshing

If you try to close the window while a mesh is still running, the app asks first — choose **Yes** to stop the run and close, or **No** to keep it running. Nothing is lost by accident.

### Case Folder Rules

A case needs `constant/` (geometry in any subfolder — scanned recursively) and `system/`. Generated dicts go in `system/`, mesh in `constant/polyMesh/`.

---

## CLI Tools

Inside WSL, with OpenFOAM sourced (`of2506`):

```bash
# STL bbox → blockMeshDict → blockMesh
python3 src/app/generateBackgroundMesh.py -stlPath constant/triSurface/geo.stl -dx 0.05 -dy 0.05 -dz 0.05

# Interactive snappyHexMeshDict builder
python3 src/app/generateSnappyHexMeshDict.py
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Launcher error with a button | Click the button — most fixes are automatic |
| Admin permission needed | Follow the numbered steps in the dialog (**Copy Command**); ask IT |
| Download servers unreachable | Corporate proxy — allow archive.ubuntu.com + dl.openfoam.com or use open network |
| WSL timed out / unreachable | **Try Again**; else `wsl --shutdown` then retry, or `wsl --update` |
| Blank window | Win10: start an X server (VcXsrv); Win11: `wsl --update` |
| `blockMesh: command not found` | Source OpenFOAM first (`of2506`) |
| `No module named 'PyQt5'` (manual run) | `sudo apt-get install python3-pyqt5` |
| No files in Tab 2 table | No `.stl`/`.obj` anywhere under `constant/` |
| ParaView button does nothing | Install ParaView under `C:\Program Files\ParaView*\` |
| `Could not parse stylesheet` | Harmless Qt warning, auto-suppressed |

---

# Developer Guide

## Repository Layout

```
C:\OpenFOAM\
├── src\
│   ├── app\        # Installer payload — everything the user gets
│   │   ├── openfoam_ui.py              # GUI entry (QMainWindow shell)
│   │   ├── ui_shared.py                # Tokens, custom widgets, popups, banners
│   │   ├── ui_landing.py               # Landing page
│   │   ├── ui_log_drawer.py            # Log drawer
│   │   ├── ui_background_mesh.py       # Tab 1
│   │   ├── ui_snappy_hex.py            # Tab 2
│   │   ├── snappy_generator.py         # Tab 2 backend (Jinja2 render + run)
│   │   ├── generateBackgroundMesh.py   # CLI — do not modify
│   │   ├── generateSnappyHexMeshDict.py# CLI — do not modify
│   │   ├── openfoam_ui_launcher.py     # Launcher source (stdlib only)
│   │   ├── OpenFOAM_UI.exe + _internal\  # Launcher binary (one-dir build)
│   │   ├── defaults.json, requirements.txt, icons\, templates\
│   └── deploy\     # Build tools (not shipped): build.bat, installer.iss,
│                   # openfoam_ui_launcher.spec, version_info.txt, generate_icon.py
├── Demo-01\, Demo-02\   # Sample cases (Demo-02: power-electronics STLs)
├── Archived\            # Old session trees (ANR-*) + reference packages (VIJ-*)
├── agents\              # Scoped subagent definitions
└── CLAUDE.md            # AI assistant guidance (full technical detail)
```

## Architecture

- **Launcher** (`OpenFOAM_UI.exe`): Windows-side, stdlib only. Splash → pre-flight checks (self-healing) → runs `python3 openfoam_ui.py` inside WSL. Nothing else is bundled — the app itself runs live from `.py` files in WSL.
- **GUI**: `openfoam_ui.py` shell; workers (`QThread`) run OpenFOAM commands; `snappy_generator.py` renders `snappyHexMeshDict` from a Jinja2 template and runs `snappyHexMesh -overwrite`. Inner solids become faceZone + cellZone so their cells are kept and named. All subprocesses use `cwd=case_dir`, never `os.chdir()`.

See `CLAUDE.md` for full detail.

## Building a Release

```bat
cd C:\OpenFOAM\src\deploy
build.bat
```

One command (~40 s): prompts a version (Enter reuses current), patches `version_info.txt` + splash label, runs PyInstaller (one-dir), copies exe + `_internal\` to `app\`, compiles `dist\OpenFOAM_UI_Setup_<version>.exe` via Inno Setup 6 (`winget install JRSoftware.InnoSetup` if missing). Always runs the full chain — the splash version is baked into the EXE.

During development, `.py` edits (except the launcher) take effect on next launch — no rebuild. Rebuild only to cut a distributable Setup EXE.

**Ship**: distribute the single `dist\OpenFOAM_UI_Setup_<version>.exe`. Smoke-test: install, shortcut launches, `Documents\OpenFOAM-Projects` has Demo-01/02, landing Location defaults there. ZIP of `src\app\` is the manual fallback.

## Platform Notes

- `C:\OpenFOAM` ↔ WSL `/mnt/c/OpenFOAM`.
- OpenFOAM target **2506** (2312 also works) — nothing hardcoded; the newest found install is used.
- ParaView auto-detected at `C:\Program Files\ParaView*\bin\paraview.exe` (newest wins).
- GUI 1100×760; needs WSLg (Win11) or an X server (Win10).

---

# License & Community

- **License**: [GPL-3.0](LICENSE) — the same license OpenFOAM itself uses (both variants). Free to use, modify, and share; derived works must stay GPL.
- **Contributing**: setup, rules, and PR flow in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security**: found a vulnerability? See [SECURITY.md](SECURITY.md) — report privately, not via public issues.
- **Conduct**: contributors follow the [Code of Conduct](CODE_OF_CONDUCT.md) (Contributor Covenant 2.1).
