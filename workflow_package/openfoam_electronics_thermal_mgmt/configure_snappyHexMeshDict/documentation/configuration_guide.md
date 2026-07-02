# snappyHexMeshDict Generator — Configuration Guide

Complete reference for the `snappyHexMeshDict` JSON configuration workflow. The generator
(`setup_snappy.py`) reads `snappy_inputs.json` and produces a ready-to-use
`system/snappyHexMeshDict` for OpenFOAM's `snappyHexMesh`.

---

## Table of Contents

1. [Overview](#overview)
2. [Workflow](#workflow)
3. [Quick Start Templates](#quick-start-templates)
   - [Minimal Template](#minimal-template)
   - [Full Template](#full-template)
4. [settings](#settings)
5. [geometry](#geometry)
   - [geometry.files](#geometryfiles)
   - [geometry.standardShapes](#geometrystandardshapes)
6. [backgroundMesh](#backgroundmesh)
7. [castellatedMeshControls](#castellatedmeshcontrols)
   - [locationInMesh — single point](#locationinmesh--single-point)
   - [locationsInMesh — multiple named points](#locationsinmesh--multiple-named-points)
8. [surfaceHandling](#surfacehandling)
   - [selectedParts](#surfacehandlingselectedparts)
   - [surfaces dict and __defaults__](#surfaces-dict-and-__defaults__)
   - [Surface type: boundary](#surface-type-boundary)
   - [Surface type: faceZone](#surface-type-facezone)
   - [Surface type: faceZone with cellZone](#surface-type-facezone-with-cellzone)
   - [Multi-region surfaces — regions](#multi-region-surfaces--regions)
   - [Multi-region surfaces — namedRegions](#multi-region-surfaces--namedregions)
   - [Resolution order](#resolution-order-for-surface-handling)
   - [autoRefine — Automatic Level Derivation](#autorefine--automatic-level-derivation)
9. [volumeRefinement](#volumerefinement)
   - [selectedParts](#volumerefinementselectedparts)
   - [regions dict and __defaults__](#volumerefinement-regions-dict-and-__defaults__)
   - [Mode: inside and outside](#mode-inside-and-outside)
   - [Mode: distance](#mode-distance)
   - [Resolution order](#resolution-order-for-volume-refinement)
10. [Complete Examples](#complete-examples)
11. [Validation Rules Summary](#validation-rules-summary)
12. [Tips & Best Practices](#tips--best-practices)
13. [Troubleshooting](#troubleshooting)
    - [JSON Validation Errors](#json-validation-errors)
    - [Settings Errors](#settings-errors)
    - [Geometry Errors](#geometry-errors)
    - [backgroundMesh Errors](#backgroundmesh-errors)
    - [surfaceHandling Errors](#surfacehandling-errors)
    - [volumeRefinement Errors](#volumerefinement-errors)
    - [Generated Output Issues](#generated-output-issues)
    - [Testing Your Configuration](#testing-your-configuration)
14. [scriptSettings — GUI-generated block](#scriptsettings--gui-generated-block)
15. [Changelog](#changelog)
16. [Appendix: Encoded Name Convention (Legacy)](#appendix-encoded-name-convention-legacy)

---

## Overview

The generator reads a single JSON file (`snappy_inputs.json`) and produces:

- `system/snappyHexMeshDict` — the primary snappyHexMesh configuration
- `system/blockMeshDict` — background hex mesh derived from a reference geometry
- `system/decomposeParDict` — parallel decomposition config (only when `numCores > 1`)
- `system/controlDict` — minimal controlDict stub for snappyHexMesh runs
- `system/fvSchemes` — minimal fvSchemes stub
- `system/fvSolution` — minimal fvSolution stub

### Generator Features

✅ **Five-section JSON schema** — `settings`, `geometry`, `backgroundMesh`, `surfaceHandling`, `volumeRefinement`

✅ **Automatic `blockMeshDict` generation** (`backgroundMesh`)
- Derives bounding box from any declared geometry file using `trimesh` (no OpenFOAM required)
- Configurable `enlargementFactor` and `baseGrid` (scalar or anisotropic vector)
- Snaps domain extents to exact multiples of the base grid

✅ **Automatic `decomposeParDict` generation** (`settings.numCores`)
- If `numCores > 1`: writes `system/decomposeParDict` using `scotch` decomposition
- If `numCores = 1`: skipped — serial run requires no decomposition

✅ **Flexible location-in-mesh** — supports single `locationInMesh` point or multiple named
   `locationsInMesh` for multi-region cell zone assignment

✅ **Multi-region STL support** — automatically writes `regions {}` blocks to the geometry
   section via `surfaceHandling.surfaces[key].regions` or `namedRegions`

✅ **Surface handling** — `boundary`, `faceZone`, `faceZone`+cellZone surface types with
   `selectedParts` allow-list and `__defaults__` fallbacks

✅ **Volume refinement** — three modes: `inside`, `outside`, `distance`

✅ **Fail-fast validation** — descriptive error messages naming the exact field and value

✅ **Conflict detection** — duplicate raw keys, duplicate clean names, invalid stems

✅ **Encoded name convention** (`extractRefinementFromNames`) — legacy feature; see
   [Appendix](#appendix-encoded-name-convention-legacy)

---

## Workflow

```
1. Create snappy_inputs.json
   └─ Option A: Open tools/snappy_inputs_generator.html in a browser (recommended)
      └─ Configure settings → geometry → surfaceHandling → Download JSON
   └─ Option B: Copy a template from Quick Start and edit by hand

2. Validate JSON syntax
   └─ python3 -m json.tool snappy_inputs.json
   └─ Must complete without errors

3. Check geometry files
   └─ All STL/OBJ files listed in geometry.files must exist in constant/triSurface/

4. Run generator
   └─ python3 setup_snappy.py
   └─ Reads snappy_inputs.json
   └─ Writes system/snappyHexMeshDict (and blockMeshDict, decomposeParDict)

5. Verify output
   └─ Inspect system/snappyHexMeshDict
   └─ Check geometry, refinementSurfaces, refinementRegions sections

6. Run snappyHexMesh
   └─ Serial (numCores=1):  runApplication snappyHexMesh -overwrite
   └─ Parallel (numCores>1): runParallel snappyHexMesh -overwrite
```

---

## Quick Start Templates

### Minimal Template

```json
{
    "settings": {
        "geometryUnit": "mm",
        "numCores": 1,
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
        "locationInMesh": [50, 25, 25]
    },
    "surfaceHandling": {
        "selectedParts": ["outer-domain"],
        "surfaces": {
            "outer-domain": {
                "type": "boundary",
                "refinementLevels": [0, 1]
            }
        }
    }
}
```

### Full Template

```json
{
    "settings": {
        "geometryUnit": "mm",
        "numCores": 4,
        "extractRefinementFromNames": false,
        "addLayers": false,
        "mergeTolerance": 1e-06
    },

    "geometry": {
        "files": ["outer-domain.stl", "heat-sink.stl", "mosfet.stl"],
        "standardShapes": [
            {
                "name": "hotSpot",
                "type": "searchableSphere",
                "centre": [50, 25, 25],
                "radius": 10
            }
        ]
    },

    "backgroundMesh": {
        "referenceGeometry": "outer-domain.stl",
        "baseGrid": 5.0,
        "enlargementFactor": 1.1
    },

    "castellatedMeshControls": {
        "locationInMesh": [50, 25, 25]
    },

    "surfaceHandling": {
        "selectedParts": ["outer-domain", "mosfet", "hotSpot"],
        "surfaces": {
            "__defaults__": {
                "type": "boundary",
                "refinementLevels": [1, 2]
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
                "faceType": "internal",
                "cellZoneInside": "inside",
                "cellZoneName": "cz_mosfet"
            }
        }
    },

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
}
```

---

## `settings`

`settings` is a required top-level dict containing at least `geometryUnit`, `numCores`,
`addLayers`, and `mergeTolerance`.

```json
"settings": {
    "geometryUnit": "mm",
    "numCores": 4,
    "extractRefinementFromNames": false,
    "addLayers": false,
    "mergeTolerance": 1e-06
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `geometryUnit` | string | yes | — | Unit of STL/geometry files. Metadata only — not applied as a scale in snappyHexMeshDict. Use in downstream pipeline scripts for unit conversion |
| `numCores` | int | yes | — | Number of parallel subdomains. Must be ≥ 1. If `1`, no `decomposeParDict` is generated (serial run). If > 1, writes `system/decomposeParDict` |
| `addLayers` | bool | yes | — | Enable boundary layer generation in snappyHexMesh |
| `mergeTolerance` | float | yes | — | Relative surface merging tolerance. `1e-06` works for most cases |
| `extractRefinementFromNames` | bool | no | `false` | Decode SURF/VOL refinement tags from filename stems and shape names. **Not recommended** — see [Appendix](#appendix-encoded-name-convention-legacy) |

**Allowed values for `geometryUnit`:** `"m"`, `"mm"`, `"cm"`, `"um"`, `"in"`, `"ft"`

**`_version` key**: Add `"_version": "1.1"` at the top level of `snappy_inputs.json` to track config compatibility. The generator prints a warning at startup if the version differs from its expected value — useful for catching stale configs after tool upgrades.

---

## `geometry`

`geometry` is a required top-level dict. It must contain at least one of `files` or `standardShapes`.

```json
"geometry": {
    "files": [...],
    "standardShapes": [...]
}
```

---

### `geometry.files`

Accepts two forms:

**1. Inline array of filenames**

```json
"files": ["mosfet.stl", "heatsink.stl", "outer-domain.stl"]
```

**2. Path to a text file** (output of `ls -1 <DIR>`, one filename per line)

```json
"files": "/home/user/case/stl_list.txt"
```

The text file may contain blank lines and `#`-prefixed comments. Each line may be a bare
filename (`foo.stl`) or include a directory prefix (`constant/triSurface/foo.stl`) — both
are normalized to the bare name automatically.

**Rules for each filename**:

- Must end in `.stl` or `.obj` (case-insensitive)
- The filename stem becomes the geometry key used throughout `surfaceHandling` and `volumeRefinement`
- Stem must start with a letter (`a–z`, `A–Z`) or underscore (`_`)
- No `name` field is permitted
- No `regions` in geometry config — named regions are declared via `surfaceHandling` (see [Multi-region surfaces](#multi-region-surfaces--regions))

---

### `geometry.standardShapes`

An array of parametric shape dicts. Each shape requires `name` and `type`. The `name`
becomes the geometry key and must be unique across all geometry entries.

Nine shape types are supported:

#### `searchableBox`

```json
{"name": "refinementBox", "type": "searchableBox", "min": [0, 0, 0], "max": [100, 50, 50]}
```

| Required | Type |
|---|---|
| `min` | `[x, y, z]` |
| `max` | `[x, y, z]` |

#### `searchableSphere`

```json
{"name": "hotSpot", "type": "searchableSphere", "centre": [50, 25, 25], "radius": 10}
```

| Required | Type |
|---|---|
| `centre` | `[x, y, z]` |
| `radius` | number |

#### `searchableCylinder`

```json
{"name": "flowPipe", "type": "searchableCylinder", "point1": [0, 25, 25], "point2": [100, 25, 25], "radius": 5}
```

| Required | Type |
|---|---|
| `point1` | `[x, y, z]` |
| `point2` | `[x, y, z]` |
| `radius` | number |

#### `searchableCone`

```json
{"name": "myCone", "type": "searchableCone", "point1": [0, 0, 0], "point2": [100, 0, 0], "radius1": 20, "radius2": 10}
```

| Field | Required | Type |
|---|---|---|
| `point1` | yes | `[x, y, z]` |
| `point2` | yes | `[x, y, z]` |
| `radius1` | yes | number (outer radius at point1) |
| `radius2` | yes | number (outer radius at point2) |
| `innerRadius1` | no | number (inner radius at point1; omit for solid) |
| `innerRadius2` | no | number (inner radius at point2; omit for solid) |

#### `searchableRotatedBox`

```json
{"name": "rotatedZone", "type": "searchableRotatedBox", "span": [100, 50, 30], "origin": [10, 5, 0], "e1": [1, 0, 0], "e3": [0, 0, 1]}
```

| Required | Type |
|---|---|
| `span` | `[x, y, z]` — dimensions |
| `origin` | `[x, y, z]` — one corner |
| `e1` | `[x, y, z]` — unit vector along span-x direction |
| `e3` | `[x, y, z]` — unit vector along span-z direction |

#### `searchableDisk`

```json
{"name": "coolantInlet", "type": "searchableDisk", "origin": [0, 25, 25], "normal": [1, 0, 0], "radius": 8}
```

| Required | Type |
|---|---|
| `origin` | `[x, y, z]` |
| `normal` | `[x, y, z]` |
| `radius` | number |

#### `searchablePlate`

```json
{"name": "baffle", "type": "searchablePlate", "origin": [50, 0, 0], "span": [0, 50, 30]}
```

| Required | Type | Note |
|---|---|---|
| `origin` | `[x, y, z]` | One corner of the plate |
| `span` | `[x, y, z]` | Extents; exactly one component must be 0 |

#### `searchablePlane`

Three `planeType` variants are supported:

```json
// pointAndNormal
{"name": "sym", "type": "searchablePlane", "planeType": "pointAndNormal", "basePoint": [50, 0, 25], "normal": [0, 1, 0]}

// embeddedPoints
{"name": "sym", "type": "searchablePlane", "planeType": "embeddedPoints", "point1": [0, 0, 0], "point2": [1, 0, 0], "point3": [0, 1, 0]}

// planeEquation (ax + by + cz = d)
{"name": "sym", "type": "searchablePlane", "planeType": "planeEquation", "a": 0, "b": 1, "c": 0, "d": 25}
```

#### `searchableSurfaceWithGaps`

```json
{"name": "mosfetWithGap", "type": "searchableSurfaceWithGaps", "surface": "mosfet", "gap": 0.5}
```

| Required | Type |
|---|---|
| `surface` | string — name of geometry entry to wrap |
| `gap` | number — gap distance |

---

## `backgroundMesh`

`backgroundMesh` is a required top-level dict. It drives generation of `system/blockMeshDict` —
the uniform hex background mesh required by snappyHexMesh. The bounding box is derived
automatically from the reference geometry using the `trimesh` library (no OpenFOAM required).

```json
"backgroundMesh": {
    "referenceGeometry": "outer-domain.stl",
    "baseGrid": 5.0,
    "enlargementFactor": 1.1
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `referenceGeometry` | string | **yes** | — | Filename (with extension) of the geometry to derive the bounding box from. Must be declared in `geometry.files` and exist in `constant/triSurface/` |
| `baseGrid` | number **or** `[dx, dy, dz]` | **yes** | — | Base cell size in geometry units. Scalar → isotropic; 3-element array → anisotropic |
| `enlargementFactor` | float | no | `1.1` | Factor by which the bounding box is expanded around its centre. Must be `> 1` |

**Behaviour**: Loads the reference geometry, computes axis-aligned bounding box, expands
symmetrically by `enlargementFactor`, snaps `maxCoords` to nearest multiple of `baseGrid`,
then writes `system/blockMeshDict` with `simpleGrading (1 1 1)`.

### `baseGrid` and refinement levels

snappyHexMesh halves the cell size at each refinement level:

```
cell size at level N = baseGrid / 2^N
```

For predictable cell sizes at every level:
```
baseGrid = desired_finest_cell_size × 2^max_refinement_level
```

**Example**: finest cells of 0.5 mm at level 5 → `baseGrid = 0.5 × 2^5 = 16 mm`

---

## `castellatedMeshControls`

`castellatedMeshControls` is a required top-level dict. It specifies one or more seed
points inside the mesh domain — snappyHexMesh retains cells reachable from these points.

Two mutually exclusive modes are supported. Having both in the same config is a fatal error.

---

### `locationInMesh` — single point

Use for single-region meshes or when one seed point is sufficient.

```json
"castellatedMeshControls": {
    "locationInMesh": [50, 25, 25]
}
```

- Must be a 3-element list of numbers `[x, y, z]`
- The point must lie inside the mesh domain (not on a surface)
- Use `tools/find_interior_point.py` to find a valid point from any watertight STL
- **Note**: the generator internally offsets each coordinate by `+1e-6` before writing to `snappyHexMeshDict`. This is a safety nudge to avoid snappyHexMesh placing the seed exactly on a face. The value in `snappy_inputs.json` is unchanged.

---

### `locationsInMesh` — multiple named points

Use when snappyHexMesh needs to create multiple named cell zones from a single meshing run.
Each entry provides a seed point and an associated cell zone name.

```json
"castellatedMeshControls": {
    "locationsInMesh": [
        {"point": [50, 25, 25], "name": "fluid_domain"},
        {"point": [10, 10, 5],  "name": "solid_pcb"},
        {"point": [20, 15, 8],  "name": "solid_heatsink"}
    ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `locationsInMesh` | array | yes | Non-empty list of point-name dicts |
| `locationsInMesh[i].point` | `[x, y, z]` | yes | Seed point inside the target zone |
| `locationsInMesh[i].name` | string | yes | Cell zone name to assign to cells reachable from this point |

**Rules**:
- Must be a non-empty list
- Each entry must be a dict with both `point` and `name`
- `point` must be a list of exactly 3 numbers
- `name` must be a non-empty string
- Mutually exclusive with `locationInMesh` — having both is a fatal error
- **Note**: as with `locationInMesh`, each point coordinate is offset by `+1e-6` internally before writing to `snappyHexMeshDict`.

**When to use `locationsInMesh`**: When meshing a multi-body CHT domain in one snappyHexMesh
pass. Each body (fluid, solid PCB, solid heatsink) gets a separate seed point and zone name.
The zones can then be split into separate regions using `splitMeshRegions`.

---

## `surfaceHandling`

`surfaceHandling` is optional. When present it controls which geometry entries appear in
`refinementSurfaces` and what zone/refinement settings they carry.

```json
"surfaceHandling": {
    "selectedParts": ["outer-domain", "mosfet", "hotSpot"],
    "surfaces": {
        "__defaults__": {
            "type": "boundary",
            "refinementLevels": [1, 2]
        },
        "mosfet": {
            "type": "faceZone",
            "refinementLevels": [1, 2],
            "faceZoneName": "fz_mosfet",
            "faceType": "internal"
        }
    }
}
```

---

### `surfaceHandling.selectedParts`

Optional array when `extractRefinementFromNames: true`; required otherwise.

Lists the geometry keys (file stems or shape names) that should appear in
`refinementSurfaces`. Keys must match entries defined in `geometry`.

When `extractRefinementFromNames: true`, any geometry entry whose key carries a `SURF_`
prefix is automatically included — `selectedParts` is then only needed for non-encoded
entries or encoded entries you want to explicitly override.

---

### `surfaces` Dict and `__defaults__`

`surfaces` is an optional dict whose keys are geometry keys. The special key `__defaults__`
provides fallback values applied to every selected part before any explicit entry is merged.

**`__defaults__` forbidden fields**: `faceZoneName`, `cellZoneName`, `regions`, `namedRegions`, `autoRefine`

**Resolution order** (later overrides earlier):
1. `__defaults__`
2. Decoded values from encoded name (if `extractRefinementFromNames: true`)
3. Explicit entry for the geometry key

```json
"surfaces": {
    "__defaults__": {
        "type": "boundary",
        "refinementLevels": [1, 2]
    },
    "transformer": {},            // uses __defaults__ fully
    "mosfet": {
        "type": "faceZone",       // overrides __defaults__.type
        "refinementLevels": [1, 3]
    }
}
```

---

### Surface type: `boundary`

Produces a standard OpenFOAM patch refinement. Only `refinementLevels` is used.

```json
"outer-domain": {
    "type": "boundary",
    "refinementLevels": [0, 1]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | `"boundary"` |
| `refinementLevels` | `[min, max]` | yes* | Surface refinement level range. *Mutually exclusive with `autoRefine`. |
| `autoRefine` | bool | no | Set `true` to have the tool compute `refinementLevels` automatically from the geometry file. Cannot be combined with `refinementLevels`. See [autoRefine](#autorefine--automatic-level-derivation). |

---

### Surface type: `faceZone`

Produces surface refinement **and** creates a named face zone in the mesh.

```json
"mosfet": {
    "type": "faceZone",
    "refinementLevels": [1, 2],
    "faceZoneName": "fz_mosfet",
    "faceType": "internal"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | `"faceZone"` |
| `refinementLevels` | `[min, max]` | yes* | Surface refinement level range. *Mutually exclusive with `autoRefine`. |
| `faceZoneName` | string | no | Name for the face zone (defaults to clean surface name) |
| `faceType` | string | no | `"internal"`, `"baffle"`, or `"boundary"` |
| `autoRefine` | bool | no | Set `true` to compute `refinementLevels` automatically. Cannot be combined with `refinementLevels`. See [autoRefine](#autorefine--automatic-level-derivation). |

---

### Surface type: `faceZone` with cellZone

Adding `cellZoneInside` also creates a cell zone marking all cells inside (or outside) the
closed surface. Use this for solid component regions.

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

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | `"faceZone"` |
| `refinementLevels` | `[min, max]` | yes* | Surface refinement level range. *Mutually exclusive with `autoRefine`. |
| `faceZoneName` | string | no | Face zone name (defaults to clean surface name) |
| `faceType` | string | no | `"internal"`, `"baffle"`, or `"boundary"` |
| `cellZoneInside` | string | yes (activates cell zone) | `"inside"` or `"outside"` |
| `cellZoneName` | string | no | Cell zone name (defaults to `faceZoneName`) |
| `autoRefine` | bool | no | Set `true` to compute `refinementLevels` automatically. Cannot be combined with `refinementLevels`. See [autoRefine](#autorefine--automatic-level-derivation). |

> **Note**: The surface must be a closed, water-tight mesh when using `cellZoneInside`.

---

### Multi-region surfaces — `regions`

An STL file may contain multiple named solid regions (e.g. `Inflow`, `Outflow`, `all_walls`).
Use `regions` when different solid regions need different refinement levels.

```json
"outer-domain": {
    "type": "boundary",
    "refinementLevels": [0, 1],
    "regions": {
        "Inflow":    {"refinementLevels": [1, 2]},
        "Outflow":   {"refinementLevels": [3, 4]},
        "all_walls": {"refinementLevels": [2, 3]}
    }
}
```

The tool automatically writes the `regions {}` block to the geometry section of
`snappyHexMeshDict` using the dict keys as solid names.

**Rules**:
- Keys are the exact solid names as they appear in the STL file (case-sensitive)
- Each region entry supports only `refinementLevels`
- `regions` is not allowed in `__defaults__`

---

### Multi-region surfaces — `namedRegions`

Use `namedRegions` when all solid regions share the same refinement level (set via the
surface-level `refinementLevels`) but still need to be declared in the geometry block.

```json
"pipe-geom": {
    "type": "boundary",
    "refinementLevels": [0, 1],
    "namedRegions": ["inlet", "outlet", "left_wall", "right_wall", "outer_wall"]
}
```

This writes the `regions {}` block in the geometry section for each listed name, but does
**not** produce per-region entries in `refinementSurfaces` — all regions inherit the
surface-level `refinementLevels`.

**Rules**:
- Must be a list of non-empty strings matching the exact solid names in the STL file
- `namedRegions` is not allowed in `__defaults__`
- If both `regions` and `namedRegions` are present, `namedRegions` takes priority for
  the geometry block (the `regions` dict still controls refinement levels)

> **Tip**: Use `grep "^solid" part.stl` to list the actual solid names in an STL file.

---

### Resolution Order for Surface Handling

```
__defaults__
  └─ decoded values from encoded name (if extractRefinementFromNames=true)
       └─ explicit entry for the geometry key
```

---

### `autoRefine` — Automatic Level Derivation

Instead of manually specifying `refinementLevels` or `level`, set `"autoRefine": true` on any surface or volume region entry. The tool analyses the geometry file and derives appropriate levels automatically.

**Surface entry example:**

```json
"mosfet": {
    "type": "faceZone",
    "autoRefine": true,
    "faceZoneName": "fz_mosfet",
    "faceType": "internal",
    "cellZoneInside": "inside",
    "cellZoneName": "cz_mosfet"
}
```

**Volume region entry example:**

```json
"volumeRefinement": {
    "selectedParts": ["mosfet"],
    "regions": {
        "mosfet": {"autoRefine": true}
    }
}
```

**Rules:**

- `autoRefine: true` and `refinementLevels` (or `level`) are **mutually exclusive** — providing both is a fatal error.
- Not supported for `geometry.standardShapes` — only file-based geometry (`.stl`/`.obj`).
- Not allowed in `__defaults__`.
- When `autoRefine: true` is used, levels are computed using `autoRefinementParams` (all fields have defaults in `defaults.json`; override in `snappy_inputs.json` if needed — see the [Appendix `autoRefinementParams` table](#autorefinementparams-fields)).

**Write-back**: After computing levels, the tool **modifies `snappy_inputs.json` in-place**: the `autoRefine: true` key is removed and replaced with the concrete `refinementLevels`/`level` values. Subsequent runs then use the written-back values directly (no re-computation).

---

## `volumeRefinement`

`volumeRefinement` is optional. When present it controls which geometry entries appear in
`refinementRegions` and what refinement mode/level they use.

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

---

### `volumeRefinement.selectedParts`

Optional array when `extractRefinementFromNames: true`; required otherwise.

Lists the geometry keys to include in `refinementRegions`. When
`extractRefinementFromNames: true`, any geometry entry whose key carries a `VOL_` prefix
is automatically included — `selectedParts` is then only needed for non-encoded entries.

---

### `volumeRefinement` regions dict and `__defaults__`

`regions` is an optional dict whose keys are geometry keys. `__defaults__` provides fallback
mode and level for all selected parts.

**Resolution order** (later wins):
1. `__defaults__`
2. Decoded values from encoded name (if `extractRefinementFromNames: true`)
3. Explicit entry for the geometry key

---

### Mode: `inside` and `outside`

Refine all cells inside (or outside) a closed surface to a fixed level.

```json
"__defaults__": {
    "mode": "inside",
    "level": 2
},
"hotSpot": {"level": 4},
"outer-domain": {"mode": "inside", "level": 0}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | string | yes (or via `__defaults__`) | `"inside"` or `"outside"` |
| `level` | int | yes* | Refinement level. *Mutually exclusive with `autoRefine`. |
| `autoRefine` | bool | no | Set `true` to compute `level` automatically. Cannot be combined with `level`. See [autoRefine](#autorefine--automatic-level-derivation). |

---

### Mode: `distance`

Progressively refine cells based on their distance from the surface. Pairs are
`[distance, level]` — at each distance threshold, cells within that distance get at
least that refinement level.

```json
"heat-sink": {
    "mode": "distance",
    "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
}
```

Reading this: within 0.5 units → level 6; within 2.0 units → level 4; within 5.0 units → level 2.

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | string | yes | `"distance"` |
| `levels` | array | yes | Non-empty array of `[distance, level]` pairs |

---

### Resolution Order for Volume Refinement

Same pattern as surface handling — `__defaults__` → decoded → explicit. **Distance mode
cannot be encoded** — provide it explicitly in `volumeRefinement.regions` regardless of
whether `extractRefinementFromNames` is active.

---

## Complete Examples

### Example 1: Single-region with multi-region STL

```json
{
    "settings": {
        "geometryUnit": "mm",
        "numCores": 1,
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": {
        "files": ["pipe-geom.stl"]
    },
    "backgroundMesh": {
        "referenceGeometry": "pipe-geom.stl",
        "baseGrid": 5.0
    },
    "castellatedMeshControls": {
        "locationInMesh": [50, 25, 25]
    },
    "surfaceHandling": {
        "selectedParts": ["pipe-geom"],
        "surfaces": {
            "pipe-geom": {
                "type": "boundary",
                "refinementLevels": [0, 1],
                "namedRegions": ["inlet", "outlet", "left_wall", "right_wall", "outer_wall"]
            }
        }
    }
}
```

---

### Example 2: Multi-region CHT with locationsInMesh

```json
{
    "settings": {
        "geometryUnit": "mm",
        "numCores": 4,
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": {
        "files": ["outer-domain.stl", "heatsink.stl", "mosfet.stl"]
    },
    "backgroundMesh": {
        "referenceGeometry": "outer-domain.stl",
        "baseGrid": 8.0
    },
    "castellatedMeshControls": {
        "locationsInMesh": [
            {"point": [50, 25, 25], "name": "fluid_domain"},
            {"point": [10, 10, 5],  "name": "solid_heatsink"},
            {"point": [20, 15, 8],  "name": "solid_mosfet"}
        ]
    },
    "surfaceHandling": {
        "selectedParts": ["outer-domain", "heatsink", "mosfet"],
        "surfaces": {
            "__defaults__": {
                "type": "boundary",
                "refinementLevels": [1, 2]
            },
            "outer-domain": {
                "type": "boundary",
                "refinementLevels": [0, 1],
                "regions": {
                    "Inflow":    {"refinementLevels": [1, 2]},
                    "Outflow":   {"refinementLevels": [1, 2]},
                    "all_walls": {"refinementLevels": [1, 2]}
                }
            },
            "heatsink": {
                "type": "faceZone",
                "refinementLevels": [1, 4],
                "faceZoneName": "fz_heatsink",
                "faceType": "internal",
                "cellZoneInside": "inside",
                "cellZoneName": "cz_heatsink"
            },
            "mosfet": {
                "type": "faceZone",
                "refinementLevels": [1, 4],
                "faceZoneName": "fz_mosfet",
                "faceType": "internal",
                "cellZoneInside": "inside",
                "cellZoneName": "cz_mosfet"
            }
        }
    },
    "volumeRefinement": {
        "selectedParts": ["outer-domain", "heatsink", "mosfet"],
        "regions": {
            "__defaults__": {"mode": "inside", "level": 2},
            "outer-domain": {"level": 0},
            "heatsink": {
                "mode": "distance",
                "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
            },
            "mosfet": {"level": 4}
        }
    }
}
```

---

### Example 3: Full explicit configuration (all features)

```json
{
    "settings": {
        "geometryUnit": "mm",
        "numCores": 8,
        "extractRefinementFromNames": false,
        "addLayers": false,
        "mergeTolerance": 1e-06
    },

    "geometry": {
        "files": [
            "outer-domain.stl",
            "PCB-board-bottom.stl",
            "heat-sink-to-252-1.stl",
            "transformer.stl",
            "mosfet.stl",
            "pcb_board.stl",
            "inductor.stl"
        ],
        "standardShapes": [
            {
                "name": "hotSpot",
                "type": "searchableSphere",
                "centre": [50, 25, 25],
                "radius": 10
            },
            {
                "name": "flowPipe",
                "type": "searchableCylinder",
                "point1": [0, 25, 25],
                "point2": [100, 25, 25],
                "radius": 5
            }
        ]
    },

    "backgroundMesh": {
        "referenceGeometry": "outer-domain.stl",
        "baseGrid": [8.0, 4.0, 8.0],
        "enlargementFactor": 1.15
    },

    "castellatedMeshControls": {
        "locationInMesh": [50, 25, 25]
    },

    "surfaceHandling": {
        "selectedParts": [
            "outer-domain", "transformer", "mosfet", "pcb_board", "inductor", "flowPipe"
        ],
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
            "pcb_board": {
                "type": "faceZone",
                "refinementLevels": [1, 4],
                "faceZoneName": "fz_pcb_board",
                "faceType": "baffle"
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
    },

    "volumeRefinement": {
        "selectedParts": [
            "outer-domain", "PCB-board-bottom", "heat-sink-to-252-1", "inductor", "hotSpot"
        ],
        "regions": {
            "__defaults__": {
                "mode": "inside",
                "level": 2
            },
            "outer-domain":       {"level": 0},
            "PCB-board-bottom":   {"level": 4},
            "heat-sink-to-252-1": {
                "mode": "distance",
                "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
            },
            "inductor":           {"level": 3},
            "hotSpot":            {"level": 4}
        }
    }
}
```

---

## Validation Rules Summary

| Rule | Scope | Error type |
|---|---|---|
| `settings` must be a dict | Top level | fatal |
| `settings.addLayers` required and bool | `settings` | fatal |
| `settings.mergeTolerance` required and float | `settings` | fatal |
| `settings.numCores` required, positive integer | `settings` | fatal |
| `settings.extractRefinementFromNames` must be bool if present | `settings` | fatal |
| `geometry` must be a dict | Top level | fatal |
| `geometry` must have `files` or `standardShapes` | `geometry` | fatal |
| Each filename must end in `.stl` or `.obj` | `geometry.files` | fatal |
| Filename stem must start with letter or `_` | `geometry.files` | fatal |
| `name` and `type` required for each standard shape | `geometry.standardShapes` | fatal |
| Shape type must be one of 9 valid types | `geometry.standardShapes` | fatal |
| Shape-specific required params must be present | per shape | fatal |
| `searchablePlate.span` must have exactly one zero | `searchablePlate` | fatal |
| No duplicate raw geometry key | `geometry` | fatal |
| No duplicate clean name | `geometry` | fatal |
| `castellatedMeshControls` must have `locationInMesh` or `locationsInMesh` | `castellatedMeshControls` | fatal |
| Having both `locationInMesh` and `locationsInMesh` is forbidden | `castellatedMeshControls` | fatal |
| `locationInMesh` must be a 3-number list | `castellatedMeshControls` | fatal |
| `locationsInMesh` must be a non-empty list of `{point, name}` dicts | `castellatedMeshControls` | fatal |
| Each `locationsInMesh[i].point` must be a 3-number list | `castellatedMeshControls` | fatal |
| Each `locationsInMesh[i].name` must be a non-empty string | `castellatedMeshControls` | fatal |
| `surfaceHandling.selectedParts` required if `surfaceHandling` present and `extractRefinementFromNames: false` | `surfaceHandling` | fatal |
| Every item in `selectedParts` must match a geometry key | `surfaceHandling` / `volumeRefinement` | fatal |
| `surfaces[name]` must be a dict | `surfaceHandling.surfaces` | fatal |
| `type` must be `"boundary"` or `"faceZone"` | per surface | fatal |
| `refinementLevels` must be `[min, max]` | per surface / region | fatal |
| `faceType` must be `"internal"`, `"baffle"`, or `"boundary"` if present | per surface | fatal |
| `cellZoneInside` must be `"inside"` or `"outside"` if present | per surface | fatal |
| `regions` in surface entry must be a dict | per surface | fatal |
| Region entry supports only `refinementLevels` | per region | fatal |
| `namedRegions` in surface entry must be a list of non-empty strings | per surface | fatal |
| `faceZoneName`, `cellZoneName`, `regions`, `namedRegions` forbidden in `__defaults__` | `surfaceHandling` | fatal |
| `autoRefine` forbidden in `__defaults__` | `surfaceHandling` / `volumeRefinement` | fatal |
| `autoRefine: true` and `refinementLevels`/`level` are mutually exclusive | per surface / volume region | fatal |
| `autoRefine: true` not supported for standard shapes | per surface / volume region | fatal |
| `volumeRefinement.selectedParts` required if `volumeRefinement` present and `extractRefinementFromNames: false` | `volumeRefinement` | fatal |
| `mode` must be `"inside"`, `"outside"`, or `"distance"` | per volume region | fatal |
| `inside`/`outside` mode requires `level` | per volume region | fatal |
| `distance` mode requires `levels` | per volume region | fatal |
| `levels` must be a non-empty array | `distance` mode | fatal |
| Each `levels` entry must be `[distance, level]` | `distance` mode | fatal |
| `backgroundMesh` required | `backgroundMesh` | fatal |
| `backgroundMesh.referenceGeometry` must be listed in `geometry.files` | `backgroundMesh` | fatal |
| `backgroundMesh.baseGrid` must be a positive number or `[dx, dy, dz]` | `backgroundMesh` | fatal |
| `backgroundMesh.enlargementFactor` must be a number `> 1` if present | `backgroundMesh` | fatal |

---

## Tips & Best Practices

**Start minimal**: begin with only `settings`, `geometry`, and `backgroundMesh`. Add
`surfaceHandling` once geometry loads correctly, then add `volumeRefinement`.

**Use `__defaults__` for shared settings**: if most surfaces share `type: boundary` and
`refinementLevels: [1, 2]`, put those in `__defaults__` and only override what differs.

**`selectedParts` as an allow-list**: only parts listed in `selectedParts` get surface or
volume refinement. Parts present in `geometry` but not in `selectedParts` appear in the
geometry block only.

**Distance refinement for heat sources**: use `mode: distance` for heat sinks and hot spots
to get fine cells near the surface and coarser cells farther away.

**cellZone requires a closed surface**: any surface with `cellZoneInside` must be fully
enclosed. Check with `surfaceCheck` before meshing.

**Region keys are case-sensitive**: the `regions` dict key must exactly match the solid name
in the STL file. Use `grep "^solid" part.stl` to list actual solid names.

**namedRegions vs regions**: use `regions` when regions need different refinement levels;
use `namedRegions` when all regions share the same level and you only need the geometry block.

**Choose `baseGrid` with refinement levels in mind**: `cell_size = baseGrid / 2^N`. Setting
`baseGrid = finest_cell_size × 2^max_level` gives clean, predictable cell sizes
(e.g. `baseGrid = 16 mm` for 0.5 mm finest cells at level 5).

**Validate JSON first**: run `python3 -m json.tool snappy_inputs.json` before running the
generator. This catches bracket/comma errors quickly.

**Check the generated output**: after running `setup_snappy.py`, inspect
`system/snappyHexMeshDict` to confirm `geometry`, `refinementSurfaces`, and
`refinementRegions` sections look correct before launching snappyHexMesh.

---

## Troubleshooting

### JSON Validation Errors

#### "Invalid JSON in snappy_inputs.json"

**Debug**: `python3 -m json.tool snappy_inputs.json`

**Common causes**: Missing comma (`{...}{...}` → `{...},{...}`), trailing comma
(`{"a": 1,}` → `{"a": 1}`), unquoted string value, unclosed bracket, `//` comments
(not valid JSON — remove all comments).

---

### Settings Errors

| Error | Cause | Fix |
|---|---|---|
| `settings is required and must be a dict` | Missing `settings` key | Add `"settings": {"geometryUnit": "mm", "numCores": 1, "addLayers": false, "mergeTolerance": 1e-06}` |
| `settings.addLayers is required` | `addLayers` missing from `settings` | Add `"addLayers": false` |
| `settings.mergeTolerance is required` | `mergeTolerance` missing | Add `"mergeTolerance": 1e-06` |
| `settings.numCores is required` | `numCores` missing | Add `"numCores": 4` |
| `settings.numCores must be a positive integer` | `numCores` is `0`, negative, float, or string | Use a whole number ≥ 1 |
| `settings.extractRefinementFromNames must be a boolean` | Value is `"true"` or `1` | Use `true` or `false` (JSON boolean) |

---

### Geometry Errors

| Error | Cause | Fix |
|---|---|---|
| `geometry must be a dict, not an array` | Old (v1) geometry array format | Replace with `"geometry": {"files": [...]}` |
| `geometry must have at least one of 'files' or 'standardShapes'` | Both keys absent | Add at least one |
| `geometry.files must be an array of strings or a string path` | `files` is a dict or non-string array | Use `"files": ["domain.stl"]` |
| `file 'domain.txt' must end in .stl or .obj` | Wrong file extension | Ensure filenames end in `.stl` or `.obj` |
| `filename stem '3d_domain' must start with a letter or underscore` | Stem starts with digit | Rename: `domain_3d.stl` ✓ |
| `duplicate geometry key 'outer-domain'` | Two files have same stem, or file stem equals a shape name | Rename one |

---

### backgroundMesh Errors

| Error | Cause | Fix |
|---|---|---|
| `backgroundMesh.referenceGeometry must be an .stl or .obj file` | Missing extension | Provide full filename: `"outer-domain.stl"` |
| `backgroundMesh.referenceGeometry is not listed in geometry.files` | Filename not declared in `geometry.files` | Add it to `geometry.files` |
| `geometry file not found at 'constant/triSurface/...'` | STL/OBJ file not on disk | Ensure all files exist in `constant/triSurface/` |
| `backgroundMesh.baseGrid must be a positive number or a list [dx, dy, dz]` | `baseGrid` is zero, negative, or wrong type | Use `5.0` (scalar) or `[8.0, 4.0, 8.0]` (anisotropic) |
| `backgroundMesh.enlargementFactor must be a number greater than 1` | `enlargementFactor` ≤ 1 | Use a value greater than 1 (default is `1.1`) |

---

### castellatedMeshControls Errors

| Error | Cause | Fix |
|---|---|---|
| `must have either 'locationInMesh' or 'locationsInMesh', not both` | Both keys specified | Remove one |
| `must contain 'locationInMesh' or 'locationsInMesh'` | Neither key present | Add `"locationInMesh": [x, y, z]` or `"locationsInMesh": [...]` |
| `locationInMesh must be a list of 3 numbers` | Not a 3-element list | Use `"locationInMesh": [50, 25, 25]` |
| `locationsInMesh must be a non-empty list` | Empty array | Add at least one `{point, name}` entry |
| `locationsInMesh[i] must be a dict with 'point' and 'name'` | Wrong entry format | Use `{"point": [x,y,z], "name": "zone"}` |
| `locationsInMesh[i].point must be a list of 3 numbers` | Point not a 3-element list | Fix to `[x, y, z]` |
| `locationsInMesh[i].name must be a non-empty string` | Empty or missing name | Provide a non-empty string |

---

### surfaceHandling Errors

| Error | Cause | Fix |
|---|---|---|
| `surfaceHandling.selectedParts is required` | `selectedParts` missing | Add `"selectedParts": ["outer-domain", ...]` |
| `selectedParts references unknown geometry key 'motfes'` | Name not in `geometry` (typo) | Check spelling against geometry keys |
| `surfaces['mosfet'] must be a dict` | Entry is not a JSON object | Wrap in `{}` |
| `surfaces['mosfet'].type must be 'boundary' or 'faceZone'` | Invalid or misspelled type | Use `"boundary"` or `"faceZone"` exactly |
| `surfaces['mosfet'].refinementLevels must be [min, max]` | Single int, empty array, or >2 elements | Use `"refinementLevels": [1, 2]` |
| `surfaces['mosfet'].faceType must be 'internal', 'baffle', or 'boundary'` | Invalid value | Use lowercase exactly |
| `surfaces['inductor'].cellZoneInside must be 'inside' or 'outside'` | Invalid value | Use `"inside"` or `"outside"` |
| `surfaces['outer-domain'].regions must be a dict` | `regions` is an array instead of a dict | Use dict with solid names as keys |
| `surfaces['outer-domain'].regions['Inflow'] contains unknown field 'faceType'` | Unsupported field in region entry | Region entries support only `refinementLevels` |
| `faceZoneName not allowed in __defaults__` | `faceZoneName`, `cellZoneName`, `regions`, `namedRegions`, or `autoRefine` in `__defaults__` | Move to explicit per-surface entry |
| `namedRegions must be a list of non-empty strings` | Not a list or contains empty/non-string entries | Use `["inlet", "outlet", "walls"]` |
| `surfaces['mosfet'] has both 'autoRefine: true' and 'refinementLevels'` | Both keys present on same entry | Remove one — they are mutually exclusive |
| `'autoRefine: true' is not supported for standard shapes` | `autoRefine` used on a `standardShapes` entry | Use explicit `refinementLevels` instead |

---

### volumeRefinement Errors

| Error | Cause | Fix |
|---|---|---|
| `volumeRefinement.selectedParts is required` | `selectedParts` missing | Add it |
| `selectedParts references unknown geometry key` | Name not in `geometry` | Check spelling |
| `regions['heat-sink'].mode must be 'inside', 'outside', or 'distance'` | Typo or wrong case | Use lowercase exactly |
| `regions['hotSpot'] in mode 'distance' requires 'levels'` | Used `level` instead of `levels` | Change key to `"levels": [[d, l], ...]` |
| `regions['hotSpot'].levels must be a non-empty array` | `levels` is `[]` or null | Provide at least one pair |
| `regions['hotSpot'].levels[1] must be [distance, level]` | Pair is not a 2-element array | Fix to `[0.5, 6]` |
| `regions['mosfet'] has both 'autoRefine: true' and 'level'` | Both keys present | Remove one — they are mutually exclusive |

---

### Generated Output Issues

**snappyHexMeshDict has syntax errors**: count `{` vs `}`, check for missing semicolons,
verify keyword spelling. Inspect the file:

```bash
head -60 system/snappyHexMeshDict
grep -n "refinementSurfaces\|refinementRegions\|geometry" system/snappyHexMeshDict
```

**cellZone on open surface causes snappyHexMesh failure**: check with `surfaceCheck mosfet.stl`.
The output should show 0 open edges. Either close the surface or remove `cellZoneInside`.

---

### Testing Your Configuration

**Step 1: Validate JSON syntax**

```bash
python3 -m json.tool snappy_inputs.json
```

**Step 2: Check geometry files exist**

```bash
python3 << 'EOF'
import json, os
with open("snappy_inputs.json") as f:
    config = json.load(f)
files = config.get("geometry", {}).get("files", [])
if isinstance(files, str):
    with open(files) as flist:
        files = [l.strip() for l in flist if l.strip() and not l.startswith("#")]
for fn in files:
    path = f"constant/triSurface/{fn}"
    status = "✓" if os.path.exists(path) else "✗ NOT FOUND"
    print(f"{status}  {path}")
EOF
```

**Step 3: Run the generator**

```bash
python3 setup_snappy.py
```

**Step 4: Inspect the generated file**

```bash
head -60 system/snappyHexMeshDict
grep -n "refinementSurfaces\|refinementRegions\|geometry" system/snappyHexMeshDict
```

**Debug mode** — capture all output:

```bash
python3 -u setup_snappy.py 2>&1 | tee generator_debug.log
```

---

## `scriptSettings` — GUI-generated block

> **Not read by `setup_snappy.py`.** This block is written by the HTML generator tool
> (`tools/snappy_inputs_generator.html`) to persist its script-generation settings alongside
> the mesh configuration. It is safe to leave in the JSON — the generator ignores it.

```json
"scriptSettings": {
    "pythonUtilsDir": "/path/to/other_utilities",
    "fluidZoneName": "domain_fluid",
    "allrunExtraEnabled": true,
    "notAComponent": ["outer-domain.stl"],
    "transformPointsEnabled": true,
    "transformPointsScale": 0.001,
    "chtConfig": {
        "enabled": true,
        "regions": [
            {"name": "domain_fluid", "zones": ["domain_fluid"]},
            {"name": "domain_solid", "zones": ["heater", "pcb"]}
        ]
    }
}
```

| Field | Description |
|---|---|
| `pythonUtilsDir` | Path to the `other_utilities/` directory on your machine |
| `fluidZoneName` | Name passed to `createFluidCellZone.py -name` |
| `allrunExtraEnabled` | Whether the `Allrun.extra` download button is active |
| `notAComponent` | Files passed to `ensureConsistentCellZones.py --exclude` (non-component geometry such as domain bounding boxes) |
| `transformPointsEnabled` / `transformPointsScale` | Whether to emit a `transformPoints -scale` step in `Allrun.extra` |
| `chtConfig` | Region groupings for `splitMeshRegions -combineZones` / `-customRegionNames`. Used to generate `Allrun.extra` and `Allclean` scripts |

See `tools/gui_workflow.md` for a description of the full script-generation workflow.

---

## Changelog

### v2.2 — 2026-05-xx

#### Backward-compatible additions

- **`locationsInMesh` in `castellatedMeshControls`** — new alternative to `locationInMesh` for
  multi-region CHT setups. Accepts a list of `{point, name}` dicts. Mutually exclusive with
  `locationInMesh`. Both keys validated at startup.
- **`namedRegions` in `surfaceHandling.surfaces`** — new key for multi-region STL files where
  all solid regions share the same refinement level. Automatically populates the geometry
  section `regions {}` block without per-region `refinementSurfaces` entries.
- **`regions {}` auto-propagation** — the tool now automatically writes the `regions {}` block
  inside the geometry section of `snappyHexMeshDict` from either `surfaceHandling.surfaces[key].regions`
  (per-region refinement) or `surfaceHandling.surfaces[key].namedRegions` (uniform refinement).
- **Serial-mode Allrun scripts** — when `numCores = 1`, generated Allrun scripts use
  `runApplication` instead of `runParallel` and omit the `decomposePar` step.

---

### v1.1 — 2026-05-07

#### Backward-compatible changes

- `autoRefinementParams.surfaceResolutionCells` is now optional (default `5.0` added to
  `defaults.json`). Existing files that specify it explicitly continue to work unchanged.

---

### v1.0 — 2026-04-29

Initial release. **Validated against**: OpenFOAM v2512.

Schema sections: `settings`, `geometry`, `backgroundMesh`, `autoRefinementParams`,
`surfaceHandling`, `volumeRefinement`, encoded filename convention.

---

## Appendix: Encoded Name Convention (Legacy)

> **Not recommended for new configurations.** Specifying refinement settings explicitly via
> `surfaceHandling` and `volumeRefinement` is clearer and easier to maintain. This feature is
> retained for backward compatibility only.

### Enabling

```json
"settings": {
    "extractRefinementFromNames": true
}
```

### Encoding Format

```
[SURF_(BND|FZ|FZ_CZ)_L<min>_L<max>_][VOL_(IN|OUT)_L<level>_]<cleanName>
```

### SURF Block Tags

| Tag | Meaning |
|---|---|
| `SURF_BND_L<min>_L<max>_` | Surface `type: boundary`, `refinementLevels: [min, max]` |
| `SURF_FZ_L<min>_L<max>_` | Surface `type: faceZone`, `refinementLevels: [min, max]` |
| `SURF_FZ_CZ_L<min>_L<max>_` | Surface `type: faceZone` + `cellZoneInside: inside`, `refinementLevels: [min, max]` |

### VOL Block Tags

| Tag | Meaning |
|---|---|
| `VOL_IN_L<level>_` | Volume `mode: inside`, `level: <level>` |
| `VOL_OUT_L<level>_` | Volume `mode: outside`, `level: <level>` |

### Decoding Examples

| Encoded name | Surface result | Volume result | Clean name |
|---|---|---|---|
| `outer-domain.stl` | (none from name) | (none from name) | `outer-domain` |
| `SURF_BND_L0_L1_outer-domain.stl` | boundary, [0, 1] | — | `outer-domain` |
| `SURF_FZ_L1_L2_mosfet.stl` | faceZone, [1, 2] | — | `mosfet` |
| `VOL_IN_L4_PCB-board-bottom.stl` | — | inside, 4 | `PCB-board-bottom` |
| `SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor.stl` | faceZone+cellZone, [1, 4] | inside, 3 | `myInductor` |
| `VOL_IN_L4_hotSpot` (shape name) | — | inside, 4 | `hotSpot` |

### Rules when `extractRefinementFromNames: true`

- `SURF_*` entries → auto-included in `refinementSurfaces`; `VOL_*` entries → auto-included in `refinementRegions`
- Non-encoded entries still need `selectedParts`
- Explicit override entries in `surfaces`/`regions` require the full encoded key in `selectedParts`
- Clean name is used in the generated `snappyHexMeshDict` output
- Distance mode cannot be encoded — always provide explicitly in `volumeRefinement.regions`
- A name starting with `SURF_` or `VOL_` that does not match the expected pattern is a fatal error

### Partial Override Example

```json
"surfaces": {
    "SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor": {
        "faceZoneName": "fz_inductor",
        "cellZoneName": "cz_inductor"
    }
}
```

The encoded name provides `type: faceZone`, `refinementLevels: [1, 4]`, `cellZoneInside: inside`.
The explicit entry adds/overrides only the zone names.

### Customising the Encoding Convention

```json
"encodingConvention": {
    "surfacePrefix": "SURF",
    "volumePrefix":  "VOL",
    "boundary":      "BND",
    "faceZone":      "FZ",
    "cellZone":      "CZ"
}
```

All values must be uppercase strings (letters A–Z and digits only). The combined `faceZone+cellZone`
tag is derived as `{faceZone}_{cellZone}`. Volume mode tags `IN`/`OUT` are fixed.

### AUTO_ — Automatic Level Derivation

`AUTO_` prefix derives refinement levels automatically from geometry analysis (requires
`extractRefinementFromNames: true`).

**Format**: `AUTO_<SURF>_(<BND>|<FZ>|<FZ_CZ>)_[<VOL>_(IN|OUT)_]<cleanName>.<ext>`

Level numbers (`_L<n>_`) must **not** appear — the engine computes them.

| Filename | Surface result | Volume result | Clean name |
|---|---|---|---|
| `AUTO_SURF_FZ_CZ_VOL_IN_mosfet.stl` | faceZone+cellZone, levels auto | inside, level auto | `mosfet` |
| `AUTO_SURF_BND_mosfet.stl` | boundary, levels auto | — | `mosfet` |
| `AUTO_VOL_IN_PCB-board.stl` | — | inside, level auto | `PCB-board` |

`AUTO_`-encoded entries are always auto-selected — no `selectedParts` entry is needed.

Alternatively, trigger automatic level derivation from the JSON by setting `autoRefine: true`
on a surface or volume region entry (mutually exclusive with `refinementLevels`/`level`).

### `autoRefinementParams` Fields

Active when any geometry uses `AUTO_` naming or `autoRefine: true`. All fields have defaults
and can be omitted.

| Field | Type | Default | Description |
|---|---|---|---|
| `surfaceResolutionCells` | float | `3` | Cells per characteristic length for `surface_min` |
| `featureResolutionCells` | float | `2.0` | Cells per feature/curvature length for `surface_max` |
| `volumeResolutionCells` | float | `10.0` | Cells across characteristic length for volume level |
| `featureAngle` | float | `30.0` | Dihedral angle threshold (°) to classify a sharp feature edge |
| `noiseRatio` | float | `20.0` | Feature curves shorter than `char_length / noiseRatio` are discarded |
| `maxLevelGap` | int | `3` | Maximum allowed difference between `surface_max` and `surface_min` |
| `minCellsAcross` | int | `10` | Minimum cells across median bbox dimension (floor on `surface_min`). Set `0` to disable |
| `gapMultiplier` | float | `3.0` | Safety factor for hydraulic-diameter char_length (flat/elongated shapes) |

### Encoding Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `AUTO_-encoded filenames require extractRefinementFromNames: true` | `AUTO_` file but setting is `false` | Set `"extractRefinementFromNames": true` |
| `AUTO_ prefix ... could not be decoded` | Level numbers included in `AUTO_` name, or missing type tag | Remove `_L<n>_` from `AUTO_` names |
| `name 'SURF_FZ_L1_mosfet' does not match expected encoding format` | Missing `L<max>` or invalid tag | Use `SURF_FZ_L1_L2_mosfet.stl` |
| `duplicate clean name` | Two encoded names decode to same clean name | Rename one file |
| `selectedParts references unknown key 'mosfet'` (encoding active) | Clean name used instead of full encoded key | Use `"SURF_FZ_L1_L2_mosfet"` as the key |
| `open mesh — results may be less accurate` | Non-watertight geometry | Check derived levels manually; add explicit override if needed |

---

**Last Updated**: 2026-05-09
**Version**: 2.2
