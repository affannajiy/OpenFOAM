# sim_inputs_generator — GUI Workflow

Browser-based wizard for generating `sim_inputs.json` and simulation shell scripts.
Open `sim_inputs_generator.html` in any modern browser — no installation required.

---

## What it generates

| File | Description |
|---|---|
| `sim_inputs.json` | Configuration for `setup_case.py` — full CHT/single-region case setup |
| `Allrun` | Runs the simulation (serial or parallel, CHT or single-region) |
| `Allclean` | Removes all generated time dirs, processor dirs, and logs |
| `custom_materials_library.json` | Exported only when custom materials are defined (side-car file) |

---

## Wizard steps

| # | Title | What you configure |
|---|---|---|
| 1 | General | Solver, case type (`cht` / `single-fluid` / `single-solid`), working directory, inputData/ folder |
| 2 | Mesh Import | Paste checkMesh logs — auto-populates regions, boundaries, cellZones, faceZones |
| 3 | CHT Interfaces | Pair fluid/solid boundaries; set conformality and thermal layers. Skipped for single-region cases |
| 4 | Material Properties | Assign materials per region/cellZone from the built-in or custom library |
| 5 | Physical Models | Gravity, reference conditions, turbulence model, radiation model |
| 6 | Boundary Conditions | BC type and values per patch, per region |
| 7 | FaceZone Conditions | Fan baffle setup (fan curve CSV) for internal faceZones in fluid regions |
| 8 | Source Terms | fvOptions volumetric heat sources per region or cellZone |
| 9 | Initial Conditions | Uniform field initialisation for all regions |
| 10 | Monitoring | Function objects: patch/cellZone/faceZone/cuttingPlane averages |
| 11 | Numerics | Discretisation schemes, linear solvers, convergence criteria, relaxation factors |
| 12 | Run Settings | End time, write interval, parallel cores, write format, time-stepping |
| 13 | Export Preview | Review JSON, download all output files |

---

## Allrun — step sequence

`Allrun` content is driven by **case type** and **number of cores** (Step 12).

**CHT + serial**
```
renumberMesh -allRegions -overwrite
$(getApplication)
```

**CHT + parallel**
```
decomposePar -allRegions
renumberMesh -allRegions -overwrite  (parallel)
$(getApplication)                    (parallel)
reconstructParMesh -allRegions
reconstructPar -allRegions -latestTime
```

**Single region + serial**
```
renumberMesh -overwrite
$(getApplication)
```

**Single region + parallel**
```
decomposePar
renumberMesh -overwrite              (parallel)
$(getApplication)                    (parallel)
reconstructParMesh -constant
reconstructPar -latestTime
```

**Baffles (optional):** if any fluid region has active FaceZone conditions (Step 7),
`createBaffles -region <name> -overwrite` is prepended before decompose/renumber.

---

## Allclean — what it removes

```
foamListTimes -rm              # all time directories
rm -rf processor* postProcessing log.*
```

---

## Key GUI settings

| Setting | Effect |
|---|---|
| **Case type** | `cht` enables CHT interfaces (Step 3) and `-allRegions` flags in Allrun |
| **Solver name** | Filtered by case type — only compatible solvers are shown |
| **Num Cores** | Controls `runParallel` vs `runApplication` and adds decompose/reconstruct steps |
| **Custom materials** | Saved to `custom_materials_library.json` — load it back via the material library panel |
| **FaceZone conditions** | Any active fan condition triggers `createBaffles` in Allrun |

---

## Project import / export

- **Save Draft** — saves full UI state (including custom materials inline) as `sim_inputs_draft.json`
- **Load Project** (Chrome/Edge) — pick a folder; auto-loads `sim_inputs.json` or draft, `custom_materials_library.json`, and any CSV files from `inputData/`
- **Load Project** (Firefox fallback) — multi-file picker; select files individually

Loading a project fully restores GUI state — downloading scripts again produces identical output.

---

## Custom materials

Custom materials are defined in the Material Library panel (Step 4).
On export, if custom materials exist, a `📥 custom_materials_library.json` button appears in
Step 13 — click it to download separately and place alongside `sim_inputs.json`.
The file can be reloaded into any session via the library panel's load button.
