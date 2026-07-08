# snappy_inputs_generator — GUI Workflow

Browser-based tool for generating `snappy_inputs.json` and meshing shell scripts.
Open `snappy_inputs_generator.html` in any modern browser — no installation required.

---

## What it generates

| File | Description |
|---|---|
| `snappy_inputs.json` | Configuration for `setup_snappy.py` — mesh refinement settings |
| `Allrun.snappy` | Runs `blockMesh` + `snappyHexMesh` (serial or parallel) |
| `Allrun.extra` | Post-snappy cell zone processing (see below) |
| `Allclean` | Removes all generated case files, preserving geometry and scripts |

---

## Allrun.extra — step sequence

`Allrun.extra` is generated from the **Allrun.extra Script Settings** panel. It runs
after `Allrun.snappy` and handles cell zone consistency, fluid zone creation, optional
mesh scaling, and multi-region splitting.

```
1. checkMesh -constant
   → baseline mesh quality check (log: log.checkMesh.beforeConsistentCellZones)

2. ensureConsistentCellZones.py --checkMeshLog ... [--exclude '(file.stl ...)']
   → makes solid cell zones mutually exclusive
   → files marked "Not a component" in the GUI are passed to --exclude

3. topoSet -dict system/topoSetDict_consistentCellZones

4. checkMesh -constant
   → verify corrected zones (log: log.checkMesh.afterConsistentCellZones)

5. createFluidCellZone.py --checkMeshLog ... -name <fluidZoneName>
   → creates fluid zone as the complement of all solid zones

6. topoSet -dict system/topoSetDict_fluidCellZone

7. [optional] transformPoints -scale <factor>
   → only emitted when "Scale Mesh to Metres" is enabled and scale ≠ 1.0
   → scale is auto-set from the geometry unit (e.g. mm → 0.001)

8. [optional] splitMeshRegions -cellZonesOnly -combineZones ... -customRegionNames ...
   → only emitted when CHT multi-region config is enabled with ≥ 2 regions

9. Final mesh check and reconstruction
   → Non-CHT:  checkMesh -constant  (+ reconstructParMesh if parallel)
   → CHT:      checkMesh -region <name> -constant  per region
               + reconstructParMesh -regions '(...)' -constant  (if parallel)
```

---

## Allclean — what it removes

```
cleanCase0                        # processor dirs, logs, time dirs
rm -rf constant/<region>  ...     # CHT region dirs (only when ≥ 2 CHT regions defined)
rm -rf system                     # all generated system/ dicts
```

Preserved: `constant/triSurface/`, `snappy_inputs.json`, `Allrun*`, `Allclean`.

---

## Key GUI settings

| Setting | Effect |
|---|---|
| **Geometry Unit** | Stored as metadata in JSON; also sets the auto-scale factor for `transformPoints` |
| **Num Cores** | Controls `runParallel` vs `runApplication` throughout all scripts |
| **Not a component** | Files (e.g. domain bounding boxes) excluded from `ensureConsistentCellZones.py` |
| **Fluid Cell Zone Name** | Name passed to `createFluidCellZone.py -name` |
| **Python Utils Dir** | Path to `other_utilities/` — must be updated per machine |
| **CHT regions** | Zone groupings for `splitMeshRegions`; also drives per-region `checkMesh` and `Allclean` `rm` lines |

---

## Round-tripping JSON

All script-generation settings are persisted in `scriptSettings` inside `snappy_inputs.json`
(see `configuration_guide.md` § scriptSettings). Loading an existing JSON fully restores
the GUI state — downloading scripts again produces identical output.
