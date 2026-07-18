# Changelog

All notable changes to the OpenFOAM UI project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2026-07-18] — Faster Launch, Single Instance, Popup Polish

### Added
- **Single-instance guard** (three layers): clicking the shortcut while the
  app is open now focuses the existing window instead of opening a second
  copy — launcher finds and raises the running "OpenFOAM GUI" window; a
  named mutex (`Local\OpenFOAM_UI_Launcher`) stops a second launcher during
  startup; a `QLockFile` in the GUI backstops manual WSL runs (stale locks
  from crashes recovered automatically) and shows a styled "Already
  running" notice.
- **Launcher fast path**: after one fully successful launch, a sentinel
  (`%TEMP%\openfoam_ui_checks_ok.json`) lets later launches skip the full
  pre-flight — one quick validation call instead of ~9 WSL round-trips.
  Cleared automatically if validation fails or the GUI crashes at startup.
- Standalone popup fallback `_run_box_standalone`: popups fired before the
  main window exists (e.g. the "Already running" notice) now render the
  same minimalist centred card inside a fullscreen dimmed backdrop instead
  of a stock Qt message box.

### Changed
- **PyInstaller build switched to one-dir** (exe + `_internal\`, UPX off):
  removes the per-launch self-extraction to `%TEMP%` and repeated
  antivirus rescans that made first runs slow. `build.bat` copies the whole
  folder; `installer.iss` unchanged (already ships the folder wholesale).
- Launcher pre-flight steps 3–5 (bashrc, python3, packages) merged into a
  single WSL probe call; GUI-ready detection moved to a Windows-side file
  (`%TEMP%\openfoam_ui_ready` via `OPENFOAM_UI_READY_FILE`) so the
  watchdog no longer spawns a WSL process every 200 ms.
- `CLAUDE.md` and `README.md` rewritten lean — same facts, roughly half
  the length; README now leads new users through the installer path.

### Fixed
- Tooltips on the header bar (Home, ParaView, tab pills), landing-page
  cards/segments, and log-drawer buttons no longer render black-on-black —
  `STYLE_TOOLTIP` appended to every inline widget stylesheet that was
  missing it.
- Two app windows could be opened by double-clicking the shortcut twice
  and then refused to close — resolved by the single-instance guard above.

## [2026-07-17] — One-File Installer v1.1.0

### Added
- **One-file Windows installer** `OpenFOAM_UI_Setup_<version>.exe` (Inno
  Setup 6, `deploy/installer.iss`): per-user install to
  `%LOCALAPPDATA%\Programs\OpenFOAM-UI` (no admin rights), desktop +
  Start-Menu shortcuts (replaced in place on reinstall), Demo-01/Demo-02
  sample cases copied to `Documents\OpenFOAM-Projects` (existing files never
  overwritten, never uninstalled), Add/Remove Programs entry with a real
  uninstaller, and a hard gate for Windows builds older than 21362 (no
  WSLg). Deep environment checks remain in the launcher's self-healing
  pre-flight.
- Landing page New-project **Location defaults to the installer's
  `Documents\OpenFOAM-Projects`** (via `install_info.json` written next to
  the app), falling back to `~/OpenFOAM`.
- Single build entry `deploy/build.bat` (replaces `build_exe.bat` +
  `build_installer.bat`): version prompt defaults to the current version,
  PyInstaller installed only when missing, always builds EXE + installer in
  one chain.

### Changed
- Moved the historical ANR-01..04 session trees and Vijay's VIJ-01..03
  reference packages under `Archived/` — the live repo is now `src/` plus
  the two demo cases.

### Fixed
- Build script no longer corrupts non-ASCII characters in
  `openfoam_ui_launcher.py` when patching the splash version label
  (PowerShell 5.1 misread the BOM-less UTF-8 source as ANSI; now patched
  via UTF-8 `[IO.File]` round-trip).
- `version_info.txt` version-tuple drift repaired (`filevers` said 1.0.5
  while `FileVersion` said 1.0.6).

## [2026-07-16] — Self-Healing Launcher v1.0.6 + Live Environment Detection

### Added
- Launcher self-healing installs: missing WSL → one-click elevated
  `wsl --install` with optional one-time **Restart Now**; missing distro →
  Ubuntu download + guided first-run terminal (account-creation polling);
  WSL1 distro → one-click convert to WSL2; missing WSLg display →
  **Update WSL** button.
- Pre-setup probes: Windows-build gate (≥ 21362 for WSLg), network
  reachability of download servers (bash `/dev/tcp`, no curl dependency),
  and disk-space checks on both the Windows and WSL sides.
- **Copy Details** on every launcher error dialog — clipboard diagnostics
  report (versions + log tail) for IT tickets.
- Manual-install guide when admin permission is declined or blocked:
  numbered steps + **Copy Command** button; launcher resumes automatically
  on the next run.
- Landing page environment card and utility checklist now show *detected*
  software versions (OpenFOAM, ParaView, Ubuntu, Python) instead of
  hardcoded labels — green dot when found, grey "not found" otherwise.

### Fixed
- GUI backend no longer hardcodes the OpenFOAM 2506 bashrc: `ui_shared` and
  `snappy_generator` now source the install the GUI was launched under
  (`$WM_PROJECT_DIR`), falling back to the newest `/usr/lib/openfoam/`
  install — 2312-only machines now run meshes instead of failing.
- Checkbox tick icons (`icons/check_16.png`, `check_32.png`) added to the
  repository — fresh clones previously showed empty checked boxes.

## [2026-07-08] — Repository Restructuring

### Changed
- Restructured the repository: live code consolidated under `src/`
  (`src/app/` = shipped distribution, `src/deploy/` = build tooling); the old
  `01_utilities/` tree removed as stale.
- Revised all subagent definitions (`agents/*.md`) to match the current layout —
  paths updated to `src/`, `foam-snappymesh` backend corrected to the Jinja2
  template + JSON engine, `foam-docs` dead entries pruned, `foam-git` commit
  template cleaned up.

### Added
- `CHANGELOG.md` documenting project history.

## [2026-07-03] — UI/UX Improvement

### Changed
- Refined GUI layout, styling, and interaction across the landing page and both
  utility tabs.

## [2026-07-02] — Snappy Backend Rework

### Changed
- Replaced the `foamDictionary`-based snappy backend with a single-pass Jinja2
  template + JSON engine (`snappy_generator.py`, `defaults.json`,
  `templates/snappyHexMeshDict.template`).

### Fixed
- Inner solids (e.g. inner cylinder inside a cube) no longer disappear:
  `FaceZone + Cell Zone` now writes `faceZone`/`faceType internal` plus
  `cellZoneInside`/`cellZone` so interior cells are kept and named.
- A `Boundary` shell no longer receives a volume refinement region (skipped +
  warned) — prevents blobby edge-refined meshes.

## [2026-06-23] — Units

### Changed
- Switched length units from metres to millimetres.

## [2026-06-12] — Example Case

### Changed
- Reset the `03_mesh_session` example case to a clean starting state.

## [2026-06-11] — Installation & Launcher

### Changed
- Revised the setup/installation flow.
- Reworked the Windows `.exe` launcher: patient WSL boot, WSLg display probe,
  OpenFOAM bashrc + Python package checks (PyQt5, numpy, jinja2), apt-only setup
  gate, distro auto-detect, Try Again dialog on failure.

## [2026-06-04] — Build & Packaging

### Changed
- Revised the PyInstaller build (`build_exe.bat`), PyQt5 packaging, and launcher.

## [2026-05-22] — SnappyHex & Launcher

### Changed
- Enhanced the SnappyHexMesh utility and revised the launcher.

## [2026-05-15] — Optimization

### Changed
- Optimized application performance and code paths.

## [2026-05-14] — Restructure & Agents

### Added
- Introduced the subagent set under `agents/` (`foam-ui`, `foam-snappymesh`,
  `foam-backgroundmesh`, `foam-docs`, `foam-git`).
- Shipped the `.exe`, deploy icons, and example case mesh.

### Changed
- Restructured the utilities layout and updated documentation.

### Fixed
- `locationInMesh` suggestion, log newline handling, and docs corrections.

## [2026-05-13] — Application Changes

### Changed
- Reworked the OpenFOAM UI application.

## [2026-05-11] — Build EXE

### Added
- First PyInstaller-built Windows executable.

## [2026-05-07] — Landing UI

### Added
- Landing page with New/Open project flow and recents.

### Changed
- UI Update 2.0 — broad interface refresh.

## [2026-05-06] — UI Integration

### Changed
- Large UI edit integrating new updates.

## [2026-04-29] — Early UI Work

### Changed
- Updated UI functionality; initial testing.

## [2026-04-27] — Initial Commit

### Added
- Initial project: OpenFOAM UI sources, documentation, and the OpenFOAM Setup and
  Installation PDF.
