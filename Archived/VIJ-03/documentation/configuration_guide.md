# sim_inputs.json Configuration Guide

Complete reference for all sections of `sim_inputs.json`. Sections appear in the same order as they do in the file. Cross-reference freely — most sections are self-contained.

> **GUI tool:** The browser-based wizard `configure_simInputs/tools/sim_inputs_generator.html` generates this file interactively. See [`configure_simInputs/tools/gui_workflow.md`](../configure_simInputs/tools/gui_workflow.md) for a walkthrough of the wizard steps and generated scripts.

> **Single-region vs multi-region layout**
>
> When exactly **one** region is declared (one fluid **or** one solid), `setup_case.py` produces the standard OpenFOAM single-region flat layout:
>
> | Item | Single-region path | Multi-region path |
> |------|--------------------|-------------------|
> | Field files | `0/T`, `0/U`, … | `0/<region>/T`, `0/<region>/U`, … |
> | Constant properties | `constant/turbulenceProperties`, … | `constant/<region>/turbulenceProperties`, … |
> | polyMesh | `constant/polyMesh/` | `constant/<region>/polyMesh/` |
> | Schemes & solution | `system/fvSchemes`, `system/fvSolution` | `system/<region>/fvSchemes`, `system/<region>/fvSolution` |
> | fvOptions | `system/fvOptions` | `system/<region>/fvOptions` |
> | `regionProperties` | not created | `constant/regionProperties` |
> | `region` in function objects | omitted | present |
> | `nOuterCorrectors` (transient fluid) | in `system/fvSolution` PIMPLE dict | in top-level `system/fvSolution` |
>
> The JSON structure is identical in both cases — only the generated file layout differs.

---

## Table of Contents

1. [simulation](#1-simulation)
2. [regions](#2-regions)
3. [region_parts](#3-region_parts)
4. [gravity](#4-gravity)
5. [reference_conditions](#5-reference_conditions)
6. [material_properties](#6-material_properties)
   - [6.1 Fluid regions](#61-fluid-regions)
   - [6.2 Solid regions](#62-solid-regions)
7. [turbulence](#7-turbulence)
   - [7.1 Supported RANS models](#71-supported-rans-models)
   - [7.2 Wall functions](#72-wall-functions)
   - [7.3 Turbulence inlet conditions](#73-turbulence-inlet-conditions)
   - [7.4 Turbulence at pressure outlets](#74-turbulence-at-pressure-outlets)
8. [radiation](#8-radiation)
   - [8.1 fvDOM coefficients](#81-fvdom-coefficients)
   - [8.2 viewFactor coefficients](#82-viewfactor-coefficients)
9. [initial_conditions](#9-initial_conditions)
10. [boundary_conditions](#10-boundary_conditions)
    - [10.1 Patch grouping](#101-patch-grouping)
    - [10.2 Fluid boundary condition types](#102-fluid-boundary-condition-types)
      - [10.2.1 `velocity-inlet`](#1021-velocity-inlet)
      - [10.2.2 `total-pressure-inlet`](#1022-total-pressure-inlet)
      - [10.2.3 `pressure-outlet`](#1023-pressure-outlet)
      - [10.2.4 `no-slip-wall`](#1024-no-slip-wall)
      - [10.2.5 `slip-wall`](#1025-slip-wall)
    - [10.3 Solid boundary condition types](#103-solid-boundary-condition-types)
      - [10.3.1 `solid-wall`](#1031-solid-wall)
    - [10.4 Thermal BC modes](#104-thermal-bc-modes)
    - [10.5 CHT interfaces](#105-cht-interfaces)
    - [10.6 Constraint patch types](#106-constraint-patch-types)
11. [faceZone_conditions](#11-facezone_conditions)
12. [numerical_schemes](#12-numerical_schemes)
13. [matrix_solvers](#13-matrix_solvers)
14. [iterative_solver](#14-iterative_solver)
15. [convergence_criteria](#15-convergence_criteria)
16. [relaxation_factors](#16-relaxation_factors)
17. [function_objects](#17-function_objects)
    - [17.1 Supported operation types](#171-supported-operation-types)
    - [17.2 cuttingPlane scope](#172-cuttingplane-scope)
    - [17.3 Field name mapping](#173-field-name-mapping)
    - [17.4 Naming convention](#174-naming-convention)
18. [fv_options](#18-fv_options)
    - [18.1 Common errors](#181-common-errors)

---

## 1. simulation

Controls the solver selection, run duration, output frequency, and parallelisation.

```json
"simulation": {
    "type": "transient",
    "solver_name": "chtMultiRegionFoam",
    "end_time": 2000,
    "write_interval": 100,
    "num_cores": 16,
    "write_format": "binary",
    "write_precision": 6,
    "time_precision": 6,
    "delta_t": 0.001,
    "adjust_timestep": true,
    "max_delta_t": 0.01,
    "max_co": 1.0,
    "max_di": 10.0
}
```

| Key | Type | Description |
|-----|------|-------------|
| `type` | string | `"steady-state"` or `"transient"` |
| `solver_name` | string | OpenFOAM solver (see table below) |
| `case_type` | string | `"cht"` (multi-region fluid+solid), `"single-fluid"`, or `"single-solid"`. Determines the region layout and which solver names are valid. |
| `end_time` | int (steady) / float (transient) | Final time or iteration count |
| `write_interval` | int (steady) / float (transient) | Write frequency (iterations or time units) |
| `num_cores` | int ≥ 1 | Number of MPI processes; if set to `1`, `decomposeParDict` is not written (serial run) |
| `write_format` | string | `"ascii"` or `"binary"` — controls OpenFOAM field file format |
| `write_precision` | int ≥ 1 | Number of significant digits for field data output |
| `time_precision` | int ≥ 1 | Number of significant digits for time directory names |
| `delta_t` | float > 0 | **Transient only.** Time-step size. When `adjust_timestep: true`, this is the initial value; OpenFOAM adjusts it during the run. Omit for steady-state (hardcoded to `1`). |
| `adjust_timestep` | bool | **Transient only.** `true` enables adaptive time-stepping; `false` uses fixed `delta_t`. Omit for steady-state. |
| `max_delta_t` | float > 0 | Maximum allowable time-step size. **Required when `adjust_timestep: true`.** |
| `max_co` | float > 0 | Maximum Courant number. **Required when `adjust_timestep: true`.** |
| `max_di` | float > 0 | Maximum diffusion number. **Required when `adjust_timestep: true`.** |

**`writeControl` is derived automatically — do not set it in the config:**

| `type` | `adjust_timestep` | `deltaT` | `writeControl` |
|--------|-------------------|----------|----------------|
| `steady-state` | — (always off) | `1` (hardcoded) | `runTime` |
| `transient` | `false` | `delta_t` (fixed) | `runTime` |
| `transient` | `true` | `delta_t` (initial) | `adjustableRunTime` |

**Valid solver names by simulation type and region configuration:**

| `type` | `case_type` | Allowed solvers |
|--------|-------------|-----------------|
| `steady-state` | `cht` | `chtMultiRegionSimpleFoam` |
| `steady-state` | `single-fluid` | `buoyantSimpleFoam`, `simpleFoam` |
| `steady-state` | `single-solid` | `solidFoam` |
| `transient` | `cht` | `chtMultiRegionFoam` |
| `transient` | `single-fluid` | `buoyantPimpleFoam`, `pimpleFoam` |
| `transient` | `single-solid` | `solidFoam` |

> **Note:** `simpleFoam` and `pimpleFoam` are **incompressible** (isothermal) — no energy equation is solved, and `gravity` and `radiation` sections are not used. All other single-fluid solvers are compressible.

---

## 2. regions

Declares the fluid and solid region names. These names must match the subdirectory names inside `constant/` (multi-region) or the `constant/polyMesh` directory name (single-region).

```json
"regions": {
    "fluids": ["domain_fluid"],
    "solids": ["domain_solid"]
}
```

- Both `fluids` and `solids` are optional lists; at least one must be non-empty.
- A region name cannot appear in both lists.
- **Multi-region:** region names must match their `constant/<region>/polyMesh` directories exactly.
- **Single-region:** only one region in total (either one fluid or one solid). The region name is used for identification in the JSON only; the polyMesh lives directly at `constant/polyMesh/`.

---

## 3. region_parts

Maps each region to its mesh components, and defines CHT interface pairs. All names must match the polyMesh exactly.

```json
"region_parts": {
    "domain_fluid": {
        "boundaries": ["Inflow", "Outflow", "all_walls", "domain_fluid_to_domain_solid"],
        "cellZones": ["fluid_zone_A"],
        "faceZones": ["fan-baffle"]
    },
    "domain_solid": {
        "boundaries": ["domain_solid_to_domain_fluid", "external_walls"],
        "cellZones": ["zone-1", "zone-2"],
        "faceZones": []
    },
    "cht_interfaces": {
        "interface-1": {
            "pair": [
                {"region": "domain_fluid", "boundary": "domain_fluid_to_domain_solid"},
                {"region": "domain_solid", "boundary": "domain_solid_to_domain_fluid"}
            ],
            "conformal": true
        }
    }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `boundaries` | list of strings | All patch names in `polyMesh/boundary` for this region |
| `cellZones` | list of strings | Cell zone names (can be empty list) |
| `faceZones` | list of strings | Face zone names (can be empty list) |
| `cht_interfaces` | dict | (Optional) CHT interface definitions — **multi-region only** |

**CHT interface:**

| Key | Type | Description |
|-----|------|-------------|
| `pair` | 2-element list | Each entry has `region` (string) and `boundary` (string) |
| `conformal` | bool | `true` if meshes share nodes at the interface; `false` for AMI |

> CHT interface thermal layers (contact resistance) are configured under [`boundary_conditions.cht_interfaces`](#105-cht-interfaces), not here.

---

## 4. gravity

Gravitational acceleration vector `[gx, gy, gz]` in m/s².

```json
"gravity": [0.0, -9.81, 0.0]
```

Must be a 3-component numeric array. Used for buoyancy-driven flow. Not used by incompressible solvers (`simpleFoam`, `pimpleFoam`).

---

## 5. reference_conditions

Reference values used for pressure/temperature aliases and equation-of-state calculations.

```json
"reference_conditions": {
    "pressure": 101325.0,
    "temperature": 298.15
}
```

| Key | Type | Description |
|-----|------|-------------|
| `pressure` | float | Reference (absolute) pressure in Pa |
| `temperature` | float | Reference temperature in K |

**Aliases:** The strings `"REF-TEMP"` and `"REF-PRES"` can be used anywhere in the config (including `initial_conditions`, `boundary_conditions`, etc.) and will be replaced with the values above at setup time.

```json
"T": "REF-TEMP"   // resolved to 298.15
"p": "REF-PRES"   // resolved to 101325.0
```

---

## 6. material_properties

Defines thermophysical properties for each region. The structure differs between fluid and solid regions.

### 6.1 Fluid regions

> **Compressible vs incompressible fluid material properties**
>
> The required properties differ depending on the solver:
> - **Compressible** (`buoyantSimpleFoam`, `buoyantPimpleFoam`, etc.): material must be referenced by name from the materials library (built-in or custom). Inline property dicts are not supported.
> - **Incompressible** (`simpleFoam`, `pimpleFoam`): only constant `rho` and `mu` are needed. Accepted as either a library name string or an inline dict. `nu = mu / rho` is computed and written to `transportProperties` automatically.

**Compressible fluid regions**

Material must be a **plain library name string**. Inline property dicts are not accepted — the code will exit with an error if a dict is provided.

```json
"domain_fluid": "air-polynomial"
```

The library entry supplies all required properties: `molecular_weight`, `rho`, `Cp`, `mu`, `kappa`. To use a fluid not in the built-in library, define it in `custom_materials_library.json` at the case root (see [Section 6.2](#62-solid-regions) for library file details — the same file format applies to fluid entries).

**Generated OpenFOAM `thermoType` combinations** (determined by the library entry):

| rho model | Cp/mu/kappa model | transport | thermo | equationOfState |
|-----------|-------------------|-----------|--------|-----------------|
| `ideal-gas-temperature-only` | `polynomial` | `polynomial` | `hPolynomial` | `incompressiblePerfectGas` |
| `ideal-gas` | `polynomial` | `polynomial` | `hPolynomial` | `perfectGas` |
| `constant` | `constant` | `const` | `hConst` | `rhoConst` |

> **Note:** `rho: constant` requires `Cp`, `mu`, `kappa` to also be `constant`. Polynomial transport with constant density is not allowed.

**Incompressible fluid regions** (`simpleFoam`, `pimpleFoam`)

Accepted as a library name string or an inline dict with `model: "constant"` for `rho` and `mu`:

```json
"domain_fluid": "air-constant"
```

```json
"domain_fluid": {
    "rho": {"model": "constant", "value": 1.225},
    "mu":  {"model": "constant", "value": 1.81e-05}
}
```

`nu = mu / rho` is computed and written to `transportProperties`. `Cp`, `kappa`, and `molecular_weight` are not used.

---

### 6.2 Solid regions

All solid material entries **must reference a material from the library** — either the built-in `materials_library.json` or a `custom_materials_library.json` placed in the case root. Three forms are supported:

**Form 1 — Simple string (uniform isotropic):**

```json
"domain_solid": "copper"
```

**Form 2 — Dict with `material` key (uniform, with optional anisotropic kappa override):**

```json
"domain_solid": { "material": "aluminum-6061" }
```

```json
"domain_solid": {
    "material": "copper",
    "kappa_type": "anisotropic",
    "kappa": [395, 10, 10],
    "coordinate_system": {
        "origin": [0.1, -4.5, 3.78],
        "e1": [0.2, 0.76, -0.38],
        "e2": [0, 1, 0]
    }
}
```

**Form 3 — Cell-zone-specific (different material per zone):**

```json
"domain_solid": {
    "type": "cell_zone_specific",
    "properties": {
        "default": "aluminum-6061",
        "zone1,zone2": "copper",
        "zone5": { "material": "steel-304" }
    }
}
```

For anisotropic conductivity per zone, add `kappa_type` and `coordinate_system` at the top level and provide a `kappa` vector in each zone entry:

```json
"domain_solid": {
    "type": "cell_zone_specific",
    "kappa_type": "anisotropic",
    "coordinate_system": {
        "origin": [0.1, -4.5, 3.78],
        "e1": [0.2, 0.76, -0.38],
        "e2": [0, 1, 0]
    },
    "properties": {
        "default": { "material": "aluminum-6061", "kappa": [160, 160, 160] },
        "zone1,zone2": { "material": "copper", "kappa": [395, 10, 10] },
        "zone5": { "material": "steel-304", "kappa": [16, 1.6, 16] }
    }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `type` | string | `"cell_zone_specific"` (only for Form 3; omit for Forms 1 and 2) |
| `material` | string | Library material name (required in Forms 2 and 3 zone entries) |
| `kappa_type` | string | `"isotropic"` (default) or `"anisotropic"` |
| `coordinate_system` | dict | Required when `kappa_type: anisotropic`. Defines local axes for conductivity tensor. |
| `coordinate_system.origin` | 3-float list | Origin point of local coordinate system |
| `coordinate_system.e1` | 3-float list | First basis vector (x-direction of conductivity) |
| `coordinate_system.e2` | 3-float list | Second basis vector |
| `properties` | dict | (Form 3 only) Zone-to-material map. `"default"` key is mandatory. |

For `cell_zone_specific`:
- Zone keys can be a single zone name (`"zone5"`) or comma-separated names (`"zone1,zone2"`) to share properties.
- `"default"` applies to all cells not matched by any other zone key.
- `kappa` is a scalar for `isotropic` (taken from the library entry), a `[kx, ky, kz]` list for `anisotropic` (must be provided explicitly per zone).
- Inline property definitions (e.g., `"Cp": 500, "rho": 2700`) are **not supported** — all properties must come from the library.

> **Note:** Built-in library materials include `"copper"`, `"aluminum-6061"`, and `"steel-304"`. To use a custom material, define it in `custom_materials_library.json` at the case root.

---

## 7. turbulence

Configures the turbulence model for all fluid regions. Omitting this section (or setting `active: false`) runs laminar.

```json
"turbulence": {
    "active": true,
    "type": "RANS",
    "RANS_config": {
        "model": "kOmegaSST",
        "model_coeffs": {
            "Prt": 0.85,
            "decayControl": true
        },
        "wall_function": "Automatic",
        "thermal_wall_function": "Standard"
    }
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `active` | bool | Yes | `true` enables turbulence |
| `type` | string | Yes | Only `"RANS"` supported (`"DES"`, `"LES"` not yet implemented) |
| `RANS_config.model` | string | Yes | RANS model name |
| `RANS_config.model_coeffs` | dict | Yes | Coefficient overrides. `Prt` (turbulent Prandtl number) is **always mandatory**. |
| `RANS_config.wall_function` | string | No | `"Standard"` or `"Automatic"` (default: `"Standard"`) |
| `RANS_config.thermal_wall_function` | string | No | `"Standard"` or `"Jayatilleke"` (default: `"Standard"`) |

### 7.1 Supported RANS models

| Model | Fields solved | Valid coefficients |
|-------|---------------|--------------------|
| `kOmegaSST` | k, omega, nut, alphat | Prt, alphaK1, alphaK2, alphaOmega1, alphaOmega2, gamma1, gamma2, beta1, beta2, betaStar, a1, b1, c1, F3, decayControl, kInf, omegaInf |
| `kOmega` | k, omega, nut, alphat | Prt, betaStar, beta, gamma, alphaK, alphaOmega |
| `kEpsilon` | k, epsilon, nut, alphat | Prt, Cmu, C1, C2, C3, sigmak, sigmaEps |
| `RNGkEpsilon` | k, epsilon, nut, alphat | Prt, Cmu, C1, C2, C3, sigmak, sigmaEps, eta0, beta |
| `realizableKE` | k, epsilon, nut, alphat | Prt, A0, C2, sigmak, sigmaEps |

Specifying a coefficient name not in the above list for the chosen model is a fatal error. `Prt` is type `float`; `decayControl`, `F3` are type `bool` — passing the wrong type is caught at setup.

### 7.2 Wall functions

| Setting (`wall_function`) | `nut` BC | `omega` BC |
|---------------------------|----------|------------|
| `"Standard"` (default) | `nutkWallFunction` | `omegaWallFunction` (blended: false) |
| `"Automatic"` | `nutUSpaldingWallFunction` | `omegaWallFunction` (blended: true) |

Use `"Automatic"` for mixed-y+ meshes (Spalding's law of the wall). `k` always uses `kqRWallFunction`; `epsilon` always uses `epsilonWallFunction`.

| Setting (`thermal_wall_function`) | `alphat` BC |
|-----------------------------------|-------------|
| `"Standard"` (default) | `compressible::alphatWallFunction` |
| `"Jayatilleke"` | `compressible::alphatJayatillekeWallFunction` |

`nut` and `alphat` BCs at inlets/outlets are `calculated` (value `1e-10`) — no user input needed.

### 7.3 Turbulence inlet conditions

Required on every `velocity-inlet` and `total-pressure-inlet` patch when `turbulence.active: true`.

**Mode 1 — explicit values (`dirichlet`):**

```json
"turbulence": {
    "mode": "dirichlet",
    "k": 0.005,
    "omega": 100.0      // use "epsilon" for k-ε models
}
```

Generates `inletOutlet` BC for k and the dissipation variable.

**Mode 2 — physics-based (`intensity-and-length-scale`):**

```json
"turbulence": {
    "mode": "intensity-and-length-scale",
    "intensity": 0.05,       // fraction, not %
    "length_scale": 0.01
}
```

Generates `turbulentIntensityKineticEnergyInlet` for k, `turbulentMixingLengthFrequencyInlet` / `turbulentMixingLengthDissipationRateInlet` for omega/epsilon.

### 7.4 Turbulence at pressure outlets

- `prevent_backflow: true` → `zeroGradient` for k/omega/epsilon. No turbulence specification needed.
- `prevent_backflow: false` → Add the same `turbulence` dict inside `backflow_conditions`.

---

## 8. radiation

Configures the radiation model for fluid regions. Omitting or setting `active: false` disables radiation.

```json
"radiation": {
    "active": true,
    "model": "fvDOM",
    "model_coeffs": {
        "nPhi": 3,
        "nTheta": 6,
        "tolerance": 0.01,
        "maxIter": 10,
        "solverFreq": 50
    }
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `active` | bool | Yes | `true` enables radiation |
| `model` | string | Yes | `"fvDOM"` or `"viewFactor"` |
| `model_coeffs` | dict | Yes | Model-specific parameters |

### 8.1 fvDOM coefficients

| Key | Type | Description |
|-----|------|-------------|
| `nPhi` | int | Number of polar angles |
| `nTheta` | int | Number of azimuthal angles |
| `tolerance` | float | Convergence tolerance for radiation solve |
| `maxIter` | int | Maximum radiation sub-iterations |
| `solverFreq` | int | Radiation solve frequency (every N fluid iterations) |

### 8.2 viewFactor coefficients

| Key | Type | Description |
|-----|------|-------------|
| `smoothing` | bool | Enable view factor smoothing |
| `constantEmissivity` | bool | Use constant surface emissivity |
| `useDirectSolver` | bool | Use direct solver for view factor matrix |
| `nBands` | int | Number of spectral bands |
| `solverFreq` | int | Radiation solve frequency |

> **Note:** The model names use OpenFOAM conventions directly — `"fvDOM"` and `"viewFactor"`. These are case-sensitive.

When radiation is active, CHT interface temperature BCs include `qr qr;` and `qrNbr qrNbr;` on the fluid side. When inactive, both are set to `none`.

> **fvDOM — `IDefault` field:** For compressible solvers (`buoyantSimpleFoam`, `buoyantPimpleFoam`, `chtMultiRegion*`), `setup_case.py` automatically generates an `IDefault` field file in each fluid region's `0/` directory. This file is required by OpenFOAM's fvDOM solver and is not needed for `viewFactor` or when radiation is inactive.

When radiation is active, `setup_case.py` also generates `constant/<region>/boundaryRadiationProperties` for each fluid region. Emissivity (= absorptivity, grey-body assumption) is written per patch:

| Patch type | Emissivity written |
|---|---|
| `no-slip-wall`, `slip-wall` | User-specified via `"emissivity"` key (default 0.9) |
| CHT interface (fluid side) | User-specified via `boundary_conditions.cht_interfaces.<name>.emissivity` (default 0.9) |
| `velocity-inlet`, `total-pressure-inlet`, `pressure-outlet` | 1.0 (hardcoded) |
| Constraint types (`cyclic`, `symmetry`, `wedge`, …) | Omitted from the file |

---

## 9. initial_conditions

Sets the initial field values for all regions. Only the `"uniform"` method is currently supported.

```json
"initial_conditions": {
    "method": "uniform",
    "domain_fluid": {
        "U": [0.0, 0.0, 0.0],
        "p": 0.0,
        "T": "REF-TEMP",
        "k": 1.0,
        "omega": 1000
    },
    "domain_solid": {
        "T": 298.15
    }
}
```

**Rules:**

- Every region defined in `regions` must have an entry here.
- **Compressible** fluid regions require: `U` (3-component vector), `p` (gauge), `T`, and turbulence fields matching the active model (`k`+`omega` or `k`+`epsilon`).
- **Incompressible** fluid regions (`simpleFoam`, `pimpleFoam`) require only `U`, `p`, and turbulence fields. `T` is **not used** and must not be specified (no energy equation is solved).
- `nut` and `alphat` default to `1e-10` if omitted from compressible fluid initial conditions.
- `p_rgh` uses the same gauge value as `p` (internally converted to absolute).
- Solid regions require only `T`.
- Aliases `"REF-TEMP"` and `"REF-PRES"` are supported.
- `p` values are gauge (relative to `reference_conditions.pressure`). The code adds `reference_pressure` internally.

---

## 10. boundary_conditions

Defines BCs per region and CHT interface. The section is optional if no explicit BCs are needed.

```json
"boundary_conditions": {
    "domain_fluid": { ... },
    "domain_solid": { ... },
    "cht_interfaces": { ... }
}
```

### 10.1 Patch grouping

Multiple patches with identical BCs can share one definition using comma-separated keys:

```json
"In1, leftIn": {
    "type": "no-slip-wall",
    "thermal": {"mode": "heat-flux", "value": 0.0}
}
```

Generates `'(In1|leftIn)'` pipe syntax in OpenFOAM field files.

**Default catch-all:** Use the reserved key `"__default__"` to apply a BC to all patches not explicitly listed. This generates `'.*'` regex syntax in OpenFOAM.

---

### 10.2 Fluid boundary condition types

#### 10.2.1 `velocity-inlet`

```json
"Inflow": {
    "type": "velocity-inlet",
    "velocity": {
        "mode": "normal-magnitude",
        "value": 5.0
    },
    "thermal": {"mode": "temperature", "value": 293.15},
    "turbulence": {"mode": "intensity-and-length-scale", "intensity": 0.05, "length_scale": 0.007}
}
```

**velocity modes:**

| `mode` | `value` type | Time-varying `component_columns` |
|--------|-------------|----------------------------------|
| `"components"` | `[Ux, Uy, Uz]` | `[col_x, col_y, col_z]` (3 columns) |
| `"normal-magnitude"` | scalar (negated internally) | `[col_mag]` (1 column) |

Provide either `value` (constant) or `time_varying` (CSV), not both.

**`time_varying` structure:**

```json
"time_varying": {
    "csv_file": "data.csv",
    "ref_column": 0,
    "component_columns": [2],
    "skip_rows": 1
}
```

CSV files are read from `inputData/` in the case directory. Values outside the time range are clamped. Interpolation is linear.

**Generated OpenFOAM field types:**

| Field | Constant | CSV (components) | CSV (normal-magnitude) |
|-------|----------|------------------|------------------------|
| U | `fixedValue` | `uniformFixedValue` (csvFile) | `surfaceNormalFixedValue` + `ramp` |
| p/p_rgh | `totalPressure` | — | — |
| T | `fixedValue` / `uniformFixedValue` | `uniformFixedValue` | — |

`thermal` mode at inlets must be `"temperature"`. See [Section 10.4 Thermal BC modes](#104-thermal-bc-modes) below.

> **Warning:** Only `"temperature"` mode is supported for `thermal` at `velocity-inlet` and `total-pressure-inlet` patches. Using `"heat-flux"` or `"adiabatic"` at an inlet will cause an error during case setup.

---

#### 10.2.2 `total-pressure-inlet`

```json
"InletPatch": {
    "type": "total-pressure-inlet",
    "total_pressure": 500.0,
    "thermal": {"mode": "temperature", "value": 293.15},
    "turbulence": { ... }
}
```

`total_pressure` is gauge (Pa). Internally converted: absolute = total_pressure + reference_pressure.

OpenFOAM types: U → `pressureInletOutletVelocity`, p/p_rgh → `totalPressure`, T → `inletOutlet`.

> **Warning:** Only `"temperature"` mode is supported for `thermal` at `total-pressure-inlet`. Using `"heat-flux"` or `"adiabatic"` will cause an error during case setup.

---

#### 10.2.3 `pressure-outlet`

```json
"Outflow": {
    "type": "pressure-outlet",
    "pressure": 0.0,
    "prevent_backflow": false,
    "backflow_conditions": {
        "thermal": {"mode": "temperature", "value": 290.15},
        "turbulence": {"mode": "intensity-and-length-scale", "intensity": 0.01, "length_scale": 0.005}
    }
}
```

`pressure` is gauge (Pa). `prevent_backflow: true` → no `backflow_conditions` needed; `zeroGradient` for T, k, omega/epsilon. `prevent_backflow: false` → `backflow_conditions` is required.

| Field | prevent_backflow=true | prevent_backflow=false |
|-------|-----------------------|------------------------|
| U | `zeroGradient` | `pressureInletOutletVelocity` |
| p/p_rgh | `fixedValue` | `totalPressure` |
| T | `zeroGradient` | `inletOutlet` |
| k/omega/epsilon | `zeroGradient` | `inletOutlet` |

---

#### 10.2.4 `no-slip-wall`

```json
"all_walls": {
    "type": "no-slip-wall",
    "emissivity": 0.9,
    "thermal": {
        "mode": "heat-transfer-coefficient",
        "htc": 28.2,
        "ambient_temperature": 298.15,
        "outer_emissivity": 0.54,
        "thermal_layers": [
            {"thickness": 0.01, "conductivity": 10.1}
        ]
    }
}
```

The `thermal` dict is optional on a `no-slip-wall`. All [thermal BC modes](#104-thermal-bc-modes) are supported.

`emissivity` is optional (default `0.9`, range `[0, 1]`). It is used only when radiation is active to populate `boundaryRadiationProperties`. It is independent of the `outer_emissivity` field inside `thermal` (which controls convective heat loss to an external ambient).

---

#### 10.2.5 `slip-wall`

```json
"symmetry_wall": {
    "type": "slip-wall",
    "emissivity": 0.9
}
```

A frictionless wall: all fields (`U`, `T`, `k`, `omega`, `nut`, `alphat`) use the OpenFOAM `slip` BC automatically. No `thermal` or `turbulence` sub-dicts are accepted — providing either is a fatal error during setup.

`emissivity` is optional (default `0.9`, range `[0, 1]`). Used only when radiation is active, identical behaviour to `no-slip-wall`.

---

### 10.3 Solid boundary condition types

#### 10.3.1 `solid-wall`

```json
"external_walls": {
    "type": "solid-wall",
    "thermal": {"mode": "temperature", "value": 323.15}
}
```

Solids only have a `T` field. Supported thermal modes: `temperature`, `heat-flux`, `heat-transfer-rate`, `heat-transfer-coefficient`. See [Section 10.4 Thermal BC modes](#104-thermal-bc-modes).

---

### 10.4 Thermal BC modes

Common across `velocity-inlet`, `no-slip-wall`, `solid-wall`, and `backflow_conditions`.

| Mode | Applicable to | Fields |
|------|---------------|--------|
| `temperature` | all | `value` (K) or `time_varying` |
| `heat-flux` | walls, solids | `value` (W/m²) |
| `heat-transfer-rate` | walls, solids | `value` (W total) |
| `heat-transfer-coefficient` | fluid walls, solid walls | `htc`, `ambient_temperature`, `outer_emissivity` (optional, default 0.0), `thermal_layers` (optional) |

**`heat-transfer-coefficient` with thermal layers:**

```json
"thermal": {
    "mode": "heat-transfer-coefficient",
    "htc": 28.2,
    "ambient_temperature": 298.15,
    "outer_emissivity": 0.54,
    "thermal_layers": [
        {"thickness": 0.01, "conductivity": 10.1},
        {"thickness": 0.02, "conductivity": 0.15}
    ]
}
```

- `outer_emissivity` = 0 (default): pure convection. > 0: radiation included.
- `thermal_layers`: each layer has `thickness` (m) and `conductivity` (W/m·K). Layers apply from fluid side outward.

**`temperature` with CSV time-varying:**

```json
"thermal": {
    "mode": "temperature",
    "time_varying": {
        "csv_file": "data.csv",
        "ref_column": 0,
        "component_columns": [4],
        "skip_rows": 1
    }
}
```

---

### 10.5 CHT interfaces

CHT interface BCs appear under `boundary_conditions.cht_interfaces` and define optional thermal contact resistance and surface emissivity for radiation.

```json
"cht_interfaces": {
    "interface-1": {
        "emissivity": 0.85,
        "thermal_layers": [
            {"thickness": 0.046, "conductivity": 35.6},
            {"thickness": 0.1,   "conductivity": 0.04}
        ]
    }
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `emissivity` | float | No | Surface emissivity [0, 1] for `boundaryRadiationProperties` on the fluid-side patch. Default `0.9`. Used only when radiation is active. |
| `thermal_layers` | list | No | Contact-resistance layers (fluid side outward). Each entry: `thickness` (m) and `conductivity` (W/m·K). |

`thermal_layers` and `emissivity` are both optional. If omitted, direct thermal contact and emissivity 0.9 are assumed.

The interface name must match a key defined in `region_parts.cht_interfaces`. The BC type generated on both sides is `compressible::turbulentTemperatureRadCoupledMixed`. `kappaMethod` is `fluidThermo` on the fluid side, `solidThermo` on the solid side.

---

### 10.6 Constraint patch types

Constraint patches (`cyclic`, `symmetry`, `wedge`, etc.) are declared in `boundary_conditions` the same way as any other patch — just set `"type"` to the constraint type name. No additional sub-dicts are needed.

```json
"boundary_conditions": {
    "domain_fluid": {
        "left_right": {"type": "cyclic"},
        "front_back":  {"type": "symmetryPlane"},
        "axis_patch":  {"type": "wedge"},
        "frontAndBack": {"type": "empty"}
    }
}
```

Field files use OpenFOAM's `setConstraintTypes` mechanism — the BC entries are written automatically and no value is required from the user. `setup_case.py` also validates and fixes `type` and `inGroups` in `polyMesh/boundary` for each constraint patch.

**Supported constraint types:**

| Type | Description |
|------|-------------|
| `cyclic` | Periodic/cyclic matching patch pair |
| `cyclicAMI` | Arbitrary mesh interface cyclic |
| `cyclicACMI` | Partially overlapping AMI cyclic |
| `cyclicSlip` | Cyclic with slip velocity |
| `empty` | 2-D / axisymmetric front/back planes |
| `nonuniformTransformCyclic` | Non-uniform cyclic transform |
| `symmetryPlane` | Flat symmetry plane |
| `symmetry` | Curved symmetry surface |
| `wedge` | Axi-symmetric wedge |
| `overset` | Overset (chimera) background region |

---

## 11. faceZone_conditions

Configures internal surface conditions (e.g., fan baffles). Requires the face zone to exist in `constant/<region>/polyMesh/faceZones` (multi-region) or `constant/polyMesh/faceZones` (single-region).

```json
"faceZone_conditions": {
    "domain_fluid": {
        "fan-baffle": {
            "type": "fan",
            "patch_name": "fanPatch",
            "fan_curve": {
                "csv_file": "fan_curve.csv",
                "ref_column": 0,
                "component_columns": [1],
                "skip_rows": 1
            }
        }
    }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `type` | string | Only `"fan"` is supported |
| `patch_name` | string | Name for the cyclic patch pair created from the face zone |
| `fan_curve.csv_file` | string | CSV path relative to `inputData/` |
| `fan_curve.ref_column` | int | Column index (0-based) for volumetric flow rate Q (m³/s) |
| `fan_curve.component_columns` | list | Column indices for pressure jump ΔP (Pa); typically `[1]` |
| `fan_curve.skip_rows` | int | Number of header rows to skip |

Generates `system/<region>/createBafflesDict` (multi-region) or `system/createBafflesDict` (single-region). After `setup_case.py`, run:

```bash
createBaffles -overwrite
```

The p_rgh field BC uses `type fan; mode volumeFlowRate;` on the cyclic patch pair.

---

## 12. numerical_schemes

Selects discretisation schemes. Three settings cover the main choices; all other schemes are fixed.

```json
"numerical_schemes": {
    "time": "Euler",
    "convection": {
        "momentum":   "second-order-upwind",
        "energy":     "second-order-upwind",
        "turbulence": "first-order-upwind"
    },
    "gradients": "green-gauss"
}
```

| Key | Options | OpenFOAM equivalent |
|-----|---------|---------------------|
| `time` | `"none"` (steady-state), `"Euler"`, `"CrankNicolson"`, `"backward"` | `steadyState`, `Euler`, `CrankNicolson 0.9`, `backward` |
| `convection.momentum` | `"first-order-upwind"`, `"second-order-upwind"` | controls `div(phi,U)` |
| `convection.energy` | `"first-order-upwind"`, `"second-order-upwind"` | controls `div(phi,h)`, `div(phi,e)`, `div(phi,K)` |
| `convection.turbulence` | `"first-order-upwind"`, `"second-order-upwind"` | controls `div(phi,k)`, `div(phi,omega)`, `div(phi,epsilon)` |
| `gradients` | `"green-gauss"`, `"least-squares"` | `Gauss linear`, `leastSquares` |

- `time: "none"` is required for `steady-state`; `"Euler"`, `"CrankNicolson"`, or `"backward"` for `transient`.
- For steady-state, all convection schemes are prefixed with `bounded `.
- Second-order upwind maps to: momentum → `Gauss linearUpwindV LIMITED`, energy/turbulence → `Gauss linearUpwind LIMITED` (cell-limited gradient).
- First-order upwind maps to `Gauss upwind` for all fields.
- Typical recommendation: `momentum` and `energy` second-order, `turbulence` first-order for robustness.
- Fixed schemes (not configurable): laplacian → `Gauss linear limited corrected 0.5`, snGrad → `limited corrected 0.5`, wallDist → `Poisson`, radiation → `Gauss linearUpwind grad(Ii_h)`.

> **Note:** `convection.energy` is ignored for incompressible solvers (`simpleFoam`, `pimpleFoam`). No energy equation is solved in those cases, so the field is stripped from the exported `fvSchemes` automatically.

---

## 13. matrix_solvers

Configures the linear algebra solvers used for each field group.

```json
"matrix_solvers": {
    "fluid": {
        "pressure": {
            "solver": "GAMG",
            "preconditioner": "GaussSeidel",
            "tolerance": 1e-05,
            "relative_tolerance": 0.01,
            "min_iter": 1,
            "max_iter": 1000
        },
        "others": {
            "solver": "PBiCGStab",
            "preconditioner": "DILU",
            "tolerance": 1e-06,
            "relative_tolerance": 0.01,
            "min_iter": 1,
            "max_iter": 100
        }
    },
    "solid": {
        "energy": {
            "solver": "PCG",
            "preconditioner": "DIC",
            "tolerance": 1e-06,
            "relative_tolerance": 0.01,
            "min_iter": 1,
            "max_iter": 1000
        }
    }
}
```

Common fields for each solver block:

| Key | Type | Description |
|-----|------|-------------|
| `solver` | string | Linear solver type (see allowed combinations below) |
| `preconditioner` | string | Must pair correctly with `solver` |
| `tolerance` | float [0, 0.1] | Absolute convergence tolerance |
| `relative_tolerance` | float [0, 0.1] | Relative convergence tolerance |
| `min_iter` | int ≥ 0 | Minimum iterations per solve |
| `max_iter` | int [1, 100000] | Maximum iterations per solve |

**Allowed solver–preconditioner combinations:**

| Block | Solver | Preconditioner / Smoother† |
|-------|--------|---------------------------|
| `fluid.pressure` | `GAMG` | `GaussSeidel` or `DICGaussSeidel` |
| `fluid.pressure` | `PCG` | `DIC` |
| `fluid.others` | `PBiCGStab` | `DILU` |
| `fluid.others` | `smoothSolver` | `GaussSeidel` or `symGaussSeidel` |
| `solid.energy` | `GAMG` | `GaussSeidel` or `DICGaussSeidel` |
| `solid.energy` | `PCG` | `DIC` |

> †For `smoothSolver` the JSON key is still `preconditioner`, but the value specifies the **smoother** name — OpenFOAM writes it as `smoother` in `fvSolution`.

`fluid.others` covers U, h/e, k, omega, epsilon. For transient cases, `*Final` solver blocks are automatically appended with `relTol 0.0`.

---

## 14. iterative_solver

Controls the pressure-velocity coupling and outer iteration loop.

```json
"iterative_solver": {
    "max_outer_iterations": 5,
    "fluid": {
        "scheme": "SIMPLE",
        "pressure_correctors": 2,
        "non_orthogonal_correctors": 1,
        "momentum_predictor": true,
        "solve_turb_once_per_timestep": false
    },
    "solid": {
        "non_orthogonal_correctors": 2
    }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `max_outer_iterations` | int [1, 100] | PIMPLE outer correctors (transient only). For multi-region transient this goes in the top-level `system/fvSolution`; for single-region transient it goes in the `PIMPLE` block of `system/fvSolution` directly. |
| `fluid.scheme` | string | `"SIMPLE"` or `"SIMPLEC"` |
| `fluid.pressure_correctors` | int ≥ 1 | Number of pressure correction steps per outer iteration |
| `fluid.non_orthogonal_correctors` | int ≥ 0 | Non-orthogonal correction passes |
| `fluid.momentum_predictor` | bool | Must be `true` for steady-state; can be `false` for transient |
| `fluid.solve_turb_once_per_timestep` | bool | Must be `false` for steady-state |
| `solid.non_orthogonal_correctors` | int ≥ 0 | Non-orthogonal correction passes for solid heat equation |

`SIMPLEC` sets `consistent true;` in the SIMPLE block. `SIMPLE` sets `consistent false;`.

---

## 15. convergence_criteria

Residual tolerances for each field group. Set a value to `-1` to skip that field in `residualControl`.

```json
"convergence_criteria": {
    "fluid": {
        "residuals": {
            "pressure": 0.001,
            "velocity": 0.0001,
            "energy": 0.0001,
            "turbulence": 0.001
        }
    },
    "solid": {
        "residuals": {
            "energy": 1e-08
        }
    }
}
```

| JSON key | OpenFOAM field | Applies to |
|----------|---------------|------------|
| `pressure` | pressure variable (`p` or `p_rgh`) | fluid |
| `velocity` | `U` | fluid |
| `energy` | `"(h\|e)"` | fluid; `h` for solid |
| `turbulence` | `"(k\|epsilon\|omega)"` | fluid |

For steady-state, residuals appear as plain tolerance values. For transient, each field gets a nested block with `tolerance` and `relTol 0.0`.

> **Note:** For incompressible solvers (`simpleFoam`, `pimpleFoam`), the `energy` residual is automatically omitted — no energy equation is solved.

---

## 16. relaxation_factors

Under-relaxation factors. Range: (0, 1.0]. Values close to 1.0 mean little relaxation.

```json
"relaxation_factors": {
    "fluid": {
        "density": 1.0,
        "pressure": 0.3,
        "velocity": 0.7,
        "energy": 0.7,
        "turbulence": 0.7
    },
    "solid": {
        "energy": 1.0
    }
}
```

| JSON key | OpenFOAM field | Notes |
|----------|---------------|-------|
| `fluid.density` | `rho` (fields block) | Compressible only; not read for incompressible |
| `fluid.pressure` | pressure variable (fields block) | — |
| `fluid.velocity` | `U` (equations block) | — |
| `fluid.energy` | `"(h\|e)"` (equations block) | Compressible only; not read for incompressible |
| `fluid.turbulence` | `"(k\|omega\|epsilon)"` (equations block) | — |
| `solid.energy` | `h` (equations block) | — |

For transient simulations: `density` is not applied by the solver; `UFinal`, `(h|e)Final`, `(k|omega|epsilon)Final` are automatically appended with value `1.0`. Same for `hFinal` in solids.

> **Note:** For incompressible solvers (`simpleFoam`, `pimpleFoam`), `fluid.density` and `fluid.energy` are not read from config. Only `pressure`, `velocity`, and `turbulence` are used.

> **Note:** For transient compressible simulations, setting `fluid.density` to less than `1.0` triggers a warning — the value is written to `fvSolution` but OpenFOAM does not apply density relaxation in transient runs. Recommended value is `1.0`.

---

## 17. function_objects

Optional monitoring quantities written to `postProcessing/`. `yPlus` (fluid) and `wallHeatFlux` (all regions) are always enabled automatically. For single-region cases the `region` keyword is omitted from all function object dictionaries (OpenFOAM requires this for single-region solvers).

`setup_case.py` writes all function object content to `system/functionObjects`, which `system/controlDict` pulls in via an `#include` directive. Edit that file directly if you need OpenFOAM-level tweaks not exposed through the config.

```json
"function_objects": {
    "domain_fluid": [
        {"type": "volume_integral",  "field": "density",      "cellZone": "fluid_zone_A"},
        {"type": "mass_average",     "field": "pressure"},
        {"type": "area_average",     "field": "yPlus",        "patch": "domain_fluid_to_domain_solid"},
        {"type": "surface_min",      "field": "wallHeatFlux", "patch": "domain_fluid_to_domain_solid"}
    ],
    "domain_solid": [
        {"type": "cellZone_average", "field": "temperature",  "cellZones": ["zone-1", "zone-2", "zone-3"]},
        {"type": "volume_average",   "field": "temperature"}
    ]
}
```

### 17.1 Supported operation types

**cellZone_average — shorthand for multi-zone monitoring (solid regions):**

| Key | Requirement | Description |
|-----|-------------|-------------|
| `type` | `"cellZone_average"` | Dedicated shorthand for per-zone average monitoring |
| `field` | required string | Field to average (`"temperature"`, `"pressure"`, etc.) |
| `cellZones` | required non-empty list | One or more cellZone names; generates a separate OpenFOAM dict per zone |

Each zone produces an independent `volFieldValue` dictionary in `system/functionObjects`, all sharing a single `__template_average_cellZone_<field>` anchor block. The `#remove "__.*"` directive strips the anchor after expansion.

**Example output** for `"cellZones": ["zone-1", "zone-2"]` with `"field": "temperature"` (multi-region; `region` keyword omitted for single-region):
```
czAvg-domain_solid-zone_1-T { ${__template_average_cellZone_T}  region domain_solid;  regionType cellZone;  name zone-1; ... }
czAvg-domain_solid-zone_2-T { ${__template_average_cellZone_T}  region domain_solid;  regionType cellZone;  name zone-2; ... }
```

**Volume / mass operations** (operate over region or optional `cellZone`):

| `type` | OpenFOAM operation | Weight |
|--------|--------------------|--------|
| `cellZone_average` | `volAverage` | — |
| `volume_average` | `volAverage` | — |
| `volume_integral` | `volIntegrate` | — |
| `volume_min` | `min` | — |
| `volume_max` | `max` | — |
| `volume_sum` | `sum` | — |
| `mass_average` | `weightedVolAverage` | `rho` |
| `mass_integral` | `weightedVolIntegrate` | `rho` |

**Surface operations** (require `patch`, `faceZone`, OR `cuttingPlane`, mutually exclusive):

| `type` | OpenFOAM operation | Notes |
|--------|--------------------|----|
| `area_average` | `areaAverage` | |
| `area_integral` | `areaIntegrate` | |
| `surface_min` | `min` | |
| `surface_max` | `max` | |
| `surface_sum` | `sum` | |
| `mass_flow_rate` | `sum` on `phi` | **Fluid only.** Field is implicit — do not specify `field`. FO name uses `massFlowRate` prefix. |
| `volume_flow_rate` | `areaNormalIntegrate` on `U` | **Fluid only.** Field is implicit — do not specify `field`. FO name uses `volFlowRate` prefix. |

**`mass_flow_rate` example:**

```json
{"type": "mass_flow_rate", "patch": "inlet"}
{"type": "mass_flow_rate", "faceZone": "mid_plane"}
```

Generated name: `massFlowRate-domain_fluid-inlet`

**`volume_flow_rate` example:**

```json
{"type": "volume_flow_rate", "patch": "inlet"}
{"type": "volume_flow_rate", "faceZone": "mid_plane"}
```

Generated name: `volFlowRate-domain_fluid-inlet`

---

### 17.2 cuttingPlane scope

Instead of a mesh patch or faceZone, any surface operation can compute on a **virtual cutting plane** — a cross-section reconstructed from volume fields at runtime, not requiring any physical mesh entity.

```json
{
    "type": "area_average",
    "field": "pressure",
    "cuttingPlane": {
        "name": "upstreamSection",
        "point": [0.05, 0.0, 0.0],
        "normal": [1.0, 0.0, 0.0]
    }
}
```

| Key | Type | Description |
|-----|------|-------------|
| `cuttingPlane.name` | string | Arbitrary label used in the FO dict and output directory name |
| `cuttingPlane.point` | `[x, y, z]` | Any point on the cutting plane |
| `cuttingPlane.normal` | `[nx, ny, nz]` | Normal vector of the cutting plane (must be non-zero) |

`patch`, `faceZone`, and `cuttingPlane` are **mutually exclusive** — exactly one must be specified.

**Generated OpenFOAM dictionary** (multi-region; `region` omitted for single-region):
```
areaAvg-domain_fluid-upstreamSection-p
{
    type                surfaceFieldValue;
    libs                (fieldFunctionObjects);
    operation           areaAverage;
    fields              (p);
    region              domain_fluid;
    regionType          sampledSurface;
    name                upstreamSection;
    sampledSurfaceDict
    {
        type            cuttingPlane;
        point           (0.05 0 0);
        normal          (1 0 0);
    }
    writeFields         false;
    enabled             true;
    log                 true;
    evaluateControl     timeStep;
    evaluateInterval    1;
    writeControl        timeStep;
    writeInterval       1;
}
```

> **Note:** `cuttingPlane` reconstructs values from **volume fields** interpolated to the cut geometry. It is valid for all surface FO types including `mass_flow_rate` and `volume_flow_rate`, and works on both fluid and solid regions.

### 17.3 Field name mapping

| JSON `field` | OpenFOAM field |
|--------------|---------------|
| `temperature` | `T` |
| `velocity` | `U` |
| `pressure` | `p` |
| `density` | `rho` |
| *(any other)* | unchanged |

### 17.4 Naming convention

```
<operation>-<region>[-<cellZone_or_patch_or_cpName>-]<field>

Examples:
  czAvg-domain_solid-zone_1-T           (cellZone_average, one entry per zone)
  volAvg-domain_fluid-T
  areaAvg-domain_fluid-domain_fluid_to_domain_solid-wallHeatFlux
  massInt-domain_solid-zone_2-T
  massFlowRate-domain_fluid-inlet        (mass_flow_rate — no field suffix; field is implicit)
  volFlowRate-domain_fluid-inlet         (volume_flow_rate — no field suffix; field is implicit)
  areaAvg-domain_fluid-upstreamSection-p (cuttingPlane — plane name replaces patch name; field suffix still required)
```

All function objects evaluate and write every time step (not configurable here; edit `prepare_function_objects_context()` in `common/utils.py` to change).

---

## 18. fv_options

Optional volumetric source terms. Only `heat-source` type is currently implemented.

```json
"fv_options": {
    "domain_fluid": [
        {"type": "heat-source", "mode": "absolute", "value": 2.1}
    ],
    "domain_solid": [
        {"type": "heat-source", "cellZone": "zone-1", "mode": "absolute", "value": 1.786},
        {"type": "heat-source", "cellZone": "zone-3", "mode": "specific", "value": 4.05}
    ]
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `type` | string | Yes | Must be `"heat-source"` |
| `mode` | string | Yes | `"absolute"` (W total) or `"specific"` (W/m³) |
| `value` | float | Yes | Heat generation rate. Positive = heat in, negative = heat out. |
| `cellZone` | string | No | Apply to this cell zone only. Omit to apply to entire region. |

OpenFOAM type: `scalarSemiImplicitSource`. The source is applied as `h ( <value> 0 )` (explicit, no implicit slope).

Generated file location: `system/<region>/fvOptions` (multi-region) or `system/fvOptions` (single-region).

### 18.1 Common errors

| Error | Cause |
|-------|-------|
| `cellZone 'X' not found` | Zone name doesn't match `polyMesh/cellZones` |
| `region 'X' not defined` | Region key not in `regions` section |
| Wrong unit (absolute vs specific) | Check mode; absolute is W, specific is W/m³ |
