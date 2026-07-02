# CLAUDE.md

Guidance for Claude Code working in this repo. Two layers: Python tooling (`01_utilities/`) and an example OpenFOAM case (`03_mesh_session/`).

## Environment

- All Python scripts run **in WSL (Ubuntu)**, not Windows CMD/PowerShell — they call OpenFOAM exes (`blockMesh`, `surfaceCheck`, `snappyHexMesh`, `foamDictionary`) that only exist in Linux.
- Source OpenFOAM first: `source /usr/lib/openfoam/openfoam2506/etc/bashrc` (target **2506**, also 2312).
- Run from inside a case dir (has both `constant/` and `system/`). Geometry subfolder in `constant/` can have any name; the GUI scans `constant/` recursively.
- Windows `C:\OpenFOAM` ↔ WSL `/mnt/c/OpenFOAM`.

## Dependencies

- WSL: `sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2` (or `pip3 install -r 01_utilities/app/requirements.txt --break-system-packages`).
- **PyQt5** (GUI), **numpy** (bbox/cell arithmetic), **jinja2** (snappy template; lazily imported with an apt-hint error so the GUI starts without it). All other imports are stdlib.

## Running

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/app/openfoam_ui.py     # GUI (recommended)
```
Landing page → create/open a project → pick a utility → Continue. CLI tools: `generateBackgroundMesh.py` (block mesh from STL bbox) and `generateSnappyHexMeshDict.py` (interactive). Feature snapping is always implicit — no `surfaceFeatureExtract`/`.eMesh`.

## Layout of `01_utilities/`

- **`app/`** — shipped to users; the distribution ZIP. All `*.py`, `defaults.json`, `requirements.txt`, `OpenFOAM_UI.exe`, `templates/`, `icons/`.
- **`deploy/`** — build tooling only (not shipped): `generate_icon.py`, `openfoam_ui_launcher.spec`, `build_exe.bat`, `version_info.txt`, `icon_source.svg`, PyInstaller artefacts.

**Building the EXE** (Windows CMD in `deploy/`): `build_exe.bat` prompts a version, patches `version_info.txt` (filevers/prodvers/FileVersion/ProductVersion) + the launcher splash label, runs PyInstaller, copies `OpenFOAM_UI.exe` to `app/`. The `.exe` is a **thin launcher** — only rebuild it when `openfoam_ui_launcher.py` changes; edits to any other `.py` take effect on next launch. ZIP the whole `app/` folder (includes `templates/`, `defaults.json`). Icons: `generate_icon.py` → `app/icons/` (16/32/48/64/128/256 PNGs + `openfoam_ui.ico`).

## GUI files (`01_utilities/app/`)

- **`openfoam_ui_launcher.py`** — Windows `.exe` entry (stdlib only). Dark splash, WSL pre-flight checks in a retry loop, then launches `openfoam_ui.py` in WSL. Targets one detected distro via `wsl -d <name> --exec bash -c` (the `--exec` prevents double shell evaluation). Checks: distro detect (registry `Lxss`) → patient WSL boot (90 s) → WSLg display + Qt compositor probe → OpenFOAM bashrc + `python3` package check (`PyQt5`, `numpy`, `jinja2`) → apt-only setup gate (no pip) → `openfoam_ui.py` present. Never asks for a Windows restart; failures end in a **Try Again** dialog. Logs to `%TEMP%\openfoam_ui_launcher.log`.
- **`openfoam_ui.py`** — `QMainWindow` shell: header bar, hero strip, tab pills, root `QStackedWidget` (0=landing, 1=utility), `LogDrawer`, status bar. No CFD logic. `qInstallMessageHandler` silences harmless Qt5 "Could not parse stylesheet" warnings.
- **`ui_shared.py`** — colour tokens, style constants, `PlusMinusSpinBox` (QSpinBox replacement), `build_card`, `positive_float`, `get_stl_zone_names`, `find_paraview_exe`, `to_wsl_path` (Windows→`/mnt/`, applied to `QFileDialog` results), `run_of_command` (streaming), `run_foam_cmd` (blocking). Also `STYLE_TOOLTIP` — the single tooltip look (white bg, black font, red rounded border); see tooltip rules below.
- **`ui_landing.py`** — `LandingWidget`; New-project / Open-existing modes; recents at `~/.openfoam_ui_recents.json`; emits `continue_clicked(case_dir, util_id)`.
- **`ui_log_drawer.py`** — `LogDrawer`; collapsible/resizable; thread-safe `write(msg, tag)` (`error`/`warn`/`info`/`cmd`); `set_running` blinking dot.
- **`ui_background_mesh.py`** — Tab 1 `BackgroundMeshWidget`: STL path + DX/DY/DZ; `_BgMeshWorker` runs `surfaceCheck` → bbox → `blockMeshDict` → `blockMesh`. Standalone; do not couple to snappy.
- **`ui_snappy_hex.py`** — Tab 2 `SnappyHexWidget`: five cards in a scroll area.
  - **Sec 01** file table (`constant/` recursive `.stl`/`.obj`): columns FILE / SURFACE TYPE / CELL ZONE / S.MIN / S.MAX / VOL DIR / V.LVL, plus standard shapes (Box/Cylinder/Sphere). Smart defaults on **new** rows (user values always win): largest-bbox STL → **Boundary** S 1/2; every other → **FaceZone + Cell Zone** S 2/2 Vol Inside V.Lvl 2. **Vol Direction is locked to None + disabled on Boundary rows** (see semantics below). `_refresh_file_list(_preserve=True)` snapshots/restores per-row values across rebuilds.
  - **Sec 02** unit, `nCellsBetweenLevels`, locationInMesh X/Y/Z + **Suggest point** (`_suggest_location_in_mesh`: 60% from largest boundary-STL centroid to its max corner; falls back to `blockMeshDict` vertices).
  - **Sec 03** static note (implicit snapping always on). **Sec 04** add-layers + per-patch `nSurfaceLayers` (auto-populated from Sec 01). **Sec 05** Generate & Run button.
  - `_collect_data()` reads widgets on the GUI thread (validates S.Max ≥ S.Min); `_SnappyWorker(QThread)` calls the backend. Tooltips are the canonical in-product help — keep in sync with semantics.
- **`snappy_generator.py`** — Tab 2 backend; renders `system/snappyHexMeshDict` in one pass from `templates/snappyHexMeshDict.template` (Jinja2), then runs `snappyHexMesh -overwrite` via `bash -c 'source <bashrc> && …'`. `generate_and_run(config, case_dir, log_cb)` is the sole entry; `validate_config` guards common mistakes. `locationInMesh` nudged `+1e-6` (`_LOCATION_OFFSET`) so it never lands on a cell face. Writes `<case>/snappy_inputs.json` (informational record; engine renders from the in-memory config). Removes numeric time dirs after run, refreshes `<case>.foam`. No `os.chdir` — all subprocess calls pass `cwd=case_dir`.

## snappyHexMesh zone semantics (critical)

- **Boundary** = outer shell / external wall; the mesh stops there. Gets `patchInfo { type wall; inGroups (walls); }`. **A Boundary shell must NOT get a volume refinement region** — a region on the domain limit is a no-op (inside) or refines the discarded padding shell into a mesh finer at the edges than at the surface (a blobby result). Both the GUI (locked Vol Dir) and `snappy_generator` (skips + warns) enforce this.
- **FaceZone + Cell Zone** = a solid body inside the domain: gets `faceZone`/`faceType internal` plus `cellZoneInside inside`/`cellZone <name>` so the interior cells are **kept and named**. FaceZone *without* Cell Zone tags faces only and discards the inner cells — this was the root cause of "inner cylinder invisible inside the cube". Mirrors Vijay's `inductor` in the reference workflow.
- `features ( )` always empty (implicit snapping). Per-patch layers rendered from `addLayersControls.layers`; `fvSchemes`/`fvSolution` not written (built-in medial-axis shrinker). `defaults.json` holds the control blocks, numbers aligned to the reference workflow (`minVol 1e-40`, etc.).
- Reference: `workflow_package/openfoam_electronics_thermal_mgmt/configure_snappyHexMeshDict/` (Vijay's `setup_snappy.py` + templates). The GUI adopts its template+JSON approach but drops trimesh/AUTO_ auto-refinement and encoding names.

## Do-not-modify

`generateBackgroundMesh.py` and `generateSnappyHexMeshDict.py` are standalone CLI tools (foamDictionary-based). The GUI uses `snappy_generator.py` independently.

## Qt5 stylesheet rules (Linux/WSL)

- `QFrame` with `border`/`border-radius`: set `setObjectName("name")` and scope as `QFrame#name { … }`. Bare-property (`background` only) is fine.
- Don't combine `setFrameShape(HLine/VLine)` with `setStyleSheet` — use `setFixedHeight(1)` + background stylesheet.
- `cursor:` in stylesheets is unsupported — use `setCursor(Qt.ArrowCursor)`.

## Tooltips

- Every interactive widget across all GUI files (`ui_snappy_hex`, `ui_background_mesh`, `ui_landing`, `ui_log_drawer`, `openfoam_ui`) has a `setToolTip` — concise, plain words (user not familiar with CFD jargon). Table column headers carry column-level help.
- Single look via `STYLE_TOOLTIP` in `ui_shared.py` (white bg, black font, red rounded border).
- **Qt cascade quirk:** Qt merges an owner widget's own stylesheet `color`/`background` into its tooltip, beating the app-wide `QToolTip{}` rule. So `STYLE_TOOLTIP` is applied app-wide (`openfoam_ui.py` `setStyleSheet`) **and** appended to every widget-level stylesheet (`ui_shared` constants loop, `PlusMinusSpinBox` `#pmsp`, header labels, combos). Any new styled widget with a tooltip must append `STYLE_TOOLTIP` too.

## Subagents (`agents/`)

| Agent | Scope |
|-------|-------|
| foam-docs | Docs only (`*.md`); never `.py` |
| foam-ui | All GUI files — wiring, navigation, workers, styling, icons, splash |
| foam-snappymesh | `snappy_generator.py` + `defaults.json` + `templates/snappyHexMeshDict.template` |
| foam-backgroundmesh | `ui_background_mesh.py` only |
| foam-git | Git ops — pre-commit, commit, push to GitHub + Bitbucket |

Invoke: `claude --agent <name> "<task>"`.

## Platform notes

- ParaView auto-detected at `/mnt/c/Program Files/ParaView*/bin/paraview.exe` (newest); path converted via `wslpath -w` before launch.
- GUI window 1100×760, centered; requires a display (WSLg or X server).
- Case dirs: `constant/<geometry>/` (STL/OBJ inputs), `constant/polyMesh/` (blockMesh output), `system/` (all dicts), `programOutputs/` (logs).
</content>
</invoke>
