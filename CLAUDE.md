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
sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2
```

Or via pip:
```bash
pip3 install -r 01_utilities/requirements.txt --break-system-packages
```

Third-party libraries used:
- **PyQt5** — GUI framework (`ui_*.py`, `openfoam_ui.py`)
- **numpy** — bounding box scaling and cell-count arithmetic (`generateBackgroundMesh.py`)
- **jinja2** — Jinja2 template rendering for `snappyHexMeshDict` and `blockMeshDict` (`setup_snappy.py`); if missing, `_SETUP_OK = False` and the GUI shows an error label in Section 05
- **trimesh** — optional; used only by `auto_refinement.py` for `AUTO_`-prefixed STL files; guarded by `_DEPS_AVAILABLE` flag

All other imports (`os`, `sys`, `subprocess`, `re`, `argparse`, `glob`, `typing`) are Python standard library.

## Running the Tools

**GUI application (recommended):**
```bash
cd /mnt/c/OpenFOAM/03_mesh_session
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```

**CLI: generate background block mesh from STL bounding box:**
```bash
python3 01_utilities/generateBackgroundMesh.py \
  -stlPath constant/triSurface/geom.stl \
  -dx 0.05 -dy 0.05 -dz 0.05
```

**CLI: interactive snappyHexMeshDict generator:**
```bash
python3 01_utilities/generateSnappyHexMeshDict.py
```

**Full mesh generation workflow (after background mesh is ready):**
```bash
surfaceFeatureExtract
snappyHexMesh -overwrite
```

## Architecture

The project has two layers: Python tooling (`01_utilities/`) and an example OpenFOAM case (`03_mesh_session/`).

### Python Tooling (`01_utilities/`)

The GUI is split across multiple files to keep each file focused and testable in isolation.

**`openfoam_ui.py`** — PyQt5 `QMainWindow` entry point. Thin shell: builds the header bar, hero strip, tab pills, `QStackedWidget`, `LogDrawer`, and status bar. Owns tab-switching logic and the Open ParaView action. No CFD logic here.

Key layout (top to bottom, fixed heights except the stack):
- **Header bar** (52 px, `#1A1A1A`): logo swatch, app name, CWD basename, tab pills, separator, Open ParaView
- **Hero strip** (80 px, `#F4F4F4`): eyebrow + title + subtitle per active tab; WORKING DIR badge on the right
- **QStackedWidget** (stretches): holds `BackgroundMeshWidget` and `SnappyHexWidget`
- **LogDrawer**: collapsible/resizable; drag its bottom grip upward to resize; starts expanded at 350 px
- **Status bar** (24 px, `#1A1A1A`): blinking status dot + text; CWD path

**`ui_shared.py`** — Colour tokens, style-sheet constants, and shared helpers:
- Colour tokens: `KS_RED`, `BG_APP`, `BG_CARD`, `LOG_BG`, etc.
- Style sheets: `STYLE_BTN_PRIMARY`, `STYLE_BTN_GHOST`, `STYLE_ENTRY`, `STYLE_SPINBOX`, `STYLE_COMBO`, `STYLE_CHECKBOX`, `STYLE_SCROLL`
- `build_card(section_label, title)` → `(QFrame, QVBoxLayout)` — standard white card with FAFAFA header
- `positive_float(value)` — returns `float` if strictly positive, else `None`
- `get_stl_zone_names(path)` — parses ASCII STL `solid` names
- `find_paraview_exe()` — scans `/mnt/c/Program Files/ParaView*/bin/paraview.exe`
- `run_of_command(cmd, cwd, log_cb)` — streaming `Popen`; merges stderr into stdout; returns exit code
- `run_foam_cmd(cmd, cwd, log_cb)` — blocking `capture_output=True`; logs stderr only on failure

**`ui_log_drawer.py`** — `LogDrawer(QWidget)`:
- Collapsible (chevron button) and resizable (drag the 8 px grip at the bottom upward); starts expanded at 350 px
- `write(message, tag)` — thread-safe; emits `_append_sig` which is handled on the main thread
- `set_running(bool)` — starts/stops an amber blinking dot animation (QTimer)
- `status_changed` signal — connected to the main window status bar
- Colour tags: `"error"` → red, `"warn"` → amber, `"info"` → blue, `"cmd"` → grey

**`ui_background_mesh.py`** — `BackgroundMeshWidget(QWidget)` (Tab 1):
- Card A: STL file path + Browse (infers case root from `constant/` in the path, offers `os.chdir`)
- Card B: DX / DY / DZ grid resolution inputs
- Overwrite banner: warns when `system/blockMeshDict`, log files, or `constant/polyMesh/` will be replaced
- Cancel button: terminates a running worker **and** clears all input fields
- `_BgMeshWorker(QThread)`: runs `surfaceCheck` → parses bbox → writes `blockMeshDict` → `blockMesh` → removes stale `.foam` files → creates `<case_name>.foam`

**`ui_snappy_hex.py`** — `SnappyHexWidget(QWidget)` (Tab 2):
- CWD slim bar (40 px) with Change button
- Five section cards (01–05) in a `QScrollArea`
- Section 01: file table with columns FILE / SURFACE TYPE / S.MIN / S.MAX / VOL DIR / V.LVL per STL row
- Section 02: geometry unit (mm/m/cm/µm/in/ft), nCellsBetweenLevels, location-in-mesh X Y Z
- Section 03: implicit feature snapping checkbox
- Section 04: add-layers checkbox + per-patch nSurfaceLayers spinboxes (auto-populated from Section 01 surface selections)
- Section 05: Generate + Run buttons; shows backend-unavailable warning if jinja2 is missing
- `_collect_data()` — reads all widget values on the GUI thread before handing a plain `dict` to a worker (thread-safety pattern)
- `_GenerateWorker(config, sys_dir, cwd)` — calls `generate_snappy_dict_from_config()`; catches both `SystemExit` and `Exception`
- `_RunSnappyWorker` — removes old time directories, streams `snappyHexMesh`, refreshes `.foam` file

**`setup_snappy.py`** — Core config merging, validation, and Jinja2 rendering:
- `deep_merge(base, override)` — recursive dict merge; lists are replaced, not combined
- `load_snappy_config(config_path)` — loads a JSON config file and merges with `defaults.json`
- `load_geometry_files(config)` — walks `constant/` recursively to locate each geometry file; accepts any subfolder name
- `process_geometry()`, `resolve_surface_handling()`, `resolve_volume_refinement()` — build the geometry, surface, and volume refinement data structures for the template
- `render_template(name, context)` — renders a Jinja2 template from `templates/`
- `generate_snappy_dict_from_config(config, sys_dir, log_cb, cwd=None)` — GUI entry point; temporarily `os.chdir(cwd)` for relative path resolution, then calls `_do_generate()`; restores CWD in `finally`
- `_do_generate(config, sys_dir, log_cb)` — wraps all validators in `try/except SystemExit` and re-raises as `RuntimeError` so worker threads can catch it cleanly
- `_write_layer_fv_files(sys_dir, log_cb)` — writes `fvSchemes` / `fvSolution` for `displacementMotionSolver` when `addLayers=true`
- `_SETUP_OK` / `_SETUP_ERR` — set at import time; `False` if jinja2 is not installed

**`encoding_utils.py`** — Filename encoding/decoding helpers:
- `build_tags()` — returns the prefix token dict from `defaults.json` (`encodingConvention`)
- `decode_surf_tag(filename)` — parses `SURF_BND/FZ/CZ_L<min>_L<max>_...` tokens from a filename
- `vol_direction()` — parses `VOL_IN/OUT_L<n>` tokens
- `empty_encoded_result()` — returns a zeroed result dict for unencoded filenames

**`auto_refinement.py`** — Optional AUTO_ geometry analysis (requires trimesh):
- `_DEPS_AVAILABLE` — `True` only when trimesh and numpy are both importable
- `parse_auto_encoded_name(filename)` — reads `AUTO_` prefix and any override tokens
- `compute_auto_levels_for_geometry(stl_path, params)` — loads mesh via trimesh, measures feature angles and gap sizes, calls `derive_snappy_levels()` to produce per-surface refinement levels
- `validate_auto_refinement_params(params)` — checks that `autoRefinementParams` values are sane

**`defaults.json`** — Default values for all snappyHexMesh controls:
- `encodingConvention` — prefix tokens (`SURF`, `VOL`, `BND`, `FZ`, `CZ`)
- `castellatedMeshControls`, `snapControls`, `addLayersControls`, `meshQualityControls` — standard OpenFOAM defaults
- `settings` — `extractRefinementFromNames`, `addLayers`, `mergeTolerance`
- `backgroundMesh.enlargementFactor` — 1.1× padding applied to STL bounding box
- `autoRefinementParams` — parameters for `AUTO_` trimesh analysis

**`templates/snappyHexMeshDict.template`** — Jinja2 template for `snappyHexMeshDict`:
- Full OpenFOAM dictionary; all values injected from the merged config dict
- `addLayersControls.layers` iterates `addLayersControls.layers.items()` — empty dict produces no output

**`templates/blockMeshDict.template`** — Jinja2 template for `blockMeshDict`:
- Injects `xMin/xMax/yMin/yMax/zMin/zMax/nx/ny/nz` from `compute_block_mesh_params()`

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
- **Jinja2 template rendering**: `snappyHexMeshDict` and `blockMeshDict` are rendered from `templates/` via `setup_snappy.render_template()`. The GUI builds a merged config dict (`defaults.json` + widget overrides via `deep_merge()`) and passes it as the Jinja2 context in one shot — no `foamDictionary` subprocess calls
- **JSON config merging**: `deep_merge(base, override)` merges defaults with GUI-collected values. Lists replace (not extend) their base counterparts. GUI-only keys (`geometry`, `surfaceHandling`, `volumeRefinement`) are added only when the user has configured them
- **Graceful dependency handling**: `setup_snappy.py` and `auto_refinement.py` wrap optional imports in `try/except`; `_SETUP_OK` / `_DEPS_AVAILABLE` flags allow the module to load even when jinja2 or trimesh are absent, with a user-visible error surfaced in the GUI
- **CWD management for relative paths**: `generate_snappy_dict_from_config()` temporarily `os.chdir(cwd)` so that `load_geometry_files()` can resolve `constant/` relative paths; CWD is always restored in a `finally` block
- **SystemExit in threads**: validators in `setup_snappy.py` call `sys.exit()` on bad input. `_do_generate()` catches `SystemExit` and re-raises as `RuntimeError` so worker threads can handle it without killing the process
- **Do not modify the CLI scripts**: `generateBackgroundMesh.py` and `generateSnappyHexMeshDict.py` are standalone tools; the GUI uses the new Jinja2-based backend (`setup_snappy.py`) independently

### OpenFOAM Case Layout (`03_mesh_session/`)

Standard OpenFOAM case structure:
- `constant/<geometry-folder>/` — input STL/OBJ geometry files (subfolder name is flexible; GUI scans all of `constant/` recursively)
- `constant/polyMesh/` — generated mesh (output of `blockMesh`)
- `system/` — all configuration dictionaries (`blockMeshDict`, `snappyHexMeshDict`, `controlDict`, `fvSchemes`, `fvSolution`)
- `programOutputs/` — captured log files from mesh tool runs

## Platform Notes

- Windows path `C:\OpenFOAM` maps to WSL path `/mnt/c/OpenFOAM`
- ParaView is detected at runtime by scanning `/mnt/c/Program Files/ParaView*/bin/paraview.exe` (picks the newest version found); path is converted to Windows UNC format via `wslpath -w` before launching
- Target OpenFOAM version: **2506** (also compatible with 2312)
- The GUI window is 1100×760, centered on the primary screen, and requires a display (run from a WSL terminal with an X server or WSLg)
