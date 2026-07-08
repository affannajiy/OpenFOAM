# VIJ-01 — Vijaya Kumar's original CLI seed

**Author:** Vijaya Kumar (developer, India). This is the earliest codebase in the project — every later version, including all the ANR (Affan Najiy Rusdi) GUI versions, is built on top of the work that starts here.

## What this version is

The bare beginning: two standalone command-line Python scripts, no GUI, no packaging.

| File | Function |
|------|----------|
| `generateBackgroundMesh.py` | Reads an STL bounding box with `surfaceCheck`, writes `system/blockMeshDict`, runs `blockMesh` to build the background box mesh. |
| `generateSnappyHexMeshDict.py` | Interactive CLI that builds `system/snappyHexMeshDict` entry-by-entry using many `foamDictionary ... -add` calls, then runs `snappyHexMesh`. |

## How it runs

Run inside an OpenFOAM case folder (has `constant/` + `system/`), after sourcing the OpenFOAM bashrc. Pure terminal — you answer prompts, it writes the dicts and calls the mesher.

## Meshing pipeline

`surfaceCheck` → write `blockMeshDict` → `blockMesh` → write `snappyHexMeshDict` (via `foamDictionary`) → `snappyHexMesh`.

## Place in the project

Foundation layer. No templates, no JSON config, no GUI. Later Vijay versions (VIJ-02, VIJ-03) add the template + JSON approach; the ANR versions wrap all this in a graphical UI.
