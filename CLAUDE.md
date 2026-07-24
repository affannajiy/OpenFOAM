# CLAUDE.md

Python tooling in `src/`; example cases `Demo-01/`, `Demo-02/` (lecturer demo, keep pre-mesh). Old ANR-*/VIJ-* trees in `Archived/`.

## Environment

- Python scripts run **in WSL (Ubuntu)** — they call OpenFOAM Linux exes. Source first: `source /usr/lib/openfoam/openfoam2506/etc/bashrc` (target 2506, also 2312).
- Run from a case dir (`constant/` + `system/`); GUI scans `constant/` recursively for geometry.
- `C:\OpenFOAM` ↔ `/mnt/c/OpenFOAM`.
- Deps (WSL): `sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2`. jinja2 lazily imported (apt-hint error); everything else stdlib.
- Launch GUI: `python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py`. CLI tools: `generateBackgroundMesh.py`, `generateSnappyHexMeshDict.py`. Feature snapping always implicit — no `surfaceFeatureExtract`/`.eMesh`.

## Layout & build

- `src/app/` — shipped payload (all `*.py`, `defaults.json`, `OpenFOAM_UI.exe` + `_internal/`, `templates/`, `icons/`). `src/deploy/` — build tooling only.
- **Build** (Windows CMD in `deploy/`): `build.bat` only — prompts version, patches `version_info.txt` + launcher splash label (UTF-8 via `[IO.File]`; `Get/Set-Content` corrupt it), PyInstaller (one-dir, upx off), xcopies `dist\OpenFOAM_UI\` to `app\`, compiles installer via Inno Setup 6 ISCC. Always full chain — splash label baked into EXE. `version_info.txt` patched via `[IO.File]` + `TrimEnd()` (no trailing newline) so an unchanged-version build leaves zero git diff there — never `Get/Set-Content` (grew a blank line per build). `.py` edits (except launcher) take effect on next launch without rebuild; rebuild only to cut a Setup EXE. Icons: `generate_icon.py`.
- **Installer** (`installer.iss`): per-user, no admin, `{localappdata}\Programs\OpenFOAM-UI`; Demos → `Documents\OpenFOAM-Projects` (`onlyifdoesntexist uninsneveruninstall`, generated outputs excluded); Windows build ≥ 21362 gate in `InitializeSetup`; writes `install_info.json` (WSL `projects_dir`, UTF-8+BOM) read by `ui_landing._default_project_location()` (`utf-8-sig`). Gotcha: in `[Code]` no line may *start* with `[...]`.

## GUI files (`src/app/`)

- **`openfoam_ui_launcher.py`** — Windows exe entry (stdlib only). Splash → pre-flight checks → launches GUI via `wsl -d <distro> --exec bash -c` (`--exec` avoids double shell eval). Checks: Windows build gate → distro detect (registry `Lxss`) → WSL boot wait (90 s) → WSL1 → WSLg display + Qt probe → merged WSL probe (bashrc/python3/packages, one wsl call) → network/disk → apt-only setup → GUI present. Self-healing installs (elevated `wsl --install` etc.); UAC declined → `_manual_install_guide` with Copy Command. Optional soft ParaView check (`_check_paraview` via `_find_paraview`, globs `C:\Program Files\ParaView*\bin\paraview.exe`, newest wins) runs at the end of `_run_checks` after all required checks pass — non-blocking: if missing and not previously declined, `_choice_dialog` offers **Download ParaView** (webbrowser → paraview.org/download) or Continue; declining writes `_PARAVIEW_DECLINED_SENTINEL` (`%TEMP%\openfoam_ui_paraview_declined`) so it never nags again. Never fails launch. Fast-path sentinel `%TEMP%\openfoam_ui_checks_ok.json` skips checks (ParaView check included) after a good run; ready file `%TEMP%\openfoam_ui_ready` (env `OPENFOAM_UI_READY_FILE`) polled locally. Single-instance: `FindWindowW("OpenFOAM GUI")` → focus + exit; named mutex `Local\OpenFOAM_UI_Launcher` blocks second launcher. Logs: `%TEMP%\openfoam_ui_launcher.log`.
- **`openfoam_ui.py`** — `QMainWindow` shell (header, hero, tab pills, `QStackedWidget` 0=landing 1=utility, `LogDrawer`). No CFD logic. `QLockFile /tmp/openfoam_ui.lock` single-instance backstop. `qInstallMessageHandler` silences bogus Qt stylesheet warnings. `closeEvent` close-guard: if either tab's `is_meshing()` true → `msg_question` (default No) to stop workers + close, else keep running. Window 1280×720 default, `setMinimumSize(640,360)`. `_refresh_cwd` polls at 5 s and skips the 3 `setText`s unless the path changed; `_refresh_paraview_state` (split out, caches `has_mesh`) also fires on `status_changed` so a finished run updates instantly; `status_changed` is likewise connected to `self._snappy_widget.refresh_state()` so a run finishing while Tab 2 is visible refreshes its pre-flight checklist instantly — the polyMesh stat crosses 9p on `/mnt/c`, so never poll it faster.
- **`ui_shared.py`** — colour tokens, style constants, `PlusMinusSpinBox`, `ChevronComboBox`, `build_card`, `to_wsl_path`, `run_of_command`/`run_foam_cmd`, version detectors (feed landing ENVIRONMENT checklist — nothing hardcoded), `find_paraview_exe`. **Popups:** Weston (WSLg WM) corner-shoves top-level windows; `X11BypassWindowManagerHint` breaks focus. So popups are in-window overlays: `_PopupOverlay` (dimmed child + local `QEventLoop`) hosting `_MessageCard` or an embedded non-native `QFileDialog` (`Qt.Widget`). **Rule: every popup uses this card style — never stock Qt dialogs.** Use `msg_info/msg_warning/msg_critical/msg_question` and `pick_open_file(s)/pick_existing_dir` only. No host window yet → `_run_box_standalone` (frameless fullscreen translucent backdrop — Weston respects fullscreen). File card: stock chrome hidden (`_FILEDLG_HIDE`), `_FileCardFrame` header with path field + Up/New Folder; `_FlatIconProvider` (keep ref on dlg or GC'd); style every inner widget class explicitly (else black-on-black). Also `STYLE_TOOLTIP`, `OF_ERROR_MAP`+`scan_log_for_fix(text)` (log → jargon-free fix or None), `MessageBanner` (result strip: `show_error`/`show_success(action)`/`hide_msg`; needs `WA_StyledBackground` + STYLE_TOOLTIP).
- **`ui_landing.py`** — New/Open, recents `~/.openfoam_ui_recents.json`, emits `continue_clicked(case_dir, util_id)`. Name sanitized live; Location WSL-converted; templates Empty / From STL (STLs copied to `constant/triSurface/`); recent-delete confirms first; default Location from `install_info.json` else `~/OpenFOAM`. Responsive: `resizeEvent` flips `_hero_row` + `_cols_row` (`QBoxLayout.setDirection`) to `TopToBottom` below 900 px width — guarded by `_is_stacked` so a drag-resize only re-lays out on the flip. Env card is `setMaximumWidth(260)`, never fixed.
- **`ui_log_drawer.py`** — collapsible `LogDrawer`; thread-safe `write(msg, tag)`; `set_running` blink; `set_step` amber "Step X/3" driven by snappy phase headers.
- **`ui_background_mesh.py`** — Tab 1: STL + DX/DY/DZ; worker: `surfaceCheck` → bbox → `blockMeshDict` → `blockMesh`. Standalone — don't couple to snappy. `MessageBanner` on finish: success → "Continue to Snappy Hex Mesh →" (`request_snappy`), error → `scan_log_for_fix`. Both tabs expose `is_meshing()` for the main-window close-guard.
- **`ui_snappy_hex.py`** — Tab 2, five cards:
  - **Sec 01** file table (`constant/` recursive .stl/.obj) + standard shapes. Fixed widths (header + row must match): USE 44, SURFACE TYPE 132, CELL ZONE 104, MIN/MAX/V.LVL 80, VOL DIR 112; FILE is the only Expanding column — widen settings there. USE unticked = fully excluded. MIN/MAX/V.LVL independent 0–20, default 0 (V.LVL disabled when Vol Dir None). Smart defaults on new rows only: largest-bbox STL → Boundary; others → FaceZone+CellZone Vol Inside. Vol Dir locked None+disabled on Boundary rows. `_refresh_file_list(_preserve=True)` keeps user values across rebuilds. Auto-rescan: `QFileSystemWatcher` on `constant/`+subdirs (non-recursive → all subdirs added, `_rewatch_constant` reattaches on change/case-switch) → 600 ms debounce timer → `_refresh_file_list(_preserve=True)`, silent. Manual "Refresh file list" button kept as fallback. Table in its own h-scroll `QScrollArea`; `_resize_file_table_scroll()` scheduled via `QTimer.singleShot(0,…)`.
  - **Sec 02** unit, `nCellsBetweenLevels`, locationInMesh + Suggest point (60% centroid→max corner; blockMeshDict fallback). Coordinate pickers each in own outlined QFrame with gaps.
  - **Sec 03** static note. **Sec 04** layers + per-patch `nSurfaceLayers`. **Sec 05** Generate & Run + PRE-FLIGHT CHECK (`_refresh_preflight`: polyMesh, ≥1 Boundary, FaceZone has CellZone, location strictly inside the bbox of the largest Boundary STL — bbox test, not true point-in-solid — falling back to location ≠ 0,0,0 only when no Boundary STL parses (standard-shapes-only or binary STL)) + `MessageBanner`. Public `refresh_state()` (re-runs `_refresh_preflight` + `_refresh_mesh_actions` + `_update_time_dirs` + `_update_dict_banner`; deliberately NOT the file list, which the `QFileSystemWatcher` owns) called from a `showEvent` override — switching to Tab 2 after building the background mesh shows the pre-flight ✓ immediately (was frozen at case-open state).
  - `_collect_data()` on GUI thread (Max ≥ Min); `_SnappyWorker(QThread)` runs backend. Tooltips = canonical help; keep in sync with semantics.
- **`snappy_generator.py`** — renders `system/snappyHexMeshDict` from Jinja2 template, runs `snappyHexMesh -overwrite`. Entry: `generate_and_run(config, case_dir, log_cb)`; `validate_config` guards. locationInMesh nudged +1e-6. Writes informational `snappy_inputs.json`; removes numeric time dirs; no `os.chdir` (pass `cwd=`).

## snappyHexMesh zone semantics (critical)

- **Boundary** = outer shell; `patchInfo { type wall; inGroups (walls); }`. **Never gets a volume refinement region** (no-op or blobby edge refinement) — GUI locks it, generator skips+warns.
- **FaceZone + Cell Zone** = solid body inside domain: `faceZone`/`faceType internal` + `cellZoneInside inside`/`cellZone <name>` so interior cells kept and named. FaceZone alone discards inner cells (the "invisible inner cylinder" bug).
- `features ( )` always empty. Per-patch layers from `addLayersControls.layers`; no `fvSchemes`/`fvSolution`. `defaults.json` holds control blocks (reference-aligned, e.g. `minVol 1e-40`).
- Reference: `Archived/VIJ-03/configure_snappyHexMeshDict/`.

## Do-not-modify

`generateBackgroundMesh.py`, `generateSnappyHexMeshDict.py` (standalone CLI tools).

## Qt5 stylesheet rules (Linux/WSL)

- Plain `QWidget` subclass ignores QSS `border`/`background` without `setAttribute(Qt.WA_StyledBackground, True)`.
- `QFrame` with border/radius: `setObjectName` + scope `QFrame#name { … }`.
- No `setFrameShape(HLine)` + stylesheet — use `setFixedHeight(1)` + bg.
- Bare QSS cascades to all descendants — always scope container rules (`objectName` + `#name` + `WA_StyledBackground`).
- Checkbox ✓: QSS can't draw glyph — `image: url(icons/check_16.png)` (`ui_shared._CHECK_PNG`, forward slashes).
- `cursor:` unsupported in QSS — `setCursor()`.
- Style `:disabled` explicitly on custom widgets (`#pmsp:disabled`, `STYLE_COMBO`); `ChevronComboBox` `▼` label recolored via `changeEvent`.
- `PlusMinusSpinBox`: layout margins `(1,1,1,1)` keep buttons inside the 1px border — zero margins = corner notch.
- QSS-drawn combo arrows render broken here — use `ChevronComboBox` (real `▼` QLabel positioned in `resizeEvent`) everywhere, never bare `QComboBox`.

## Fonts

- Two tokens in `ui_shared.py`: `FONT_UI = "Helvetica"`, `FONT_MONO = "monospace"`. **Never hardcode a family** — all QSS uses `font-family: {FONT_UI}` / `{FONT_MONO}` (needs an f-string).
- Single names on purpose: fontconfig always resolves them, Qt5 QSS is unreliable with comma fallback lists. `Helvetica` → Nimbus Sans when `fonts-urw-base35` is installed (launcher apt list), else DejaVu Sans.
- Windows font names never resolve under WSL — `Segoe UI`/`Consolas` were silently substituted with DejaVu for years. Exception: `openfoam_ui_launcher.py` is Tkinter on **Windows**, so `Segoe UI` there is correct — leave it.
- Keep `FONT_MONO` a separate role (log drawer, paths, coordinate/value fields) — raw snappyHexMesh output needs fixed-width columns.

## Tooltips

- Every interactive widget has `setToolTip` — plain words, no CFD jargon. One look: `STYLE_TOOLTIP` (white bg, black text, red border).
- Qt merges a widget's own stylesheet into its tooltip, beating app-wide `QToolTip{}` — so `STYLE_TOOLTIP` is applied app-wide **and** appended to every widget-level stylesheet. Any new styled widget with a tooltip must append it too.

## Subagents (`.claude/agents/`)

Use these when developing this project — route work to the matching agent rather than editing broadly by hand:

foam-docs (docs only, never .py) · foam-ui (all GUI files) · foam-snappymesh (`snappy_generator.py`, `defaults.json`, template) · foam-backgroundmesh (`ui_background_mesh.py` only) · foam-git (commit/push GitHub+Bitbucket). Invoke: `claude --agent <name> "<task>"` (definitions live in `.claude/agents/*.md`).

## Usability (read before building UI)

Any UI change must satisfy Nielsen's heuristics as captured in [`documentation/USABILITY_HEURISTICS.md`](documentation/USABILITY_HEURISTICS.md) — consult it **first**, then build. It is the usability contract for this application.

## Platform notes

- ParaView auto-detected `/mnt/c/Program Files/ParaView*/bin/paraview.exe` (newest), `wslpath -w` before launch.
- GUI 1100×760, needs display (WSLg/X).
- Case dirs: `constant/<geometry>/`, `constant/polyMesh/`, `system/`, `programOutputs/`.
