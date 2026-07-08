# ANR-01 — Affan's first GUI (Tkinter)

**Author:** Affan Najiy Rusdi (ANR). First graphical version. Built on top of the base CLI tools (see the VIJ versions) — this wraps the two scripts in a simple window.

## What this version is

Three files: the two base CLI tools plus one **Tkinter** GUI that drives them.

| File | Function |
|------|----------|
| `generateBackgroundMesh.py` | Background-mesh tool (surfaceCheck → blockMeshDict → blockMesh). |
| `generateSnappyHexMeshDict.py` | Snappy dict builder (foamDictionary → snappyHexMesh). |
| `openfoam_ui.py` | **Tkinter** two-tab GUI. Tab 1 = background mesh (pick STL, set dx/dy/dz, run blockMesh). Tab 2 = snappyHexMesh. Calls the two CLI scripts via subprocess. |

## Key trait

GUI toolkit is **Tkinter** (Python stdlib) — later ANR versions switch to **PyQt5**. Single-file UI, no modular split, no packaging, no exe.

## Meshing pipeline

Same as the base underneath — `surfaceCheck` → `blockMesh` → `snappyHexMeshDict` (foamDictionary) → `snappyHexMesh` — now clickable instead of typed.

## Place in the project

First step from CLI to GUI. Proves the wrap-in-a-window idea. Everything after (ANR-02+) rebuilds the UI in PyQt5 and swaps the backend to the template+JSON engine.
