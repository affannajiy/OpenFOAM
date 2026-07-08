# snappyHexMeshDict JSON Configuration Guide

Complete reference for `snappy_inputs.json`. The generator reads this file and produces
`system/snappyHexMeshDict` for use with OpenFOAM's `snappyHexMesh`.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [settings](#settings)
3. [geometry](#geometry)
   - [geometry.files](#geometryfiles)
   - [geometry.standardShapes](#geometrystandardshapes)
4. [backgroundMesh](#backgroundmesh)
5. [autoRefinementParams](#autorefinementparams)
6. [surfaceHandling](#surfacehandling)
   - [selectedParts](#surfacehandlingselectedparts)
   - [surfaces dict and __defaults__](#surfacehandlingsurfaces-dict-and-__defaults__)
   - [Surface type: boundary](#surface-type-boundary)
   - [Surface type: faceZone](#surface-type-facezone)
   - [Surface type: faceZone with cellZone](#surface-type-facezone-with-cellzone)
   - [Multi-region surfaces](#multi-region-surfaces)
   - [Resolution order](#resolution-order-for-surface-handling)
6. [volumeRefinement](#volumerefinement)
   - [selectedParts](#volumerefinementselectedparts)
   - [regions dict and __defaults__](#volumerefinementregions-dict-and-__defaults__)
   - [Mode: inside and outside](#mode-inside-and-outside)
   - [Mode: distance](#mode-distance)
   - [Resolution order](#resolution-order-for-volume-refinement)
7. [extractRefinementFromNames — Encoded Name Convention](#extractrefinementfromnames--encoded-name-convention)
   - [Customising the Encoding Convention](#customising-the-encoding-convention)
   - [AUTO_ — Automatic Level Derivation](#auto--automatic-level-derivation)
8. [Complete Examples](#complete-examples)
9. [Validation Rules Summary](#validation-rules-summary)
10. [Tips & Best Practices](#tips--best-practices)

---

## Quick Start

### Minimal Configuration (geometry + surface handling only)

```json
{
    "settings": {
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": {
        "files": ["outer-domain.stl"]
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

### Medium Complexity (standard shapes + volume refinement)

```json
{
    "settings": {
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": {
        "files": ["outer-domain.stl", "heat-sink.stl"],
        "standardShapes": [
            {
                "name": "hotSpot",
                "type": "searchableSphere",
                "centre": [50, 25, 25],
                "radius": 10
            }
        ]
    },
    "surfaceHandling": {
        "selectedParts": ["outer-domain", "heat-sink"],
        "surfaces": {
            "__defaults__": {
                "type": "boundary",
                "refinementLevels": [1, 2]
            },
            "outer-domain": {
                "refinementLevels": [0, 1]
            },
            "heat-sink": {
                "type": "faceZone",
                "refinementLevels": [1, 4],
                "faceZoneName": "fz_heatsink",
                "faceType": "internal",
                "cellZoneInside": "inside",
                "cellZoneName": "cz_heatsink"
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

`settings` is a required top-level dict. It must contain at least `geometryUnit`, `addLayers`,
and `mergeTolerance`.

```json
"settings": {
    "geometryUnit": "mm",
    "extractRefinementFromNames": false,
    "addLayers": false,
    "mergeTolerance": 1e-06
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `geometryUnit` | string | yes | Unit of the STL/geometry files. Stored as metadata only — not applied as a scale in snappyHexMeshDict. Use in downstream pipeline scripts (e.g. Allrun) for unit conversion. |
| `addLayers` | bool | yes | Enable boundary layer generation in snappyHexMesh |
| `mergeTolerance` | float | yes | Relative surface merging tolerance. `1e-06` works for most cases |
| `extractRefinementFromNames` | bool | no (default `false`) | When `true`, decode SURF/VOL refinement tags from filename stems and shape names |
| `openfoamVersion` | string | no (default `"2506"`) | OpenFOAM version string written into the file header of all generated dictionaries |

**Allowed values for `geometryUnit`:**

| Value | Unit |
|---|---|
| `"m"` | Metres |
| `"mm"` | Millimetres |
| `"cm"` | Centimetres |
| `"um"` | Micrometres (µm) |
| `"in"` | Inches |
| `"ft"` | Feet |

---

## `backgroundMesh`

`backgroundMesh` is a required top-level dict. It drives generation of `system/blockMeshDict` — the uniform hex background mesh required by snappyHexMesh. The bounding box is derived automatically from the reference geometry using the `trimesh` library (no OpenFOAM environment required).

```json
"backgroundMesh": {
    "referenceGeometry": "outer-domain.stl",
    "baseGrid": 5.0
}
```

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `referenceGeometry` | string | **yes** | — | Filename (with extension) of the geometry to derive the bounding box from. Must be declared in `geometry.files` and exist in `constant/triSurface/` |
| `baseGrid` | number **or** `[dx, dy, dz]` | **yes** | — | Base cell size in geometry units. Scalar → isotropic; 3-element array → anisotropic |
| `enlargementFactor` | float | no | `1.1` | Factor by which the bounding box is expanded around its centre. Must be `> 1` |

### Behaviour

1. Loads `constant/triSurface/<referenceGeometry>` with trimesh
2. Computes axis-aligned bounding box
3. Expands each axis symmetrically: `centre ± enlargementFactor × half-extent`
4. Snaps `maxCoords` outward to the nearest exact multiple of `baseGrid` so the domain
   length is divisible by the cell size — cell count `n = ceil(length / baseGrid)`
5. Writes `system/blockMeshDict` with a single hex block and `simpleGrading (1 1 1)`

### Anisotropic grid example

```json
"backgroundMesh": {
    "referenceGeometry": "outer-domain.stl",
    "baseGrid": [8.0, 4.0, 8.0],
    "enlargementFactor": 1.15
}
```

### `baseGrid` and snappyHexMesh refinement levels

snappyHexMesh halves the cell size at each refinement level:

```
cell size at level N = baseGrid / 2^N
```

To get predictable cell sizes at every refinement level, choose:

```
baseGrid = desired_finest_cell_size × 2^max_refinement_level
```

**Example**: finest cells should be 0.5 mm, maximum refinement level is 5:
```
baseGrid = 0.5 × 2^5 = 16 mm
→ level 5: 0.5 mm,  level 4: 1 mm,  level 3: 2 mm,  level 2: 4 mm
```

This is a recommendation, not a requirement — any positive value is accepted.

---

## `autoRefinementParams`

`autoRefinementParams` configures the automatic refinement level derivation engine. It is
only active when at least one geometry file uses the `AUTO_` encoded name prefix (see
[AUTO_ — Automatic Level Derivation](#auto--automatic-level-derivation)).

**Requires `settings.extractRefinementFromNames: true`** — AUTO_-encoded filenames are a
fatal error when `extractRefinementFromNames` is false.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `surfaceResolutionCells` | float | **yes** | — | Cells per characteristic length for the minimum surface refinement level. Typical range: 3–10 |
| `featureResolutionCells` | float | no | `2.0` | Cells per feature curve / curvature radius for the maximum surface level |
| `volumeResolutionCells` | float | no | `10.0` | Cells across the characteristic interior volume/gap for volume level |
| `featureAngle` | float | no | `30.0` | Dihedral angle threshold (degrees) to classify a sharp geometric feature edge |
| `noiseRatio` | float | no | `20.0` | Feature curves shorter than `char_length / noiseRatio` are discarded as CAD noise |
| `maxLevelGap` | int | no | `3` | Maximum allowed difference between `surface_max` and `surface_min` |
| `minCellsAcross` | int | no | `10` | Minimum cells across the median bounding-box dimension (floor on `surface_min`); set `0` to disable |
| `gapMultiplier` | float | no | `3.0` | Safety factor for hydraulic-diameter char_length (flat/elongated closed shapes) |

Mandatory field `surfaceResolutionCells` must appear in `snappy_inputs.json`. All other
fields have defaults in `defaults.json` and can be omitted.

### Minimum example

```json
"autoRefinementParams": {
    "surfaceResolutionCells": 5
}
```

### How levels are derived

For each AUTO_-encoded geometry file the engine:

1. **Loads** `constant/triSurface/<filename>` with trimesh
2. **Computes characteristic length** (`char_length`):
   - Closed (watertight) mesh — compact: `V^(1/3)`; flat/elongated: `gapMultiplier × V/A`
   - Open mesh: `min(sqrt(A), max_edge_length)` — a warning is printed; results may be
     less accurate than for watertight geometries
3. **Surface min level** — stricter of two floors:
   - `char_length / surfaceResolutionCells` (proportional to geometry scale)
   - `median_bbox_dim / minCellsAcross` (bounding-box floor)
4. **Surface max level** — most demanding of:
   - Sharp feature edges (dihedral > `featureAngle`), grouped into tessellation-invariant
     curves; curves shorter than `char_length / noiseRatio` discarded as CAD noise
   - Smooth curvature (Gaussian curvature at non-feature vertices)
   - Capped at `surface_min + maxLevelGap`
5. **Volume level** — `char_length / volumeResolutionCells`, capped at `surface_min`

### Anisotropic baseGrid

When `backgroundMesh.baseGrid` is `[dx, dy, dz]`, the minimum of the three values is used
as `base_grid_size` for all auto-refinement calculations. This gives the most conservative
(highest) refinement levels. A notice is printed to stdout when this fallback is applied.

### baseGrid recommendation (applies to auto-refinement too)

For predictable cell sizes: `baseGrid = finest_desired_cell_size × 2^max_level`.
The auto-refinement engine will produce levels consistent with this if the geometry and
`surfaceResolutionCells` are set appropriately.

---



`geometry` is a required top-level dict. It must contain at least one of `files` or
`standardShapes`.

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

The text file may contain blank lines and `#`-prefixed comment lines — these are ignored.
Each line may be a bare filename (`foo.stl`) or include the directory prefix
(`constant/triSurface/foo.stl`) — the tool normalises both to the bare name automatically.

**Rules for each filename**:

- Must end in `.stl` or `.obj` (case-insensitive)
- The filename stem (name without extension) becomes the geometry key used throughout
  `surfaceHandling` and `volumeRefinement`
- Stem must start with a letter (`a–z`, `A–Z`) or underscore (`_`) — stems starting with
  a digit or special character are a fatal error
- No `name` field is permitted — the key is always derived from the stem
- No `regions` in geometry — multi-region config lives in `surfaceHandling.surfaces`

**Examples**:

```json
"files": [
    "outer-domain.stl",          // key: outer-domain
    "heat-sink-to-252-1.stl",    // key: heat-sink-to-252-1
    "pcb_board.stl"              // key: pcb_board
]
```

When `extractRefinementFromNames: true` the stem may carry an encoding prefix:

```json
"files": [
    "SURF_FZ_L1_L2_mosfet.stl",                    // key: SURF_FZ_L1_L2_mosfet
    "SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor.stl"    // key: SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor
]
```

See [extractRefinementFromNames](#extractrefinementfromnames--encoded-name-convention) for the
full encoding specification.

---

### `geometry.standardShapes`

An array of parametric shape dicts. Each shape requires `name` and `type`.

```json
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
```

The `name` value becomes the geometry key used in `surfaceHandling` and `volumeRefinement`.
It must be unique across all geometry entries (files + shapes).

Nine shape types are supported:

---

#### `searchableBox`

Axis-aligned cuboid defined by two corner points.

```json
{
    "name": "refinementBox",
    "type": "searchableBox",
    "min": [0, 0, 0],
    "max": [100, 50, 50]
}
```

| Required | Type |
|---|---|
| `min` | `[x, y, z]` |
| `max` | `[x, y, z]` |

---

#### `searchableSphere`

Perfect sphere defined by centre and radius.

```json
{
    "name": "hotSpot",
    "type": "searchableSphere",
    "centre": [50, 25, 25],
    "radius": 10
}
```

| Required | Type |
|---|---|
| `centre` | `[x, y, z]` |
| `radius` | number |

---

#### `searchableCylinder`

Cylinder defined by two axis endpoints and a radius.

```json
{
    "name": "flowPipe",
    "type": "searchableCylinder",
    "point1": [0, 25, 25],
    "point2": [100, 25, 25],
    "radius": 5
}
```

| Required | Type |
|---|---|
| `point1` | `[x, y, z]` |
| `point2` | `[x, y, z]` |
| `radius` | number |

---

#### `searchableCone`

Truncated cone (frustum) defined by two axis endpoints and four radii (outer and inner at
each end).

```json
{
    "name": "myCone",
    "type": "searchableCone",
    "point1": [0, 0, 0],
    "point2": [100, 0, 0],
    "radius1": 20,
    "radius2": 10,
    "inner1": 0,
    "inner2": 0
}
```

| Required | Type |
|---|---|
| `point1` | `[x, y, z]` |
| `point2` | `[x, y, z]` |
| `radius1` | number (outer radius at point1) |
| `radius2` | number (outer radius at point2) |
| `inner1` | number (inner radius at point1, 0 for solid) |
| `inner2` | number (inner radius at point2, 0 for solid) |

---

#### `searchableRotatedBox`

A cuboid that can be arbitrarily oriented in space.

```json
{
    "name": "rotatedZone",
    "type": "searchableRotatedBox",
    "span": [100, 50, 30],
    "origin": [10, 5, 0],
    "e1": [1, 0, 0],
    "e3": [0, 0, 1]
}
```

| Required | Type |
|---|---|
| `span` | `[x, y, z]` — dimensions |
| `origin` | `[x, y, z]` — one corner |
| `e1` | `[x, y, z]` — unit vector along span-x direction |
| `e3` | `[x, y, z]` — unit vector along span-z direction |

---

#### `searchableDisk`

A flat circular disk defined by its centre, normal, and radius.

```json
{
    "name": "coolantInlet",
    "type": "searchableDisk",
    "origin": [0, 25, 25],
    "normal": [1, 0, 0],
    "radius": 8
}
```

| Required | Type |
|---|---|
| `origin` | `[x, y, z]` |
| `normal` | `[x, y, z]` |
| `radius` | number |

---

#### `searchablePlate`

A flat rectangular plate. Exactly one component of `span` must be zero — this determines
which axis has zero thickness.

```json
{
    "name": "baffle",
    "type": "searchablePlate",
    "origin": [50, 0, 0],
    "span": [0, 50, 30]
}
```

| Required | Type | Note |
|---|---|---|
| `origin` | `[x, y, z]` | One corner of the plate |
| `span` | `[x, y, z]` | Extents; exactly one component must be 0 |

---

#### `searchablePlane`

An infinite plane. Three `planeType` variants are supported.

**pointAndNormal**:

```json
{
    "name": "symmetryPlane",
    "type": "searchablePlane",
    "planeType": "pointAndNormal",
    "basePoint": [50, 0, 25],
    "normal": [0, 1, 0]
}
```

**embeddedPoints** (three non-collinear points):

```json
{
    "name": "symmetryPlane",
    "type": "searchablePlane",
    "planeType": "embeddedPoints",
    "points": [
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0]
    ]
}
```

**planeEquation** (ax + by + cz = d):

```json
{
    "name": "symmetryPlane",
    "type": "searchablePlane",
    "planeType": "planeEquation",
    "a": 0, "b": 1, "c": 0,
    "d": 25
}
```

| Required for all | Type |
|---|---|
| `planeType` | `"pointAndNormal"`, `"embeddedPoints"`, or `"planeEquation"` |

---

#### `searchableSurfaceWithGaps`

Wraps another named geometry and adds a uniform gap around it.

```json
{
    "name": "mosfetWithGap",
    "type": "searchableSurfaceWithGaps",
    "surface": "mosfet",
    "gap": 0.5
}
```

| Required | Type |
|---|---|
| `surface` | string — name of the geometry entry to wrap |
| `gap` | number — gap distance |

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
`refinementSurfaces`. When `extractRefinementFromNames: true`, any geometry entry whose
key carries a `SURF_` prefix is **automatically included** — you do not need to list it
here. `selectedParts` is then only needed for:

1. **Non-encoded entries** (no `SURF_` prefix) — e.g. `"outer-domain"`, `"transformer"`
2. **Encoded entries you want to override** — an entry in `surfaces` (other than
   `__defaults__`) must have its key present in `selectedParts`; omitting it is a fatal error

Keys must match entries defined in `geometry`. When `extractRefinementFromNames: true`,
use the full encoded key (e.g. `"SURF_FZ_L1_L2_mosfet"`) for any override entries.

---

### `surfaceHandling.surfaces` Dict and `__defaults__`

`surfaces` is an optional dict whose keys are geometry keys. The special key `__defaults__`
provides fallback values that are applied to every selected part before any explicit entry
is merged in.

**`__defaults__` forbidden fields**: `faceZoneName`, `cellZoneName`, `regions`

These are per-surface details that cannot be shared safely and must appear in the explicit
per-surface entry.

**Resolution order** (later overrides earlier):
1. `__defaults__`
2. Decoded values from the encoded name (if `extractRefinementFromNames: true`)
3. Explicit entry for the geometry key

```json
"surfaces": {
    "__defaults__": {
        "type": "boundary",
        "refinementLevels": [1, 2]
    },
    "transformer": {},                 // uses __defaults__ fully
    "mosfet": {
        "type": "faceZone",            // overrides __defaults__.type
        "refinementLevels": [1, 3],    // overrides __defaults__.refinementLevels
        "faceZoneName": "fz_mosfet",
        "faceType": "internal"
    }
}
```

---

### Surface type: `boundary`

Produces a standard OpenFOAM patch refinement. Only `refinementLevels` is used; any
faceZone/cellZone fields are ignored.

```json
"outer-domain": {
    "type": "boundary",
    "refinementLevels": [0, 1]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | `"boundary"` |
| `refinementLevels` | `[min, max]` | yes | Surface refinement level range |

---

### Surface type: `faceZone`

Produces surface refinement **and** creates a named face zone in the mesh. The face zone
tracks the surface faces, which is needed for baffles, internal interfaces, or boundary
conditions on internal surfaces.

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
| `refinementLevels` | `[min, max]` | yes | Surface refinement level range |
| `faceZoneName` | string | no | Name for the face zone (defaults to the clean surface name) |
| `faceType` | string | no | `"internal"`, `"baffle"`, or `"boundary"` |

---

### Surface type: `faceZone` with cellZone

Adding `cellZoneInside` to a `faceZone` entry also creates a cell zone that marks all
cells inside (or outside) the closed surface. Use this for solid component regions.

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
| `refinementLevels` | `[min, max]` | yes | Surface refinement level range |
| `faceZoneName` | string | no | Face zone name (defaults to clean surface name) |
| `faceType` | string | no | `"internal"`, `"baffle"`, or `"boundary"` |
| `cellZoneInside` | string | yes (activates cell zone) | `"inside"` or `"outside"` |
| `cellZoneName` | string | no | Cell zone name (defaults to `faceZoneName`) |

**Note**: The surface must be a closed, water-tight mesh when using `cellZoneInside`.
Open surfaces with holes will cause snappyHexMesh to fail or produce incorrect results.

---

### Multi-Region Surfaces

An STL file may contain multiple named solid regions (e.g. `Inflow`, `Outflow`,
`all_walls`). Use the `regions` dict inside the surface entry to set per-region
refinement levels.

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

**Rules**:
- Keys are the exact solid names as they appear in the STL file (case-sensitive)
- No renaming — the key IS the name used in the generated mesh
- Each region entry supports only `refinementLevels`
- Unknown fields in a region entry are a fatal error
- `regions` is not allowed in `__defaults__`

---

### Resolution Order for Surface Handling

For each selected part, the final configuration is assembled in this order (later wins):

```
__defaults__
  └─ decoded values from encoded name (if extractRefinementFromNames=true)
       └─ explicit entry for the geometry key
```

Example: `__defaults__` sets `type: boundary, refinementLevels: [1, 2]`. The explicit
entry for `mosfet` sets `type: faceZone, refinementLevels: [1, 3]`. Result: `type: faceZone,
refinementLevels: [1, 3]`.

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
is **automatically included** — you do not need to list it here. `selectedParts` is then
only needed for:

1. **Non-encoded entries** (no `VOL_` prefix) — e.g. `"outer-domain"`, `"heat-sink"`
2. **Encoded entries you want to override** — an entry in `regions` (other than
   `__defaults__`) must have its key present in `selectedParts`; omitting it is a fatal error

Keys must match entries in `geometry`. When `extractRefinementFromNames: true`, use the
full encoded key for any override entries.

---

### `volumeRefinement.regions` Dict and `__defaults__`

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
| `level` | int | yes | Refinement level |

---

### Mode: `distance`

Progressively refine cells based on their distance from the surface. Pairs are
`[distance, level]` — at each distance threshold, cells within that distance get at
least that refinement level.

```json
"heat-sink-to-252-1": {
    "mode": "distance",
    "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
}
```

Reading this: within 0.5 units → level 6; within 2.0 units → level 4; within 5.0 units
→ level 2.

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | string | yes | `"distance"` |
| `levels` | array | yes | Non-empty array of `[distance, level]` pairs |

Each pair must be exactly two numbers. The array must be non-empty.

---

### Resolution Order for Volume Refinement

Same pattern as surface handling:

```
__defaults__
  └─ decoded values from encoded name (if extractRefinementFromNames=true)
       └─ explicit entry for the geometry key
```

**Distance mode cannot be encoded** — if a surface needs distance-based refinement,
provide it explicitly in `volumeRefinement.regions` regardless of whether
`extractRefinementFromNames` is on.

---

## `extractRefinementFromNames` — Encoded Name Convention

When `settings.extractRefinementFromNames: true`, refinement parameters can be embedded
directly in the filename stem (for file-based geometry) or the `name` field (for standard
shapes). The generator decodes them automatically.

### Encoding Format

```
[SURF_(BND|FZ|FZ_CZ)_L<min>_L<max>_][VOL_(IN|OUT)_L<level>_]<cleanName>
```

The SURF block and VOL block are both optional, but the combined string must match the
expected pattern exactly if it starts with `SURF_` or `VOL_`.

### SURF Block Tags

| Tag | Meaning |
|---|---|
| `SURF_BND_L<min>_L<max>_` | Surface `type: boundary`, `refinementLevels: [min, max]` |
| `SURF_FZ_L<min>_L<max>_` | Surface `type: faceZone`, `refinementLevels: [min, max]` |
| `SURF_FZ_CZ_L<min>_L<max>_` | Surface `type: faceZone` with `cellZoneInside: inside`, `refinementLevels: [min, max]` |

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
| `SURF_BND_L0_L0_flowPipe` (shape name) | boundary, [0, 0] | — | `flowPipe` |

### Rules when `extractRefinementFromNames: true`

- **Auto-selection**: encoded entries are automatically included as surface or volume
  refinement candidates based on their prefix — no need to list them in `selectedParts`
  - `SURF_*` entries → included in `refinementSurfaces`
  - `VOL_*` entries → included in `refinementRegions`
  - Entries with both prefixes (e.g. `SURF_FZ_CZ_L1_L4_VOL_IN_L3_`) → included in both
- **`selectedParts` for overrides only**: if you place an explicit entry in `surfaces` or
  `regions` (not `__defaults__`) for an encoded key, that key **must** also appear in
  `selectedParts` — omitting it is a fatal error with a hint message
- **Non-encoded entries still need `selectedParts`**: entries without a `SURF_`/`VOL_`
  prefix are never auto-selected; list them explicitly in `selectedParts`
- **Key in `selectedParts` and `surfaces`/`regions`**: use the **full encoded name**
  (e.g. `"SURF_FZ_L1_L2_mosfet"`, not `"mosfet"`)
- **Clean name** is used in the generated `snappyHexMeshDict` output
- **Explicit entries always override**: an explicit entry in `surfaces` or `regions` for
  the encoded key wins over the decoded values (resolution order applies)
- **Partial overrides work**: if the encoded name decodes `type` and `refinementLevels`,
  you can add only `faceZoneName` and `cellZoneName` in the explicit entry without
  repeating the level info
- **Distance mode cannot be encoded**: must always be explicit in `volumeRefinement.regions`
- **Fatal error**: a name that starts with `SURF_` or `VOL_` but does not match the
  expected pattern

### Example: partial override with encoded name

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

---

### Customising the Encoding Convention

The prefix tokens and type tags used in encoded names are defined in the `encodingConvention`
block. Defaults ship in `defaults.json` and can be overridden per-case in `snappy_inputs.json`.

```json
"encodingConvention": {
    "surfacePrefix": "SURF",
    "volumePrefix":  "VOL",
    "boundary":      "BND",
    "faceZone":      "FZ",
    "cellZone":      "CZ"
}
```

| Key | Default | Meaning |
|---|---|---|
| `surfacePrefix` | `SURF` | Trigger word for surface encoding block |
| `volumePrefix` | `VOL` | Trigger word for volume encoding block |
| `boundary` | `BND` | Tag for `type: boundary` |
| `faceZone` | `FZ` | Tag for `type: faceZone` |
| `cellZone` | `CZ` | Tag for faceZone + cellZone (combined as `{faceZone}_{cellZone}`, e.g. `FZ_CZ`) |

**Rules:**
- All values must be **uppercase** strings containing only letters `A–Z` and digits `0–9`
- The combined faceZone+cellZone tag is derived automatically: `{faceZone}_{cellZone}`
- The volume mode tags `IN` (inside) and `OUT` (outside) are fixed and not configurable
- Renaming tokens requires updating all existing encoded filenames accordingly

**Example — using shorter tokens:**

```json
"encodingConvention": {
    "surfacePrefix": "S",
    "volumePrefix":  "V",
    "boundary":      "B",
    "faceZone":      "FZ",
    "cellZone":      "CZ"
}
```

Filenames would then use `S_FZ_L1_L2_mosfet.stl` and `V_IN_L4_PCB.stl`.

---

### AUTO_ — Automatic Level Derivation

The `AUTO_` prefix is a special extension of the encoding convention that **derives
refinement levels automatically** from the geometry file using trimesh analysis — no level
numbers are specified in the filename.

**Prerequisite**: `settings.extractRefinementFromNames: true` must be set. An `AUTO_`-encoded
file with `extractRefinementFromNames: false` is a fatal error.

#### Encoding format

```
AUTO_<SURF>_(<BND>|<FZ>|<FZ_CZ>)_[<VOL>_(IN|OUT)_]<cleanName>.<ext>
AUTO_<VOL>_(IN|OUT)_<cleanName>.<ext>
```

Level numbers (`_L<n>_`) must **not** appear — the engine computes them. Including level
numbers after an `AUTO_` tag is a fatal error.

#### Examples

| Filename | Surface result | Volume result | Clean name |
|---|---|---|---|
| `AUTO_SURF_FZ_CZ_VOL_IN_mosfet.stl` | faceZone+cellZone, levels auto | inside, level auto | `mosfet` |
| `AUTO_SURF_BND_mosfet.stl` | boundary, levels auto | — | `mosfet` |
| `AUTO_SURF_FZ_inductor.stl` | faceZone, levels auto | — | `inductor` |
| `AUTO_VOL_IN_PCB-board.stl` | — | inside, level auto | `PCB-board` |

#### Auto-selection

AUTO_-encoded entries are **always auto-selected** into surface and volume refinement
regardless of `selectedParts`. Listing them in `selectedParts` is not required (and has
no effect on auto-selection).

#### Explicit overrides

AUTO_-encoded entries **can** have explicit overrides in `surfaceHandling.surfaces` or
`volumeRefinement.regions` without being listed in `selectedParts`. If you want to override
only the zone names while keeping auto-derived levels, add only those fields:

```json
"surfaces": {
    "AUTO_SURF_FZ_CZ_VOL_IN_mosfet": {
        "faceZoneName": "fz_mosfet",
        "cellZoneName": "cz_mosfet"
    }
}
```

Resolution order: defaults → auto-derived levels → explicit entry.

#### Configuring the auto-refinement engine

Set parameters in `autoRefinementParams`. Only `surfaceResolutionCells` is mandatory:

```json
"autoRefinementParams": {
    "surfaceResolutionCells": 5
}
```

See the [autoRefinementParams](#autorefinementparams) section for all fields.

#### Open mesh warning

If the geometry file is not watertight (open mesh), the script prints a warning and
continues. Results may be less accurate — verify the derived levels manually and adjust
`surfaceResolutionCells` or add explicit overrides as needed.

---



### Example 1: Explicit (no encoding)

```json
{
    "settings": {
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

### Example 2: Encoded names

```json
{
    "settings": {
        "extractRefinementFromNames": true,
        "addLayers": false,
        "mergeTolerance": 1e-06
    },

    "geometry": {
        "files": [
            "outer-domain.stl",
            "VOL_IN_L4_PCB-board-bottom.stl",
            "heat-sink-to-252-1.stl",
            "transformer.stl",
            "SURF_FZ_L1_L2_mosfet.stl",
            "pcb_board.stl",
            "SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor.stl"
        ],
        "standardShapes": [
            {
                "name": "VOL_IN_L4_hotSpot",
                "type": "searchableSphere",
                "centre": [50, 25, 25],
                "radius": 10
            },
            {
                "name": "SURF_BND_L0_L0_flowPipe",
                "type": "searchableCylinder",
                "point1": [0, 25, 25],
                "point2": [100, 25, 25],
                "radius": 5
            }
        ]
    },

    "surfaceHandling": {
        "selectedParts": [
            "outer-domain", "transformer", "SURF_FZ_L1_L2_mosfet",
            "pcb_board", "SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor", "SURF_BND_L0_L0_flowPipe"
        ],
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
            "pcb_board": {
                "type": "faceZone",
                "refinementLevels": [1, 4],
                "faceZoneName": "fz_pcb_board",
                "faceType": "baffle"
            },
            "SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor": {
                "faceZoneName": "fz_inductor",
                "cellZoneName": "cz_inductor"
            }
        }
    },

    "volumeRefinement": {
        "selectedParts": [
            "outer-domain", "VOL_IN_L4_PCB-board-bottom", "heat-sink-to-252-1",
            "SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor", "VOL_IN_L4_hotSpot"
        ],
        "regions": {
            "__defaults__": {
                "mode": "inside",
                "level": 2
            },
            "outer-domain": {"level": 0},
            "heat-sink-to-252-1": {
                "mode": "distance",
                "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
            }
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
| No duplicate clean name (after stripping encoding) | `geometry` | fatal |
| `surfaceHandling.selectedParts` required if `surfaceHandling` present and `extractRefinementFromNames: false` | `surfaceHandling` | fatal |
| Every item in `selectedParts` must match a geometry key | `surfaceHandling` / `volumeRefinement` | fatal |
| `surfaces[name]` must be a dict | `surfaceHandling.surfaces` | fatal |
| `type` must be `"boundary"` or `"faceZone"` | per surface | fatal |
| `refinementLevels` must be `[min, max]` | per surface / region | fatal |
| `faceType` must be `"internal"`, `"baffle"`, or `"boundary"` if present | per surface | fatal |
| `cellZoneInside` must be `"inside"` or `"outside"` if present | per surface | fatal |
| `regions` in surface entry must be a dict | per surface | fatal |
| Region entry supports only `refinementLevels` | per region | fatal |
| `faceZoneName`, `cellZoneName`, `regions` forbidden in `__defaults__` | `surfaceHandling` | fatal |
| `volumeRefinement.selectedParts` required if `volumeRefinement` present and `extractRefinementFromNames: false` | `volumeRefinement` | fatal |
| `mode` must be `"inside"`, `"outside"`, or `"distance"` | per volume region | fatal |
| `inside`/`outside` mode requires `level` | per volume region | fatal |
| `distance` mode requires `levels` | per volume region | fatal |
| `levels` must be a non-empty array | `distance` mode | fatal |
| Each `levels` entry must be `[distance, level]` | `distance` mode | fatal |
| Encoded name starting with `SURF_`/`VOL_` must match expected pattern | encoding | fatal |
| `backgroundMesh` required in `snappy_inputs.json` | `backgroundMesh` | fatal |
| `backgroundMesh.referenceGeometry` required | `backgroundMesh` | fatal |
| `backgroundMesh.referenceGeometry` must be listed in `geometry.files` | `backgroundMesh` | fatal |
| `backgroundMesh.baseGrid` must be a positive number or `[dx, dy, dz]` | `backgroundMesh` | fatal |
| `backgroundMesh.enlargementFactor` must be a number `> 1` if present | `backgroundMesh` | fatal |
| `AUTO_` prefix requires `settings.extractRefinementFromNames: true` | encoding | fatal |
| `AUTO_` encoded name must contain at least one SURF or VOL block | encoding | fatal |
| `AUTO_` SURF/VOL block must not contain explicit level numbers (`_L<n>_`) | encoding | fatal |
| `autoRefinementParams.surfaceResolutionCells` required when any AUTO_ file present | `autoRefinementParams` | fatal |
| All `autoRefinementParams` numeric fields must be positive | `autoRefinementParams` | fatal |
| `autoRefinementParams.maxLevelGap` and `minCellsAcross` must be non-negative integers | `autoRefinementParams` | fatal |

---

## Tips & Best Practices

**Start minimal**: begin with only `settings` and `geometry`. Add `surfaceHandling` once
geometry loads correctly, then add `volumeRefinement`.

**Use `__defaults__` for shared settings**: if most surfaces share `type: boundary` and
`refinementLevels: [1, 2]`, put those in `__defaults__` and only override what differs.

**`selectedParts` as an allow-list**: when `extractRefinementFromNames: false`, only parts
listed in `selectedParts` get surface or volume refinement. When
`extractRefinementFromNames: true`, encoded entries (`SURF_*` / `VOL_*`) are auto-selected;
`selectedParts` is only needed for non-encoded entries and encoded entries with explicit
overrides in `surfaces`/`regions`. Parts in `geometry` that are neither auto-selected nor
listed appear in the geometry block only.

**Distance refinement for heat sources**: use `mode: distance` for heat sinks and hot
spots to get fine cells near the surface and coarser cells farther away, avoiding a sharp
level jump.

**cellZone requires a closed surface**: any surface with `cellZoneInside` must be fully
enclosed. Check with `surfaceCheck` before meshing.

**Region keys are case-sensitive**: the `regions` dict key must exactly match the solid
name in the STL file. Use `grep "^solid" part.stl` to list actual solid names.

**Keep file stems unique after encoding strip**: if `extractRefinementFromNames: true`,
two files that decode to the same clean name are a fatal error. Plan names carefully.

**Validate JSON first**: run `python3 -m json.tool snappy_inputs.json` before running the
generator. This catches bracket/comma errors quickly.

**Check the generated output**: after running `setup_snappy.py`, inspect
`system/snappyHexMeshDict` to confirm `geometry`, `refinementSurfaces`, and
`refinementRegions` sections look correct before launching snappyHexMesh.

**Choose `baseGrid` with refinement levels in mind**: snappyHexMesh halves the cell size
at each level — `cell_size = baseGrid / 2^N`. Setting
`baseGrid = finest_cell_size × 2^max_level` gives clean, predictable cell sizes at every
level (e.g. `baseGrid = 16 mm` for 0.5 mm finest cells at level 5). Any positive value
works; this is a recommendation, not a requirement.

---

**Last Updated**: 2026-04-26
**Version**: 2.0
