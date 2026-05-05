# Tools

Helper utilities for preparing inputs to `setup_snappy.py`. These tools run
**before** the main workflow and are independent of the Python environment.

---

## geometry_renamer.html

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

