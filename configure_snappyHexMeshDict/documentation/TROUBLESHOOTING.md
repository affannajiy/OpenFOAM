# Troubleshooting Guide

Common issues and solutions when using the snappyHexMeshDict generator. Each section matches
the error category reported by `setup_snappy.py`.

---

## JSON Validation Errors

### "Invalid JSON in snappy_inputs.json"

**Cause**: JSON syntax error — missing comma, bracket, quote, etc.

**Debug**:
```bash
python3 -m json.tool snappy_inputs.json
```

**Common causes**:
- Missing comma between items: `{...}{...}` ✗ → `{...},{...}` ✓
- Trailing comma after last item: `{"a": 1,}` ✗ → `{"a": 1}` ✓
- Unquoted string value: `"mode": inside` ✗ → `"mode": "inside"` ✓
- Unclosed bracket: `[[0.5, 6]` ✗ → `[[0.5, 6]]` ✓
- `//` comments inside JSON: not valid JSON — remove all comments

---

## Settings Errors

### "settings is required and must be a dict"

**Cause**: Top-level `settings` key is missing or not a JSON object.

**Fix**: Add the `settings` dict:
```json
{
    "settings": {
        "addLayers": false,
        "mergeTolerance": 1e-06
    },
    "geometry": { ... }
}
```

---

### "settings.addLayers is required"

**Cause**: `addLayers` field missing from `settings`.

**Fix**:
```json
"settings": {
    "addLayers": false,        // add this
    "mergeTolerance": 1e-06
}
```

---

### "settings.mergeTolerance is required"

**Cause**: `mergeTolerance` field missing from `settings`.

**Fix**:
```json
"settings": {
    "addLayers": false,
    "mergeTolerance": 1e-06    // add this
}
```

---

### "settings.extractRefinementFromNames must be a boolean"

**Cause**: Value is a string or number instead of `true`/`false`.

**Wrong**:
```json
"extractRefinementFromNames": "true"
"extractRefinementFromNames": 1
```

**Fix**:
```json
"extractRefinementFromNames": true
```

---

## Geometry Errors

### "geometry must be a dict, not an array"

**Cause**: Using the old (v1) geometry array format.

**Wrong** (old format):
```json
"geometry": [
    {"file": "domain.stl", ...}
]
```

**Fix** (new format):
```json
"geometry": {
    "files": ["domain.stl"]
}
```

---

### "geometry must have at least one of 'files' or 'standardShapes'"

**Cause**: Both `files` and `standardShapes` are absent from `geometry`.

**Fix**: Add at least one:
```json
"geometry": {
    "files": ["outer-domain.stl"]
}
```

---

### "geometry.files must be an array of strings or a string path"

**Cause**: `files` is a dict, a number, or an array containing non-strings.

**Wrong**:
```json
"files": {"name": "domain.stl"}
"files": 42
"files": [{"file": "domain.stl"}]
```

**Fix**:
```json
"files": ["domain.stl", "heat-sink.stl"]
// OR
"files": "/path/to/stl_list.txt"
```

---

### "geometry.files path not found: /path/to/stl_list.txt"

**Cause**: `files` was given as a string path but the text file doesn't exist at that location.

**Check**:
```bash
ls -la /path/to/stl_list.txt
```

**Fix**: Use the correct absolute or relative path to the file list.

---

### "file 'domain.txt' must end in .stl or .obj"

**Cause**: A filename in `geometry.files` has the wrong extension.

**Fix**: Ensure every file ends in `.stl` or `.obj` (case-insensitive).

---

### "filename stem '3d_domain' must start with a letter or underscore"

**Cause**: The stem (filename without extension) starts with a digit or special character.

**Wrong**: `3d_domain.stl`, `_123.stl` ✓ (underscore is fine), `123domain.stl` ✗

**Fix**: Rename the file so the stem starts with a letter or `_`:
```
domain_3d.stl   ✓
_domain.stl     ✓
domain.stl      ✓
```

---

### "name field not allowed on file entry when extractRefinementFromNames=true"

**Cause**: Old-style `name` field placed inside a files entry (not applicable — file
entries have no configurable fields; the key comes from the stem).

**Wrong**:
```json
"files": [{"name": "domain", "file": "domain.stl"}]
```

**Fix**:
```json
"files": ["domain.stl"]
```

The geometry key is always the stem — `domain` in this case.

---

### "name 'SURF_FZ_L1_mosfet' does not match expected encoding format"

**Cause**: The filename stem or shape name starts with `SURF_` or `VOL_` but the rest of
the string does not match the required pattern.

**Expected format** (SURF block):
```
SURF_(BND|FZ|FZ_CZ)_L<min>_L<max>_<cleanName>
```

**Wrong**:
```
SURF_FZ_L1_mosfet.stl         ✗  (missing L<max>)
SURF_FACEZONE_L1_L2_mosfet.stl ✗  (invalid tag FACEZONE)
```

**Fix**:
```
SURF_FZ_L1_L2_mosfet.stl      ✓
```

---

### "duplicate geometry key 'outer-domain'"

**Cause**: Two files have the same stem, or a file stem and a shape name are identical.

**Wrong**:
```json
"files": ["outer-domain.stl", "outer-domain.obj"]
```

**Fix**: Rename one of the files to give it a unique stem.

---

### "duplicate clean name 'mosfet' from keys 'SURF_FZ_L1_L2_mosfet' and 'SURF_BND_L0_L1_mosfet'"

**Cause**: Two different encoded names decode to the same clean name.

**Fix**: Rename one of the source files/shapes to use a different clean name.

---

## Standard Shape Errors

### "geometry.standardShapes[N].type 'searchableTorus' is not a valid shape type"

**Cause**: Unknown shape type.

**Valid types**:
- `searchableBox`, `searchableSphere`, `searchableCylinder`
- `searchableCone`, `searchableRotatedBox`, `searchableDisk`
- `searchablePlate`, `searchablePlane`, `searchableSurfaceWithGaps`

**Fix**: Check spelling and use one of the types above.

---

### searchableBox: "must have 'min' and 'max'"

```json
// Wrong
{"type": "searchableBox", "name": "box", "min": [0, 0, 0]}

// Fix
{"type": "searchableBox", "name": "box", "min": [0, 0, 0], "max": [100, 50, 50]}
```

---

### searchableSphere: "must have 'centre' and 'radius'"

```json
// Wrong
{"type": "searchableSphere", "name": "spot", "centre": [50, 25, 25]}

// Fix
{"type": "searchableSphere", "name": "spot", "centre": [50, 25, 25], "radius": 10}
```

---

### searchableCylinder: "must have 'point1', 'point2', 'radius'"

```json
// Wrong
{"type": "searchableCylinder", "name": "pipe", "point1": [0, 25, 25], "point2": [100, 25, 25]}

// Fix
{"type": "searchableCylinder", "name": "pipe", "point1": [0, 25, 25], "point2": [100, 25, 25], "radius": 5}
```

---

### searchablePlate: "span must have exactly one zero component"

**Cause**: `span` has zero, two, or three zero components instead of exactly one.

**Wrong**:
```json
"span": [100, 50, 50]    // no zeros ✗
"span": [100, 0, 0]      // two zeros ✗
```

**Fix**:
```json
"span": [100, 0, 50]     // XZ plate (Y=0) ✓
"span": [100, 50, 0]     // XY plate (Z=0) ✓
"span": [0, 100, 50]     // YZ plate (X=0) ✓
```

---

### searchablePlane: "must have 'planeType'"

Three variants are supported:

```json
// pointAndNormal
{"planeType": "pointAndNormal", "basePoint": [50, 0, 25], "normal": [0, 1, 0]}

// embeddedPoints
{"planeType": "embeddedPoints", "points": [[0,0,0], [1,0,0], [0,1,0]]}

// planeEquation
{"planeType": "planeEquation", "a": 0, "b": 1, "c": 0, "d": 25}
```

---

## `backgroundMesh` Errors

### "backgroundMesh.referenceGeometry must be an .stl or .obj file"

**Cause**: `referenceGeometry` value does not end in `.stl` or `.obj`.

**Fix**: Provide the full filename including extension:
```json
"referenceGeometry": "outer-domain.stl"   // ✓
"referenceGeometry": "outer-domain"        // ✗
```

---

### "backgroundMesh.referenceGeometry is not listed in geometry.files"

**Cause**: The filename given in `referenceGeometry` is not declared in `geometry.files`.

**Fix**: Ensure the file appears in your `geometry.files` list (or text file):
```json
"geometry": { "files": ["outer-domain.stl", "mosfet.stl"] },
"backgroundMesh": { "referenceGeometry": "outer-domain.stl", ... }
```

---

### "geometry file '...' not found at 'constant/triSurface/...'"

**Cause**: A file declared in `geometry.files` (including the `referenceGeometry`) does not
exist on disk at `constant/triSurface/`. This check runs at startup for **all** geometry
files — not just the reference geometry.

**Fix**: Ensure all STL/OBJ files are placed in `constant/triSurface/` before running the generator.

---

### "backgroundMesh.baseGrid must be a positive number or a list [dx, dy, dz]"

**Cause**: `baseGrid` is missing, zero, negative, or a list that is not exactly three positive numbers.

**Fix**:
```json
"baseGrid": 5.0            // isotropic
"baseGrid": [8.0, 4.0, 8.0]  // anisotropic
```

---

### "backgroundMesh.enlargementFactor must be a number greater than 1"

**Cause**: `enlargementFactor` was overridden with a value `≤ 1`.

**Fix**: Use a value greater than 1 (default is `1.1`):
```json
"backgroundMesh": { "enlargementFactor": 1.1, ... }
```

---

## `autoRefinementParams` Errors

### "autoRefinementParams.surfaceResolutionCells is required when using AUTO_-encoded geometry"

**Cause**: At least one geometry file has the `AUTO_` prefix but `surfaceResolutionCells`
is not set.

**Fix**: Add `autoRefinementParams` with `surfaceResolutionCells` to your `snappy_inputs.json`:
```json
"autoRefinementParams": {
    "surfaceResolutionCells": 5
}
```

---

### "AUTO_-encoded filenames require extractRefinementFromNames: true"

**Cause**: A geometry file starts with `AUTO_` but `settings.extractRefinementFromNames`
is `false`.

**Fix**: Set `"extractRefinementFromNames": true` in your `settings` block.

---

### "AUTO_ prefix with SURF block but could not be decoded"

**Cause**: Malformed `AUTO_` surface block. Common mistakes:
- Missing surface type tag (`BND`, `FZ`, `FZ_CZ`)
- Explicit level numbers included (`_L1_L2_`) — these are forbidden in AUTO_ names

**Fix**: Use the format `AUTO_SURF_<tag>_[VOL_(IN|OUT)_]<name>` without level numbers:
- ✅ `AUTO_SURF_FZ_CZ_VOL_IN_mosfet.stl`
- ❌ `AUTO_SURF_FZ_CZ_L1_L4_VOL_IN_mosfet.stl` (level numbers not allowed)

---

### "Auto-refinement computation failed for '<filename>'"

**Cause**: trimesh could not process the geometry file. Possible reasons:
- File is corrupt or not a valid STL/OBJ
- Geometry has no faces (empty or degenerate mesh)

**Fix**: Validate the STL with `meshlab` or `checkMesh`. Ensure the file is a valid
triangulated surface. If the mesh is open (non-watertight), computation still runs but
a warning is printed — check results manually.

---

### Warning: "open mesh — results may be less accurate"

**Cause**: The geometry file is not watertight. `char_length` uses
`min(sqrt(A), max_edge_length)` instead of the volume-based formula.

**Action**: Check the derived levels and compare with your engineering judgement. Increase
`surfaceResolutionCells` if levels seem too coarse, or add an explicit override in
`surfaceHandling.surfaces` / `volumeRefinement.regions`.

---

## surfaceHandling Errors

### "surfaceHandling.selectedParts is required"

**Cause**: `surfaceHandling` dict is present, `extractRefinementFromNames: false`, but
`selectedParts` key is missing.

**Fix**:
```json
"surfaceHandling": {
    "selectedParts": ["outer-domain", "mosfet"],
    "surfaces": { ... }
}
```

> **Note**: When `extractRefinementFromNames: true`, `selectedParts` is optional.
> Encoded entries (`SURF_*`) are auto-selected. You only need `selectedParts` for
> non-encoded entries or encoded entries with explicit overrides in `surfaces`.

---

### "surfaceHandling.selectedParts references unknown geometry key 'motfes'"

**Cause**: A name in `selectedParts` is not in `geometry` (often a typo, or a clean name
used instead of the full encoded name).

**Fix**: Check the spelling against your `geometry.files` stems and `standardShapes`
names. When `extractRefinementFromNames: true`, use the full encoded key:

```json
// Wrong (clean name only)
"selectedParts": ["mosfet"]

// Fix (full encoded key)
"selectedParts": ["SURF_FZ_L1_L2_mosfet"]
```

---

### "surfaces['mosfet'] must be a dict"

**Cause**: An entry in `surfaceHandling.surfaces` is not a JSON object.

**Wrong**:
```json
"surfaces": {
    "mosfet": "boundary"
}
```

**Fix**:
```json
"surfaces": {
    "mosfet": {
        "type": "boundary",
        "refinementLevels": [1, 2]
    }
}
```

---

### "surfaces['mosfet'].type must be 'boundary' or 'faceZone'"

**Cause**: Invalid or misspelled `type` value.

**Wrong**: `"type": "Boundary"`, `"type": "face_zone"`, `"type": "cellZone"`

**Fix**:
```json
"type": "boundary"
// OR
"type": "faceZone"
```

---

### "surfaces['mosfet'].refinementLevels must be [min, max]"

**Cause**: `refinementLevels` is a single integer, an empty array, or has more than two
elements.

**Wrong**:
```json
"refinementLevels": 2
"refinementLevels": [1]
"refinementLevels": [1, 2, 3]
```

**Fix**:
```json
"refinementLevels": [1, 2]
```

---

### "surfaces['mosfet'].faceType must be 'internal', 'baffle', or 'boundary'"

**Cause**: Invalid `faceType` value (often wrong case or misspelling).

**Wrong**: `"faceType": "Internal"`, `"faceType": "internal_face"`

**Fix**:
```json
"faceType": "internal"
// OR "baffle" / "boundary"
```

---

### "surfaces['inductor'].cellZoneInside must be 'inside' or 'outside'"

**Cause**: Invalid value for `cellZoneInside`.

**Wrong**: `"cellZoneInside": "enclosed"`, `"cellZoneInside": "Inside"`

**Fix**:
```json
"cellZoneInside": "inside"
// OR
"cellZoneInside": "outside"
```

---

### "surfaces['outer-domain'].regions must be a dict"

**Cause**: `regions` is an array instead of a dict, or some other non-dict type.

**Wrong** (old format):
```json
"regions": [
    {"originalName": "Inflow", "renamedAs": "inlet"}
]
```

**Fix** (new format — dict with solid names as keys):
```json
"regions": {
    "Inflow":  {"refinementLevels": [1, 2]},
    "Outflow": {"refinementLevels": [3, 4]}
}
```

---

### "surfaces['outer-domain'].regions['Inflow'] contains unknown field 'faceType'"

**Cause**: A region entry has a field other than `refinementLevels`.

Region entries support **only** `refinementLevels`. All other surface options (`type`,
`faceZoneName`, `faceType`, etc.) belong at the surface level, not the region level.

**Wrong**:
```json
"regions": {
    "Inflow": {
        "refinementLevels": [1, 2],
        "faceType": "internal"        // not allowed here
    }
}
```

**Fix**: Remove unsupported fields from the region entry.

---

### "faceZoneName not allowed in __defaults__"

**Cause**: `faceZoneName`, `cellZoneName`, or `regions` was placed inside `__defaults__`.
These fields are per-surface details that cannot be shared.

**Wrong**:
```json
"__defaults__": {
    "type": "faceZone",
    "refinementLevels": [1, 2],
    "faceZoneName": "fz_default"    // not allowed
}
```

**Fix**: Move `faceZoneName` / `cellZoneName` / `regions` to the explicit per-surface entry:
```json
"__defaults__": {
    "type": "faceZone",
    "refinementLevels": [1, 2]
},
"mosfet": {
    "faceZoneName": "fz_mosfet",    // correct place
    "faceType": "internal"
}
```

---

## volumeRefinement Errors

### "volumeRefinement.selectedParts is required"

**Cause**: `volumeRefinement` dict present, `extractRefinementFromNames: false`, but
`selectedParts` missing.

**Fix**:
```json
"volumeRefinement": {
    "selectedParts": ["outer-domain", "hotSpot"],
    "regions": { ... }
}
```

> **Note**: When `extractRefinementFromNames: true`, `selectedParts` is optional.
> Encoded entries (`VOL_*`) are auto-selected. You only need `selectedParts` for
> non-encoded entries or encoded entries with explicit overrides in `regions`.

---

### "volumeRefinement.selectedParts references unknown geometry key 'heatSink'"

**Cause**: A key in `selectedParts` is not in `geometry`. Check spelling and, when encoding
is active, use the full encoded key.

---

### "regions['heat-sink'].mode must be 'inside', 'outside', or 'distance'"

**Cause**: Invalid or misspelled `mode`.

**Wrong**: `"mode": "Inside"`, `"mode": "dist"`, `"mode": "within"`

**Fix**:
```json
"mode": "inside"     // or "outside" or "distance"
```

---

### "regions['hotSpot'] in mode 'distance' requires 'levels'"

**Cause**: `mode: distance` was set but `levels` is missing (perhaps `level` was used
instead).

**Wrong**:
```json
{"mode": "distance", "level": 4}
```

**Fix**:
```json
{
    "mode": "distance",
    "levels": [[0.5, 6], [2.0, 4], [5.0, 2]]
}
```

---

### "regions['hotSpot'].levels must be a non-empty array"

**Cause**: `levels` is `[]`, `null`, or not an array.

**Fix**: Provide at least one pair:
```json
"levels": [[0.5, 6]]
```

---

### "regions['hotSpot'].levels[1] must be [distance, level]"

**Cause**: A levels entry is not a 2-element array.

**Wrong**:
```json
"levels": [
    [0.5, 6, "extra"],    // 3 elements ✗
    [2.0],                // 1 element ✗
    {"dist": 5.0, "lv": 2}  // dict ✗
]
```

**Fix**:
```json
"levels": [
    [0.5, 6],
    [2.0, 4],
    [5.0, 2]
]
```

---

## Generated Output Issues

### snappyHexMeshDict has syntax errors

**Check**:
1. Look for unclosed braces — count `{` vs `}`
2. Check for missing semicolons after values
3. Verify keyword spelling

If the Jinja2 template has a rendering problem, `setup_snappy.py` will usually print the
error. If the file is generated but invalid, inspect carefully:

```bash
head -60 system/snappyHexMeshDict
grep -n "refinementSurfaces\|refinementRegions" system/snappyHexMeshDict
```

---

### cellZone on open surface causes snappyHexMesh failure

**Cause**: `cellZoneInside` was set for a surface that is not fully closed.

**Check**:
```bash
surfaceCheck mosfet.stl
```
The output should show 0 open edges.

**Fix**: Either close the surface (fix the geometry) or remove `cellZoneInside` and use
only a face zone:

```json
"mosfet": {
    "type": "faceZone",
    "refinementLevels": [1, 2],
    "faceZoneName": "fz_mosfet",
    "faceType": "internal"
    // no cellZoneInside — surface is open
}
```

---

### Extra blank lines in generated file

**Cause**: Jinja2 template whitespace not stripped.

**Solution**: The current template uses `{%-` syntax which strips leading whitespace. If
blank lines appear, the template may have been edited incorrectly. Check that block tags
use the hyphen form: `{%- if ... %}`, `{%- for ... %}`, `{%- endfor %}`.

---

## Testing Your Configuration

### Step 1: Validate JSON syntax

```bash
python3 -m json.tool snappy_inputs.json
```

Should print the reformatted JSON with no errors.

### Step 2: Check geometry files exist

```bash
python3 << 'EOF'
import json, os

with open("snappy_inputs.json") as f:
    config = json.load(f)

files = config.get("geometry", {}).get("files", [])
if isinstance(files, str):
    with open(files) as flist:
        files = [l.strip() for l in flist if l.strip() and not l.startswith("#")]

for path in files:
    status = "✓" if os.path.exists(path) else "✗ NOT FOUND"
    print(f"{status}  {path}")
EOF
```

### Step 3: Run the generator

```bash
python3 setup_snappy.py
```

Read the output for any validation errors. On success you should see confirmation that
`system/snappyHexMeshDict` was written.

### Step 4: Inspect the generated file

```bash
head -60 system/snappyHexMeshDict
grep -n "refinementSurfaces\|refinementRegions\|geometry" system/snappyHexMeshDict
```

Verify that the geometry block, `refinementSurfaces`, and `refinementRegions` sections
contain the expected entries.

---

## Debug Mode

Capture all output for inspection:

```bash
python3 -u setup_snappy.py 2>&1 | tee generator_debug.log
```

If you need to trace the configuration parsing, add temporary `print` statements to
`setup_snappy.py` around the loading and merging logic:

```python
print(f"[debug] geometry keys: {list(geometry.keys())}")
print(f"[debug] surfaceHandling resolved: {resolved_surfaces}")
```

---

## Need More Help?

1. **Check examples** — `snappy_inputs.json` has a complete working configuration
2. **Read the schema** — `documentation/JSON_SCHEMA_GUIDE.md` for detailed field docs
3. **OpenFOAM reference** — `examples/refinementSurfaces` shows expected output format
4. **Error messages** — always read them in full; they name the exact field and value

---

**Last Updated**: 2026-04-26
