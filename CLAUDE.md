# CLAUDE.md

Guidance for Claude Code working in this repo. Two layers: Python tooling (`src/`) and an example OpenFOAM case (`03_mesh_session/`).

## Environment

- All Python scripts run **in WSL (Ubuntu)**, not Windows CMD/PowerShell — they call OpenFOAM exes (`blockMesh`, `surfaceCheck`, `snappyHexMesh`, `foamDictionary`) that only exist in Linux.
- Source OpenFOAM first: `source /usr/lib/openfoam/openfoam2506/etc/bashrc` (target **2506**, also 2312).
- Run from inside a case dir (has both `constant/` and `system/`). Geometry subfolder in `constant/` can have any name; the GUI scans `constant/` recursively.
- Windows `C:\OpenFOAM` ↔ WSL `/mnt/c/OpenFOAM`.

## Dependencies

- WSL: `sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2` (or `pip3 install -r src/app/requirements.txt --break-system-packages`).
- **PyQt5** (GUI), **numpy** (bbox/cell arithmetic), **jinja2** (snappy template; lazily imported with an apt-hint error so the GUI starts without it). All other imports are stdlib.

## Running

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py     # GUI (recommended)
```
Landing page → create/open a project → pick a utility → Continue. CLI tools: `generateBackgroundMesh.py` (block mesh from STL bbox) and `generateSnappyHexMeshDict.py` (interactive). Feature snapping is always implicit — no `surfaceFeatureExtract`/`.eMesh`.

## Layout of `src/`

- **`app/`** — shipped to users; the distribution ZIP. All `*.py`, `defaults.json`, `requirements.txt`, `OpenFOAM_UI.exe`, `templates/`, `icons/`.
- **`deploy/`** — build tooling only (not shipped): `generate_icon.py`, `openfoam_ui_launcher.spec`, `build_exe.bat`, `version_info.txt`, `icon_source.svg`, PyInstaller artefacts.

**Building the EXE** (Windows CMD in `deploy/`): `build_exe.bat` prompts a version, patches `version_info.txt` (filevers/prodvers/FileVersion/ProductVersion) + the launcher splash label, runs PyInstaller, copies `OpenFOAM_UI.exe` to `app/`. The `.exe` is a **thin launcher** — only rebuild it when `openfoam_ui_launcher.py` changes; edits to any other `.py` take effect on next launch. ZIP the whole `app/` folder (includes `templates/`, `defaults.json`). Icons: `generate_icon.py` → `app/icons/` (16/32/48/64/128/256 PNGs + `openfoam_ui.ico`).

## GUI files (`src/app/`)

- **`openfoam_ui_launcher.py`** — Windows `.exe` entry (stdlib only). Dark splash, WSL pre-flight checks in a retry loop, then launches `openfoam_ui.py` in WSL. Targets one detected distro via `wsl -d <name> --exec bash -c` (the `--exec` prevents double shell evaluation). Checks: Windows build gate (≥21362 for WSLg) → distro detect (registry `Lxss`) → patient WSL boot (90 s) → WSL1 detect → WSLg display + Qt compositor probe → OpenFOAM bashrc + `python3` package check (`PyQt5`, `numpy`, `jinja2`) → network (`bash /dev/tcp`, no curl dep) + disk-space probes → apt-only setup gate (no pip) → `openfoam_ui.py` present. **Self-healing:** missing WSL → elevated `wsl --install --no-distribution` via `_run_elevated` (PowerShell `Start-Process -Verb RunAs`) + optional one-time Restart Now offer (`shutdown /r /t 5` — the only allowed restart ask); no distro → `wsl --install -d Ubuntu --no-launch` + guided first-run terminal (polls `ls /home` non-empty = account created); WSL1 → `wsl --set-version <d> 2`; missing display env → `wsl --update` + shutdown. UAC declined / no admin rights (`_is_uac_declined`: "canceled by the user"/0x800704C7 in elevated output) or install failure → `_manual_install_guide`: numbered steps (ask IT → admin PowerShell → exact command → restart → relaunch resumes), **Copy Command** button (`copy_cmd=` on `_choice_dialog`) + Copy Details, then launcher closes; next run re-checks and continues. Long Windows-side commands via `_run_win_streaming` (splash pumped, UTF-16 console decode via `_decode_console`). Other failures end in a **Try Again** dialog; every error dialog has **Copy Details** (`_diagnostics_report`: versions + log tail → clipboard). Logs to `%TEMP%\openfoam_ui_launcher.log`.
- **`openfoam_ui.py`** — `QMainWindow` shell: header bar, hero strip, tab pills, root `QStackedWidget` (0=landing, 1=utility), `LogDrawer`, status bar. No CFD logic. `qInstallMessageHandler` silences harmless Qt5 "Could not parse stylesheet" warnings.
- **`ui_shared.py`** — colour tokens, style constants, `PlusMinusSpinBox` (QSpinBox replacement), `ChevronComboBox` (QComboBox replacement — real `▼` QLabel child instead of a QSS-drawn arrow; see Qt5 stylesheet rules below), `build_card`, `positive_float`, `get_stl_zone_names`, `find_paraview_exe`, version detectors (`detect_openfoam_version` — `$WM_PROJECT_VERSION` then `/usr/lib/openfoam/openfoam*` glob; `detect_ubuntu_version` — `/etc/os-release`; `detect_python_version`; `detect_paraview_version` — parsed from exe path, `'?'` = found but unversioned) used by `ui_landing`'s hero meta + ENVIRONMENT checklist (green dot + real version, grey + "not found" — nothing hardcoded), `to_wsl_path` (Windows→`/mnt/`, applied to `QFileDialog` results), `run_of_command` (streaming), `run_foam_cmd` (blocking). **In-window popups:** Weston (WSLg's WM) forcibly re-places every managed top-level window at a corner one frame after it maps (even if positioned pre-show → visible flicker), and `X11BypassWindowManagerHint` avoids that but breaks input focus (unclickable boxes, app lockup). So popups are NOT top-level windows at all: `_PopupOverlay` (dimmed child widget of the main window + local `QEventLoop`) hosts either a `_MessageCard` (custom icon/title/text/buttons; Esc→No/Cancel, Enter→default) or an embedded non-native `QFileDialog` re-parented with `Qt.Widget`. Weston never sees a child widget → instantly centred, cannot lose focus or stick. All popups must go through the wrappers: `msg_info`/`msg_warning`/`msg_critical`/`msg_question` (never static or dialog-based `QMessageBox`) and `pick_open_file`/`pick_open_files`/`pick_existing_dir` (never `QFileDialog.get*`). `_run_box`/`_run_file_dialog` fall back to a real dialog only when no visible host window exists. **Modern file card:** `_run_file_dialog` strips the stock QFileDialog chrome (`_FILEDLG_HIDE` child names: sidebar, lookIn row, fileType row, toolbar buttons — hidden via `findChild`) and wraps the dialog in `_build_file_card` → `_FileCardFrame` (objectName `popupCard`): title, editable path field (Enter jumps via `directoryEntered` sync), **↑ Up** and **＋ New Folder** header buttons (the latter clicks the hidden stock `newFolderButton`). `_FileCardFrame.keyPressEvent` routes Esc→`dlg.reject()` (dialog only handles Esc when focus is inside it). Icons: `_FlatIconProvider` (QPainter-drawn flat folder/file glyphs; `.stl`/`.obj` tinted KS_RED) — keep a reference on the dlg (`dlg._icon_provider`) or it's GC'd. Every inner widget class is explicitly styled (embedded dialog otherwise inherits the system dark palette → black-on-black). Also `STYLE_TOOLTIP` — single tooltip look (white bg, black font, red rounded border); see tooltip rules. **`OF_ERROR_MAP` + `scan_log_for_fix(text)`** — scans raw OpenFOAM log for known signatures (locationInMesh, `selected 0 cells`, missing blockMeshDict, jinja2, negative volume, `FOAM FATAL ERROR`, …) → jargon-free fix or `None`. **`MessageBanner(QWidget)`** — reusable result strip above the log in both tabs: `show_error(msg)` (red ✕), `show_success(msg, action_label=None, action_cb=None)` (green ✓ + optional button), `hide_msg()`. Needs `WA_StyledBackground` + appends `STYLE_TOOLTIP`.
- **`ui_landing.py`** — `LandingWidget`; New/Open modes; recents at `~/.openfoam_ui_recents.json`; emits `continue_clicked(case_dir, util_id)`. Footer **Open →** gated by `_update_continue_state` (project+utility valid; double-click card also works). Name live-sanitized via `textEdited` (`_sanitize_name`, junk→`_`). Location `to_wsl_path`-converted (`C:\…`→`/mnt/…`; non-`/` rejected). Template = **Empty** or **From STL** (dead "Copy" removed); From STL → inline multi-file picker (`_browse_stls`→`self._stl_files`) copied to `constant/triSurface/` in `_on_continue`. Recent-entry × now confirms via `QMessageBox.question` before removal (`_on_recent_delete`; folder itself untouched).
- **`ui_log_drawer.py`** — `LogDrawer`; collapsible/resizable; thread-safe `write(msg, tag)` (`error`/`warn`/`info`/`cmd`); `set_running` blinking dot; `set_step(text)` amber "Step X/3: …" label next to OUTPUT LOG (empty string hides it) — driven by `ui_snappy_hex._collect_log` matching snappyHexMesh's own phase headers ("Castellating mesh"/"Snapping mesh"/"Adding layers", case-insensitive).
- **`ui_background_mesh.py`** — Tab 1 `BackgroundMeshWidget`: STL path + DX/DY/DZ; `_BgMeshWorker` runs `surfaceCheck` → bbox → `blockMeshDict` → `blockMesh`. Standalone; do not couple to snappy. On finish shows a `MessageBanner`: green success carries a **Continue to Snappy Hex Mesh →** action (emits `request_snappy`, wired in `openfoam_ui.py` to `_switch_tab(1)`); red error shows `scan_log_for_fix` result (worker lines collected into `self._run_log`, success/error decided by last `status_changed` colour).
- **`ui_snappy_hex.py`** — Tab 2 `SnappyHexWidget`: five cards in a scroll area.
  - **Sec 01** file table (`constant/` recursive `.stl`/`.obj`): columns USE / FILE / SURFACE TYPE / CELL ZONE / MIN / MAX / VOL DIR / V.LVL (header + tooltip + error text say `Min`/`Max`, not `S.Min`/`S.Max`), plus standard shapes (Box/Cylinder/Sphere). Fixed column widths (header cell + row widget must match): USE 44, SURFACE TYPE 132, CELL ZONE 104, MIN/MAX/V.LVL pickers 80, VOL DIR 112. FILE is the only `Expanding` column so it absorbs slack and shrinks when the setting columns grow — widen settings there, don't touch FILE. **USE checkbox** — unticked fully excludes the file (skipped in `_collect_data` and `_refresh_layer_patches`, so it never enters `geometry{}`); other row widgets disabled via `_update_use`. MIN/MAX are independent 0–20 spin boxes defaulting **0/0** and V.LVL is an independent 0–20 field defaulting **0**, matching Vijay's HTML tool (`refinementLevels: [0, 0]`, separate `volLevel`) — V.LVL is only disabled when Vol Dir = None. Smart defaults on **new** rows (user values always win): largest-bbox STL → **Boundary**; every other → **FaceZone + Cell Zone** Vol Inside. **Vol Direction is locked to None + disabled on Boundary rows** (see semantics below). `_refresh_file_list(_preserve=True)` snapshots/restores per-row values across rebuilds. The table lives in its own `QScrollArea` (`_file_table_scroll`, `widgetResizable=False`, horizontal-scroll-only) so the fixed-width columns scroll instead of clipping at the window edge; `_resize_file_table_scroll()` re-fits its height and is scheduled via `QTimer.singleShot(0, ...)` at the top of `_refresh_file_list` so it runs after every rebuild regardless of which return path fires.
  - **Sec 02** unit, `nCellsBetweenLevels`, locationInMesh X/Y/Z + **Suggest point** (`_suggest_location_in_mesh`: 60% from largest boundary-STL centroid to its max corner; falls back to `blockMeshDict` vertices). Each of the 3 coordinate pickers sits in its own outlined `QFrame` with a gap between them — flush-adjacent `PlusMinusSpinBox` borders used to merge into one bar, making it unclear which +/- belonged to which axis.
  - **Sec 03** static note (implicit snapping always on). **Sec 04** add-layers + per-patch `nSurfaceLayers` (auto-populated from Sec 01). **Sec 05** Generate & Run button + **PRE-FLIGHT CHECK** label (`_refresh_preflight`: ✓/✗ for polyMesh exists, ≥1 used Boundary row, every used FaceZone row has Cell Zone, location ≠ (0,0,0); refreshed live on row/location signals and again first thing in `_generate_and_run`).
  - `_collect_data()` reads widgets on the GUI thread (validates Max ≥ Min); `_SnappyWorker(QThread)` calls the backend. Tooltips are the canonical in-product help — keep in sync with semantics. Sec 05 also hosts a `MessageBanner` shown in `_on_run_done`: green success (ParaView hint) or red `scan_log_for_fix` result (worker lines collected into `self._run_log`).
- **`snappy_generator.py`** — Tab 2 backend; renders `system/snappyHexMeshDict` in one pass from `templates/snappyHexMeshDict.template` (Jinja2), then runs `snappyHexMesh -overwrite` via `bash -c 'source <bashrc> && …'`. `generate_and_run(config, case_dir, log_cb)` is the sole entry; `validate_config` guards common mistakes. `locationInMesh` nudged `+1e-6` (`_LOCATION_OFFSET`) so it never lands on a cell face. Writes `<case>/snappy_inputs.json` (informational record; engine renders from the in-memory config). Removes numeric time dirs after run, refreshes `<case>.foam`. No `os.chdir` — all subprocess calls pass `cwd=case_dir`.

## snappyHexMesh zone semantics (critical)

- **Boundary** = outer shell / external wall; the mesh stops there. Gets `patchInfo { type wall; inGroups (walls); }`. **A Boundary shell must NOT get a volume refinement region** — a region on the domain limit is a no-op (inside) or refines the discarded padding shell into a mesh finer at the edges than at the surface (a blobby result). Both the GUI (locked Vol Dir) and `snappy_generator` (skips + warns) enforce this.
- **FaceZone + Cell Zone** = a solid body inside the domain: gets `faceZone`/`faceType internal` plus `cellZoneInside inside`/`cellZone <name>` so the interior cells are **kept and named**. FaceZone *without* Cell Zone tags faces only and discards the inner cells — this was the root cause of "inner cylinder invisible inside the cube". Mirrors Vijay's `inductor` in the reference workflow.
- `features ( )` always empty (implicit snapping). Per-patch layers rendered from `addLayersControls.layers`; `fvSchemes`/`fvSolution` not written (built-in medial-axis shrinker). `defaults.json` holds the control blocks, numbers aligned to the reference workflow (`minVol 1e-40`, etc.).
- Reference: `workflow_package/openfoam_electronics_thermal_mgmt/configure_snappyHexMeshDict/` (Vijay's `setup_snappy.py` + templates). The GUI adopts its template+JSON approach but drops trimesh/AUTO_ auto-refinement and encoding names.

## Do-not-modify

`generateBackgroundMesh.py` and `generateSnappyHexMeshDict.py` are standalone CLI tools (foamDictionary-based). The GUI uses `snappy_generator.py` independently.

## Qt5 stylesheet rules (Linux/WSL)

- **A plain `QWidget` subclass ignores stylesheet `border`/`background` unless `setAttribute(Qt.WA_StyledBackground, True)` is set** — the box model isn't painted otherwise. This is why `PlusMinusSpinBox`'s `#pmsp` group outline was invisible no matter the border colour; child buttons/edit paint their own bg so they showed, but the outer frame did not. `PlusMinusSpinBox` uses `BORDER_STRONG` (#9CA3AF) for the outer outline + the two internal −/number/+ dividers so each picker reads as one bordered unit.
- `QFrame` with `border`/`border-radius`: set `setObjectName("name")` and scope as `QFrame#name { … }`. Bare-property (`background` only) is fine.
- Don't combine `setFrameShape(HLine/VLine)` with `setStyleSheet` — use `setFixedHeight(1)` + background stylesheet.
- **Bare QSS declarations cascade to all descendants**: `w.setStyleSheet("border-bottom: …")` on a container draws that border on every child label too (stray line through hero-strip text). Always scope container rules: `setObjectName` + `QWidget#name { … }` + `WA_StyledBackground`.
- `QCheckBox::indicator:checked` can't draw a ✓ glyph in QSS — `image: url(icons/check_16.png)` (pre-rendered white tick, generated once; also `check_32.png`). Path built in `ui_shared._CHECK_PNG` with forward slashes.
- `cursor:` in stylesheets is unsupported — use `setCursor(Qt.ArrowCursor)`.
- **Disabled state must be styled explicitly on custom widgets** — Qt's `:disabled` QSS doesn't auto-grey them. `PlusMinusSpinBox` has `QWidget#pmsp:disabled` (BG_SUBTLE bg + faint BORDER) and `QLineEdit:disabled` (TEXT_MUTED); `STYLE_COMBO` has `QComboBox:disabled`. `ChevronComboBox`'s `▼` is a QLabel child NOT reached by `QComboBox:disabled`, so a `changeEvent` override recolors it to TEXT_MUTED on `QEvent.EnabledChange`. Used so Boundary-row locked CELL ZONE / VOL DIR / V.LVL read as non-editable.
- **`PlusMinusSpinBox` corner-gap fix:** the row `QHBoxLayout` uses `setContentsMargins(1,1,1,1)` so the −/+ buttons sit INSIDE the 1px outer `#pmsp` border instead of painting over it (button inner radius 3px = outer 4px − 1px border). Zero margins re-introduces the white-sliver notch at the rounded corners.
- `QComboBox::down-arrow` drawn via QSS borders (`width/height: 0px` + directional `border-width`/`border-color`) is fragile and rendered as a solid block instead of a triangle in this Qt5/WSLg setup. Fixed by `ChevronComboBox` in `ui_shared.py` — a real `▼` `QLabel` child positioned in `resizeEvent()`, same idea as `LogDrawer`'s `_chevron_btn.setText("▼")`. Use `ChevronComboBox` instead of bare `QComboBox` everywhere in the GUI; `STYLE_COMBO`'s `::down-arrow` rule just hides the native arrow (`image: none; width/height: 0px;`).

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
