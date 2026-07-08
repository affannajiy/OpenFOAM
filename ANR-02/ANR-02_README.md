# ANR-02 — Affan's modular PyQt5 GUI + template backend

**Author:** Affan Najiy Rusdi (ANR). Second GUI version. Two big moves: switch the UI from Tkinter to **PyQt5**, and swap the meshing backend to the **template + JSON engine** (from VIJ-02).

## What this version is

The GUI split into modular files, with the VIJ-02 snappy configurator pulled in as the backend.

| File | Function |
|------|----------|
| `openfoam_ui.py` | PyQt5 main shell (header, tabs, log drawer). |
| `ui_landing.py` | Landing page — create/open a project, pick a utility. |
| `ui_background_mesh.py` | Tab 1 — background mesh worker (surfaceCheck → blockMeshDict → blockMesh). |
| `ui_snappy_hex.py` | Tab 2 — snappyHexMesh setup (file table, zones, layers). |
| `ui_shared.py` | Shared widgets, styles, command runners. |
| `ui_log_drawer.py` | Collapsible output log. |
| `setup_snappy.py`, `auto_refinement.py`, `encoding_utils.py` | **VIJ-02 backend** — template+JSON snappy dict engine. |
| `defaults.json`, `templates/` | Control-block defaults and Jinja2 templates (from VIJ-02). |
| `generateBackgroundMesh.py`, `generateSnappyHexMeshDict.py` | Original CLI tools kept alongside. |

## Key traits

- **Tkinter → PyQt5** rewrite of the UI.
- Backend now renders `snappyHexMeshDict` from a template in one pass (the VIJ-02 way) instead of many `foamDictionary` calls.
- Modular `ui_*` files. No exe / packaging yet.

## Place in the project

The merge point: PyQt5 GUI + the VIJ-02 template engine. Sets the file structure all later ANR versions keep refining.
