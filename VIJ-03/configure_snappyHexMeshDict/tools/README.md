# Tools

Helper utilities for preparing inputs to `setup_snappy.py`. These tools run
**before** the main workflow and are independent of the Python environment.

---

## snappy_inputs_generator.html

A browser-based GUI for building `snappy_inputs.json` — the configuration file
consumed by `setup_snappy.py`. Use this instead of hand-writing JSON.

### What it does

Provides a point-and-click interface for configuring geometry files and standard
shapes, assigning surface/volume refinement settings, and downloading a valid
`snappy_inputs.json` ready for `setup_snappy.py`.

### Usage

1. Open `snappy_inputs_generator.html` in any modern browser (Chrome, Edge, Firefox)
2. Fill in the **Settings** panel:

| Field | Description |
|-------|-------------|
| **Geometry Unit** | Unit of your STL/OBJ files (`mm`, `cm`, `m`, `um`, `in`, `ft`) |
| **Num Cores** ⚠ | Number of parallel subdomains (must be ≥ 1). If `1`, no `decomposeParDict` is generated (serial run). If > 1, writes `system/decomposeParDict` with `numberOfSubdomains` |
| **Location In Mesh** | A point strictly inside the mesh domain (x, y, z). Use `find_interior_point.py` to find this automatically |
| **Reference Geometry** | The STL/OBJ file snappyHexMesh bases the bounding box on. Populated from included files. Required for automatic `blockMeshDict` generation |
| **Base Grid** | Background mesh cell size. **Uniform** = single value; **Anisotropic** = separate dx, dy, dz |

3. Click **Browse triSurface Folder** and select the folder containing your STL/OBJ files
   (typically `constant/triSurface`)
4. Configure each file in the **Geometry Files** table (see below)
5. Optionally add parametric shapes with **+ Add Shape** in the **Standard Shapes** panel
6. Click **Download JSON** → save as `snappy_inputs.json` in your case directory

### Toolbar Buttons

| Button | Action |
|--------|--------|
| **Browse triSurface Folder** | Loads all `.stl`, `.obj`, `.stlb` files from a folder. If the table is not empty, prompts whether to replace all rows or append new files only. Deduplicates — files already in the table are skipped |
| **Load snappy_inputs.json** | Loads an existing `snappy_inputs.json` back into the UI for round-trip editing. Restores all file rows, shape rows, sub-regions, auto-refine flags, and settings |
| **Download JSON** | Generates `snappy_inputs.json` and saves it. Uses the browser's native Save dialog (`showSaveFilePicker`) if available, otherwise triggers a browser download |
| **Clear** | Removes all geometry file rows and shape rows |

### Geometry Files Table Columns

| Column | Description |
|--------|-------------|
| **Include** | Whether this file appears in `geometry.files`. Uncheck to exclude from JSON |
| **Multi-region** | Enable if the STL has multiple solid regions (inlet, outlet, walls, etc.). When checked, sub-region rows appear for per-solid `refinementLevels`. Auto-detected for ASCII STL files on browse. **Disables Auto Refine** |
| **Surface Type** | `none` = geometry only (no surface refinement); `boundary` = mesh boundary patch; `faceZone` = face zone (and optionally a cell zone) |
| **Cell Zone** | Create a cell zone inside the surface. Only active when Surface Type = `faceZone` |
| **Auto Refine** | Let `setup_snappy.py` compute refinement levels automatically from geometry analysis. Sets `autoRefine: true` in the JSON (see note below). Disabled when Multi-region is on |
| **Surf Min / Max** | Manual surface refinement level range `[min, max]`. Disabled when Auto Refine is on |
| **Vol Dir** | Volume refinement direction: `none`, `inside`, or `outside`. Independent of surface type and Auto Refine — can be set freely for any surface type including boundary. Disabled only when the row is not included |
| **Vol Level** | Volume refinement level. Disabled when Vol Dir = `none` or Auto Refine is on (level is auto-computed in that case) |

#### Multi-region sub-rows

When **Multi-region** is enabled, indented sub-rows appear — one per solid region.
Enter the exact solid name from the STL file and set independent `Surf Min`/`Surf Max`
for each region. ASCII STL files have solid names pre-filled automatically on browse.
Use `grep "^solid" filename.stl` to list solid names manually.

### Standard Shapes Table

Click **+ Add Shape** to add a parametric geometry object. Supports all 9 shape types:

| Shape Type | Parameters shown in UI |
|------------|------------------------|
| `Sphere` | centre (x, y, z), radius |
| `Cylinder` | point1, point2, radius |
| `Box` | min (x, y, z), max (x, y, z) |
| `Cone` | point1, radius1, point2, radius2 |
| `RotatedBox` | origin, span, e1, e3 |
| `Disk` | origin, normal, radius |
| `Plate` | origin, span |
| `Plane` | planeType selector (`pointAndNormal` / `embeddedPoints` / `planeEquation`) + type-specific fields |
| `SurfaceWithGaps` | surface filename, gap |

Shapes have the same Surface Type, Cell Zone, Surf Min/Max, Vol Dir, Vol Level columns
as file rows. **Auto Refine is not available for shapes** — use explicit level values.

### Auto Refine Note

The **Auto Refine** toggle uses the `autoRefine: true` JSON key (not the `AUTO_`
filename prefix encoding convention). The two mechanisms are equivalent from
`setup_snappy.py`'s perspective. The JSON key approach (`autoRefine: true`) is
preferred and is what this tool generates.

### Output Format

The downloaded JSON uses the explicit configuration schema — no encoded filenames:

```json
{
    "_version": "1.1",
    "settings": { "geometryUnit": "mm", "numCores": 4 },
    "backgroundMesh": {
        "referenceGeometry": "outer-domain.stl",
        "baseGrid": 10
    },
    "geometry": {
        "files": ["outer-domain.stl", "mosfet.stl"],
        "standardShapes": [...]
    },
    "surfaceHandling": {
        "selectedParts": ["outer-domain", "mosfet"],
        "surfaces": {
            "__defaults__": { "type": "boundary", "refinementLevels": [0, 0] },
            "mosfet": { "type": "faceZone", "cellZoneInside": "inside", "refinementLevels": [1, 4] }
        }
    },
    "volumeRefinement": {
        "selectedParts": ["outer-domain"],
        "regions": {
            "__defaults__": { "mode": "inside", "level": 0 },
            "outer-domain": { "mode": "inside", "level": 0 }
        }
    },
    "castellatedMeshControls": {
        "locationInMesh": [50, 25, 25]
    }
}
```

Fields not shown in the UI (`addLayers`, `mergeTolerance`, mesh quality controls, etc.)
are supplied by `defaults.json` when `setup_snappy.py` runs.

### Notes

- The generated JSON uses **explicit refinement levels** — the recommended approach.
  The encoding convention (`geometry_renamer.html`) is no longer recommended
- `locationInMesh` must be a point inside the mesh domain. Use `find_interior_point.py`
  if unsure
- After downloading, open in a text editor and check any `[0, 0]` default refinement
  levels — the tool cannot know your target cell sizes

---

## geometry_renamer.html

> **Legacy tool** — only needed when using the prefix-based name encoding convention,
> which is [not recommended for new configurations](../documentation/ENCODING_CONVENTION.md).
> For new configurations, use `snappy_inputs_generator.html` instead.

A browser-based tool for assigning encoding prefixes to geometry files
(`.stl`, `.obj`) before running `setup_snappy.py`.

### What it does

`setup_snappy.py` reads refinement settings from the encoded filename. This
tool provides a graphical interface for building those encoded names and
generates the shell rename commands.

**Encoding format produced:**

| Mode | Example output |
|------|---------------|
| Auto refine | `AUTO_SURF_FZ_CZ_VOL_IN_mosfet.stl` |
| Manual levels | `SURF_FZ_CZ_L2_L5_VOL_IN_L3_mosfet.stl` |
| Surface only | `SURF_BND_L2_L4_emi-shield.stl` |
| Volume only (auto) | `AUTO_VOL_IN_outer-domain.stl` |

### Usage

1. Open `geometry_renamer.html` in any modern browser (Chrome, Edge, Firefox)
2. Click **Browse Folder** and select the folder containing your STL files
   (typically `constant/triSurface`)
3. Configure each file using the table columns:

| Column | Description |
|--------|-------------|
| **Encode** | Uncheck to skip a file entirely |
| **Auto Refine** | Derive refinement levels automatically from geometry (`AUTO_` prefix). Disables manual level inputs. |
| **Surface Type** | `boundary` → `BND`, `faceZone` → `FZ` |
| **Cell Zone** | Appends `_CZ` to faceZone token (`FZ_CZ`). Only active when Surface Type is faceZone. |
| **Surf Min / Max** | Manual surface refinement levels (disabled when Auto is on) |
| **Volume Refinement** | `Inside` → `VOL_IN`, `Outside` → `VOL_OUT`, `none` → no volume block |
| **Vol. Level** | Manual volume refinement level (disabled when Auto is on) |

4. Review the **Encoded Name Preview** column (live update)
5. Click **Copy to Clipboard** and paste the script into a terminal running
   from the geometry files directory

### Already-encoded files

If the folder already contains encoded filenames, the tool detects and parses
them automatically. Each such file is marked with an **already encoded** badge
and its current settings are pre-populated. If no changes are made, no rename
command is generated for that file.

### Notes

- Files where Encode is unchecked are omitted from the rename script entirely
- A warning badge appears in the stat bar for any row with neither surface nor
  volume type selected (these produce no prefix and are skipped)
- The generated script assumes the terminal is already `cd`'d into the geometry
  files directory

---

## flip_normals.py

A command-line utility to flip the face normals of one or more STL files
in-place. Useful when snappyHexMesh reports an inside-out surface or when
`locationInMesh` ends up on the wrong side.

**Requires:** `trimesh` (`pip install trimesh`)

### Usage

```bash
# Single file
python3 tools/flip_normals.py constant/triSurface/mosfet-1.stl

# Multiple files at once
python3 tools/flip_normals.py heatsink.stl pcb-board.stl emi-shield.stl
```

The original file is overwritten. Copy or version-control the file first if
you need to preserve the original.

### Notes

- Accepts `.stl` and `.stlb` extensions
- Prints face count and a confirmation line for each file processed
- Validates all paths before processing any file — no partial writes on error

---

## find_interior_point.py

Finds a point strictly inside a closed geometry file and prints it in one of
three formats. The primary use case is generating `locationInMesh` for
`snappyHexMeshDict` without manual inspection in a CAD tool.

**Supports:** `.stl`, `.stlb`, `.obj`

**Requires:** `numpy`, `trimesh` (`pip install numpy trimesh`)

### Usage

```bash
# Default — space-separated (easy to copy-paste)
python3 tools/find_interior_point.py constant/triSurface/outer-domain.stl

# OpenFOAM locationInMesh format — paste directly into snappyHexMeshDict
python3 tools/find_interior_point.py outer-domain.stl --format foam

# JSON — for scripting
python3 tools/find_interior_point.py outer-domain.stl --format json

# Mesh with holes — attempt automatic repair first
python3 tools/find_interior_point.py outer-domain.stl --repair
```

**Example output (`--format foam`):**
```
(25.24 16.93 100.69)
```

Paste directly into `castellatedMeshControls`:
```
castellatedMeshControls
{
    locationInMesh  (25.24 16.93 100.69);
    ...
}
```

### How it works

The algorithm uses three steps, falling back to the next only if the previous
fails:

**Step 1 — Bounding-box centre**
The midpoint of the geometry's bounding box is tested first. This works
immediately for any convex shape (box, sphere, cylinder) and is the fastest
path.

**Step 2 — Uniform grid search**
For concave or hollow shapes (e.g. a U-bracket or a housing with an internal
void), the bounding-box centre may fall outside the solid. The algorithm
builds a uniform 10×10×10 grid of candidate points across the bounding box,
shifted 1% inward from each face to avoid landing exactly on the surface.
All candidates are tested at once (vectorised ray-cast). From the interior
hits, the point closest to the bounding-box centre is returned — the most
geometrically central choice. Increase `--grid-resolution` for very concave
geometries.

**Step 3 — Random sampling fallback**
If the grid produces no interior hits, `trimesh.sample.volume_mesh()` draws
64 random points inside the mesh using signed-volume decomposition —
mathematically guaranteed to be interior for any watertight mesh. The point
closest to the centre is returned.

### `--repair` mode (non-watertight meshes)

If the mesh has holes or inconsistent normals, the tool exits with an
actionable error message:

```
Error: 'outer-domain.stl' is not a closed (watertight) mesh.
       A closed surface is required to find a reliable interior point.
       Options:
         1. Re-run with --repair to attempt automatic hole filling.
         2. Check for flipped normals: python3 flip_normals.py <file>
         3. Inspect the mesh: surfaceCheck <file>
```

With `--repair`, two further strategies are tried in order:

**Repair Step A — trimesh hole filling**
`trimesh.repair.fill_holes()` and `trimesh.repair.fix_winding()` are applied.
If the mesh becomes watertight, the normal 3-step algorithm runs on the
repaired mesh.

**Repair Step B — Voxelisation fallback**
If the mesh remains open after repair (e.g. large gaps), the mesh is
converted to a filled voxel grid. The centroid of the enclosed voxel closest
to the bounding-box centre is returned. This works even for meshes with holes
because the voxeliser uses inside/outside voting rather than ray-casting.
The result is marked as **approximate** in the output.

If both repair steps fail, the tool advises using `pymeshfix` or a CAD tool
for manual inspection.

### Notes

- The mesh must be watertight for a reliable result. Use `--repair` for meshes
  with small defects; voxelisation results should be visually verified.
- `--grid-resolution N` controls Step 2 (default 10 → 1000 candidates).
  Raise to 20 for highly concave geometry.
- JSON output includes an `"approximate": true/false` field indicating whether
  the voxelisation fallback was used.

