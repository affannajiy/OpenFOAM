# OpenFOAM topoSetDict Generators

This directory contains Python utility scripts that automate the generation of `topoSetDict` files for OpenFOAM cases. They manage complex multi-region meshing by ensuring mutually exclusive solid cellZones and automatically generating the complementary fluid domain.

## Requirements

* **Python:** 3.12+
* **OpenFOAM:** v2512
* **Dependencies:** `jinja2>=3.1` (for `ensureConsistentCellZones.py` and `createFluidCellZone.py`); all other scripts use the standard library only

Verify your environment before first use:
```bash
python3 check_env.py
```

Install dependencies if needed:
```bash
pip install -r requirements.txt
```

---

## Scripts

### 1. `ensureConsistentCellZones.py`

#### What it does

In a multi-region CHT (conjugate heat transfer) mesh, multiple solid components (heater, PCB, housing, etc.) are each represented by a closed surface file (`.stl` or `.obj`) and must each occupy a distinct, non-overlapping `cellZone`. If the surfaces overlap in geometry — which is common with CAD tolerances — the mesh cells in the overlap region end up assigned to more than one zone, which causes `topoSet` and solver errors.

This script generates `system/topoSetDict_consistentCellZones`: a `topoSet` dictionary that adds each surface to its cellZone and then explicitly subtracts all higher-priority surfaces from it, ensuring every cell belongs to exactly one zone.

#### How priority works

Surface files are discovered automatically in `--surfaceDir` and sorted alphabetically. **Sort order defines priority: the first file alphabetically has the highest priority.** When two surfaces overlap, the overlapping cells are kept in the higher-priority zone and removed from the lower-priority one.

For example, with three surfaces:

```
constant/triSurface/
  chip.stl       → priority 1 (highest)
  heater.stl     → priority 2
  pcb.stl        → priority 3 (lowest)
```

The generated actions will be:

| Zone | Operations |
|------|-----------|
| `chip` | clear → add from `chip.stl` |
| `heater` | clear → add from `heater.stl` → **subtract `chip.stl`** |
| `pcb` | clear → add from `pcb.stl` → **subtract `chip.stl`** → **subtract `heater.stl`** |

After running `topoSet`, each cell belongs to exactly one zone, with no gaps and no overlaps.

> **Tip:** Use `--dry-run` before writing the file. The summary prints the full priority order and planned operations so you can verify correctness before committing.

#### Two modes

| Mode | When to use | Reset action |
|------|-------------|--------------|
| **Default** | Zones already exist in the mesh (re-running after mesh changes) | `clear` + `add` per zone |
| **`--createNewCellZones`** | Fresh mesh — zones do not yet exist | `new` per zone (creates and fills in one step) |

The script validates which mode is appropriate by checking the `--checkMeshLog` file:
- **Default mode**: issues a warning (non-fatal) if a zone name is not found in the log — this may indicate a typo or a surface that should be excluded.
- **`--createNewCellZones`**: exits with a fatal error if any zone already exists in the mesh — this prevents accidentally overwriting existing zone data.

#### Zone naming

Zone names are derived automatically from the surface file basename, with the extension stripped:

```
chip.stl    →  cellZone: chip
heater.stl  →  cellZone: heater
pcb.stl     →  cellZone: pcb
```

If two files in the directory produce the same zone name (e.g. `heater.stl` and `heater.obj`), the script exits with a fatal error listing the conflict.

#### Excluding files

Not every surface file in `--surfaceDir` represents a solid zone. Domain boundary surfaces (e.g. outer enclosure, fluid box) should be skipped. Use `--exclude` to list filenames to ignore during auto-discovery:

```bash
--exclude '(outer-enclosure.stl fluid-domain.stl)'
```

Exclusion is case-sensitive on the filename body but case-insensitive on the extension, so `outer-enclosure.STL` is excluded by `outer-enclosure.stl`.

#### Prerequisites

- Run from the **OpenFOAM case root** directory. The script checks for `system/controlDict` and exits immediately if it is not found.
- The `--checkMeshLog` file must contain a `Checking basic cellZone addressing...` section. Run `checkMesh` and redirect its output to a log file before invoking this script.
- Surface files referenced in the dict must be present in `constant/triSurface` at the time `topoSet` is run (not at the time this script is run).

#### Usage

```bash
# Default mode — update existing cellZones (--surfaceDir defaults to constant/triSurface):
python3 ensureConsistentCellZones.py \
    --checkMeshLog log.checkMesh_start \
    [--surfaceDir constant/triSurface] \
    [--exclude '(outer-domain.stl)'] \
    [--dry-run]

# Create-new mode — create brand-new cellZones on a fresh mesh:
python3 ensureConsistentCellZones.py \
    --checkMeshLog log.checkMesh_start \
    --createNewCellZones \
    [--surfaceDir constant/triSurface] \
    [--exclude '(outer-domain.stl)'] \
    [--dry-run]
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--surfaceDir` | No | Directory containing `.stl`/`.obj` surface files to process. Defaults to `constant/triSurface` |
| `--checkMeshLog` | Yes | Path to a `checkMesh` log file used to validate zone names against the mesh |
| `--createNewCellZones` | No | Create zones that do not yet exist in the mesh (uses `action new` instead of `clear` + `add`) |
| `--exclude` | No | Space-separated list of filenames to skip during auto-discovery, e.g. `'(outer-domain.stl fluid-box.stl)'` |
| `--dry-run` | No | Print the priority order and planned operations without writing any file |

#### Output

Writes `system/topoSetDict_consistentCellZones` (overwrites if it already exists). Pass this file to `topoSet`:

```bash
topoSet -dict system/topoSetDict_consistentCellZones
```

---

### 2. `createFluidCellZone.py`

#### What it does

After running `ensureConsistentCellZones.py` to define all solid zones, this script generates `system/topoSetDict_fluidCellZone` to carve out the complementary fluid zone. It reads all existing solid cellZone names from a `--checkMeshLog` file, unions them, and inverts the selection so that every mesh cell not belonging to a solid zone is assigned to the fluid zone.

#### Usage

```bash
python3 createFluidCellZone.py --checkMeshLog log.checkMesh_start [-name domain_fluid] [--dry-run]
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--checkMeshLog` | Yes | Path to a `checkMesh` log file used to discover existing solid cellZone names |
| `-name` | No | Name of the resulting fluid cellZone (default: `domain_fluid`) |
| `--dry-run` | No | Print the discovered solid zones and planned actions without writing the file |

#### Output

Writes `system/topoSetDict_fluidCellZone`. Pass this file to `topoSet`:

```bash
topoSet -dict system/topoSetDict_fluidCellZone
```

---

## Typical Workflow

1. **Run `checkMesh`** on your initial mesh and save the log:
   ```bash
   checkMesh > log.checkMesh_start 2>&1
   ```

2. **Preview the solid zone plan** with `--dry-run` to confirm priority order and exclusions:
   ```bash
   python3 ensureConsistentCellZones.py \
       --surfaceDir constant/triSurface \
       --checkMeshLog log.checkMesh_start \
       --createNewCellZones \
       --exclude '(outer-domain.stl)' \
       --dry-run
   ```

3. **Generate and apply the solid cellZone dict:**
   ```bash
   python3 ensureConsistentCellZones.py \
       --surfaceDir constant/triSurface \
       --checkMeshLog log.checkMesh_start \
       --createNewCellZones \
       --exclude '(outer-domain.stl)'
   topoSet -dict system/topoSetDict_consistentCellZones
   ```

4. **Generate and apply the fluid cellZone dict:**
   ```bash
   python3 createFluidCellZone.py --checkMeshLog log.checkMesh_start -name fluid_region
   topoSet -dict system/topoSetDict_fluidCellZone
   ```
