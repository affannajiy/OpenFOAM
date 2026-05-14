# SnappyHexMesh Reference

Complete reference for the `configure_snappyHexMeshDict` toolchain — covers the JSON configuration schema, geometry types, surface and volume refinement, the filename encoding convention, auto-refinement, and the default solver parameters baked into `defaults.json`.

---

## Table of Contents

1. [Overview and Workflow](#overview-and-workflow)
2. [File Structure](#file-structure)
3. [Running the Generator](#running-the-generator)
4. [snappy\_inputs.json Schema](#snappy_inputsjson-schema)
   - [settings](#settings)
   - [backgroundMesh](#backgroundmesh)
   - [geometry](#geometry)
   - [surfaceHandling](#surfacehandling)
   - [volumeRefinement](#volumerefinement)
5. [Standard Shape Types](#standard-shape-types)
6. [Surface Types](#surface-types)
7. [Volume Refinement Modes](#volume-refinement-modes)
8. [Filename Encoding Convention](#filename-encoding-convention)
9. [AUTO\_ — Automatic Level Derivation](#auto_--automatic-level-derivation)
10. [Default Solver Parameters (defaults.json)](#default-solver-parameters-defaultsjson)
11. [Refinement Level Reference](#refinement-level-reference)
12. [Common Errors and Fixes](#common-errors-and-fixes)
13. [Tips and Best Practices](#tips-and-best-practices)

---

## Overview and Workflow

The toolchain generates `system/snappyHexMeshDict` (and `system/blockMeshDict`) from a JSON configuration file (`snappy_inputs.json`). The pipeline:

```
snappy_inputs.json
       │
       ▼
setup_snappy.py  ──  defaults.json  ──  templates/
       │
       ├──▶  system/blockMeshDict     (via trimesh bounding box)
       └──▶  system/snappyHexMeshDict (via Jinja2 template)
```

The three meshing stages OpenFOAM performs:

| Stage | Controls | What happens |
|---|---|---|
| **castellatedMesh** | `castellatedMeshControls` | Cuts background hex mesh to geometry surfaces; applies surface and volume refinement |
| **snap** | `snapControls` | Projects cell faces onto the STL surface |
| **addLayers** | `addLayersControls` | Extrudes prismatic boundary layers from wall surfaces |

---

## File Structure

```
configure_snappyHexMeshDict/
├── setup_snappy.py          ← main entry point; config merge, validate, render
├── auto_refinement.py       ← AUTO_ level derivation engine (requires trimesh + numpy)
├── encoding_utils.py        ← shared tag parsing for both parsers
├── defaults.json            ← default solver parameters (all overridable)
├── snappy_inputs.json       ← case-specific config (edit this per case)
├── templates/
│   ├── snappyHexMeshDict.template
│   └── blockMeshDict.template
├── documentation/
│   ├── JSON_SCHEMA_GUIDE.md
│   ├── QUICK_REFERENCE.md
│   ├── TROUBLESHOOTING.md
│   └── CHANGELOG.md
└── examples/
    └── 01_thermal_mgmt_case_2/
```

---

## Running the Generator

**All commands must be run in WSL with OpenFOAM sourced, from inside the case directory.**

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
cd /path/to/your/case

# Generate both snappyHexMeshDict and blockMeshDict
python3 /mnt/c/OpenFOAM/configure_snappyHexMeshDict/setup_snappy.py

# Run the mesh
blockMesh
surfaceFeatureExtract
snappyHexMesh -overwrite
```

The case directory must contain `constant/` and `system/`. Geometry files must be in `constant/<geometry-folder>/` (the tool scans all of `constant/` recursively for `.stl` and `.obj`).

---

## snappy\_inputs.json Schema

`snappy_inputs.json` is merged on top of `defaults.json` using a recursive dict merge — values you set override defaults; values you omit fall back to defaults. The keys `geometry`, `surfaceHandling`, and `volumeRefinement` are **case-only** and must not appear in `defaults.json`.

### Minimal template

```json
{
    "_version": "1.0",
    "settings": {
        "geometryUnit": "mm",
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": {
        "files": ["outer-domain.stl"]
    },
    "backgroundMesh": {
        "referenceGeometry": "outer-domain.stl",
        "baseGrid": 5.0
    },
    "castellatedMeshControls": {
        "locationInMesh": [50, 50, 50]
    }
}
```

---

### `settings`

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `geometryUnit` | string | **yes** | — | Unit of STL files: `"m"`, `"mm"`, `"cm"`, `"um"`, `"in"`, `"ft"`. Metadata only — not applied as a scale factor |
| `addLayers` | bool | **yes** | — | Enable boundary layer generation |
| `mergeTolerance` | float | **yes** | — | Surface merging tolerance; `1e-06` works for most cases |
| `extractRefinementFromNames` | bool | no | `false` | Decode SURF/VOL refinement tags from filenames / shape names |
| `openfoamVersion` | string | no | `"2506"` | Written into generated file headers |

---

### `backgroundMesh`

Controls generation of `system/blockMeshDict` — the uniform hex background mesh that snappyHexMesh refines. Bounding box is derived automatically from the reference STL via trimesh.

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `referenceGeometry` | string | **yes** | — | Filename (with extension) from `geometry.files`; must exist in `constant/<geo-dir>/` |
| `baseGrid` | number or `[dx,dy,dz]` | **yes** | — | Base cell size in geometry units. Scalar → isotropic; 3-element array → anisotropic |
| `enlargementFactor` | float | no | `1.1` | Bounding box is expanded: `centre ± factor × half-extent`. Must be `> 1` |

**Algorithm**: loads STL with trimesh → computes AABB → expands by `enlargementFactor` → snaps `maxCoords` outward to nearest exact multiple of `baseGrid` → `n = ceil(length / baseGrid)`.

**Choosing baseGrid**: snappyHexMesh halves the cell size at each refinement level:
```
cell size at level N = baseGrid / 2^N
```
For clean sizes at every level: `baseGrid = finest_cell_size × 2^max_level`

Example: finest cells 0.5 mm at level 5 → `baseGrid = 16 mm`.

---

### `geometry`

Must contain at least one of `files` or `standardShapes`.

#### `geometry.files`

List of STL/OBJ filenames (or path to a text file listing them one per line). All files must reside in `constant/<geometry-folder>/`.

```json
"files": [
    "outer-domain.stl",
    "heat-sink.stl",
    "mosfet.stl"
]
```

Rules:
- Must end in `.stl` or `.obj` (case-insensitive)
- Filename stem (name without extension) becomes the geometry **key** used in `surfaceHandling` and `volumeRefinement`
- Stem must start with a letter (`a–z`, `A–Z`) or underscore — stems starting with a digit are a fatal error
- No `name` field allowed — the key is always derived from the stem

#### `geometry.standardShapes`

Parametric geometry objects that don't need an STL file. Each shape requires `name` and `type`. The `name` becomes the geometry key.

```json
"standardShapes": [
    {
        "name": "hotSpot",
        "type": "searchableSphere",
        "centre": [50, 25, 25],
        "radius": 10
    }
]
```

See [Standard Shape Types](#standard-shape-types) for all nine supported types.

---

### `surfaceHandling`

Optional. Controls which geometry entries appear in `refinementSurfaces` and what refinement/zone settings they carry.

```json
"surfaceHandling": {
    "selectedParts": ["outer-domain", "mosfet", "inductor"],
    "surfaces": {
        "__defaults__": {
            "type": "boundary",
            "refinementLevels": [1, 2],
            "faceType": "internal"
        },
        "outer-domain": {
            "type": "boundary",
            "refinementLevels": [0, 1],
            "regions": {
                "Inflow":    {"refinementLevels": [1, 2]},
                "Outflow":   {"refinementLevels": [3, 4]},
                "all_walls": {"refinementLevels": [2, 3]}
            }
        },
        "mosfet": {
            "type": "faceZone",
            "refinementLevels": [1, 2],
            "faceZoneName": "fz_mosfet",
            "faceType": "internal"
        },
        "inductor": {
            "type": "faceZone",
            "refinementLevels": [1, 4],
            "faceZoneName": "fz_inductor",
            "faceType": "internal",
            "cellZoneInside": "inside",
            "cellZoneName": "cz_inductor"
        }
    }
}
```

**`selectedParts`**: array of geometry keys to include. When `extractRefinementFromNames: true`, entries with `SURF_` prefix are auto-included — `selectedParts` is then only needed for non-encoded entries and for encoded entries that need explicit overrides.

**`__defaults__`**: fallback values applied to every selected part. Forbidden in `__defaults__`: `faceZoneName`, `cellZoneName`, `regions`.

**Resolution order** (later wins):
```
__defaults__
  └─ decoded values from encoded filename (if extractRefinementFromNames=true)
       └─ explicit per-surface entry
```

**Per-surface fields**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | string | yes | `"boundary"` or `"faceZone"` |
| `refinementLevels` | `[min, max]` | yes | Surface refinement level range |
| `faceZoneName` | string | no | Face zone name (defaults to clean surface name) |
| `faceType` | string | no | `"internal"`, `"baffle"`, or `"boundary"` |
| `cellZoneInside` | string | no | `"inside"` or `"outside"` — activates a cell zone |
| `cellZoneName` | string | no | Cell zone name (defaults to `faceZoneName`) |
| `regions` | dict | no | Per-solid-region refinement overrides for multi-region STLs |

**Multi-region STLs**: keys in `regions` must exactly match the solid names in the STL file (case-sensitive). Each region entry supports only `refinementLevels`.

```json
"regions": {
    "Inflow":    {"refinementLevels": [1, 2]},
    "Outflow":   {"refinementLevels": [3, 4]},
    "all_walls": {"refinementLevels": [2, 3]}
}
```

---

### `volumeRefinement`

Optional. Controls which geometry entries appear in `refinementRegions` and what refinement mode/level they use.

```json
"volumeRefinement": {
    "selectedParts": ["outer-domain", "heat-sink", "hotSpot"],
    "regions": {
        "__defaults__": {
            "mode": "inside",
            "level": 2
        },
        "outer-domain": {"level": 0},
        "heat-sink": {
            "mode": "distance",
            "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
        },
        "hotSpot": {"level": 4}
    }
}
```

**Resolution order** (later wins):
```
__defaults__
  └─ decoded values from encoded name (if extractRefinementFromNames=true)
       └─ explicit per-region entry
```

**Per-region fields**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `mode` | string | yes (or via `__defaults__`) | `"inside"`, `"outside"`, or `"distance"` |
| `level` | int | for `inside`/`outside` | Refinement level |
| `levels` | array | for `distance` | `[[distance, level], ...]` pairs |

---

## Standard Shape Types

Nine parametric shape types are supported. All shapes can be used in `surfaceHandling` and `volumeRefinement`.

| Type | Required Parameters |
|---|---|
| `searchableBox` | `min: [x,y,z]`, `max: [x,y,z]` |
| `searchableSphere` | `centre: [x,y,z]`, `radius: N` |
| `searchableCylinder` | `point1: [x,y,z]`, `point2: [x,y,z]`, `radius: N` |
| `searchableCone` | `point1`, `point2`, `radius1`, `radius2`, `innerRadius1`, `innerRadius2` |
| `searchableRotatedBox` | `span: [x,y,z]`, `origin: [x,y,z]`, `e1: [x,y,z]`, `e3: [x,y,z]` |
| `searchableDisk` | `origin: [x,y,z]`, `normal: [x,y,z]`, `radius: N` |
| `searchablePlate` | `origin: [x,y,z]`, `span: [x,y,z]` (exactly one zero component) |
| `searchablePlane` | `planeType: "pointAndNormal"\|"embeddedPoints"\|"planeEquation"` + type-specific fields |
| `searchableSurfaceWithGaps` | `surface: "geom-name"`, `gap: N` |

### Examples

```json
// Axis-aligned box refinement zone
{"name": "fineBox", "type": "searchableBox", "min": [0,0,0], "max": [100,50,50]}

// Sphere hotspot
{"name": "hotSpot", "type": "searchableSphere", "centre": [50,25,25], "radius": 10}

// Cylinder for pipe or jet
{"name": "pipe", "type": "searchableCylinder",
 "point1": [0,25,25], "point2": [100,25,25], "radius": 5}

// Rotated box (arbitrary orientation)
{"name": "rotZone", "type": "searchableRotatedBox",
 "span": [100,50,30], "origin": [10,5,0], "e1": [1,0,0], "e3": [0,0,1]}

// Infinite plane (symmetry)
{"name": "symPlane", "type": "searchablePlane",
 "planeType": "pointAndNormal", "basePoint": [50,0,25], "normal": [0,1,0]}
```

---

## Surface Types

| Goal | `type` | Extra fields needed |
|---|---|---|
| Patch refinement only | `boundary` | `refinementLevels` |
| Internal face zone (no solid) | `faceZone` | `refinementLevels`, `faceZoneName`, `faceType` |
| Solid region (face + cell zones) | `faceZone` | above + `cellZoneInside`, `cellZoneName` |

### `boundary`

Standard OpenFOAM patch. No faceZone or cellZone is created.

```json
"outer-domain": {
    "type": "boundary",
    "refinementLevels": [0, 1]
}
```

### `faceZone` (no cellZone)

Creates a face zone tracking the surface. Useful for baffles, internal interfaces, or boundary conditions on internal surfaces.

```json
"mosfet": {
    "type": "faceZone",
    "refinementLevels": [1, 2],
    "faceZoneName": "fz_mosfet",
    "faceType": "internal"
}
```

`faceType` options:
- `"internal"` — face zone with internal connectivity
- `"baffle"` — creates a baffle (two boundary patches back-to-back)
- `"boundary"` — treated as a boundary patch

### `faceZone` + `cellZone`

Adding `cellZoneInside` creates a cell zone marking all cells inside (or outside) the closed surface. Used for solid component regions in CHT, porous media, etc.

```json
"inductor": {
    "type": "faceZone",
    "refinementLevels": [1, 4],
    "faceZoneName": "fz_inductor",
    "faceType": "internal",
    "cellZoneInside": "inside",
    "cellZoneName": "cz_inductor"
}
```

The surface must be **closed and watertight** when using `cellZoneInside`. Open surfaces with holes will cause snappyHexMesh to fail or produce incorrect results — validate with `surfaceCheck` first.

---

## Volume Refinement Modes

| Mode | Use case | Required field |
|---|---|---|
| `inside` | Refine all cells inside a closed surface | `level: N` |
| `outside` | Refine all cells outside a closed surface | `level: N` |
| `distance` | Progressive refinement based on distance from surface | `levels: [[d, l], ...]` |

### Distance mode

Pairs are `[distance, level]`. Reading `[[0.5, 6], [2.0, 4], [5.0, 2]]`: within 0.5 units → level 6; within 2.0 units → level 4; within 5.0 units → level 2.

```json
"heat-sink": {
    "mode": "distance",
    "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
}
```

Distance mode **cannot be encoded** in the filename — always specify it explicitly in `volumeRefinement.regions`.

---

## Filename Encoding Convention

When `settings.extractRefinementFromNames: true`, refinement parameters can be embedded directly in the filename stem (for files) or the `name` field (for standard shapes). The generator decodes them automatically.

### Format

```
[SURF_(BND|FZ|FZ_CZ)_L<min>_L<max>_][VOL_(IN|OUT)_L<level>_]<cleanName>
```

Both blocks are optional, but any string that starts with `SURF_` or `VOL_` must match the full expected pattern — partial matches are a fatal error.

### SURF Block Tags

| Tag | Surface type | Levels |
|---|---|---|
| `SURF_BND_L<min>_L<max>_` | `boundary` | `[min, max]` |
| `SURF_FZ_L<min>_L<max>_` | `faceZone` | `[min, max]` |
| `SURF_FZ_CZ_L<min>_L<max>_` | `faceZone` + `cellZoneInside: inside` | `[min, max]` |

### VOL Block Tags

| Tag | Volume mode | Level |
|---|---|---|
| `VOL_IN_L<level>_` | `inside` | `<level>` |
| `VOL_OUT_L<level>_` | `outside` | `<level>` |

### Decoding Examples

| Filename stem | Surface | Volume | Clean name |
|---|---|---|---|
| `outer-domain` | none | none | `outer-domain` |
| `SURF_BND_L0_L1_outer-domain` | boundary, [0, 1] | — | `outer-domain` |
| `SURF_FZ_L1_L2_mosfet` | faceZone, [1, 2] | — | `mosfet` |
| `VOL_IN_L4_PCB-board-bottom` | — | inside, 4 | `PCB-board-bottom` |
| `SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor` | faceZone+cellZone, [1, 4] | inside, 3 | `myInductor` |

### Auto-selection behaviour

When `extractRefinementFromNames: true`:
- `SURF_*` entries → automatically included in `refinementSurfaces`
- `VOL_*` entries → automatically included in `refinementRegions`
- Entries with both prefixes → included in both
- **`selectedParts` is still required** for non-encoded entries and encoded entries that need explicit overrides in `surfaces`/`regions`
- When providing an override, use the **full encoded name** as the key (e.g. `"SURF_FZ_L1_L2_mosfet"`, not `"mosfet"`)
- The **clean name** (prefix-stripped) is used in the generated `snappyHexMeshDict`

### Customising the encoding convention

The prefix tokens are defined in `encodingConvention` (defaults in `defaults.json`, overridable per case):

```json
"encodingConvention": {
    "surfacePrefix": "SURF",
    "volumePrefix":  "VOL",
    "boundary":      "BND",
    "faceZone":      "FZ",
    "cellZone":      "CZ"
}
```

All values must be uppercase strings (`A–Z` and `0–9` only). The combined faceZone+cellZone tag is `{faceZone}_{cellZone}` (e.g. `FZ_CZ`). The volume mode tags `IN`/`OUT` are fixed and not configurable.

---

## AUTO\_ — Automatic Level Derivation

The `AUTO_` prefix derives refinement levels automatically from geometry analysis using trimesh — no level numbers are specified in the filename.

**Prerequisite**: `settings.extractRefinementFromNames: true` must be set.

### Format

```
AUTO_SURF_(BND|FZ|FZ_CZ)_[VOL_(IN|OUT)_]<cleanName>.<ext>
AUTO_VOL_(IN|OUT)_<cleanName>.<ext>
```

Level numbers (`_L<n>_`) must **not** appear — including them is a fatal error.

### Examples

| Filename | Surface | Volume | Clean name |
|---|---|---|---|
| `AUTO_SURF_FZ_CZ_VOL_IN_mosfet.stl` | faceZone+cellZone, auto | inside, auto | `mosfet` |
| `AUTO_SURF_BND_outer.stl` | boundary, auto | — | `outer` |
| `AUTO_VOL_IN_PCB-board.stl` | — | inside, auto | `PCB-board` |

### How levels are derived (`derive_snappy_levels`)

For each AUTO_-encoded file:

1. **Load** `constant/<geo-dir>/<filename>` with trimesh and process the mesh.
2. **Characteristic length** (`char_length`):
   - Closed compact mesh (sphericity > 0.6): `V^(1/3)`
   - Closed flat/elongated mesh (sphericity ≤ 0.6): `gapMultiplier × V/A` (hydraulic diameter)
   - Open mesh: `min(sqrt(A), max_edge_length)` — a warning is printed; results may be less accurate.
3. **Surface min level** — stricter of two floors:
   - `char_length / surfaceResolutionCells` (proportional to geometry scale)
   - `median_bbox_dim / minCellsAcross` (bounding-box floor)
4. **Surface max level** — most demanding of:
   - Sharp feature edges (dihedral > `featureAngle`), grouped into tessellation-invariant curves; curves shorter than `char_length / noiseRatio` are discarded as CAD noise; 10th percentile of remaining curve lengths drives the level.
   - Smooth curvature (Gaussian curvature at non-feature vertices); 10th percentile of radius of curvature drives the level.
   - Capped at `surface_min + maxLevelGap`.
5. **Volume level**: `char_length / volumeResolutionCells`, capped at `surface_min`.

### `autoRefinementParams` fields

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `surfaceResolutionCells` | float | **yes** | — | Cells per `char_length` for `surface_min`. Typical range: 3–10 |
| `featureResolutionCells` | float | no | `2.0` | Cells per feature curve/curvature radius for `surface_max` |
| `volumeResolutionCells` | float | no | `10.0` | Cells across `char_length` for volume level |
| `featureAngle` | float | no | `30.0` | Dihedral angle threshold (°) for sharp feature edges |
| `noiseRatio` | float | no | `20.0` | Feature curves shorter than `char_length / noiseRatio` are discarded |
| `maxLevelGap` | int | no | `3` | Cap on `surface_max − surface_min` |
| `minCellsAcross` | int | no | `10` | Min cells across median bbox dimension; `0` disables |
| `gapMultiplier` | float | no | `3.0` | Hydraulic-diameter safety factor for flat/elongated shapes |

For anisotropic `baseGrid [dx, dy, dz]`, the minimum value is used as `base_grid_size` (most conservative — gives highest levels).

AUTO_-encoded entries are **always auto-selected** — listing them in `selectedParts` is not required. They can still have explicit overrides in `surfaces`/`regions` without being in `selectedParts`.

```json
"surfaces": {
    "AUTO_SURF_FZ_CZ_VOL_IN_mosfet": {
        "faceZoneName": "fz_mosfet",
        "cellZoneName": "cz_mosfet"
    }
}
```

---

## Default Solver Parameters (defaults.json)

These are the out-of-the-box values. Override any key in `snappy_inputs.json`.

### `castellatedMeshControls`

| Parameter | Default | Notes |
|---|---|---|
| `maxLocalCells` | `100000000` | Max cells per processor during castellated mesh |
| `maxGlobalCells` | `300000000` | Max total cells; triggers early termination if exceeded |
| `minRefinementCells` | `10` | Minimum cells to refine at a level before stopping |
| `maxLoadUnbalance` | `0.1` | Max fractional load imbalance between processors |
| `resolveFeatureAngle` | `30` | Angle (°) to resolve feature lines |
| `nCellsBetweenLevels` | `2` | Buffer cells between two refinement levels |
| `allowFreeStandingZoneFaces` | `true` | Allow face zones not on a boundary |
| `locationInMesh` | **required** | A point `[x, y, z]` guaranteed to be inside the mesh domain (not in any solid) |

### `snapControls`

| Parameter | Default | Notes |
|---|---|---|
| `nSmoothPatch` | `3` | Smoothing iterations on the patch |
| `nSmoothInternal` | `5` | Smoothing iterations on internal points |
| `tolerance` | `2` | Snapping tolerance relative to local cell size |
| `nSolveIter` | `30` | Solver iterations per snap iteration |
| `nRelaxIter` | `5` | Relaxation iterations |
| `nFeatureSnapIter` | `10` | Feature snapping iterations |
| `implicitFeatureSnap` | `true` | Snap to features without `.eMesh` file |
| `explicitFeatureSnap` | `false` | Snap to features from `.eMesh` file (requires `surfaceFeatureExtract`) |
| `multiRegionFeatureSnap` | `false` | Snap across multiple regions simultaneously |

### `addLayersControls`

| Parameter | Default | Notes |
|---|---|---|
| `relativeSizes` | `true` | Layer thicknesses are relative to local undistorted cell size |
| `expansionRatio` | `1.2` | Thickness ratio between successive layers |
| `finalLayerThickness` | `0.1` | Thickness of the outermost layer (relative) |
| `featureAngle` | `180` | Angle (°) above which no layers are added |
| `slipFeatureAngle` | `30` | Angle below which layers are allowed to slip |
| `nGrow` | `0` | Extra cells grown around patches without layers |
| `nBufferCellsNoExtrude` | `0` | Buffer zone around patches without extrusion |
| `minMedialAxisAngle` | `90` | Min angle between medial axis and feature edge |
| `maxFaceThicknessRatio` | `0.3` | Max thickness ratio on a face |
| `maxThicknessToMedialRatio` | `0.3` | Max ratio of layer thickness to medial axis distance |
| `minThickness` | `0.0001` | Minimum absolute layer thickness |
| `nLayerIter` | `50` | Max layer addition iterations |
| `nRelaxIter` | `5` | Relaxation iterations per layer iteration |
| `nSmoothSurfaceNormals` | `5` | Surface normal smoothing iterations |
| `nSmoothNormals` | `30` | Interior normal smoothing iterations |
| `nSmoothThickness` | `10` | Thickness smoothing iterations |
| `nRelaxedIter` | `50` | Max relaxed iterations |
| `nMedialAxisIter` | `10` | Medial axis iterations |

### `meshQualityControls`

| Parameter | Default | Notes |
|---|---|---|
| `maxNonOrtho` | `65` | Max non-orthogonality (°) |
| `maxBoundarySkewness` | `20` | Max boundary face skewness |
| `maxInternalSkewness` | `4` | Max internal face skewness |
| `maxConcave` | `80` | Max concavity (°) |
| `minFlatness` | `0.5` | Min face flatness |
| `minVol` | `1e-40` | Min cell volume |
| `minTetQuality` | `-1e-30` | Min tet quality |
| `minArea` | `-1` | Min face area (negative = no limit) |
| `minTwist` | `0.02` | Min face twist |
| `minDeterminant` | `0.001` | Min cell determinant |
| `minFaceWeight` | `0.05` | Min face interpolation weight |
| `minVolRatio` | `0.01` | Min volume ratio |
| `minTriangleTwist` | `-1` | Min triangle twist (negative = no limit) |
| `minEdgeLength` | `-1` | Min edge length (negative = no limit) |
| `relaxed.maxNonOrtho` | `70` | Relaxed non-ortho limit during failed iterations |
| `nSmoothScale` | `4` | Quality smoothing iterations |
| `errorReduction` | `0.75` | Error reduction factor per smoothing pass |

### `settings` (in defaults.json)

| Parameter | Default |
|---|---|
| `extractRefinementFromNames` | `false` |
| `addLayers` | `false` |
| `mergeTolerance` | `1e-06` |

### `backgroundMesh` (in defaults.json)

| Parameter | Default |
|---|---|
| `enlargementFactor` | `1.1` |

### `encodingConvention`

| Token | Default |
|---|---|
| `surfacePrefix` | `"SURF"` |
| `volumePrefix` | `"VOL"` |
| `boundary` | `"BND"` |
| `faceZone` | `"FZ"` |
| `cellZone` | `"CZ"` |

### `autoRefinementParams` (defaults)

| Parameter | Default |
|---|---|
| `featureResolutionCells` | `2.0` |
| `volumeResolutionCells` | `10.0` |
| `featureAngle` | `30.0` |
| `noiseRatio` | `20.0` |
| `maxLevelGap` | `3` |
| `minCellsAcross` | `10` |
| `gapMultiplier` | `3.0` |

---

## Refinement Level Reference

| Level | Cell size (× baseGrid) | Typical use |
|---|---|---|
| 0 | 1× | Outer domain, far-field |
| 1 | 0.5× | Near outer domain walls |
| 2 | 0.25× | Domain interior |
| 3 | 0.125× | Near medium components |
| 4 | 0.0625× | Near detailed components |
| 5 | 0.03125× | Critical surfaces |
| 6+ | < 0.016× | Hot spots, fine geometric features |

Cell size = `baseGrid / 2^level`. Example with `baseGrid = 16 mm`:
```
level 0: 16 mm    level 3: 2 mm
level 1: 8 mm     level 4: 1 mm
level 2: 4 mm     level 5: 0.5 mm
```

---

## Common Errors and Fixes

| Error message | Cause | Fix |
|---|---|---|
| `JSON parse error` | Missing comma, bracket, or quote | Run `python3 -m json.tool snappy_inputs.json` |
| `settings is required` | Missing top-level `settings` dict | Add `"settings": {"geometryUnit": "mm", "addLayers": false, "mergeTolerance": 1e-06}` |
| `geometry must be a dict` | Old array-style geometry | Replace with `"geometry": {"files": [...]}` |
| `must have files or standardShapes` | Both geometry keys absent | Add at least one to `geometry` |
| `file not found at constant/triSurface/` | File doesn't exist at expected path | Verify filename and folder |
| `stem must start with letter or _` | Filename starts with digit/special char | Rename the file |
| `duplicate clean name` | Two files decode to the same clean key | Rename one file |
| `selectedParts references unknown geometry` | Key not in `geometry` | Check spelling and encoding prefix |
| `faceZoneName not allowed in __defaults__` | Forbidden field in defaults section | Move to the explicit per-surface entry |
| `type must be boundary or faceZone` | Typo or wrong case | Use exact lowercase string |
| `mode must be inside, outside, or distance` | Typo | Use exact lowercase string |
| `distance mode requires levels` | Used `level` instead of `levels` | Change to `"levels": [[d, l], ...]` |
| `levels[N] must be [distance, level]` | Level pair is not a 2-element array | Fix to `[distance, level]` format |
| `backgroundMesh.locationInMesh required` | Missing `castellatedMeshControls.locationInMesh` | Add a point `[x, y, z]` inside the fluid domain |
| `AUTO_ requires extractRefinementFromNames: true` | `AUTO_`-prefix file with encoding disabled | Set `"extractRefinementFromNames": true` |
| `surfaceResolutionCells required` | AUTO_ file present but parameter missing | Add `"autoRefinementParams": {"surfaceResolutionCells": 5}` |
| `cellZone fails / incorrect region` | Surface not watertight | Check with `surfaceCheck`; fix open edges in CAD before meshing |

---

## Tips and Best Practices

**Start minimal** — begin with only `settings`, `geometry`, and `backgroundMesh`. Confirm `blockMeshDict` is generated correctly. Then add `surfaceHandling`, then `volumeRefinement`.

**Validate JSON first** — `python3 -m json.tool snappy_inputs.json` catches syntax errors before running the generator.

**Use `__defaults__` for shared settings** — if most surfaces share `type: boundary, refinementLevels: [1, 2]`, put those in `__defaults__` and override only what differs.

**`locationInMesh` must be inside the fluid domain** — place it clearly inside the background mesh but outside any solid geometry. If it falls inside a solid, snappyHexMesh will erase the wrong region.

**cellZone requires a closed, watertight surface** — validate with `surfaceCheck` before meshing. Open meshes produce incorrect or missing cell zones.

**Region keys are case-sensitive** — `regions` dict keys must exactly match the solid names in the STL. To list actual solid names: `grep "^solid" part.stl`.

**Distance refinement for heat sources** — `mode: distance` avoids a sharp level jump at heat sinks and hot spots by grading refinement with distance from the surface.

**Choose `baseGrid` with refinement in mind** — `cell_size = baseGrid / 2^N`. Setting `baseGrid = finest_cell_size × 2^max_level` gives clean, predictable cell sizes at every level.

**Keep clean names unique** — when `extractRefinementFromNames: true`, two filenames that strip to the same clean name are a fatal error. Plan names before encoding.

**Verify the generated output** — after running `setup_snappy.py`, inspect `system/snappyHexMeshDict` to confirm the `geometry`, `refinementSurfaces`, and `refinementRegions` sections are correct before launching `snappyHexMesh`.

**Implicit vs explicit feature snapping** — `implicitFeatureSnap: true` (default) snaps to geometric features without needing `.eMesh` files. Set `explicitFeatureSnap: true` (and run `surfaceFeatureExtract`) for sharper feature capture on complex geometry.

**AUTO_ open mesh warning** — if a geometry file is not watertight, the engine continues with a warning and uses `min(sqrt(A), max_edge_length)` as the characteristic length. Results may be less accurate — verify the derived levels manually and adjust `surfaceResolutionCells` or add explicit overrides.

---

*Source: `configure_snappyHexMeshDict/` — `setup_snappy.py`, `auto_refinement.py`, `encoding_utils.py`, `defaults.json`, `templates/`, and `documentation/`.*
*OpenFOAM target version: 2506.*
