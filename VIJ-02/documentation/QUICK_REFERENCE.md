# snappyHexMeshDict JSON — Quick Reference

## Minimal Template (geometry only)

```json
{
    "settings": {
        "geometryUnit": "mm",
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": {
        "files": ["domain.stl"]
    }
}
```

---

## Full Template (all four sections)

```json
{
    "settings": {
        "geometryUnit": "mm",
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

## `settings` Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `geometryUnit` | string | yes | — | Unit of geometry files (`"m"`, `"mm"`, `"cm"`, `"um"`, `"in"`, `"ft"`). Metadata only — not written to snappyHexMeshDict |
| `addLayers` | bool | yes | — | Enable boundary layer generation |
| `mergeTolerance` | float | yes | — | Surface merging tolerance (use `1e-06`) |
| `extractRefinementFromNames` | bool | no | `false` | Decode refinement info from encoded names |
| `openfoamVersion` | string | no | `"2506"` | OpenFOAM version written into all generated file headers |

---

## `geometry` Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | array of strings **or** string path | at least one of `files`/`standardShapes` | STL/OBJ filenames, or path to a text file listing them |
| `standardShapes` | array of shape dicts | at least one of `files`/`standardShapes` | Parametric geometry objects |

**`geometry.files` rules**:
- Each filename must end in `.stl` or `.obj` (case-insensitive)
- Filename stem must start with a letter (`a–z`, `A–Z`) or underscore (`_`)
- No `name` field — the geometry key is the filename stem (e.g. `"mosfet.stl"` → key `"mosfet"`)
- String path variant: one filename per line; blank lines and `#` comments ignored;
  bare names (`foo.stl`) and path-prefixed names (`constant/triSurface/foo.stl`) are both accepted

**`geometry.standardShapes` rules**:
- `name` and `type` are required for every shape
- `name` must be unique across all geometry entries
- No `name` field when `extractRefinementFromNames=true` and name is encoded (the name IS the encoded string)

---

## `backgroundMesh` Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `referenceGeometry` | string | **yes** | — | Filename (with `.stl`/`.obj`) from `geometry.files`; must exist in `constant/triSurface/` |
| `baseGrid` | number or `[dx,dy,dz]` | **yes** | — | Base cell size in geometry units. Scalar → isotropic; array → anisotropic |
| `enlargementFactor` | float | no | `1.1` | Bounding box expansion factor around centre. Must be `> 1` |

**`baseGrid` tip** — snappyHexMesh halves cell size at each level (`size = baseGrid / 2^N`).
For clean cell sizes at every level, use `baseGrid = finest_cell_size × 2^max_level`
(e.g. 16 mm for 0.5 mm finest cells at level 5). Any positive value is accepted.

---

## `autoRefinementParams` Fields

Active only when geometry files with the `AUTO_` name prefix are present.
Requires `settings.extractRefinementFromNames: true`.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `surfaceResolutionCells` | float | **yes** | — | Cells per char_length for `surface_min`. Typical: 3–10 |
| `featureResolutionCells` | float | no | `2.0` | Cells per feature/curvature length for `surface_max` |
| `volumeResolutionCells` | float | no | `10.0` | Cells across char_length for volume level |
| `featureAngle` | float | no | `30.0` | Dihedral angle threshold (°) for sharp feature edges |
| `noiseRatio` | float | no | `20.0` | Curves shorter than `char_length / noiseRatio` discarded |
| `maxLevelGap` | int | no | `3` | Cap on `surface_max − surface_min` |
| `minCellsAcross` | int | no | `10` | Min cells across median bbox dim (floor on `surface_min`); `0` disables |
| `gapMultiplier` | float | no | `3.0` | Hydraulic-diameter safety factor for flat/elongated shapes |

Anisotropic `baseGrid [dx, dy, dz]` → minimum value used; a notice is printed.
Open meshes → warning printed, computation continues.



| Type | Required Parameters |
|---|---|
| `searchableBox` | `min: [x,y,z]`, `max: [x,y,z]` |
| `searchableSphere` | `centre: [x,y,z]`, `radius: N` |
| `searchableCylinder` | `point1: [x,y,z]`, `point2: [x,y,z]`, `radius: N` |
| `searchableCone` | `point1`, `point2`, `radius1`, `radius2`, `inner1`, `inner2` |
| `searchableRotatedBox` | `span: [x,y,z]`, `origin: [x,y,z]`, `e1: [x,y,z]`, `e3: [x,y,z]` |
| `searchableDisk` | `origin: [x,y,z]`, `normal: [x,y,z]`, `radius: N` |
| `searchablePlate` | `origin: [x,y,z]`, `span: [x,y,z]` (exactly one zero component) |
| `searchablePlane` | `planeType: "pointAndNormal"\|"embeddedPoints"\|"planeEquation"` + type-specific fields |
| `searchableSurfaceWithGaps` | `surface: "name"`, `gap: N` |

---

## `surfaceHandling.surfaces` Fields

| Field | Type | Required | Applies to | Description |
|---|---|---|---|---|
| `type` | string | yes | all | `"boundary"` or `"faceZone"` |
| `refinementLevels` | `[min, max]` | yes | all | Surface refinement level range |
| `faceZoneName` | string | no | `faceZone` | Face zone name (defaults to clean surface name) |
| `faceType` | string | no | `faceZone` | `"internal"`, `"baffle"`, or `"boundary"` |
| `cellZoneName` | string | no | `faceZone` with cell zone | Cell zone name (defaults to `faceZoneName`) |
| `cellZoneInside` | string | no | `faceZone` with cell zone | `"inside"` or `"outside"` |
| `regions` | dict | no | multi-region STLs | Per-solid-region `refinementLevels` overrides |

**`__defaults__` forbidden fields**: `faceZoneName`, `cellZoneName`, `regions`

**`regions` dict**: Keys are exact solid names from the STL file. Each entry supports only `refinementLevels`.

---

## `volumeRefinement.regions` Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `mode` | string | no (use `__defaults__`) | `"inside"`, `"outside"`, or `"distance"` |
| `level` | int | for `inside`/`outside` | Refinement level |
| `levels` | array | for `distance` | `[[distance, level], ...]` pairs |

---

## Surface Type Quick Reference

| Goal | `type` | Extra fields needed |
|---|---|---|
| Patch on boundary | `boundary` | `refinementLevels` |
| Internal face zone (no solid) | `faceZone` | `refinementLevels`, `faceZoneName`, `faceType` |
| Solid region (face + cell zones) | `faceZone` | above + `cellZoneInside`, `cellZoneName` |

---

## Volume Mode Quick Reference

| Mode | Use case | Required field |
|---|---|---|
| `inside` | Refine inside a closed surface | `level: N` |
| `outside` | Refine outside a closed surface | `level: N` |
| `distance` | Progressive refinement by distance | `levels: [[d, l], ...]` |

```json
"heat-sink": {
    "mode": "distance",
    "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
}
```

---

## Encoded Name Format Summary

Activate with `settings.extractRefinementFromNames: true`.

```
[SURF_(BND|FZ|FZ_CZ)_L<min>_L<max>_][VOL_(IN|OUT)_L<level>_]<cleanName>
```

| Tag | Meaning |
|---|---|
| `SURF_BND_L0_L1_` | Surface `boundary`, levels [0, 1] |
| `SURF_FZ_L1_L2_` | Surface `faceZone`, levels [1, 2] |
| `SURF_FZ_CZ_L1_L4_` | Surface `faceZone` + cell zone (inside), levels [1, 4] |
| `VOL_IN_L3_` | Volume `inside`, level 3 |
| `VOL_OUT_L2_` | Volume `outside`, level 2 |

**Examples**:
```
SURF_BND_L0_L1_outer-domain.stl   → boundary [0,1], key "SURF_BND_L0_L1_outer-domain"
SURF_FZ_L1_L2_mosfet.stl          → faceZone [1,2], key "SURF_FZ_L1_L2_mosfet"
VOL_IN_L4_hotSpot                  → vol inside 4, key "VOL_IN_L4_hotSpot"
SURF_FZ_CZ_L1_L4_VOL_IN_L3_inductor.stl
                                   → faceZone+cellZone [1,4], vol inside 3
```

- When `extractRefinementFromNames: true`, encoded entries (`SURF_*` / `VOL_*`) are
  **auto-selected** — no need to list them in `selectedParts`
- `selectedParts` still required for non-encoded entries and for any encoded entry with
  an explicit override in `surfaces`/`regions` (full encoded name as key)
- Distance mode **cannot** be encoded — add explicitly in `volumeRefinement.regions`
- Explicit entries always override encoded values

---

## Running the Generator

```bash
cd configure_snappyHexMeshDict
python3 setup_snappy.py
```

Reads `snappy_inputs.json` → writes `system/snappyHexMeshDict`.

---

## Refinement Level Reference

| Level | Approx. cell size | Typical use |
|---|---|---|
| 0–1 | ~100 mm | Outer domain, far-field |
| 2–3 | ~10–50 mm | Domain interior |
| 4–5 | ~1–10 mm | Near components |
| 6+ | < 1 mm | Critical surfaces, hot spots |

Cell size = base mesh cell size ÷ 2^level

---

## Common Errors & Quick Fixes

| Error | Cause | Fix |
|---|---|---|
| `JSON parse error` | Malformed JSON (missing comma, bracket, etc.) | `python3 -m json.tool snappy_inputs.json` |
| `settings is required` | Missing top-level `settings` dict | Add `"settings": {"geometryUnit": "mm", "addLayers": ..., "mergeTolerance": ...}` |
| `geometry must be a dict` | Old array-style geometry | Replace with `"geometry": {"files": [...]}` |
| `must have files or standardShapes` | Both keys absent | Add at least one to `geometry` |
| `file not found` | STL path doesn't exist | Verify filename and location |
| `stem must start with letter or _` | Filename starts with digit/special char | Rename the file |
| `duplicate clean name` | Two files strip to same key | Rename one file |
| `selectedParts references unknown key` | Name not in `geometry` | Check spelling and encoding prefix |
| `faceZoneName not allowed in __defaults__` | Forbidden field in defaults | Move to explicit per-surface entry |
| `mode must be inside, outside, or distance` | Typo or wrong case | Use lowercase exactly |
| `distance mode requires levels` | Used `level` instead of `levels` | Change key to `"levels": [[d, l], ...]` |
| `levels[N] must be [distance, level]` | Pair is not a 2-element array | Fix to `[distance, level]` |

---

**Last Updated**: 2026-04-26 | Version 2.0
