# snappyHexMeshDict Generator — Documentation Index

Complete documentation for the snappyHexMeshDict JSON configuration workflow. The generator reads
`snappy_inputs.json` and produces a ready-to-use `system/snappyHexMeshDict` for OpenFOAM.

---

## Quick Navigation

| Document | Best For | Read Time |
|---|---|---|
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | Templates, field tables, one-liners | 5 min |
| [JSON_SCHEMA_GUIDE.md](JSON_SCHEMA_GUIDE.md) | Full parameter reference, worked examples | 20–30 min |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Error messages, debugging, testing procedures | 10–15 min |
| [CHANGELOG.md](CHANGELOG.md) | Schema version history, breaking changes | 2 min |
| [../tools/README.md](../tools/README.md) | Helper utilities — geometry renamer, flip normals | 2 min |

---

## Document Descriptions

### [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

**Best for**: Fast lookups, copy-paste templates

**Contents**:
- Minimal and full JSON templates
- `settings`, `geometry`, `surfaceHandling`, `volumeRefinement` field tables
- Standard shapes at a glance
- Type quick reference (boundary / faceZone / faceZone+cellZone)
- Volume mode quick reference (inside / outside / distance)
- Encoded name format summary
- Common errors & quick fixes

**Use when**: You already understand the schema and just need syntax or a field name.

---

### [JSON_SCHEMA_GUIDE.md](JSON_SCHEMA_GUIDE.md)

**Best for**: Learning the schema, setting up complex cases

**Contents**:
- Table of contents
- Quick start (minimal and medium configs)
- `settings` section reference
- `geometry` section — files array, text-file loading, all 9 standard shapes
- `backgroundMesh` — automatic `blockMeshDict` generation from a reference geometry
- `autoRefinementParams` — automatic surface/volume level derivation from geometry analysis
- `surfaceHandling` — selectedParts, surfaces dict, `__defaults__`, boundary/faceZone/cellZone
- Multi-region surfaces with `regions` dict
- `volumeRefinement` — selectedParts, regions dict, all three modes
- `extractRefinementFromNames` — full encoding spec with examples
- Complete working examples (explicit and encoded)
- Validation rules summary
- Tips & best practices

**Use when**: You want to understand the full schema or build a complex configuration.

---

### [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

**Best for**: Fixing errors, diagnosing unexpected output

**Contents**:
- JSON validation errors
- `settings` errors
- `geometry` errors (files, shapes, encoding, naming)
- `surfaceHandling` errors
- `volumeRefinement` errors
- Generated output issues
- Testing procedures (4-step process)

**Use when**: The generator reports an error or the output looks wrong.

---

## Dependencies

See the top-level [`README.md`](../README.md) for package requirements and
run [`check_env.py`](../check_env.py) to verify your environment before first use.

---

## Workflow Overview

```
0. Prepare geometry filenames  [optional — only needed when using encoded names]
   └─ Open tools/geometry_renamer.html in a browser
   └─ Browse to constant/triSurface (or wherever STL files live)
   └─ Configure surface/volume encoding per file
   └─ Copy rename script → paste in terminal → run

1. Create snappy_inputs.json
   └─ Copy minimal template from QUICK_REFERENCE
   └─ Customize using JSON_SCHEMA_GUIDE examples

2. Validate JSON syntax
   └─ python3 -m json.tool snappy_inputs.json
   └─ Must complete without errors

3. Check geometry files
   └─ Ensure all STL/OBJ files listed in geometry.files exist
   └─ ls -la *.stl

4. Run generator
   └─ python3 setup_snappy.py
   └─ Reads snappy_inputs.json
   └─ Writes system/snappyHexMeshDict

5. Verify output
   └─ Inspect system/snappyHexMeshDict
   └─ Look for geometry, refinementSurfaces, refinementRegions
   └─ Check OpenFOAM dictionary syntax

6. Run snappyHexMesh
   └─ snappyHexMesh -overwrite
   └─ Mesh written to constant/polyMesh
```

---

## JSON Structure at a Glance

The configuration is a single JSON object with four top-level sections:

```json
{
    "settings": {
        "extractRefinementFromNames": false,
        "addLayers": false,
        "mergeTolerance": 1e-06
    },

    "geometry": {
        "files": ["mosfet.stl", "heatsink.stl"],
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
        "selectedParts": ["mosfet", "heatsink", "hotSpot"],
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
    },

    "volumeRefinement": {
        "selectedParts": ["heatsink", "hotSpot"],
        "regions": {
            "__defaults__": {
                "mode": "inside",
                "level": 2
            },
            "heatsink": {"level": 4},
            "hotSpot": {
                "mode": "distance",
                "levels": [[0.5, 6], [2.0, 4]]
            }
        }
    }
}
```

---

## Common Tasks

### "I want to mesh a simple domain with an outer boundary"

Use `geometry.files` with one STL, add it to `surfaceHandling.selectedParts` and
`volumeRefinement.selectedParts`:

```json
{
    "settings": {"addLayers": false, "mergeTolerance": 1e-06},
    "geometry": {"files": ["outer-domain.stl"]},
    "surfaceHandling": {
        "selectedParts": ["outer-domain"],
        "surfaces": {
            "outer-domain": {"type": "boundary", "refinementLevels": [0, 1]}
        }
    },
    "volumeRefinement": {
        "selectedParts": ["outer-domain"],
        "regions": {"outer-domain": {"mode": "inside", "level": 0}}
    }
}
```

---

### "I need to track a face zone and create a cell zone for a solid component"

Set `type: faceZone` with `cellZoneInside` in `surfaceHandling.surfaces`:

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

---

### "I have a multi-region STL (inlet, outlet, walls)"

Use the `regions` dict inside the surface entry:

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

---

### "I want a parametric refinement zone without an STL"

Add a standard shape to `geometry.standardShapes` and reference its name in
`surfaceHandling` or `volumeRefinement`:

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

---

### "I want to encode refinement info in filenames"

Set `settings.extractRefinementFromNames: true` and use encoded stems:

```
SURF_FZ_L1_L2_mosfet.stl        → faceZone, levels [1,2], name mosfet
VOL_IN_L4_PCB-board-bottom.stl  → volume inside level 4, name PCB-board-bottom
SURF_FZ_CZ_L1_L4_VOL_IN_L3_myInductor.stl
                                 → faceZone+cellZone [1,4], vol inside 3, name myInductor
```

See [JSON_SCHEMA_GUIDE.md → extractRefinementFromNames](JSON_SCHEMA_GUIDE.md#extractrefinementfromnames--encoded-name-convention).

---

### "I'm getting an error"

1. `python3 -m json.tool snappy_inputs.json` — catch JSON syntax issues first
2. Read the error message — it names the exact field and problem
3. Search [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the matching error heading

---

## Version Information

See [`CHANGELOG.md`](CHANGELOG.md) for schema version history and breaking changes.

---

**Last Updated**: 2026-04-29
**Status**: Production Ready

---

## Generator Features

✅ **Four-section JSON schema** — `settings`, `geometry`, `backgroundMesh`, `surfaceHandling`, `volumeRefinement`

✅ **Automatic `blockMeshDict` generation** (`backgroundMesh`)
- Derives bounding box from any declared geometry file using `trimesh` (no OpenFOAM required)
- Configurable `enlargementFactor` and `baseGrid` (scalar or anisotropic vector)
- Snaps domain extents to exact multiples of the base grid

✅ **Automatic refinement level derivation** (`AUTO_` encoding + `autoRefinementParams`)
- Prefix geometry files with `AUTO_SURF_<tag>_[VOL_(IN|OUT)_]<name>` — no level numbers needed
- Engine analyses geometry (char_length, feature edges, curvature) to compute surface [min, max] and volume levels
- Requires `settings.extractRefinementFromNames: true`
- Results printed to stdout with per-file surface and volume levels

✅ **Geometry file existence check** — all files declared in `geometry.files` must exist in
   `constant/triSurface/` before any processing begins

✅ **Geometry sources**
- `geometry.files` — inline array of STL/OBJ filenames or path to a text file listing them
- `geometry.standardShapes` — 9 parametric types (searchableBox, searchableSphere, searchableCylinder,
  searchableCone, searchableRotatedBox, searchableDisk, searchablePlate, searchablePlane,
  searchableSurfaceWithGaps)

✅ **Surface handling**
- `selectedParts` controls which geometry entries appear in `refinementSurfaces`
- `__defaults__` provides fallback values for all selected parts
- Supports `boundary`, `faceZone`, and `faceZone`+cellZone surface types
- Multi-region surfaces via per-entry `regions` dict (no renaming — keys are the exact solid names)

✅ **Volume refinement**
- `selectedParts` controls which entries appear in `refinementRegions`
- `__defaults__` provides fallback mode and level
- Three modes: `inside`, `outside`, `distance` (with `[[distance, level], ...]` pairs)

✅ **Encoded name convention** (`extractRefinementFromNames`)
- Encode surface and volume refinement info directly in filenames or shape names
- Explicit entries in `surfaces`/`regions` always override encoded values
- Distance mode must always be explicit — cannot be encoded

✅ **Conflict detection** — duplicate raw keys, duplicate clean names, invalid stems

✅ **Fail-fast validation** — descriptive error messages that name the exact field and value

✅ **Clean OpenFOAM output** — properly formatted `snappyHexMeshDict`, no extra blank lines

---

## Input / Output

### Input: `snappy_inputs.json`

User-written JSON file containing `settings`, `geometry`, and optionally `surfaceHandling`
and `volumeRefinement`. A working example is provided at `snappy_inputs.json`.

### Output: `system/snappyHexMeshDict`

Generated OpenFOAM dictionary containing:
- `geometry` block (all surfaces and shapes)
- `castellatedMeshControls` with `refinementSurfaces` and `refinementRegions`
- `snapControls`, `addLayersControls`, `meshQualityControls`
- `mergeTolerance`

Run with: `snappyHexMesh -overwrite`

---

## Tips for Success

1. **Start with QUICK_REFERENCE** — get a working template in minutes
2. **Use the provided snappy_inputs.json** — copy and modify it
3. **Validate JSON first** — `python3 -m json.tool snappy_inputs.json`
4. **Read error messages carefully** — they name the exact field and problem
5. **Check generated output** — verify refinementSurfaces and refinementRegions sections
6. **Add features incrementally** — start with geometry only, then add surfaceHandling, then volumeRefinement
