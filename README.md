# OpenFOAM Mesh Generation Utilities

Python utilities for automating snappyHexMesh setup in ESI OpenFOAM v2506.

## Prerequisites

- WSL/Ubuntu with OpenFOAM installed (see `openfoam-setup-guide.md`)
- OpenFOAM environment sourced (`of2506` or `source /usr/lib/openfoam/openfoam2506/etc/bashrc`)
- `python3-numpy` for `generateBackgroundMesh.py`
- `python3-tk` for `openfoam_ui.py`
- Run scripts from within an OpenFOAM case directory

## Scripts

### openfoam_ui.py

Unified tkinter GUI that wraps both mesh utilities in a tabbed interface. Recommended for interactive use.

```bash
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```

- **Tab 1 — Background Mesh**: file picker for the STL, grid-size inputs, and a live log panel; calls `generateBackgroundMesh.py` via subprocess.
- **Tab 2 — snappyHexMeshDict**: scrollable multi-section form that drives `foamDictionary` directly to build `system/snappyHexMeshDict`.
  - Section 1: select surface/edge files from `constant/triSurface/`; add standard shapes (Box, Cylinder, Sphere)
  - Section 2: castellation & refinement — edge, surface, volumetric, and gap refinement levels; nCellsBetweenLevels; location in mesh
  - Section 3: snap controls — implicit or explicit feature snapping
  - Section 4: layer addition — per-patch nSurfaceLayers
  - Section 5: two-step action — "Generate snappyHexMeshDict" writes `system/snappyHexMeshDict` (and `fvSchemes`/`fvSolution` when layers are enabled); "Run snappyHexMesh" then calls the binary and streams output to the log; existing time directories are shown live; mesh quality parameters are hardcoded defaults

Requires `python3-tk` (`sudo apt-get install python3-tk`). Launch from an OpenFOAM case directory with the environment already sourced.

### generateBackgroundMesh.py

Reads an STL file's bounding box via `surfaceCheck`, generates `system/blockMeshDict`, and runs `blockMesh`.

```bash
python3 generateBackgroundMesh.py -stlPath <path/to/file.stl> -dx <float> -dy <float> -dz <float>
```

| Argument | Description |
|----------|-------------|
| `-stlPath` | Path to the STL file |
| `-dx` | Base grid size in x-direction |
| `-dy` | Base grid size in y-direction |
| `-dz` | Base grid size in z-direction |

Logs are written to `programOutputs/`.

### generateSnappyHexMeshDict.py

Interactively builds `system/snappyHexMeshDict` through a series of prompts. Also generates `system/fvSchemes` and `system/fvSolution` when boundary layer addition is enabled. Written for ESI OpenFOAM v2312; compatible with v2506.

```bash
python3 generateSnappyHexMeshDict.py
```

Requires `system/controlDict` and `constant/triSurface/` to exist before running.

## Typical Workflow

```bash
# 1. Generate background mesh (GUI or CLI)
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
# — or —
python3 generateBackgroundMesh.py -stlPath constant/triSurface/geometry.stl -dx 0.1 -dy 0.1 -dz 0.1

# 2. Extract feature edges (for explicit snapping)
surfaceFeatureExtract

# 3. Generate snappyHexMeshDict (GUI or CLI)
# Use Tab 2 in openfoam_ui.py, or:
python3 generateSnappyHexMeshDict.py

# 4. Run snappyHexMesh (GUI button in Section 5, or CLI)
snappyHexMesh -overwrite
```

## Setup

See [openfoam-setup-guide.md](openfoam-setup-guide.md) for full WSL + OpenFOAM installation instructions and alias configuration.
