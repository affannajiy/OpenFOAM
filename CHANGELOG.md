# Changelog

All notable changes to the OpenFOAM UI project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
