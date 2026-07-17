# VIJ-03 — Vijaya Kumar's full case-setup workflow

**Author:** Vijaya Kumar (developer, India). Third and largest Vijay version. Grows from "just meshing" to a complete OpenFOAM case-setup pipeline: mesh + simulation inputs + material properties + helper utilities.

## What this version is

A full workflow package, still CLI/HTML-driven (no PyQt5 GUI). Covers the whole path from geometry to a runnable case.

| File / folder | Function |
|------|----------|
| `setup_case.py` | Top-level case builder. Renders `controlDict`, `fvSchemes`, `fvSolution`, `decomposeParDict`, etc. from templates; resolves config aliases and per-region settings. |
| `materials_library.json` | Named material properties library. |
| `path_config.py`, `common/utils.py` | Shared path handling + command/execution helpers. |
| `configure_snappyHexMeshDict/` | The full snappy configurator (setup_snappy.py, templates, defaults.json, docs) — the VIJ-02 tool folded in. Adds more templates: `controlDict`, `decomposeParDict`, `fvSchemes`, `fvSolution`. |
| `configure_simInputs/` | HTML tool (`sim_inputs_generator.html`) for building simulation inputs. |
| `other_utilities/` | Mesh helpers: `createFluidCellZone.py`, `ensureConsistentCellZones.py`, `fetchMeshParts/`, plus a `checkMesh` log parser in `_common.py`. |
| `documentation/` | Configuration guide, examples, code review notes. |

## Meshing + case pipeline

`surfaceCheck` → `blockMesh` → `snappyHexMesh` (template+JSON) → cell-zone/consistency utilities → `decomposePar` (parallel split) → write solver dicts → run. Adds `checkMesh` quality reporting and parallel decomposition — steps the ANR GUI does not (yet) use.

## Place in the project

The most complete Vijay codebase — beyond meshing into full simulation setup. The ANR GUI so far adopts only the meshing half (snappy template + JSON); the sim-inputs, materials, decomposePar and checkMesh parts live here as the reference for future GUI work.
