# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Requirements

All Python scripts must be run from within WSL (Ubuntu) — **not** Windows CMD/PowerShell — because they invoke OpenFOAM executables (`blockMesh`, `surfaceCheck`, `foamDictionary`, `snappyHexMesh`, `surfaceFeatureExtract`) that only exist in the Linux environment.

Before running any script, the OpenFOAM environment must be sourced:
```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
```

Scripts must be run from inside an OpenFOAM case directory (e.g., `03_mesh_session/`), since they write output files to `system/` and read from `constant/triSurface/` relative to the current working directory.

## Running the Tools

**GUI application (recommended):**
```bash
cd /mnt/c/OpenFOAM/03_mesh_session
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```

**CLI: generate background block mesh from STL bounding box:**
```bash
python3 01_utilities/generateBackgroundMesh.py \
  -stlPath constant/triSurface/geom.stl \
  -dx 0.05 -dy 0.05 -dz 0.05
```

**CLI: interactive snappyHexMeshDict generator:**
```bash
python3 01_utilities/generateSnappyHexMeshDict.py
```

**Full mesh generation workflow (after background mesh is ready):**
```bash
surfaceFeatureExtract
snappyHexMesh -overwrite
```

Python dependencies needed in WSL: `python3-tk`, `python3-numpy`.

## Architecture

The project has two layers: Python tooling (`01_utilities/`) and an example OpenFOAM case (`03_mesh_session/`).

### Python Tooling (`01_utilities/`)

**`openfoam_ui.py`** — Tkinter GUI wrapping the two CLI tools. Key classes:
- `App` (main window, inherits `tk.Tk`) contains two tabs
- `BackgroundMeshTab` — collects STL file + dx/dy/dz, spawns `generateBackgroundMesh.py` as a subprocess; auto-detects case root from STL path
- `SnappyHexMeshTab` — multi-section scrollable form that calls `foamDictionary` directly to write mesh refinement config; Section 5 has both a "Generate snappyHexMeshDict" button and a "Run snappyHexMesh" button that streams binary output to the log; existing time directories (/1, /2, …) are shown live
- `LogPanel` / `StatusBar` — real-time log streaming from subprocesses; `queue.Queue` is used to push lines from a worker thread to the Tk main loop

**`generateBackgroundMesh.py`** — Standalone CLI:
1. Calls `surfaceCheck` on the STL, parses bounding box coordinates via regex
2. Scales the box by 1.1× (padding), computes integer cell counts from dx/dy/dz
3. Writes `system/blockMeshDict`, then runs `blockMesh`

**`generateSnappyHexMeshDict.py`** — Interactive CLI:
- Prompts for refinement levels, feature edge snapping, boundary layer parameters
- Parses ASCII STL `solid` names to enumerate surfaces
- Writes `system/snappyHexMeshDict`, `system/fvSchemes`, `system/fvSolution`
- Uses `foamDictionary` subprocess calls for dictionary manipulation

### Design Patterns

- **Subprocess-based integration**: all OpenFOAM executables are invoked via `subprocess.run` / `subprocess.Popen`; stdout/stderr is captured to log panels or parsed with regex
- **GUI re-implements CLI logic**: the GUI does not simply call the CLI scripts for all operations; `SnappyHexMeshTab` drives `foamDictionary` directly
- **Output files are text templates**: mesh dictionaries are built as formatted strings and written to `system/` — no templating library is used

### OpenFOAM Case Layout (`03_mesh_session/`)

Standard OpenFOAM case structure:
- `constant/triSurface/` — input STL geometry files
- `constant/polyMesh/` — generated mesh (output of `blockMesh`)
- `system/` — all configuration dictionaries (`blockMeshDict`, `snappyHexMeshDict`, `controlDict`, `fvSchemes`, `fvSolution`)
- `programOutputs/` — captured log files from mesh tool runs

## Platform Notes

- Windows path `C:\OpenFOAM` maps to WSL path `/mnt/c/OpenFOAM`
- ParaView is detected at runtime by scanning `C:/Program Files/ParaView*/bin/paraview.exe` (picks the newest version found)
- Target OpenFOAM version: **2506** (also compatible with 2312)
