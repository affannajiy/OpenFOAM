# Code Review — 24 May 2026

**Scope:** `setup_case.py`, `common/utils.py`, `configure_simInputs/tools/sim_inputs_generator.html`, `documentation/configuration_guide.md`  
**Objectives:** Critical bugs · Code bloat / refactoring opportunities · HTML–Python consistency · Documentation accuracy and clarity  

---

## Severity legend

| Label | Meaning |
|-------|---------|
| 🔴 **Critical** | Will silently corrupt output, crash the tool, or cause OpenFOAM to reject the generated case |
| 🟡 **Bug** | Incorrect behaviour in an edge case, or potentially misleading code that could lead to bugs |
| 🔵 **Refactor** | No correctness impact; reduces duplication, dead code, or maintenance burden |
| ⚪ **Minor** | Style / cosmetic; no functional impact |

---

## 1. `setup_case.py`

### 1.1 🔴 `get_turbulence_content()` called twice, second call discards the first result

**Lines:** 233 and 313

```python
# Line 233 — writes turbulenceProperties files
is_turb_active, turb_model, turb_template, turb_context = get_turbulence_content(config)

# … 80 lines later, line 313 — determines which field files to create
turb_is_active, turb_model, _, _ = get_turbulence_content(config)
```

The second call re-reads, re-validates and re-parses the same turbulence section of the config. The two return values it keeps (`turb_is_active`, `turb_model`) are already available from the first call (`is_turb_active`, `turb_model`). If the turbulence config is borderline invalid, the validation in `get_turbulence_content()` runs twice with no benefit.

**Fix:** Replace line 313 with a simple rename so the field-file section uses the already-computed result:

```python
# Line 313 — no second call needed
turb_is_active = is_turb_active
# turb_model is already in scope from line 233
```

---

### 1.2 🔵 `convergence_dict` fetched inside each conditional block

**Lines:** 804 (inside `if fluids:`) and 815 (inside `if solids:`)

```python
if fluids:
    …
    convergence_dict = get_config_value(config, "convergence_criteria", expected_type=dict)   # line 804
    …

if solids:
    …
    convergence_dict = get_config_value(config, "convergence_criteria", expected_type=dict)   # line 815
    …
```

When both fluids and solids are present, the top-level `convergence_criteria` dict is fetched and validated twice. It should be hoisted to before both blocks.

**Fix:**

```python
convergence_dict = get_config_value(config, "convergence_criteria", expected_type=dict)

if fluids:
    fluid_convergence_dict = get_config_value(convergence_dict, "fluid", expected_type=dict)
    …

if solids:
    solid_convergence_dict = get_config_value(convergence_dict, "solid", expected_type=dict)
    …
```

---

### 1.3 ⚪ `urf = None` declared twice

**Lines:** 777 and 823

```python
urf = None          # line 777 — in the pre-initialisation block

…

urf = None          # line 823 — immediately before the relaxation-factors block
solid_urf = None
```

The second assignment has no effect — `urf` is not touched between line 777 and line 823. It is confusing because it looks like an intentional reset.

**Fix:** Remove the redundant line 823 `urf = None` (keep `solid_urf = None` if it is not initialised above).

---

### 1.4 🔵 Duplicate `opt_entries` building loop in fvOptions generation

**Lines:** 554–574 (single-region path) and 586–606 (multi-region path)

Both blocks build an identical `opt_entries` list from `fvoptions_dict[region]` before calling `_render_template`. The only difference is the `location` string and the output file path. The list-building logic is copy-pasted verbatim.

**Fix:** Extract to a helper (in `utils.py` or as a local function at the top of `setup_case.py`):

```python
def _build_fvoptions_entries(opts):
    entries = []
    for opt in opts:
        has_cellzone = "cellZone" in opt
        cell_zone = opt.get("cellZone", "")
        entries.append({
            "entry_name": f"heat_source-cellZone-{cell_zone}" if has_cellzone
                          else f"heat_source-all-{region}",
            "selection_mode": "cellZone" if has_cellzone else "all",
            "has_cellzone": has_cellzone,
            "cell_zone": cell_zone,
            "mode": opt.get("mode", "absolute"),
            "value": opt.get("value", 0.0),
        })
    return entries
```

Then both paths reduce to a single call:

```python
opt_entries = _build_fvoptions_entries(fvoptions_dict[region])
```

---

### 1.5 🔵 No `main()` guard — all code runs at module level

`setup_case.py` has no `if __name__ == "__main__":` guard. Every import or test invocation of the module executes the full case-generation logic, including file I/O and `sys.exit()` calls. This makes the script impossible to unit-test and violates standard Python packaging conventions.

**Fix:** Wrap the entire body in a `main()` function and call it under `if __name__ == "__main__":`. This does not change runtime behaviour but enables future testing.

---

## 2. `common/utils.py`

### 2.1 🔴 Regex patterns built from unescaped patch names

**Affected functions:** `validate_and_fix_polymesh_patch()` and `validate_and_fix_cht_patch()`

Both functions build a compiled regex from a user-supplied patch name, e.g.:

```python
patch_pattern = re.compile(rf'(\s{patch_name}\s*\{{[^}}]*\}})', re.DOTALL)
```

If a patch name contains regex metacharacters (e.g. `inlet.1`, `fan(in)`, `patch+A`), the pattern compiles to something unintended and may match the wrong section of `constant/polyMesh/boundary`, silently producing a corrupt mesh boundary file.

**Fix:** Always escape the patch name:

```python
patch_pattern = re.compile(rf'(\s{re.escape(patch_name)}\s*\{{[^}}]*\}})', re.DOTALL)
```

---

### 2.2 🟡 Fragile string manipulation in `build_time_varying_inlet_temperature_bc()`

**Lines:** ~2339–2355

```python
def build_time_varying_inlet_temperature_bc(…):
    bc_block = build_time_varying_bc(…)
    return bc_block.rstrip("}") + "    value               $internalField;\n    }"
```

This function appends a `value` keyword by stripping the closing `}` from another function's output and re-adding it. If `build_time_varying_bc()` ever changes its output format (e.g., adds trailing whitespace or a newline), this breaks silently and produces malformed OpenFOAM syntax.

**Fix:** Pass the extra field as a parameter to `build_time_varying_bc()`, or have `build_time_varying_bc()` return the block without the closing brace and let callers close it.

---

### 2.3 🔵 Dead code: `get_vector()` (line 1289)

```python
def get_vector(prompt):
    """Prompt user for x y z via stdin."""
    …
```

This function reads from `stdin` and is never called from `setup_case.py` or any other current script. The entire input pipeline is JSON-driven. The function is also missing return-type documentation and has no validation.

**Fix:** Remove the function entirely or move it to a standalone utility if ever needed interactively.

---

### 2.4 🔵 Dead code: backward-compatibility wrappers for internal functions

**Lines:** ~2029–2364 — six trivial one-liner wrappers, all annotated "for backward compatibility":

| Wrapper | Calls | Notes |
|---------|-------|-------|
| `validate_time_varying_velocity()` | `_validate_time_varying_velocity()` | trivial relay |
| `_validate_time_varying_thermal()` | `_validate_time_varying_thermal_impl()` | trivial relay |
| `build_time_varying_velocity_bc()` | `build_time_varying_bc()` | trivial relay |
| `build_time_varying_normal_magnitude_velocity_bc()` | `build_time_varying_bc()` | trivial relay |
| `build_time_varying_inlet_temperature_bc()` | `build_time_varying_bc()` + string splice | fragile (see 2.2) |
| `build_time_varying_wall_temperature_bc()` | `build_time_varying_bc()` | trivial relay |

These are not a public API. All callers are inside `utils.py` itself. Layers of indirection with "backward compatibility" comments in an internal module add confusion without benefit.

**Fix:** Inline the wrappers into their callers and remove the wrapper functions.

---

### 2.5 🔵 Redundant validation in solid material processing

`_resolve_solid()` (inside `resolve_material_reference()`) already fully validates the solid material structure — it exits with a descriptive error for any invalid configuration. `validate_solid_material_properties()` then partially re-validates the already-resolved dict (checking the `type` field that `_resolve_solid()` always sets). This is harmless but adds a second pass over data that is already guaranteed valid.

**Note:** No fix required immediately; worth tracking when either function is next modified.

---

## 3. `sim_inputs_generator.html`

### 3.1 ℹ️ `rhoSimpleFoam` and `rhoPimpleFoam` not yet supported in the wizard — known limitation

**Line:** 467–479 (`SOLVERS` constant)

```js
single_fluid: {
  steady:    ['buoyantSimpleFoam', 'simpleFoam'],
  transient: ['buoyantPimpleFoam', 'pimpleFoam']
}
```

The Python backend (`validate_solver_name()` in `utils.py`) already accepts `rhoSimpleFoam` (steady) and `rhoPimpleFoam` (transient) as valid single-fluid solvers, and the configuration guide documents them in Section 1. However, the HTML wizard intentionally omits them pending a dedicated UI implementation.

**Current behaviour:** Configs for these two solvers must be written or edited by hand. If a `sim_inputs.json` using `rhoSimpleFoam`/`rhoPimpleFoam` is loaded into the wizard, the solver name will be silently reset to the first available option (`buoyantSimpleFoam`/`buoyantPimpleFoam`) because it is not in the `SOLVERS` list.

**When adding wizard support,** the following will be needed:
- Add the solvers to `SOLVERS.single_fluid.steady` and `SOLVERS.single_fluid.transient`.
- Verify that `isIncompressibleSolver()` continues to return `false` for both (they are compressible; no change required to the current guard).
- Review any wizard steps that condition UI elements on solver type (e.g., gravity, radiation, thermal BCs) to ensure they behave correctly for these solvers.

---

### 3.2 🔴 `loadSimInputs()` has no error handling around `JSON.parse()`

**Location:** `loadSimInputs()` function, JSON parsing step

```js
const d = JSON.parse(json);   // throws SyntaxError for invalid JSON
```

There is no `try/catch` around this call. If the user selects a non-JSON file (e.g., a CSV or an empty file), an uncaught `SyntaxError` is thrown. Depending on the browser, this either crashes the application silently or leaves the state in a partially-modified inconsistent form.

**Fix:**

```js
let d;
try {
  d = JSON.parse(json);
} catch (e) {
  showMessage('error', `Failed to parse JSON: ${e.message}`);
  return;
}
```

---

### 3.3 🔴 `velocity-inlet` and `total-pressure-inlet` allow unsupported thermal modes

**Line:** `renderFluidBCConfig()`, velocity-inlet branch

```js
renderThermalSection(region, patch, 'thermal', bc.thermal,
  ['temperature', 'heat-flux', 'adiabatic'],   // ← heat-flux and adiabatic allowed
  thermalDisabled)
```

The Python backend and the documentation are explicit that inlet thermal BCs must use `temperature` mode (Section 10 of `configuration_guide.md`: *"thermal mode at inlets must be `"temperature"`"*). If a user selects `heat-flux` or `adiabatic` on a velocity-inlet in the wizard and exports, `setup_case.py` will fail validation (or silently produce an incorrect BC) when the JSON is run.

The same issue applies to the `total-pressure-inlet` branch.

**Fix:** Restrict allowed modes for inlet types to `['temperature']`:

```js
if (bc.type === 'velocity-inlet') {
  return `…${renderThermalSection(region, patch, 'thermal', bc.thermal, ['temperature'], thermalDisabled)}…`;
}
if (bc.type === 'total-pressure-inlet') {
  return `…${renderThermalSection(region, patch, 'thermal', bc.thermal, ['temperature'], thermalDisabled)}…`;
}
```

---

### 3.4 🟡 Inconsistent default BC thermal mode between `BC_DEFAULTS` and `ensureFluidBC()`

**Lines:** `BC_DEFAULTS` constant (line ~531) vs `ensureFluidBC()` function (line ~2476)

```js
// BC_DEFAULTS — used when the user clicks a type in the dropdown:
'no-slip-wall': { type: 'no-slip-wall', thermal: { mode: 'temperature', value: 298.15 } }

// ensureFluidBC() — called when a new patch appears with no BC:
function ensureFluidBC(region, patch) {
  if (!existing) setBC(region, patch, { type: 'no-slip-wall', thermal: { mode: 'heat-flux', value: 0 } });
}
```

Patches created via the dropdown get `thermal.mode: 'temperature'`, while patches auto-initialised by `ensureFluidBC()` get `thermal.mode: 'heat-flux'`. A user who sees `heat-flux` pre-populated may not notice, and both values are valid for walls — but the inconsistency is confusing and could lead to accidentally exporting `heat-flux: 0` for all walls.

**Fix:** Make `ensureFluidBC()` use `BC_DEFAULTS`:

```js
function ensureFluidBC(region, patch) {
  if (!getBC(region, patch)) setBC(region, patch, deepClone(BC_DEFAULTS['no-slip-wall']));
}
```

---

### 3.5 ⚪ `gravity` key position in exported JSON differs from documented order

**Location:** `buildExportJSON()` (end of function)

The `gravity` and `radiation` keys are appended conditionally at the very end of the exported JSON object. The documentation (Section 4) lists gravity as the fourth top-level key, immediately after `region_parts`. JSON key order has no semantic meaning to the Python backend, so this does not cause bugs — but it makes manual comparison between a wizard-generated file and a hand-crafted one based on the docs needlessly confusing.

**Fix (optional):** Include `gravity` and `radiation` at their documented positions in `buildExportJSON()`. Alternatively, add a note to the documentation stating that key order in the file is irrelevant.

---

## 4. `documentation/configuration_guide.md`

### 4.1 🔴 Section 6 solid material examples show an unsupported inline property format

**Lines:** The solid region examples in Section 6 (material_properties) contain JSON like:

```json
"domain_solid": {
    "type": "uniform",
    "molecular_weight": 28.0,
    "Cp": 500,
    "rho": 2700,
    "kappa": 200.0
}
```

This format is **not supported** by the current Python backend. In `utils.py`, `_resolve_solid()` handles only three shapes for a solid region entry:

1. A plain string (library lookup): `"domain_solid": "copper"`
2. A dict with a `"material"` key: `"domain_solid": { "material": "copper" }`
3. A dict with `"type": "cell_zone_specific"` (per-zone material assignment)

Any other dict structure triggers `sys.exit()` with an error. The `"type": "uniform"` form shown in the documentation will always fail. Running `setup_case.py` with the documented examples verbatim is impossible.

**Fix:** Replace the solid material examples entirely with supported forms:

```json
// Simple library reference (recommended):
"domain_solid": "copper"

// Explicit library reference dict:
"domain_solid": { "material": "aluminum-6061" }

// Per cell-zone assignment:
"domain_solid": {
    "type": "cell_zone_specific",
    "heat_sink": { "material": "aluminum-6061" },
    "pcb": { "material": "fr4" }
}
```

---

### 4.2 🟡 Inlet thermal mode restriction is buried; HTML wizard contradicts it

**Line 547:** The note *"thermal mode at inlets must be `"temperature"`"* is brief and located mid-section inside a table footnote. Because the HTML wizard (see § 3.3 above) currently allows `heat-flux` and `adiabatic` on inlets, a user who generated a config with the wizard and then consults the docs will be confused when setup fails.

**Fix:**  
1. In the documentation, promote this restriction to a ⚠ **Warning** block at the start of the `velocity-inlet` section:
   > **Warning:** The `thermal` mode for all inlet boundary types (`velocity-inlet`, `total-pressure-inlet`) must be `"temperature"`. `heat-flux` and `adiabatic` are only valid on wall and solid patches.

2. Fix the HTML wizard as described in § 3.3 so the two are consistent.

---

### 4.3 🔵 Section 6 fluid material examples show inline definitions before library references

**Context:** Section 6 (material_properties) leads with inline fluid property dicts (`rho`, `Cp`, `mu`, `kappa` with nested model and coefficients) before showing the recommended library-reference approach. For compressible solvers (`buoyantSimpleFoam`, `rhoSimpleFoam`, etc.), inline fluid definitions are **not supported** — `resolve_material_reference()` requires a string library name. For incompressible solvers (`simpleFoam`, `pimpleFoam`) inline dicts are accepted as a special case.

The documentation does not make this solver-type distinction clear, and the ordering of examples implies that inline definitions are the primary pattern.

**Fix:**  
- Lead with the library-reference pattern as the primary example for all solvers.  
- Move inline dict examples to a clearly labelled "incompressible solvers only" sub-section.

---

### 4.4 ⚪ Section 12 (numerical_schemes) — `convection.energy` for incompressible solvers

Section 12 lists `convection.energy` as a configurable key. For incompressible solvers (`simpleFoam`/`pimpleFoam`), there is no energy equation. The HTML wizard (in `buildExportJSON()`) strips this key for incompressible configs:

```js
if (incompressible) delete ns.convection.energy;
```

The documentation does not mention that `convection.energy` is silently ignored (or omitted) for incompressible cases. A user editing a JSON by hand for `simpleFoam` may include it expecting it to have an effect.

**Fix:** Add a brief note: *"`convection.energy` is only applicable to compressible solvers; it is ignored for `simpleFoam`/`pimpleFoam`."*

---

### 4.5 ⚪ Naming convention example in Section 17 has a minor inconsistency

**Line 1089 (naming convention block):**

```
areaAvg-domain_fluid-upstreamSection-p (cuttingPlane — plane name replaces patch name, no field suffix for implicit-field types)
```

The comment says "no field suffix for implicit-field types" but the example does include the field suffix (`-p`). `area_average` on pressure is not an implicit-field type — only `mass_flow_rate` and `volume_flow_rate` are implicit (they do not take a `field` parameter). The comment is mislabelled.

**Fix:** Remove the parenthetical note, or change the example to a `mass_flow_rate` with a cuttingPlane to actually demonstrate the implicit-field / no-suffix case.

---

## 5. Summary table

| # | File | Severity | Finding |
|---|------|----------|---------|
| 1.1 | `setup_case.py` | 🔴 | `get_turbulence_content()` called twice; second call discards first result |
| 1.2 | `setup_case.py` | 🔵 | `convergence_dict` fetched redundantly inside both `if fluids:` and `if solids:` |
| 1.3 | `setup_case.py` | ⚪ | `urf = None` assigned twice |
| 1.4 | `setup_case.py` | 🔵 | fvOptions `opt_entries` loop duplicated verbatim for single- vs multi-region |
| 1.5 | `setup_case.py` | 🔵 | No `main()` guard; all code runs at module level |
| 2.1 | `utils.py` | 🔴 | `re.escape()` not used on patch names in polyMesh regex patterns |
| 2.2 | `utils.py` | 🟡 | `build_time_varying_inlet_temperature_bc()` splices output via `rstrip("}")` — fragile |
| 2.3 | `utils.py` | 🔵 | Dead code: `get_vector()` — stdin-based, never called |
| 2.4 | `utils.py` | 🔵 | Dead code: six "backward-compat" wrappers for an internal-only API |
| 2.5 | `utils.py` | 🔵 | Solid material validation runs twice (once in `_resolve_solid()`, again in `validate_solid_material_properties()`) |
| 3.1 | HTML wizard | ℹ️ | `rhoSimpleFoam`/`rhoPimpleFoam` not yet in wizard — intentional; planned for a future release |
| 3.2 | HTML wizard | 🔴 | `loadSimInputs()` missing `try/catch` around `JSON.parse()` — crashes on invalid file |
| 3.3 | HTML wizard | 🔴 | Velocity/pressure inlet allows `heat-flux` and `adiabatic` thermal modes — rejected by Python backend |
| 3.4 | HTML wizard | 🟡 | `BC_DEFAULTS['no-slip-wall']` and `ensureFluidBC()` produce different default thermal modes |
| 3.5 | HTML wizard | ⚪ | `gravity` placed at end of exported JSON instead of its documented position |
| 4.1 | Docs | 🔴 | Section 6 solid examples use `"type": "uniform"` inline format — unsupported by backend; always fails |
| 4.2 | Docs | 🟡 | Inlet thermal mode restriction buried; HTML wizard contradicts it |
| 4.3 | Docs | 🔵 | Fluid material inline examples shown before library-reference pattern; compressible vs incompressible distinction missing |
| 4.4 | Docs | ⚪ | Section 12 does not note that `convection.energy` is silently ignored for incompressible solvers |
| 4.5 | Docs | ⚪ | Naming convention example comment in Section 17 incorrectly says "no field suffix" for a non-implicit-field example |

---

## 6. Recommended action order

The five remaining 🔴 Critical issues should be addressed first because they are the most likely to cause silent data corruption or confusing failures:

1. **[3.2]** Wrap `JSON.parse()` in `loadSimInputs()` with a `try/catch`
2. **[3.3]** Restrict inlet thermal modes in the HTML wizard to `['temperature']`
3. **[4.1]** Rewrite Section 6 solid material examples to use supported library-reference forms
4. **[2.1]** Add `re.escape()` to the polyMesh patch regex — low risk fix, high risk if left
5. **[1.1]** Remove the duplicate `get_turbulence_content()` call (one-line fix)
6. **[2.2]** Refactor `build_time_varying_inlet_temperature_bc()` to eliminate string splicing
7. Remaining 🔵 refactors and ⚪ cosmetic issues per discretion
