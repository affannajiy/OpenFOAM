# Changelog

All notable changes to the OpenFOAM UI project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
