# ANR-04 — Affan's current production layout

**Author:** Affan Najiy Rusdi (ANR). Latest GUI version. Restructured into a clean **`app/` (shipped) + `deploy/` (build tooling)** split, with icons and a single project-specific snappy backend. This is the layout described in the project's `CLAUDE.md`.

## What this version is

The cleaned, production structure. Users get the `app/` folder; `deploy/` stays behind for building.

| Folder / file | Function |
|------|----------|
| `app/` | **Shipped to users** — the distribution. All `ui_*.py`, `openfoam_ui.py`, `snappy_generator.py`, `defaults.json`, `requirements.txt`, `OpenFOAM_UI.exe`, `templates/`, `icons/`. |
| `app/snappy_generator.py` | **The single snappy backend** — the in-house engine (the older `setup_snappy.py` now dropped). Renders `system/snappyHexMeshDict` from the Jinja2 template, runs `snappyHexMesh -overwrite`. |
| `app/icons/` | App icons (16–256 px PNGs + `openfoam_ui.ico`). |
| `deploy/` | **Not shipped** — build only: `build_exe.bat`, `generate_icon.py`, `icon_source.svg`, `openfoam_ui_launcher.spec`, `version_info.txt`, PyInstaller artefacts. |

## Key traits

- **`app/` + `deploy/` separation** — clean line between what ships and what builds.
- **One backend** — `snappy_generator.py` only; the older `setup_snappy.py` retired.
- Icons + polished launcher/splash.
- The exe is a **thin launcher**: only rebuild it when `openfoam_ui_launcher.py` changes; edits to other `.py` take effect on next launch.

## Meshing pipeline

`surfaceCheck` → write `blockMeshDict` → `blockMesh` → render `snappyHexMeshDict` (Jinja2 template + in-memory config) → `snappyHexMesh -overwrite`.

## Place in the project

The current, cleaned version — the base the active `src/` work continues from. Full lineage: **VIJ-01 → VIJ-02 → VIJ-03** (base CLI → template engine → full workflow) feeding **ANR-01 → ANR-02 → ANR-03 → ANR-04** (Tkinter GUI → PyQt5 + template backend → packaged exe → clean app/deploy layout).
