# OpenFOAM Mesh Generation Utilities

Python utilities for automating snappyHexMesh setup in ESI OpenFOAM v2506, with a PyQt5 GUI and CLI fallbacks.

## Prerequisites

- WSL/Ubuntu with OpenFOAM installed (see [`documentation/OpenFOAMSetup.md`](documentation/OpenFOAMSetup.md))
- OpenFOAM environment sourced: `source /usr/lib/openfoam/openfoam2506/etc/bashrc`
- Python dependencies installed (see [Installation](#installation))
- Scripts must be launched from inside an OpenFOAM case directory

## Installation

Install Python dependencies in WSL:

```bash
sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2
```

Or with pip (Ubuntu 24.04+):

```bash
pip3 install -r 01_utilities/requirements.txt --break-system-packages
```

| Package | Required | Purpose |
|---------|----------|---------|
| `PyQt5` | Yes | GUI framework |
| `numpy` | Yes | Bounding box arithmetic |
| `jinja2` | Yes | Dictionary template rendering |
| `trimesh` | Optional | `AUTO_` auto-refinement analysis |

## GUI Application (Recommended)

Launch from WSL (the working directory does not need to be a case directory — the landing page lets you choose):

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```

### Landing Page

On first launch the GUI shows a landing page where you can:

- **New project** — enter a name and location; the tool creates the folder structure (`constant/triSurface/`, `system/`, `0/`) and stub dictionaries (`controlDict`, `fvSchemes`, `fvSolution`).
- **Open existing** — browse to or pick from the recent-projects list; the tool validates that `system/controlDict` exists.

Then choose a utility (Background Mesh or SnappyHexMesh Dict) and click **Continue →** to open the main workspace.  The ← Home button in the header bar returns to the landing page at any time.

Recent projects are stored in `~/.openfoam_ui_recents.json` (max 10 entries; each has a × button to remove it).

The GUI is a 1100×760 PyQt5 window with two tabs:

### Tab 1 — Background Mesh

Generates `system/blockMeshDict` from an STL bounding box and runs `blockMesh`.

1. **STL file** — browse or paste path; auto-detects case root from `constant/` in the path (works regardless of the geometry subfolder name)
2. **Grid resolution** — DX / DY / DZ cell sizes in metres
3. Click **Generate Background Mesh** — runs `surfaceCheck`, writes `blockMeshDict`, runs `blockMesh`, creates `<case>.foam`
4. **Cancel** — stops a running job and clears all input fields

### Tab 2 — SnappyHexMesh Dict

Five-section card form that writes `system/snappyHexMeshDict` via Jinja2 template rendering and optionally runs `snappyHexMesh`.

| Section | Content |
|---------|---------|
| **01 Geometry** | File table listing all STL/OBJ files found under `constant/` (any subfolder); set Surface Type (None / Boundary / FaceZone / FaceZone+CellZone), min/max refinement levels, and Volume Direction + level per file; filenames may use the `SURF_` / `VOL_` encoding convention for auto-population |
| **02 Castellation** | Geometry unit (mm / m / cm / µm / in / ft), nCellsBetweenLevels, location-in-mesh X Y Z |
| **03 Snap controls** | Implicit feature snapping toggle |
| **04 Layer addition** | Enable boundary layers; per-patch nSurfaceLayers spinboxes (populated from Section 01 surface selections) |
| **05 Generate & Run** | **Generate snappyHexMeshDict** merges GUI values with `defaults.json` and renders `system/snappyHexMeshDict` (plus `fvSchemes`/`fvSolution` when layers are on); **Run snappyHexMesh** streams the solver to the log and refreshes the `.foam` file |

#### Filename Encoding Convention

STL files can embed refinement metadata directly in the filename so the GUI auto-populates fields:

```
SURF_BND_L2_L4_wallName.stl          → Boundary surface, refinement 2–4
SURF_FZ_CZ_L1_L2_VOL_IN_L3_zone.stl → FaceZone+CellZone surface, vol inside at level 3
AUTO_wallName.stl                     → Auto-analysis via trimesh (requires trimesh installed)
```

Prefix tokens: `SURF` (surface), `BND` (boundary), `FZ` (face zone), `CZ` (cell zone), `VOL` (volume region), `IN`/`OUT` (inside/outside), `L<n>` (refinement level).

The **Output Log** at the bottom of the window starts expanded and streams all subprocess output with colour-coded tags. Drag its bottom edge upward to resize it, or click the chevron to collapse/expand.

## CLI Tools

### generateBackgroundMesh.py

Reads an STL bounding box via `surfaceCheck`, writes `system/blockMeshDict`, and runs `blockMesh`.

```bash
cd /mnt/c/OpenFOAM/03_mesh_session
source /usr/lib/openfoam/openfoam2506/etc/bashrc

python3 /mnt/c/OpenFOAM/01_utilities/generateBackgroundMesh.py \
  -stlPath constant/triSurface/geometry.stl \
  -dx 0.05 -dy 0.05 -dz 0.05
```

| Argument | Description |
|----------|-------------|
| `-stlPath` | Path to the STL file |
| `-dx` | Cell size in x (metres) |
| `-dy` | Cell size in y (metres) |
| `-dz` | Cell size in z (metres) |

Logs are written to `programOutputs/`.

### generateSnappyHexMeshDict.py

Interactive CLI that builds `system/snappyHexMeshDict` through prompts. Also generates `system/fvSchemes` and `system/fvSolution` when boundary layer addition is enabled.

```bash
cd /mnt/c/OpenFOAM/03_mesh_session
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/generateSnappyHexMeshDict.py
```

Requires `system/controlDict` and a `constant/` directory to exist in the case root.

## Typical Workflow

```bash
# 1. Source the OpenFOAM environment
source /usr/lib/openfoam/openfoam2506/etc/bashrc

# 2. Launch the GUI (landing page opens first)
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
# Landing page: create a new project or open an existing one, choose utility, Continue →

# 3. Generate background mesh
# Tab 1: select STL, set DX/DY/DZ, click Generate

# 3. Extract feature edges (for explicit snapping)
surfaceFeatureExtract

# 4. Configure and run snappyHexMesh
# Tab 2: configure all sections, Generate dict, then Run
# — or CLI fallback:
snappyHexMesh -overwrite

# 5. Open in ParaView
# Click "Open ParaView" in the header bar
```

## Repository Layout

```
C:\OpenFOAM\
├── 01_utilities\               # Python tooling
│   ├── openfoam_ui.py          # PyQt5 GUI entry point (single command to run everything)
│   ├── ui_shared.py            # Colour tokens, styles, shared helpers
│   ├── ui_log_drawer.py        # Collapsible/resizable log drawer widget
│   ├── ui_background_mesh.py   # Background Mesh tab widget
│   ├── ui_snappy_hex.py        # SnappyHexMesh Dict tab widget (Jinja2-based)
│   ├── setup_snappy.py         # Core config merging, validation, and template rendering
│   ├── encoding_utils.py       # Filename encoding/decoding (SURF_, VOL_, FZ_, etc.)
│   ├── auto_refinement.py      # AUTO_ geometry analysis via trimesh (optional)
│   ├── defaults.json           # Default values for all snappyHexMesh controls
│   ├── templates\
│   │   ├── snappyHexMeshDict.template  # Jinja2 template for snappyHexMeshDict
│   │   └── blockMeshDict.template      # Jinja2 template for blockMeshDict
│   ├── generateBackgroundMesh.py       # CLI: blockMesh from STL bbox (do not modify)
│   ├── generateSnappyHexMeshDict.py    # CLI: interactive snappyHexMeshDict (do not modify)
│   └── requirements.txt        # Python dependencies
├── 03_mesh_session\            # Example OpenFOAM case
│   ├── constant\<geometry>\    # Input STL geometry files (any subfolder name)
│   ├── constant\polyMesh\      # Generated mesh (blockMesh output)
│   ├── system\                 # Dictionaries (blockMeshDict, snappyHexMeshDict, …)
│   └── programOutputs\         # Captured log files
├── documentation\
│   └── OpenFOAMSetup.md        # Setup, deployment, and troubleshooting guide
└── CLAUDE.md                   # AI assistant guidance
```

## Notes

- Windows path `C:\OpenFOAM` maps to WSL path `/mnt/c/OpenFOAM`
- Target OpenFOAM version: **2506** (also compatible with 2312)
- ParaView is detected automatically by scanning `C:\Program Files\ParaView*\bin\paraview.exe` (newest version wins)
- All OpenFOAM executables must be run inside WSL — they do not exist in Windows CMD/PowerShell
- Qt5 on Linux/WSL prints harmless `Could not parse stylesheet` messages for some `QFrame` widgets; a `qInstallMessageHandler` in `openfoam_ui.py` silences these so only genuine Qt warnings appear on stderr
