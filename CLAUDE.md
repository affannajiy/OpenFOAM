# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Requirements

All Python scripts must be run from within WSL (Ubuntu) — **not** Windows CMD/PowerShell — because they invoke OpenFOAM executables (`blockMesh`, `surfaceCheck`, `foamDictionary`, `snappyHexMesh`, `surfaceFeatureExtract`) that only exist in the Linux environment.

Before running any script, the OpenFOAM environment must be sourced:
```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
```

Scripts must be run from inside an OpenFOAM case directory (e.g., `03_mesh_session/`), since they write output files to `system/` and read geometry from `constant/` relative to the current working directory. A valid case root must contain both a `constant/` folder and a `system/` folder; the geometry subfolder inside `constant/` (e.g. `triSurface`, `geometry`, `surfaces`) may have any name.

## Python Dependencies

Install in WSL:
```bash
sudo apt-get install -y python3-pyqt5 python3-numpy
```

Or via pip:
```bash
pip3 install -r 01_utilities/app/requirements.txt --break-system-packages
```

Third-party libraries used:
- **PyQt5** — GUI framework (`ui_*.py`, `openfoam_ui.py`)
- **numpy** — bounding box scaling and cell-count arithmetic (`generateBackgroundMesh.py`)

All other imports (`os`, `sys`, `subprocess`, `re`, `argparse`, `glob`, `typing`, `json`, `shutil`) are Python standard library.

## Running the Tools

**GUI application (recommended):**
```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/app/openfoam_ui.py
# Landing page opens — create or open a project, choose a utility, then Continue →
```

**CLI: generate background block mesh from STL bounding box:**
```bash
python3 01_utilities/app/generateBackgroundMesh.py \
  -stlPath constant/triSurface/geom.stl \
  -dx 0.05 -dy 0.05 -dz 0.05
```

**CLI: interactive snappyHexMeshDict generator:**
```bash
python3 01_utilities/app/generateSnappyHexMeshDict.py
```

**Full mesh generation workflow (after background mesh is ready):**
```bash
surfaceFeatureExtract
snappyHexMesh -overwrite
```

## Architecture

The project has two layers: Python tooling (`01_utilities/`) and an example OpenFOAM case (`03_mesh_session/`).

`01_utilities/` is split into two subfolders:
- **`app/`** — everything distributed to end users: all `*.py` app files, `defaults.json`, `requirements.txt`, `OpenFOAM_UI.exe`, `templates/`, and `icons/`. This folder is the distribution ZIP.
- **`deploy/`** — build tooling only (not shipped): `generate_icon.py`, `openfoam_ui_launcher.spec`, `build_exe.bat`, `version_info.txt`, `icon_source.svg`, and the PyInstaller `build/`/`dist/` artefacts.

**Icon sizes** (`deploy/generate_icon.py` → `app/icons/`):

| File | Size | Used by |
|------|------|---------|
| `icon_16.png` | 16×16 | Windows system / Explorer small |
| `icon_32.png` | 32×32 | Windows system standard |
| `icon_48.png` | 48×48 | Windows Explorer list/detail |
| `icon_64.png` | 64×64 | Splash screen image |
| `icon_128.png` | 128×128 | High-DPI / macOS |
| `icon_256.png` | 256×256 | Qt window icon (`QIcon`) |
| `openfoam_ui.ico` | all 6 sizes | Embedded in `OpenFOAM_UI.exe` |

**Building the EXE** (Windows CMD from `deploy/`):
```bat
build_exe.bat
```
This runs `generate_icon.py` → PyInstaller → copies `OpenFOAM_UI.exe` to `app/`.

### Python Tooling (`01_utilities/app/`)

The GUI is split across multiple files to keep each file focused and testable in isolation.

**`openfoam_ui_launcher.py`** — Windows-only `.exe` entry point (built with PyInstaller via `openfoam_ui_launcher.spec`). Stdlib only (`tkinter`, `subprocess`, `sys`, `os`, `time`). Shows a dark branded splash window, runs six pre-flight checks (WSL reachable, WSLg display, OpenFOAM bashrc, python3, required packages, `openfoam_ui.py` present), then launches `openfoam_ui.py` inside WSL via `subprocess.Popen` and immediately closes the splash. Required packages checked: `PyQt5`, `numpy`. If check 3 finds OF v2312 but not v2506, it surfaces a version-mismatch error with specific install instructions. The `.exe` is a thin launcher only — all application logic runs in WSL. Do not rebuild the `.exe` unless `openfoam_ui_launcher.py` itself changes; edits to any other `.py` file take effect immediately on the next launch.

**`openfoam_ui.py`** — PyQt5 `QMainWindow` entry point. Thin shell: builds the header bar, hero strip, tab pills, `QStackedWidget`, `LogDrawer`, and status bar. Owns tab-switching logic and the Open ParaView action. No CFD logic here.

Window title bar / taskbar icon is `openfoam_ui.ico` (multi-size; OS picks the right resolution). A module-level `qInstallMessageHandler` (installed before `QApplication` is created) silences Qt5's harmless `"Could not parse stylesheet"` warnings. These are false positives emitted by `QFrame` widgets with `border-radius` inside `QScrollArea` hierarchies on Linux/WSL — the styles are applied correctly despite the warning. All other Qt diagnostics are forwarded to `stderr` unchanged.

Key layout (top to bottom, fixed heights except the stack):
- **Header bar** (52 px, `#1A1A1A`): ← Home button (hidden on landing page), 20×20 `icon_32.png` logo (scaled `QLabel`), app name, CWD basename, tab pills, separator, Open ParaView
- **Root `QStackedWidget`**: index 0 = `LandingWidget`; index 1 = utility UI (hero + tab stack + log)
- **Hero strip** (80 px, `#F4F4F4`): eyebrow + title + subtitle per active tab; WORKING DIR badge on the right
- **Tab `QStackedWidget`** (stretches): holds `BackgroundMeshWidget` and `SnappyHexWidget`
- **LogDrawer**: collapsible/resizable; drag its bottom grip upward to resize; starts expanded at 350 px
- **Status bar** (24 px, `#1A1A1A`): blinking status dot + text; CWD path

**`ui_shared.py`** — Colour tokens, style-sheet constants, and shared helpers:
- Colour tokens: `KS_RED`, `KS_RED_DARK`, `KS_RED_LT`, `KS_BLACK`, `BG_APP`, `BG_CARD`, `BG_SUBTLE`, `LOG_BG`, etc.
- Style sheets: `STYLE_BTN_PRIMARY`, `STYLE_BTN_GHOST`, `STYLE_BTN_SMALL_GHOST`, `STYLE_BTN_SMALL_RED`, `STYLE_ENTRY`, `STYLE_ENTRY_MONO`, `STYLE_SPINBOX`, `STYLE_COMBO`, `STYLE_CHECKBOX`, `STYLE_SCROLL`
- `PlusMinusSpinBox(QWidget)` — custom integer spin box with explicit − and + buttons; drop-in QSpinBox replacement exposing `value()`, `setValue(int)`, `setRange(int, int)`, `setFixedWidth(int)`, and `valueChanged` signal; used by all level spinboxes in both tab widgets
- `build_card(section_label, title)` → `(QFrame, QVBoxLayout)` — standard white card with FAFAFA header
- `positive_float(value)` — returns `float` if strictly positive, else `None`
- `get_stl_zone_names(path)` — parses ASCII STL `solid` names
- `find_paraview_exe()` — scans `/mnt/c/Program Files/ParaView*/bin/paraview.exe`
- `to_wsl_path(p)` — converts Windows drive-letter paths (e.g. `C:\foo`) to WSL `/mnt/` equivalents; called on any path returned by `QFileDialog` which may use Windows format under WSLg
- `run_of_command(cmd, cwd, log_cb)` — streaming `Popen`; merges stderr into stdout; returns exit code
- `run_foam_cmd(cmd, cwd, log_cb)` — blocking `capture_output=True`; logs stderr only on failure

**`ui_landing.py`** — `LandingWidget(QWidget)` — full-window landing page shown before any utility tab:
- Placed at index 0 of `MainWindow._root_stack`; emits `continue_clicked(case_dir, util_id)` when Continue is pressed
- Two modes via segmented control: **New project** (name + location + template + folder preview) and **Open existing** (browse + recents list with × delete)
- Recents stored at `~/.openfoam_ui_recents.json` (max 10); helpers `_load_recents` / `_save_recents` / `_prepend_recent`
- `_make_recent_row(entry)` → `QFrame` with objectName `"recent_row"` and scoped `QFrame#recent_row { }` stylesheet (required to avoid Qt5 Linux parse errors — see Qt5 Stylesheet Rules below)
- `_rebuild_recents_list()` — clears and repopulates the recents scroll area; called on delete and on mode switch
- `_build_utility_card(body)` — two clickable `QFrame` utility selectors (objectName-scoped) + environment status dots
- `_style_util_card(card, selected)` — toggles card border/background between unselected and KS_RED selected state
- New project creation writes stub `controlDict`, `fvSchemes`, `fvSolution` via `_write_stub()`

**`ui_log_drawer.py`** — `LogDrawer(QWidget)`:
- Collapsible (chevron button) and resizable (drag the 8 px grip at the bottom upward); starts expanded at 350 px
- Toolbar button order (left to right): **[Copy]** **[Clear]** **[▲/▼]** — Copy and Clear are shown/hidden together using `setVisible`; both hidden when the log is empty, shown once content is appended
- `write(message, tag)` — thread-safe; emits `_append_sig` which is handled on the main thread; normalises each message to end with exactly one `\n` before insertion so line counts are accurate
- `set_running(bool)` — starts/stops an amber blinking dot animation (QTimer)
- `status_changed` signal — connected to the main window status bar
- Colour tags: `"error"` → red, `"warn"` → amber, `"info"` → blue, `"cmd"` → grey

**`ui_background_mesh.py`** — `BackgroundMeshWidget(QWidget)` (Tab 1):
- Card A: STL file path + Browse (infers case root from `constant/` in the path, offers `os.chdir`)
- Card B: DX / DY / DZ grid resolution inputs
- Overwrite banner: warns when `system/blockMeshDict`, log files, or `constant/polyMesh/` will be replaced
- Cancel button: terminates a running worker **and** clears all input fields
- `set_case_dir(case_dir)` — public method called by `MainWindow.show_utility()` when the user picks a project on the landing page
- `_GBM_AVAILABLE` flag — `True` if `generateBackgroundMesh.py` is importable; if `False`, bbox is parsed via inline regex fallback so the tab still works
- `_BgMeshWorker(QThread)`: runs `surfaceCheck` → parses bbox → writes `blockMeshDict` → `blockMesh` → removes stale snappy time directories and `.foam` files → creates `<case_name>.foam`

**`ui_snappy_hex.py`** — `SnappyHexWidget(QWidget)` (Tab 2):
- CWD slim bar (40 px) with Change button
- Five section cards (01–05) in a `QScrollArea`
- Section 01: file table scanning `constant/` recursively for `.stl` and `.obj` files; columns FILE / SURFACE TYPE / CELL ZONE / S.MIN / S.MAX / VOL DIR / V.LVL per file row; plus a `PlusMinusSpinBox` to add **standard shapes** (Box / Cylinder / Sphere) with coordinate inputs and vol direction/level rendered inline per shape
  - Surface Type dropdown: None / Boundary / FaceZone
  - Cell Zone checkbox: enabled only when Surface Type is FaceZone; auto-unchecks when type changes away
  - V.LVL spinbox: disabled when Vol Direction is "None"
  - Section 04 layer patches auto-populate from Section 01; multi-zone STLs expand each solid name as a separate patch entry
  - `_refresh_file_list(_preserve=True)` snapshots per-row values (Surface Type, Cell Zone, S.Min, S.Max, Vol Dir, V.Lvl) keyed by filename **before** destroying widgets, then restores them after the rebuild but **before** signal connects so the restore does not fire `_refresh_layer_patches` mid-rebuild. Without this, every Refresh / Change / `set_case_dir` call silently reset Vol Dir to "None" and caused `refinementRegions` to come out empty. A transient green confirmation banner ("✓ File list refreshed — your previous settings have been restored.") is shown for 4 s via `QTimer.singleShot` whenever values were actually preserved. The initial `__init__` call passes `_preserve=False` to skip the snapshot/banner on first build.
- Section 02: geometry unit (mm/m/cm/um/in/ft), nCellsBetweenLevels, location-in-mesh X/Y/Z (`QDoubleSpinBox`) + red/green warning label + **Suggest point** button — `_suggest_location_in_mesh` first scans the largest **boundary STL** (rows with Surface Type ≠ "None") for `vertex` lines, picks the STL with the largest bbox volume, and places the point at 60 % from its centroid to its max corner. Falls back silently to `blockMeshDict` vertex parsing when no STL parses (binary STL, missing files, etc.); the fallback regex is scoped to the `vertices` block to avoid matching cell-count tuples in `blocks`. Success label reports the chosen STL plus its bounds and reminds the engineer to verify the point lies outside inner solid bodies.
- Section 03: implicit feature snapping checkbox + explicit-requires-.eMesh note
- Section 04: add-layers checkbox + per-patch nSurfaceLayers `PlusMinusSpinBox` (auto-populated from Section 01)
- Section 05: single "Generate Dict & Run snappyHexMesh" button
- **Tooltips**: every interactive widget across all five sections carries a multi-line `setToolTip()` explaining its purpose, valid choices, and common engineering pitfalls (e.g. FaceZone is for MRF/CHT interfaces only, not solid walls). Headers (FILE / SURFACE TYPE / VOL DIR) also carry tooltips. Tooltips are the canonical in-product help — keep them in sync with the dictionary semantics when changing behaviour.
- `set_case_dir(case_dir)` — public method called by `MainWindow.show_utility()`; applies `to_wsl_path()` to handle Windows paths from WSLg file dialogs, then refreshes the file list and all banners
- `_collect_data()` — reads all widget values on the GUI thread and returns the config dict for `snappy_generator.generate_and_run()`; validates S.Max ≥ S.Min; raises `ValueError` on invalid input
- `_collect_shapes()` — builds the standard shapes list; raises `ValueError` on missing/invalid coordinate fields
- `_SnappyWorker(QThread)` — calls `snappy_generator.generate_and_run()` in a thread; emits `log_signal(str, str)` and `finished_signal(bool)`

**`snappy_generator.py`** — Backend for Tab 2; generates `snappyHexMeshDict` and runs `snappyHexMesh`:
- `generate_and_run(config, case_dir, log_cb) → bool` — sole public entry point
- Writes the FoamFile header directly, then runs `foamDictionary` commands in the same sequence as `generateSnappyHexMeshDict.py` (geometry → castellatedMeshControls → features → refinementRegions → refinementSurfaces → snapControls → addLayersControls → meshQualityControls)
- All `foamDictionary` calls are wrapped in `bash -c 'source ... && foamDictionary ...'` via `["bash", "-c", cmd]` with `cwd=case_dir` — never uses `os.chdir()`
- Features block written by direct file manipulation (foamDictionary cannot write list-of-dict syntax)
- If `addLayers=True`, also writes `fvSchemes` and `fvSolution` for `displacementMotionSolver`
- Streams `snappyHexMesh` output line-by-line using `line.rstrip('\r')` (strips Windows carriage returns only, preserving trailing newlines for the log drawer)
- After `snappyHexMesh -overwrite` completes: removes numeric time directories (except `0`), refreshes `<case_name>.foam` sentinel file
- Raises `RuntimeError` if any `foamDictionary` call returns non-zero exit code

**`defaults.json`** — Default OpenFOAM solver parameters (no encoding or auto-refinement keys):
- `settings` — `addLayers`, `mergeTolerance`, `openfoamVersion`
- `castellatedMeshControls`, `snapControls`, `addLayersControls`, `meshQualityControls` — standard OpenFOAM defaults read by `snappy_generator.py` at runtime

**`generateBackgroundMesh.py`** — Standalone CLI (do not modify):
1. Calls `surfaceCheck` on the STL, parses bounding box coordinates via regex
2. Scales the box by 1.1× (padding), computes integer cell counts from dx/dy/dz
3. Writes `system/blockMeshDict`, then runs `blockMesh`

**`generateSnappyHexMeshDict.py`** — Interactive CLI (do not modify):
- Prompts for refinement levels, feature edge snapping, boundary layer parameters
- Parses ASCII STL `solid` names to enumerate surfaces
- Writes `system/snappyHexMeshDict`, `system/fvSchemes`, `system/fvSolution`
- Uses `foamDictionary` subprocess calls for dictionary manipulation

### Design Patterns

- **Subprocess-based integration**: all OpenFOAM executables are invoked via `subprocess.run` / `subprocess.Popen`; stdout/stderr is captured to the `LogDrawer` or parsed with regex
- **Thread safety**: worker threads (`QThread` subclasses) communicate with the UI exclusively via Qt signals. Widget state is read on the GUI thread in `_collect_data()` before workers start — no widget access from threads
- **Two subprocess helpers**: `run_of_command` (streaming, for long-running commands) vs `run_foam_cmd` (blocking, for quick `foamDictionary` writes that produce noisy stderr)
- **foamDictionary subprocess chain**: `snappy_generator.generate_and_run()` writes `snappyHexMeshDict` by running a sequence of `foamDictionary -add` calls (mirroring `generateSnappyHexMeshDict.py`) and then streams `snappyHexMesh -overwrite`. Each call is wrapped in `bash -c 'source <OF_bashrc> && foamDictionary ...'` so the OpenFOAM environment is always available, regardless of how the GUI was launched. The features block (list-of-dict syntax) is injected by direct file manipulation since `foamDictionary` cannot write it.
- **No os.chdir() in snappy_generator**: all subprocess calls pass `cwd=case_dir` explicitly; the generator never changes the process working directory
- **Do not modify the CLI scripts**: `generateBackgroundMesh.py` and `generateSnappyHexMeshDict.py` are standalone tools; the GUI uses `snappy_generator.py` independently
- **Qt5 Stylesheet Rules (Linux/WSL)** — Qt5 on Ubuntu generates `Could not parse stylesheet of object QFrame(...)` warnings in two situations:
  1. `setFrameShape(QFrame.HLine/VLine)` combined with `setStyleSheet()` on the same `QFrame` — fix: remove `setFrameShape`; use `setFixedHeight(1)` + background-only stylesheet instead
  2. `QFrame { border: ...; border-radius: ...; }` (bare type selector, no objectName) — fix: always call `setObjectName("name")` and scope the rule as `QFrame#name { ... }`. A single property like `background` only is safe without scoping; adding `border` or `border-radius` requires scoping
  - `cursor: default;` in `QPushButton:disabled` stylesheets is unsupported on Linux Qt5 — use `setCursor(Qt.ArrowCursor)` via Python API instead
  - Bare property stylesheets (no type selector) are safe on `QLabel` and `QPushButton` but should be avoided on `QFrame`

### OpenFOAM Case Layout (`03_mesh_session/`)

Standard OpenFOAM case structure:
- `constant/<geometry-folder>/` — input STL/OBJ geometry files (subfolder name is flexible; GUI scans all of `constant/` recursively)
- `constant/polyMesh/` — generated mesh (output of `blockMesh`)
- `system/` — all configuration dictionaries (`blockMeshDict`, `snappyHexMeshDict`, `controlDict`, `fvSchemes`, `fvSolution`)
- `programOutputs/` — captured log files from mesh tool runs

## Subagents

Five scoped subagents are defined in `/agents/`. Each agent owns a specific slice of the
codebase and has explicit forbidden-file lists to prevent cross-contamination.

| Agent | Scope |
|-------|-------|
| foam-docs | Documentation only (`*.md`); never modifies `.py` files |
| foam-ui | All GUI files — wiring, navigation, workers, visual design, styling, icons, splash screen |
| foam-snappymesh | `snappy_generator.py` + `defaults.json` |
| foam-backgroundmesh | `ui_background_mesh.py` only |
| foam-git | Git operations — pre-commit checks, commit authoring, push to GitHub and Bitbucket |

> `foam-design` has been merged into `foam-ui`.

### Invoking a subagent

From the project root in Claude Code:
```
claude --agent foam-snappymesh "fix the refinementRegions entry for faceZone surfaces"
claude --agent foam-ui "fix Section 04 not refreshing when Section 01 changes"
claude --agent foam-ui "update the splash screen icon"
claude --agent foam-git "commit the latest UI changes and push to both remotes"
```

### Agent file location
`/mnt/c/OpenFOAM/agents/`  (Windows: `C:\OpenFOAM\agents\`)

## Platform Notes

- Windows path `C:\OpenFOAM` maps to WSL path `/mnt/c/OpenFOAM`
- ParaView is detected at runtime by scanning `/mnt/c/Program Files/ParaView*/bin/paraview.exe` (picks the newest version found); path is converted to Windows UNC format via `wslpath -w` before launching
- Target OpenFOAM version: **2506** (also compatible with 2312)
- The GUI window is 1100×760, centered on the primary screen, and requires a display (run from a WSL terminal with an X server or WSLg)
