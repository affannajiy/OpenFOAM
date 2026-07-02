# common/utils.py
import subprocess
import sys
import os
import re
import shutil
import json

# Constraint boundary types — handled automatically by setConstraintTypes in field files.
# Only the polyMesh/boundary entry needs type and inGroups set correctly.
CONSTRAINT_TYPES = frozenset([
    "cyclic", "cyclicAMI", "cyclicACMI", "cyclicSlip", "empty",
    "nonuniformTransformCyclic", "symmetryPlane", "symmetry", "wedge", "overset"
])

#==============================================================================
def load_config_file(file_path="sim_inputs.json"):
    """
    Loads simulation settings from a JSON file.
    Validates that the file exists and is valid JSON.
    """
    # 1. Check if file exists
    if not os.path.exists(file_path):
        sys.exit(f"Error: Input file '{file_path}' not found.\n"
                 "Please create this file with your simulation settings.")

    # 2. Parse the JSON
    try:
        with open(file_path, 'r') as f:
            config = json.load(f)

        return config

    except json.JSONDecodeError as e:
        sys.exit(f"Error: The file '{file_path}' contains invalid JSON.\n"
                 f"Details: {e}")
    except Exception as e:
        sys.exit(f"Unexpected error reading config: {e}")
#==============================================================================
def get_config_value(config, key, expected_type=None, valid_options=None, min_val=None, max_val=None, required=True):
    """
    Retrieves, validates, and types-checks a value from the config dictionary.
    
    :param config: The dictionary loaded from JSON.
    :param key: The key to look up.
    :param expected_type: The required Python type (e.g., int, float, str, list).
    :param valid_options: A list of allowed specific values.
    :param min_val: Minimum allowed value (inclusive) for numbers.
    :param max_val: Maximum allowed value (inclusive) for numbers.
    :param required: If True, exits if key is missing.
    :return: The validated value.
    """
    # 1. Check Existence
    if key not in config:
        if required:
            sys.exit(f"Config Error: Missing required parameter '{key}'.")
        return None

    value = config[key]

    # 2. Check Type (e.g., ensure "max_iterations" is an int, not a float or string)
    if expected_type is not None:
        # Special handling: standard JSON numbers might be read as floats or ints.
        # If we expect float, we often accept int. But if we expect int, we reject float.
        # Guard against bool (bool is a subclass of int in Python), so e.g. "active": true
        # must not silently coerce to 1.0 when expected_type=float.
        if expected_type == float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value) # Auto-convert int to float
        
        if not isinstance(value, expected_type):
            sys.exit(f"Config Error: '{key}' must be of type {expected_type.__name__}, "
                     f"but got {type(value).__name__} ({value}).")

    # 3. Check Specific Options (Enumeration)
    if valid_options is not None:
        if value not in valid_options:
            sys.exit(f"Config Error: Invalid value for '{key}': '{value}'.\n"
                     f"  Allowed values: {valid_options}")

    # 4. Check Numeric Ranges
    if min_val is not None:
        if value < min_val:
            sys.exit(f"Config Error: '{key}' must be >= {min_val}. Got {value}.")

    if max_val is not None:
        if value > max_val:
            sys.exit(f"Config Error: '{key}' must be <= {max_val}. Got {value}.")

    return value

#==============================================================================
def normalize_patch_name(patch_name):
    """
    Converts comma-separated patch names to OpenFOAM pipe syntax with quotes.
    Converts special '__default__' key to OpenFOAM regex ".*" for default BC.
    Strips whitespace from all patch names.
    
    Examples:
    - "Inflow" → "Inflow" (no change)
    - "leftInflow, rightInflow, topInflow" → "\"(leftInflow|rightInflow|topInflow)\""
    - "__default__" → "\".*\"" (special default BC keyword)
    - "  walls  " → "walls" (whitespace stripped)
    
    :param patch_name: Patch name from JSON config (may contain commas, or be __default__)
    :return: Patch name in OpenFOAM format (with quoted pipe syntax or regex for default)
    """
    # Handle special __default__ key - convert to OpenFOAM regex
    if patch_name.strip() == "__default__":
        return '".*"'
    
    # Check if patch_name contains comma
    if "," not in patch_name:
        return patch_name.strip()
    
    # Split by comma and strip whitespace from each patch name
    patches = [p.strip() for p in patch_name.split(",")]
    
    # Remove any empty strings
    patches = [p for p in patches if p]
    
    if len(patches) == 1:
        return patches[0]
    
    # Convert to OpenFOAM pipe syntax with double quotes: "(patch1|patch2|patch3)"
    return f'"({"|".join(patches)})"'

#==============================================================================
def resolve_config_aliases(config, reference_conditions):
    """
    Recursively resolves aliases throughout the config dictionary.
    Supported aliases:
    - "REF-TEMP": replaced with temperature from reference_conditions
    - "REF-PRES": replaced with pressure from reference_conditions
    
    :param config: The entire config dictionary
    :param reference_conditions: Dictionary with 'temperature' and 'pressure' keys
    :return: The config dictionary with aliases resolved
    """
    ref_temp = reference_conditions.get("temperature")
    ref_pres = reference_conditions.get("pressure")
    
    alias_map = {
        "REF-TEMP": ref_temp,
        "REF-PRES": ref_pres
    }
    
    def recursive_resolve(obj):
        """Recursively traverse and resolve aliases in dicts and lists."""
        if isinstance(obj, dict):
            return {key: recursive_resolve(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [recursive_resolve(item) for item in obj]
        elif isinstance(obj, str):
            if obj in alias_map:
                resolved = alias_map[obj]
                if resolved is None:
                    sys.exit(f"Config Error: Alias '{obj}' referenced but corresponding value "
                            f"not found in reference_conditions.")
                return resolved
            # Check for unknown aliases (strings that look like aliases but aren't recognized)
            elif obj.startswith("REF-"):
                sys.exit(f"Config Error: Unknown alias '{obj}'. "
                        f"Supported aliases: REF-TEMP, REF-PRES")
            return obj
        else:
            return obj
    
    return recursive_resolve(config)
#==============================================================================
def get_vector_input(config, key, required=True):
    """
    Reads a list from config and validates it is a 3-component numeric vector.
    """
    val = get_config_value(config, key, expected_type=list, required=required)

    if val is None:
        return None

    if len(val) != 3:
        sys.exit(f"Config Error: '{key}' must have exactly 3 components (x, y, z).")

    # Ensure all items are numbers
    if not all(isinstance(x, (int, float)) for x in val):
        sys.exit(f"Config Error: '{key}' entries must be numbers.")

    return val
#==============================================================================
def parse_matrix_solvers(solver_dict, block_name, region_type="fluid"):
    """
    Parses, validates, and checks logical combinations for a matrix solver block.

    :param solver_dict: Dict of solver settings from JSON
    :param block_name: Name of the solver block (e.g. "pressure", "others", "energy")
    :param region_type: "fluid" (default) or "solid"
    """
    if not solver_dict:
        sys.exit(f"Config Error: Missing solver settings for '{block_name}'.")

    # 1. Extract the raw values
    solver = get_config_value(solver_dict, "solver", expected_type=str)
    preconditioner = get_config_value(solver_dict, "preconditioner", expected_type=str)
    tolerance = get_config_value(solver_dict, "tolerance", expected_type=float, min_val=0.0, max_val=0.1)
    rel_tol = get_config_value(solver_dict, "relative_tolerance", expected_type=float, min_val=0.0, max_val=0.1)
    min_iter = get_config_value(solver_dict, "min_iter", expected_type=int, min_val=0)
    max_iter = get_config_value(solver_dict, "max_iter", expected_type=int, min_val=1, max_val=100000)

    # 2. Enforce Strict Solver & Preconditioner Logic
    if block_name == "pressure" or (block_name == "energy" and region_type == "solid"):
        valid_solvers = ["GAMG", "PCG"]
        if solver not in valid_solvers:
            sys.exit(f"Config Error: Invalid solver '{solver}' for {block_name}. Allowed: {valid_solvers}")

        if solver == "GAMG":
            valid_preconds = ["GaussSeidel", "DICGaussSeidel"]
        elif solver == "PCG":
            valid_preconds = ["DIC"]

        if preconditioner not in valid_preconds:
            sys.exit(f"Config Error: Solver '{solver}' in {block_name} requires one of these preconditioners: {valid_preconds}. Got: '{preconditioner}'")

    elif block_name == "others":
        valid_solvers = ["smoothSolver", "PBiCGStab"]
        if solver not in valid_solvers:
            sys.exit(f"Config Error: Invalid solver '{solver}' for {block_name}. Allowed: {valid_solvers}")

        if solver == "smoothSolver":
            valid_preconds = ["GaussSeidel", "symGaussSeidel"]
        elif solver == "PBiCGStab":
            valid_preconds = ["DILU"]

        if preconditioner not in valid_preconds:
            sys.exit(f"Config Error: Solver '{solver}' in {block_name} requires one of these preconditioners: {valid_preconds}. Got: '{preconditioner}'")

    else:
        # Catch-all in case you add new blocks (like 'velocity' or 'k') later
        sys.exit(f"Config Error: Unknown solver block '{block_name}'.")

    # 3. Determine the OpenFOAM keyword (smoother vs preconditioner)
    if solver in ["GAMG", "smoothSolver"]:
        precond_keyword = "smoother"
    elif solver in ["PBiCGStab", "PCG"]:
        precond_keyword = "preconditioner"
    else:
        precond_keyword = "preconditioner" # Safe fallback

    # 4. Return the clean, validated dictionary mapped to OpenFOAM keywords
    return {
        "solver": solver,
        "preconditioner": preconditioner,
        "precond_keyword": precond_keyword,
        "tolerance": tolerance,
        "relative_tolerance": rel_tol,
        "min_iter": min_iter,
        "max_iter": max_iter
    }
#==============================================================================
def to_openfoam_vector(vec):
    """
    Converts a Python list [x, y, z] to an OpenFOAM vector string "(x y z)".
    Uses 'g' formatting to remove unnecessary trailing zeros (0.0 -> 0).
    """
    # check if it's a valid list of 3
    if not isinstance(vec, (list, tuple)) or len(vec) != 3:
        raise ValueError(f"Input must be a list of 3 numbers. Got: {vec}")

    # The :g format removes insignificant zeros (0.00 -> 0)
    return f"({vec[0]:g} {vec[1]:g} {vec[2]:g})"
#==============================================================================
def to_openfoam_list(items):
    """
    Converts a Python list ['a', 'b', 'c'] or [1, 2, 3]
    to an OpenFOAM list string "(a b c)" or "(1 2 3)".
    Converts items to strings if needed.
    """
    if not items:
        return "()"

    # Convert all items to strings and join with a single space
    str_items = [str(item) for item in items]
    return f"({' '.join(str_items)})"
#==============================================================================
def get_region_config(config):
    """
    Extracts region lists and validates that fluids and solids are mutually exclusive.
    Both fluids and solids are optional, but at least one must be present.

    :param config: The main configuration dictionary.
    :return: A tuple (fluids_list, solids_list)
    """
    # 1. Get the 'regions' dictionary
    regions_dict = get_config_value(config, "regions", expected_type=dict)

    # 2. Extract the lists (both optional, default to empty list if not provided)
    fluids = get_config_value(regions_dict, "fluids", expected_type=list, required=False) or []
    solids = get_config_value(regions_dict, "solids", expected_type=list, required=False) or []

    # 3. Validate that at least one region type is present
    if not fluids and not solids:
        sys.exit("Config Error: At least one region (fluid or solid) must be defined in the 'regions' section.")

    # 4. Validate content types (must be strings)
    for f in fluids:
        if not isinstance(f, str):
            sys.exit(f"Config Error: Fluid region '{f}' must be a string.")
    for s in solids:
        if not isinstance(s, str):
            sys.exit(f"Config Error: Solid region '{s}' must be a string.")

    # 5. CRITICAL CHECK: Mutual Exclusivity
    # Convert lists to sets to find intersection (overlap)
    fluid_set = set(fluids)
    solid_set = set(solids)

    intersection = fluid_set.intersection(solid_set)

    if intersection:
        sys.exit(f"Config Error: The following regions are defined as BOTH fluid and solid:\n"
                 f"  {list(intersection)}\n"
                 "  A region cannot be both. Please fix 'sim_inputs.json'.")

    return fluids, solids
#==============================================================================
def get_region_parts(config, all_regions):
    """
    Extracts and validates region_parts (boundaries, cellZones, faceZones) for all regions.
    
    :param config: The main configuration dictionary
    :param all_regions: List of all region names (fluids + solids)
    :return: Dictionary with region_parts {region_name: {boundaries: [...], cellZones: [...], faceZones: [...]}}
    """
    region_parts_dict = get_config_value(config, "region_parts", expected_type=dict, required=True)
    
    region_parts = {}
    for region in all_regions:
        region_parts_data = get_config_value(region_parts_dict, region, expected_type=dict, required=True)
        
        boundaries = get_config_value(region_parts_data, "boundaries", expected_type=list, required=True)
        cellZones = get_config_value(region_parts_data, "cellZones", expected_type=list, required=True)
        faceZones = get_config_value(region_parts_data, "faceZones", expected_type=list, required=True)
        
        # Validate that all zone names are strings
        for name in boundaries + cellZones + faceZones:
            if not isinstance(name, str):
                sys.exit(f"Config Error: Region '{region}': zone/boundary names must be strings, got {type(name)}")
        
        region_parts[region] = {
            "boundaries": boundaries,
            "cellZones": cellZones,
            "faceZones": faceZones
        }
    
    return region_parts

#==============================================================================
def validate_solver_name(solver_name, sim_type, fluids, solids):
    """
    Validates the solver_name against simulation type and region configuration.
    
    :param solver_name: The solver name from config
    :param sim_type: "steady-state" or "transient"
    :param fluids: List of fluid region names
    :param solids: List of solid region names
    """
    # Define allowed solvers per simulation type
    steady_state_solvers = ["chtMultiRegionSimpleFoam",
                            "buoyantSimpleFoam", "rhoSimpleFoam", "solidFoam", "simpleFoam"]
    transient_solvers = ["chtMultiRegionFoam",
                         "buoyantPimpleFoam", "rhoPimpleFoam", "solidFoam", "pimpleFoam"]
    cht_solvers = ["chtMultiRegionSimpleFoam", "chtMultiRegionFoam"]

    # Validate solver_name against simulation type
    if sim_type == "steady-state":
        if solver_name not in steady_state_solvers:
            sys.exit(f"Config Error: Solver '{solver_name}' is not valid for steady-state simulations.\n"
                     f"  Allowed: {steady_state_solvers}")
    else:
        if solver_name not in transient_solvers:
            sys.exit(f"Config Error: Solver '{solver_name}' is not valid for transient simulations.\n"
                     f"  Allowed: {transient_solvers}")

    # Validate solver_name against region configuration
    num_regions = len(fluids) + len(solids)
    num_fluids = len(fluids)
    num_solids = len(solids)

    if solver_name in cht_solvers:
        if num_regions < 2:
            sys.exit(f"Config Error: Solver '{solver_name}' requires at least 2 regions (fluids + solids).\n"
                     f"  Current: {num_fluids} fluid(s), {num_solids} solid(s)")

    if num_fluids == 1 and num_solids == 0:
        # Only one fluid region — buoyant, rho, or incompressible (simpleFoam/pimpleFoam)
        allowed_single_fluid = ["buoyantSimpleFoam", "rhoSimpleFoam", "simpleFoam"] if sim_type == "steady-state" else \
                               ["buoyantPimpleFoam", "rhoPimpleFoam", "pimpleFoam"]
        if solver_name not in allowed_single_fluid:
            sys.exit(f"Config Error: Solver '{solver_name}' is not valid for a single fluid region.\n"
                     f"  Allowed: {allowed_single_fluid}")

    if num_solids == 1 and num_fluids == 0:
        # Only one solid region - must use solidFoam
        if solver_name != "solidFoam":
            sys.exit(f"Config Error: Solver '{solver_name}' is not valid for a single solid region.\n"
                     f"  Required: solidFoam")

#==============================================================================
def is_incompressible_solver(solver_name):
    """
    Returns True if the solver is an incompressible isothermal solver
    (simpleFoam or pimpleFoam).  These solvers do not solve an energy equation,
    use kinematic pressure p = P/rho, and require transportProperties instead of
    thermophysicalProperties in constant/.

    :param solver_name: OpenFOAM solver name string
    :return: True for simpleFoam / pimpleFoam, False for all other solvers
    """
    return solver_name in ("simpleFoam", "pimpleFoam")

# Registry of supported RANS models and their coefficients.
# Each entry: coefficient_name -> {"type": <python type>, "default": <OpenFOAM default>}
# "type" is used to validate user-supplied values; "default" is shown in error messages.
# Defaults reflect OpenFOAM v2512 built-in values.
_RANS_MODEL_COEFFICIENTS = {
    "kOmegaSST": {
        "Prt":          {"type": float, "default": 0.85},
        "alphaK1":      {"type": float, "default": 0.85},
        "alphaK2":      {"type": float, "default": 1.0},
        "alphaOmega1":  {"type": float, "default": 0.5},
        "alphaOmega2":  {"type": float, "default": 0.856},
        "gamma1":       {"type": float, "default": 0.555556},
        "gamma2":       {"type": float, "default": 0.44},
        "beta1":        {"type": float, "default": 0.075},
        "beta2":        {"type": float, "default": 0.0828},
        "betaStar":     {"type": float, "default": 0.09},
        "a1":           {"type": float, "default": 0.31},
        "b1":           {"type": float, "default": 1.0},
        "c1":           {"type": float, "default": 10.0},
        "F3":           {"type": bool,  "default": False},
        "decayControl": {"type": bool,  "default": False},
        "kInf":         {"type": float, "default": 0.0},
        "omegaInf":     {"type": float, "default": 0.0},
    },
    "kOmega": {
        "Prt":          {"type": float, "default": 0.85},
        "betaStar":     {"type": float, "default": 0.09},
        "beta":         {"type": float, "default": 0.072},
        "gamma":        {"type": float, "default": 0.52},
        "alphaK":       {"type": float, "default": 0.5},
        "alphaOmega":   {"type": float, "default": 0.5},
    },
    "kEpsilon": {
        "Prt":          {"type": float, "default": 0.85},
        "Cmu":          {"type": float, "default": 0.09},
        "C1":           {"type": float, "default": 1.44},
        "C2":           {"type": float, "default": 1.92},
        "C3":           {"type": float, "default": 0.0},
        "sigmak":       {"type": float, "default": 1.0},
        "sigmaEps":     {"type": float, "default": 1.3},
    },
    "RNGkEpsilon": {
        "Prt":          {"type": float, "default": 0.85},
        "Cmu":          {"type": float, "default": 0.0845},
        "C1":           {"type": float, "default": 1.42},
        "C2":           {"type": float, "default": 1.68},
        "C3":           {"type": float, "default": 0.0},
        "sigmak":       {"type": float, "default": 0.71942},
        "sigmaEps":     {"type": float, "default": 0.71942},
        "eta0":         {"type": float, "default": 4.38},
        "beta":         {"type": float, "default": 0.012},
    },
    "realizableKE": {
        "Prt":          {"type": float, "default": 0.85},
        "A0":           {"type": float, "default": 4.0},
        "C2":           {"type": float, "default": 1.9},
        "sigmak":       {"type": float, "default": 1.0},
        "sigmaEps":     {"type": float, "default": 1.2},
    },
}
#==============================================================================
def get_turbulence_content(config):
    """
    Reads turbulence configuration, validates it, and returns a Jinja2 template name
    and context dict for rendering turbulenceProperties.

    :param config: The main configuration dictionary
    :return: Tuple (is_active, model, template_name, context)
             - is_active: bool
             - model: RANS model name string, or None for laminar
             - template_name: Jinja2 template path relative to templates/
             - context: dict of template variables (excludes openfoam_version and location,
                        which are supplied by the caller at render time)
    """
    _LAMINAR_TEMPLATE = "constant/fluid/turbulenceProperties_laminar.template"
    _RANS_TEMPLATE    = "constant/fluid/turbulenceProperties_rans.template"

    turbulence_dict = get_config_value(config, "turbulence", expected_type=dict, required=False)

    if turbulence_dict is None:
        return False, None, _LAMINAR_TEMPLATE, {}

    is_active = get_config_value(turbulence_dict, "active", expected_type=bool, required=True)

    if not is_active:
        return False, None, _LAMINAR_TEMPLATE, {}

    turb_type = get_config_value(turbulence_dict, "type", expected_type=str, required=True)

    if turb_type == "DES":
        sys.exit(f"Config Error: DES turbulence type is not supported yet.")
    elif turb_type == "LES":
        sys.exit(f"Config Error: LES turbulence type is not supported yet.")
    elif turb_type != "RANS":
        sys.exit(f"Config Error: Unknown turbulence type '{turb_type}'. "
                f"Supported types: RANS (DES and LES coming soon)")

    rans_config = get_config_value(turbulence_dict, "RANS_config", expected_type=dict, required=True)

    valid_models = list(_RANS_MODEL_COEFFICIENTS.keys())
    model = get_config_value(rans_config, "model", expected_type=str, valid_options=valid_models, required=True)

    model_coeffs = get_config_value(rans_config, "model_coeffs", expected_type=dict, required=True)

    # Prt is mandatory for all models
    get_config_value(model_coeffs, "Prt", expected_type=float, required=True)

    get_config_value(rans_config, "wall_function", expected_type=str,
                     valid_options=["Standard", "Automatic"], required=False)
    get_config_value(rans_config, "thermal_wall_function", expected_type=str,
                     valid_options=["Standard", "Jayatilleke"], required=False)

    # Validate each user-supplied coefficient against the registry
    registry = _RANS_MODEL_COEFFICIENTS[model]
    for param_name, param_value in model_coeffs.items():
        if param_name not in registry:
            sys.exit(f"Config Error: Coefficient '{param_name}' is not valid for model '{model}'. "
                    f"Valid coefficients: {', '.join(sorted(registry.keys()))}")

        expected_type = registry[param_name]["type"]
        default       = registry[param_name]["default"]

        if expected_type == float:
            if isinstance(param_value, bool) or not isinstance(param_value, (int, float)):
                sys.exit(f"Config Error: Coefficient '{param_name}' for model '{model}' must be a "
                        f"number (default: {default}), "
                        f"but got {type(param_value).__name__} ({param_value}).")
        elif expected_type == bool:
            if not isinstance(param_value, bool):
                sys.exit(f"Config Error: Coefficient '{param_name}' for model '{model}' must be a "
                        f"boolean (default: {str(default).lower()}), "
                        f"but got {type(param_value).__name__} ({param_value}).")

    # Build pre-formatted coefficient block (alignment handled here, not in the template)
    coeff_entries = []
    for param_name, param_value in model_coeffs.items():
        expected_type = registry[param_name]["type"]
        if expected_type == bool:
            formatted = str(param_value).lower()
        else:
            formatted = str(param_value)
        coeff_entries.append(f"        {param_name:<15} {formatted};")

    context = {
        "model":        model,
        "coeffs_block": "\n".join(coeff_entries),
    }
    return is_active, model, _RANS_TEMPLATE, context
#==============================================================================
def get_radiation_content(config):
    """
    Reads radiation configuration, validates it, and returns a Jinja2 template name
    and context dict for rendering radiationProperties.

    :param config: The main configuration dictionary
    :return: Tuple (is_active, model, template_name, context)
             - is_active: bool
             - model: radiation model name string, or None if inactive
             - template_name: Jinja2 template path relative to templates/
             - context: dict of template variables (excludes openfoam_version and location)
    """
    _NONE_TEMPLATE       = "constant/fluid/radiationProperties_none.template"
    _FVDOM_TEMPLATE      = "constant/fluid/radiationProperties_fvdom.template"
    _VIEWFACTOR_TEMPLATE = "constant/fluid/radiationProperties_viewfactor.template"

    radiation_dict = get_config_value(config, "radiation", expected_type=dict, required=False)

    if radiation_dict is None:
        return False, None, _NONE_TEMPLATE, {}

    is_active = get_config_value(radiation_dict, "active", expected_type=bool, required=True)

    if not is_active:
        return False, None, _NONE_TEMPLATE, {}

    valid_models = ["fvDOM", "viewFactor"]
    model = get_config_value(radiation_dict, "model", expected_type=str, valid_options=valid_models, required=True)

    model_coeffs = get_config_value(radiation_dict, "model_coeffs", expected_type=dict, required=True)

    if model == "fvDOM":
        nPhi       = get_config_value(model_coeffs, "nPhi",       expected_type=int,   required=True)
        nTheta     = get_config_value(model_coeffs, "nTheta",     expected_type=int,   required=True)
        tolerance  = get_config_value(model_coeffs, "tolerance",  expected_type=float, required=True)
        maxIter    = get_config_value(model_coeffs, "maxIter",    expected_type=int,   required=True)
        solverFreq = get_config_value(model_coeffs, "solverFreq", expected_type=int,   required=True)
        context = {
            "nPhi":       nPhi,
            "nTheta":     nTheta,
            "tolerance":  tolerance,
            "maxIter":    maxIter,
            "solverFreq": solverFreq,
        }
        return is_active, model, _FVDOM_TEMPLATE, context

    elif model == "viewFactor":
        smoothing           = get_config_value(model_coeffs, "smoothing",           expected_type=bool, required=True)
        constantEmissivity  = get_config_value(model_coeffs, "constantEmissivity",  expected_type=bool, required=True)
        useDirectSolver     = get_config_value(model_coeffs, "useDirectSolver",     expected_type=bool, required=True)
        nBands              = get_config_value(model_coeffs, "nBands",              expected_type=int,  required=True)
        solverFreq          = get_config_value(model_coeffs, "solverFreq",          expected_type=int,  required=True)
        context = {
            "smoothing":          str(smoothing).lower(),
            "constantEmissivity": str(constantEmissivity).lower(),
            "useDirectSolver":    str(useDirectSolver).lower(),
            "nBands":             nBands,
            "solverFreq":         solverFreq,
        }
        return is_active, model, _VIEWFACTOR_TEMPLATE, context

#==============================================================================
# Materials library path — same directory as this module
_BUILTIN_LIBRARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "materials_library.json")

# Keys that are metadata in a library entry and must be stripped before use
_LIBRARY_METADATA_KEYS = {"_description", "_type", "_info"}

_CUSTOM_LIBRARY_FILENAME = "custom_materials_library.json"

def load_materials_library():
    """
    Loads the built-in materials library and, if present in the current working
    directory, automatically merges a custom library named
    'custom_materials_library.json'.

    Rules enforced:
      - Built-in library must have no duplicate material names.
      - Custom library must not define any name already present in the built-in
        library — entries must be entirely new names.
      - Every entry in both libraries must have '_type' ('fluid' or 'solid').

    :return: Merged dict {material_name -> property_dict}.
    """
    def _detect_duplicates(pairs):
        """object_pairs_hook for json.loads — raises on duplicate keys."""
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f"Duplicate material name '{key}' found in library.")
            seen[key] = value
        return seen

    def _load_library_file(path, label):
        if not os.path.exists(path):
            sys.exit(f"Error: Materials library file not found: '{path}'.")
        try:
            with open(path, "r") as f:
                raw = json.load(f, object_pairs_hook=_detect_duplicates)
        except ValueError as e:
            sys.exit(f"Error in {label}: {e}")
        except json.JSONDecodeError as e:
            sys.exit(f"Error: '{path}' contains invalid JSON.\nDetails: {e}")
        return raw

    # Load built-in library
    builtin_raw = _load_library_file(os.path.normpath(_BUILTIN_LIBRARY_PATH), "built-in materials library")

    # Strip top-level metadata key (_info) and collect material entries
    builtin_library = {}
    for name, entry in builtin_raw.items():
        if name.startswith("_"):
            continue
        if "_type" not in entry:
            sys.exit(f"Error: Built-in library entry '{name}' is missing required '_type' field ('fluid' or 'solid').")
        if entry["_type"] not in ("fluid", "solid"):
            sys.exit(f"Error: Built-in library entry '{name}' has invalid '_type': '{entry['_type']}'. Must be 'fluid' or 'solid'.")
        builtin_library[name] = entry

    # Auto-detect custom library in the current working directory
    custom_library_path = os.path.join(os.getcwd(), _CUSTOM_LIBRARY_FILENAME)
    if not os.path.exists(custom_library_path):
        return builtin_library

    # Load and validate custom library
    custom_raw = _load_library_file(custom_library_path, "custom materials library")

    custom_library = {}
    for name, entry in custom_raw.items():
        if name.startswith("_"):
            continue
        # Conflict check — custom library must not redefine built-in names
        if name in builtin_library:
            sys.exit(
                f"Error: Custom materials library defines '{name}' which already exists in the "
                f"built-in library. Use a different name (e.g., '{name}-custom') to avoid conflicts."
            )
        if "_type" not in entry:
            sys.exit(f"Error: Custom library entry '{name}' is missing required '_type' field ('fluid' or 'solid').")
        if entry["_type"] not in ("fluid", "solid"):
            sys.exit(f"Error: Custom library entry '{name}' has invalid '_type': '{entry['_type']}'. Must be 'fluid' or 'solid'.")
        custom_library[name] = entry

    return {**builtin_library, **custom_library}

#==============================================================================
def resolve_material_reference(region_cfg, region_name, region_type, library):
    """
    Resolves a material reference in sim_inputs.json to a fully-expanded property dict,
    ready for the existing validate_* and build_* functions.

    Accepted forms in sim_inputs.json:

      Fluids (string only):
          "domain_fluid": "air-constant"

      Uniform solid (isotropic):
          "domain_solid": "copper"

      Uniform solid (anisotropic):
          "domain_solid": {
              "material": "FR4",
              "kappa_type": "anisotropic",
              "kappa": [kx, ky, kz],
              "coordinate_system": { "origin": [...], "e1": [...], "e2": [...] }
          }

      Cell-zone-specific solid (isotropic):
          "domain_solid": {
              "type": "cell_zone_specific",
              "properties": {
                  "default":   "steel-304",
                  "zone1,zone2": "copper"
              }
          }

      Cell-zone-specific solid (anisotropic):
          "domain_solid": {
              "type": "cell_zone_specific",
              "kappa_type": "anisotropic",
              "coordinate_system": { "origin": [...], "e1": [...], "e2": [...] },
              "properties": {
                  "default":     { "material": "steel-304",   "kappa": [kx, ky, kz] },
                  "zone1,zone2": { "material": "copper",      "kappa": [kx, ky, kz] }
              }
          }

    :param region_cfg:  Value of material_properties[region_name] from sim_inputs.json.
    :param region_name: Region name (for error messages).
    :param region_type: 'fluid' or 'solid' — validated against library entry _type.
    :param library:     Merged library dict from load_materials_library().
    :return:            Fully-resolved property dict ready for validate_* and build_*.
    """
    if region_type == "fluid":
        return _resolve_fluid(region_cfg, region_name, library)
    return _resolve_solid(region_cfg, region_name, library)

# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _resolve_fluid(region_cfg, region_name, library):
    if not isinstance(region_cfg, str):
        sys.exit(
            f"Error in region '{region_name}': Fluid material must be a plain material name string "
            f"(e.g., \"air-constant\"). Full inline definitions and dict forms are not supported.\n"
            f"To use a custom material, add it to the custom materials library."
        )
    return _lookup_and_strip(region_cfg, region_name, "fluid", library)

def _resolve_solid(region_cfg, region_name, library):
    # Form 1: plain string → uniform isotropic solid
    if isinstance(region_cfg, str):
        props = _lookup_and_strip(region_cfg, region_name, "solid", library)
        return {"type": "uniform", **props}

    if not isinstance(region_cfg, dict):
        sys.exit(
            f"Error in region '{region_name}': Solid material entry must be a string or a dict. "
            f"Got: {type(region_cfg).__name__}."
        )

    # Form 2: dict with "material" key → uniform solid (with optional anisotropic override)
    if "material" in region_cfg:
        return _resolve_uniform_solid(region_cfg, region_name, library)

    # Form 3: dict with "type": "cell_zone_specific"
    if region_cfg.get("type") == "cell_zone_specific":
        return _resolve_cell_zone_specific(region_cfg, region_name, library)

    # Anything else
    sys.exit(
        f"Error in region '{region_name}': Solid material_properties entry must be one of:\n"
        f"  - A string (material name) for a uniform isotropic solid\n"
        f"  - A dict with a 'material' key for a uniform anisotropic solid\n"
        f"  - A dict with 'type': 'cell_zone_specific' for a multi-zone solid\n"
        f"Full inline property definitions are not supported. "
        f"Define the material in the materials library and reference it by name."
    )

def _resolve_uniform_solid(region_cfg, region_name, library):
    """Handles: 'material' + optional anisotropic kappa override."""
    _UNIFORM_ALLOWED = {"material", "kappa_type", "kappa", "coordinate_system"}
    unexpected = set(region_cfg.keys()) - _UNIFORM_ALLOWED
    if unexpected:
        sys.exit(
            f"Error in region '{region_name}': Unexpected keys alongside 'material': {sorted(unexpected)}.\n"
            f"Allowed keys: {sorted(_UNIFORM_ALLOWED)}.\n"
            f"For any other property changes, create a custom library entry."
        )

    kappa_type = region_cfg.get("kappa_type")
    if kappa_type is not None and kappa_type != "anisotropic":
        sys.exit(
            f"Error in region '{region_name}': The only permitted kappa_type override is 'anisotropic'. "
            f"Got '{kappa_type}'. For isotropic solids, omit 'kappa_type'."
        )

    if kappa_type == "anisotropic":
        _aniso_require_all(region_cfg, region_name)

    props = _lookup_and_strip(region_cfg["material"], region_name, "solid", library)
    result = {"type": "uniform", **props}

    if kappa_type == "anisotropic":
        result["kappa_type"]        = "anisotropic"
        result["kappa"]             = region_cfg["kappa"]
        result["coordinate_system"] = region_cfg["coordinate_system"]

    return result

def _resolve_cell_zone_specific(region_cfg, region_name, library):
    """Handles cell_zone_specific solid regions."""
    _CZS_ALLOWED = {"type", "kappa_type", "coordinate_system", "properties"}
    unexpected = set(region_cfg.keys()) - _CZS_ALLOWED
    if unexpected:
        sys.exit(
            f"Error in region '{region_name}' (cell_zone_specific): Unexpected keys: {sorted(unexpected)}.\n"
            f"Allowed keys: {sorted(_CZS_ALLOWED)}."
        )

    kappa_type = region_cfg.get("kappa_type", "isotropic")
    if kappa_type not in ("isotropic", "anisotropic"):
        sys.exit(f"Error in region '{region_name}': kappa_type must be 'isotropic' or 'anisotropic', got '{kappa_type}'.")

    if kappa_type == "anisotropic" and "coordinate_system" not in region_cfg:
        sys.exit(f"Error in region '{region_name}': 'coordinate_system' is required when kappa_type is 'anisotropic'.")

    properties_cfg = region_cfg.get("properties")
    if not isinstance(properties_cfg, dict) or not properties_cfg:
        sys.exit(f"Error in region '{region_name}': 'properties' must be a non-empty dict.")
    if "default" not in properties_cfg:
        sys.exit(f"Error in region '{region_name}': 'properties' must contain a 'default' entry.")

    resolved_properties = {
        zone_key: _resolve_zone_entry(zone_cfg, zone_key, region_name, kappa_type, library)
        for zone_key, zone_cfg in properties_cfg.items()
    }

    result = {"type": "cell_zone_specific"}
    if kappa_type == "anisotropic":
        result["kappa_type"]        = "anisotropic"
        result["coordinate_system"] = region_cfg["coordinate_system"]
    result["properties"] = resolved_properties
    return result

def _resolve_zone_entry(zone_cfg, zone_key, region_name, outer_kappa_type, library):
    """Resolves a single zone entry inside a cell_zone_specific solid."""
    context = f"region '{region_name}', zone '{zone_key}'"

    # String form
    if isinstance(zone_cfg, str):
        if outer_kappa_type == "anisotropic":
            sys.exit(
                f"Error in {context}: Zone is part of an anisotropic region but no kappa vector was provided. "
                f"Use {{\"material\": \"{zone_cfg}\", \"kappa\": [kx, ky, kz]}} instead of a plain string."
            )
        return _lookup_and_strip(zone_cfg, context, "solid", library)

    # Dict form
    if isinstance(zone_cfg, dict) and "material" in zone_cfg:
        allowed = {"material", "kappa"} if outer_kappa_type == "anisotropic" else {"material"}
        unexpected = set(zone_cfg.keys()) - allowed
        if unexpected:
            sys.exit(
                f"Error in {context}: Unexpected keys: {sorted(unexpected)}. "
                f"Allowed alongside 'material': {sorted(allowed)}."
            )
        props = _lookup_and_strip(zone_cfg["material"], context, "solid", library)
        if outer_kappa_type == "anisotropic":
            if "kappa" not in zone_cfg:
                sys.exit(
                    f"Error in {context}: Zone is part of an anisotropic region. "
                    f"A 'kappa' vector [kx, ky, kz] must be provided alongside 'material'."
                )
            props["kappa"] = zone_cfg["kappa"]
        return props

    sys.exit(
        f"Error in {context}: Zone entry must be a material name (string) or "
        f"{{\"material\": \"name\"}} / {{\"material\": \"name\", \"kappa\": [kx, ky, kz]}}.\n"
        f"Full inline property definitions are not supported."
    )

def _aniso_require_all(cfg, region_name):
    """Validates that all three anisotropic keys are present together."""
    aniso_keys = {"kappa_type", "kappa", "coordinate_system"}
    missing = aniso_keys - set(cfg.keys())
    if missing:
        sys.exit(
            f"Error in region '{region_name}': Incomplete anisotropic override. "
            f"Missing: {sorted(missing)}. All three must be specified together: "
            f"'kappa_type', 'kappa', 'coordinate_system'."
        )

def _lookup_and_strip(material_name, context_label, region_type, library):
    """Looks up material by name, validates _type, returns a copy with metadata stripped."""
    if material_name not in library:
        available = sorted(k for k in library)
        sys.exit(
            f"Error in {context_label}: Material '{material_name}' not found in the library.\n"
            f"Available materials: {', '.join(available)}"
        )
    entry = library[material_name]
    if entry.get("_type") != region_type:
        sys.exit(
            f"Error in {context_label}: Material '{material_name}' is a {entry.get('_type')} material "
            f"but this is a {region_type} region. Use a {region_type} material."
        )
    return {k: v for k, v in entry.items() if k not in _LIBRARY_METADATA_KEYS}

#==============================================================================
def validate_fluid_material_properties(material_props_dict, region_name, reference_pressure):
    """
    Validates fluid material properties structure and checks allowed combinations.
    
    :param material_props_dict: Dictionary with rho, Cp, mu, kappa properties
    :param region_name: Name of the fluid region (for error messages)
    :param reference_pressure: Reference pressure from reference_conditions
    """
    # Check for solid property signature (would have "type" field)
    if "type" in material_props_dict:
        sys.exit(f"Error in region '{region_name}': This is a fluid region but has a solid property configuration (contains 'type' field). "
                 f"Fluid regions should have 'rho', 'Cp', 'mu', 'kappa' with model definitions, not 'type'.")
    
    # Check for valid fluid property signature - all required fields must be present and be dicts
    required_fluid_fields = ["rho", "Cp", "mu", "kappa"]
    missing_fields = [field for field in required_fluid_fields if field not in material_props_dict]
    if missing_fields:
        sys.exit(f"Error in region '{region_name}': This is a fluid region but is missing required properties: {', '.join(missing_fields)}. "
                 f"Fluid properties must include all of: 'rho', 'Cp', 'mu', 'kappa'.")
    
    # Verify they are all dicts with model definitions
    for field in required_fluid_fields:
        if not isinstance(material_props_dict.get(field), dict):
            sys.exit(f"Error in region '{region_name}': Expected '{field}' to be a dict with a 'model' field in fluid properties. "
                     f"Got {type(material_props_dict.get(field)).__name__} instead.")
        if "model" not in material_props_dict.get(field, {}):
            sys.exit(f"Error in region '{region_name}': Expected '{field}' dict to have a 'model' key. "
                     f"Fluid properties require model definitions for all transport properties.")
    
    # Molecular weight is always required
    mw = get_config_value(material_props_dict, "molecular_weight", expected_type=float, required=True)

    valid_rho_models = ["constant", "ideal-gas-temperature-only", "ideal-gas"]
    valid_other_models = ["constant", "polynomial"]
    
    # Validate rho
    rho_dict = get_config_value(material_props_dict, "rho", expected_type=dict, required=True)
    rho_model = get_config_value(rho_dict, "model", expected_type=str, valid_options=valid_rho_models, required=True)
    
    if rho_model == "constant":
        rho_value = get_config_value(rho_dict, "value", expected_type=float, required=True)
    
    # Validate Cp, mu, kappa
    for prop_name in ["Cp", "mu", "kappa"]:
        prop_dict = get_config_value(material_props_dict, prop_name, expected_type=dict, required=True)
        prop_model = get_config_value(prop_dict, "model", expected_type=str, valid_options=valid_other_models, required=True)
        
        if prop_model == "constant":
            value = get_config_value(prop_dict, "value", expected_type=float, required=True)
        elif prop_model == "polynomial":
            coeffs = get_config_value(prop_dict, "coefficients", expected_type=list, required=True)
            if len(coeffs) != 8:
                sys.exit(f"Error in region '{region_name}': {prop_name} polynomial must have exactly 8 coefficients, got {len(coeffs)}")
            for i, coeff in enumerate(coeffs):
                if not isinstance(coeff, (int, float)):
                    sys.exit(f"Error in region '{region_name}': {prop_name} coefficient {i} is not a number")
        
        # Check combination constraints
        if rho_model == "constant" and prop_model == "polynomial":
            sys.exit(f"Error in region '{region_name}': constant density cannot have temperature-dependent {prop_name}. Only constant {prop_name} allowed.")

#==============================================================================
_FLUID_THERMO_TEMPLATE = "constant/fluid/thermophysicalProperties.template"

def build_thermophysical_properties(material_props_dict, region_name, reference_pressure):
    """
    Builds thermophysicalProperties context for a fluid region.
    Assumes material properties have been validated by validate_fluid_material_properties.

    :param material_props_dict: Raw material properties dictionary with rho, Cp, mu, kappa
    :param region_name: Name of the fluid region
    :param reference_pressure: Reference pressure from reference_conditions
    :return: Tuple (template_name, context_dict) for Jinja2 rendering
    """
    rho_dict   = get_config_value(material_props_dict, "rho",   expected_type=dict, required=True)
    cp_dict    = get_config_value(material_props_dict, "Cp",    expected_type=dict, required=True)
    mu_dict    = get_config_value(material_props_dict, "mu",    expected_type=dict, required=True)
    kappa_dict = get_config_value(material_props_dict, "kappa", expected_type=dict, required=True)

    rho_model = get_config_value(rho_dict, "model", expected_type=str, required=True)
    cp_model  = get_config_value(cp_dict,  "model", expected_type=str, required=True)
    mu_model  = get_config_value(mu_dict,  "model", expected_type=str, required=True)

    ctx = {
        "rho_model":      rho_model,
        "cp_model":       cp_model,
        "mu_model":       mu_model,
        "eos_type":       {"constant": "rhoConst", "ideal-gas-temperature-only": "incompressiblePerfectGas", "ideal-gas": "perfectGas"}[rho_model],
        "thermo_type":    {"constant": "hConst",  "polynomial": "hPolynomial"}[cp_model],
        "transport_type": {"constant": "const",   "polynomial": "polynomial"}[mu_model],
        "mol_weight":     get_config_value(material_props_dict, "molecular_weight", expected_type=float, required=True),
    }

    if rho_model == "constant":
        ctx["rho_value"] = get_config_value(rho_dict, "value", expected_type=float, required=True)
    elif rho_model == "ideal-gas-temperature-only":
        ctx["pRef"] = reference_pressure

    if cp_model == "constant":
        ctx["cp_value"] = get_config_value(cp_dict, "value", expected_type=float, required=True)
    else:
        ctx["cp_coeffs"] = to_openfoam_list(get_config_value(cp_dict, "coefficients", expected_type=list, required=True))

    if mu_model == "constant":
        mu_value    = get_config_value(mu_dict,    "value", expected_type=float, required=True)
        kappa_value = get_config_value(kappa_dict, "value", expected_type=float, required=True)
        cp_value    = get_config_value(cp_dict,    "value", expected_type=float, required=True)
        ctx["mu_value"] = mu_value
        ctx["pr"]       = f"{mu_value * cp_value / kappa_value:.4f}"
    else:
        ctx["mu_coeffs"]    = to_openfoam_list(get_config_value(mu_dict,    "coefficients", expected_type=list, required=True))
        ctx["kappa_coeffs"] = to_openfoam_list(get_config_value(kappa_dict, "coefficients", expected_type=list, required=True))

    return _FLUID_THERMO_TEMPLATE, ctx

#==============================================================================
def validate_solid_material_properties(solid_props_dict, region_name):
    """
    Validates solid material properties structure for uniform or cell_zone_specific types.
    Handles both isotropic and anisotropic thermal conductivity.
    
    :param solid_props_dict: Dictionary with type and properties
    :param region_name: Name of the solid region (for error messages)
    """
    # Check for fluid property signature (would have rho, Cp, mu, kappa as dicts with models)
    if "type" not in solid_props_dict:
        fluid_field_indicators = ["rho", "Cp", "mu", "kappa"]
        found_fluid_fields = [field for field in fluid_field_indicators 
                             if field in solid_props_dict and isinstance(solid_props_dict.get(field), dict) and "model" in solid_props_dict.get(field, {})]
        if found_fluid_fields:
            sys.exit(f"Error in region '{region_name}': This is a solid region but has a fluid property configuration. "
                     f"Found fluid-specific fields with 'model': {', '.join(found_fluid_fields)}. "
                     f"Solid regions should have 'type' field with value 'uniform' or 'cell_zone_specific', not fluid property definitions.")
        else:
            sys.exit(f"Error in region '{region_name}': This is a solid region but is missing required 'type' field. "
                     f"Solid regions must have 'type' field with value 'uniform' or 'cell_zone_specific'.")
    
    prop_type = get_config_value(solid_props_dict, "type", expected_type=str, valid_options=["uniform", "cell_zone_specific"], required=True)
    
    # kappa_type defaults to "isotropic"
    kappa_type = get_config_value(solid_props_dict, "kappa_type", expected_type=str, valid_options=["isotropic", "anisotropic"], required=False) or "isotropic"
    
    # If anisotropic, coordinate_system is required
    if kappa_type == "anisotropic":
        coord_sys = get_config_value(solid_props_dict, "coordinate_system", expected_type=dict, required=True)
        origin = get_config_value(coord_sys, "origin", expected_type=list, required=True)
        e1 = get_config_value(coord_sys, "e1", expected_type=list, required=True)
        e2 = get_config_value(coord_sys, "e2", expected_type=list, required=True)
        
        if len(origin) != 3 or len(e1) != 3 or len(e2) != 3:
            sys.exit(f"Error in region '{region_name}': coordinate_system vectors must have 3 components")
    
    if prop_type == "uniform":
        # Validate uniform properties
        for prop_name in ["molecular_weight", "Cp", "rho"]:
            value = get_config_value(solid_props_dict, prop_name, expected_type=float, required=True)
        
        # Validate kappa (scalar for isotropic, vector for anisotropic)
        if kappa_type == "isotropic":
            kappa = get_config_value(solid_props_dict, "kappa", expected_type=float, required=True)
        else:  # anisotropic
            kappa = get_config_value(solid_props_dict, "kappa", expected_type=list, required=True)
            if len(kappa) != 3:
                sys.exit(f"Error in region '{region_name}': anisotropic kappa must be a 3-component vector")
    
    elif prop_type == "cell_zone_specific":
        # Validate cell_zone_specific properties
        properties_dict = get_config_value(solid_props_dict, "properties", expected_type=dict, required=True)
        
        # "default" is mandatory for cell_zone_specific
        default_props = get_config_value(properties_dict, "default", expected_type=dict, required=True)
        for prop_name in ["molecular_weight", "Cp", "rho"]:
            value = get_config_value(default_props, prop_name, expected_type=float, required=True)
        
        # Validate kappa in default
        if kappa_type == "isotropic":
            kappa = get_config_value(default_props, "kappa", expected_type=float, required=True)
        else:  # anisotropic
            kappa = get_config_value(default_props, "kappa", expected_type=list, required=True)
            if len(kappa) != 3:
                sys.exit(f"Error in region '{region_name}': anisotropic kappa must be a 3-component vector")
        
        # Validate other zone properties
        for zone_key, zone_props in properties_dict.items():
            if zone_key == "default":
                continue
            
            if not isinstance(zone_key, str):
                sys.exit(f"Error in region '{region_name}': zone key must be a string, got {type(zone_key)}")
            
            zone_props_dict = get_config_value(properties_dict, zone_key, expected_type=dict, required=True)
            
            for prop_name in ["molecular_weight", "Cp", "rho"]:
                value = get_config_value(zone_props_dict, prop_name, expected_type=float, required=True)
            
            # Validate kappa (scalar for isotropic, vector for anisotropic)
            if kappa_type == "isotropic":
                kappa = get_config_value(zone_props_dict, "kappa", expected_type=float, required=True)
            else:  # anisotropic
                kappa = get_config_value(zone_props_dict, "kappa", expected_type=list, required=True)
                if len(kappa) != 3:
                    sys.exit(f"Error in region '{region_name}': anisotropic kappa must be a 3-component vector")

#==============================================================================
_SOLID_THERMO_TEMPLATE = "constant/solid/thermophysicalProperties.template"

def build_solid_thermophysical_properties(solid_props_dict, region_name):
    """
    Builds thermophysicalProperties context for a solid region.
    Assumes properties have been validated by validate_solid_material_properties.
    Handles both isotropic and anisotropic thermal conductivity.

    :param solid_props_dict: Dictionary with type and properties (uniform or cell_zone_specific)
    :param region_name: Name of the solid region
    :return: Tuple (template_name, context_dict) for Jinja2 rendering
    """
    prop_type  = get_config_value(solid_props_dict, "type",       expected_type=str, required=True)
    kappa_type = get_config_value(solid_props_dict, "kappa_type", expected_type=str, required=False) or "isotropic"

    ctx = {
        "prop_type":      prop_type,
        "kappa_type":     kappa_type,
        "mixture_type":   "pureMixture" if prop_type == "uniform" else "pureZoneMixture",
        "transport_type": "constAnIso"  if kappa_type == "anisotropic" else "constIso",
    }

    if kappa_type == "anisotropic":
        coord_sys = get_config_value(solid_props_dict, "coordinate_system", expected_type=dict, required=True)
        ctx["coord_origin"] = to_openfoam_vector(get_config_value(coord_sys, "origin", expected_type=list, required=True))
        ctx["coord_e1"]     = to_openfoam_vector(get_config_value(coord_sys, "e1",     expected_type=list, required=True))
        ctx["coord_e2"]     = to_openfoam_vector(get_config_value(coord_sys, "e2",     expected_type=list, required=True))

    def _kappa_str(props):
        if kappa_type == "isotropic":
            return str(get_config_value(props, "kappa", expected_type=float, required=True))
        return to_openfoam_vector(get_config_value(props, "kappa", expected_type=list, required=True))

    def _zone_dict(props, name):
        return {
            "name":       name,
            "mol_weight": get_config_value(props, "molecular_weight", expected_type=float, required=True),
            "cp":         get_config_value(props, "Cp",               expected_type=float, required=True),
            "rho":        get_config_value(props, "rho",              expected_type=float, required=True),
            "kappa":      _kappa_str(props),
        }

    if prop_type == "uniform":
        ctx.update(_zone_dict(solid_props_dict, ""))
    else:
        properties_dict = get_config_value(solid_props_dict, "properties", expected_type=dict, required=True)
        zones = [_zone_dict(get_config_value(properties_dict, "default", expected_type=dict, required=True), '"(none|.*)"')]
        for zone_key, zone_props in properties_dict.items():
            if zone_key == "default":
                continue
            names = [z.strip() for z in zone_key.split(",")]
            zone_expr = names[0] if len(names) == 1 else f'"({"|".join(names)})"'
            zones.append(_zone_dict(zone_props, zone_expr))
        ctx["zones"] = zones

    return _SOLID_THERMO_TEMPLATE, ctx

#==============================================================================
_TRANSPORT_PROPS_TEMPLATE = "constant/fluid/transportProperties.template"

def validate_incompressible_material_properties(mat_dict, region_name):
    """
    Validates material properties for incompressible isothermal solvers
    (simpleFoam / pimpleFoam).

    Only constant rho and constant mu are required.  Cp, kappa and molecular_weight
    are neither required nor used — nu = mu / rho is written to transportProperties.

    :param mat_dict: Material properties dict for the region (already resolved from library)
    :param region_name: Region name (for error messages)
    """
    for prop in ("rho", "mu"):
        if prop not in mat_dict:
            sys.exit(
                f"Config Error: Incompressible material for region '{region_name}' is missing '{prop}'.\n"
                f"  Both 'rho' and 'mu' must be present with model='constant'."
            )
        prop_dict = mat_dict[prop]
        if not isinstance(prop_dict, dict):
            sys.exit(
                f"Config Error: '{prop}' in region '{region_name}' must be a dict "
                f"with 'model' and 'value' keys."
            )
        model = prop_dict.get("model")
        if model != "constant":
            sys.exit(
                f"Config Error: '{prop}' in region '{region_name}' must use model='constant' "
                f"for incompressible solvers (simpleFoam / pimpleFoam).\n"
                f"  Found model='{model}'.  Temperature-dependent properties are not supported."
            )
        value = prop_dict.get("value")
        if not isinstance(value, (int, float)) or value <= 0:
            sys.exit(
                f"Config Error: '{prop}' value in region '{region_name}' must be a positive number. "
                f"Got: {value}"
            )


def build_transport_properties(mat_dict, region_name):
    """
    Builds transportProperties context for an incompressible fluid region.
    Computes nu = mu / rho from constant material properties.

    :param mat_dict: Resolved and validated material properties dict (rho + mu constant)
    :param region_name: Region name (for error messages)
    :return: Tuple (template_name, context_dict)
    """
    rho = float(mat_dict["rho"]["value"])
    mu  = float(mat_dict["mu"]["value"])
    nu  = mu / rho
    return _TRANSPORT_PROPS_TEMPLATE, {"nu": nu, "region_name": region_name}

#==============================================================================
def execute_command(command):
    """
    Executes a shell command and handles the output.
    :param command: Command string to be executed.
    """
    try:
        # Added check=False so we can handle the return code manually below
        result = subprocess.run(command, text=True, capture_output=True, shell=True)
        
        if result.returncode != 0:
            print("Command failed with error:")
            print(result.stderr)
            return False # Return False on failure
        return True # Return True on success

    except FileNotFoundError:
        print(f"Command not found: {command}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while executing command: {e}")
        return False
#==============================================================================

def get_boolean_input(prompt):
    """
    Prompt the user for a boolean response (True/False).
    :param prompt: The question to display to the user.
    :return: True for 'true', False for 'false'.
    """
    while True:
        response = input(prompt + " (y/n): ").strip().lower()
        if response in ["true", "t", "yes", "y", "1"]:
            return True
        elif response in ["false", "f", "no", "n", "0"]:
            return False
        else:
            print("Invalid input. Please type 'y' or 'n'.")

#==============================================================================
#==============================================================================
def check_and_reset_directory(dir_name):
    """
    Ensures a clean, empty directory exists at dir_name.
    Deletes all existing content if present, then recreates the directory.
    The pre-run scan in setup_case.py informs the user before this runs.

    Result: A clean, empty directory named 'dir_name'.
    """
    if os.path.exists(dir_name):
        try:
            shutil.rmtree(dir_name)
        except OSError as e:
            sys.exit(f"Error removing '{dir_name}': {e}")

    try:
        os.makedirs(dir_name)
    except OSError as e:
        sys.exit(f"Error creating '{dir_name}': {e}")
#==============================================================================
#==============================================================================
def init_constant_directory(solids, fluids, is_single_region=False):
    """
    Validates and sets up the 'constant' directory.

    1. Checks if region folders (or flat polyMesh for single-region) exist.
    2. Checks if 'polyMesh' exists and is not empty in each region.
    3. Removes stale configuration FILES only — subdirectories (e.g. triSurface/)
       are left untouched.

    The pre-run scan in setup_case.py already reported what will be removed and
    the user confirmed before this function is called.

    :param is_single_region: When True, polyMesh is expected directly under 'constant/'
                             (flat single-region layout) rather than 'constant/<region>/'.
    """
    base_dir = "constant"

    # 1. Critical Check: Does 'constant' exist?
    if not os.path.exists(base_dir):
        sys.exit(f"Error: '{base_dir}' directory missing. Please generate the mesh first.")

    all_regions = solids + fluids

    if is_single_region:
        # Single-region: polyMesh lives directly under constant/
        poly_path = os.path.join(base_dir, "polyMesh")
        print("Validating mesh directories...")
        if not os.path.isdir(poly_path):
            sys.exit(f"Error: Missing 'polyMesh' folder in '{base_dir}' (single-region layout).")
        if not os.listdir(poly_path):
            sys.exit(f"Error: 'polyMesh' folder in '{base_dir}' is empty.")

        # Remove stale files only — leave subdirectories (triSurface etc.) intact
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isfile(item_path):
                try:
                    os.unlink(item_path)
                    print(f"  Removed: {item_path}")
                except Exception as e:
                    sys.exit(f"Failed to delete '{item_path}': {e}")
        return

    # Multi-region: each region has its own subfolder with polyMesh
    print("Validating mesh directories...")
    for region in all_regions:
        region_path = os.path.join(base_dir, region)
        poly_path = os.path.join(region_path, "polyMesh")

        if not os.path.exists(region_path):
            sys.exit(f"Error: Missing region directory '{region_path}'.")
        if not os.path.isdir(poly_path):
            sys.exit(f"Error: Missing 'polyMesh' folder in '{region_path}'.")
        if not os.listdir(poly_path):
            sys.exit(f"Error: 'polyMesh' folder in '{region_path}' is empty.")

    # Remove stale files only from each region folder — leave subdirectories intact
    for region in all_regions:
        region_path = os.path.join(base_dir, region)
        for item in os.listdir(region_path):
            item_path = os.path.join(region_path, item)
            if os.path.isfile(item_path):
                try:
                    os.unlink(item_path)
                    print(f"  Removed: {item_path}")
                except Exception as e:
                    sys.exit(f"Failed to delete '{item_path}': {e}")

#==============================================================================
def get_pressure_variable_name(solver_name):
    """
    Determines the correct OpenFOAM pressure variable name based on the solver.
    Solvers accounting for buoyancy/gravity use 'p_rgh', others use 'p'.
    
    :param solver_name: Name of the OpenFOAM solver (e.g., 'chtMultiRegionFoam')
    :return: 'p' or 'p_rgh'
    """
    solvers_using_p = [
        "simpleFoam", 
        "rhoSimpleFoam", 
        "pimpleFoam", 
        "rhoPimpleFoam"
    ]
    
    solvers_using_p_rgh = [
        "buoyantPimpleFoam", 
        "buoyantSimpleFoam", 
        "chtMultiRegionFoam", 
        "chtMultiRegionSimpleFoam"
    ]

    if solver_name in solvers_using_p:
        return "p"
    elif solver_name in solvers_using_p_rgh:
        return "p_rgh"
    else:
        sys.exit(
            f"Config Error: Unknown OpenFOAM solver '{solver_name}'. "
            f"Cannot determine if pressure variable should be 'p' or 'p_rgh'."
        )

#==============================================================================
def get_fluid_field_files(pres_var_name, turb_model, is_incompressible=False, rad_model=None):
    """
    Determine which field files are needed for a fluid region.

    :param pres_var_name: Pressure variable name ('p' or 'p_rgh')
    :param turb_model: Turbulence model name or None for laminar
    :param is_incompressible: True for simpleFoam/pimpleFoam — omits T and alphat
    :param rad_model: Radiation model name ('fvDOM', 'viewFactor') or None if inactive
    :return: List of field filenames to create
    """
    if is_incompressible:
        # Incompressible isothermal: no temperature, no thermal diffusivity
        files = ["U", "p"]
    else:
        files = ["U", "T", "p"]

    # Add pressure variant if needed
    if pres_var_name == "p_rgh":
        files.append("p_rgh")

    # Add turbulence files if turbulence is active (turb_model is not None)
    if turb_model is not None:
        if is_incompressible:
            files.append("nut")          # alphat is thermal-only; not needed
        else:
            files.extend(["nut", "alphat"])

        if turb_model in ["kEpsilon", "RNGkEpsilon", "realizableKE"]:
            files.extend(["k", "epsilon"])
        elif turb_model in ["kOmega", "kOmegaSST"]:
            files.extend(["k", "omega"])

    # fvDOM requires IDefault in each fluid region (compressible only)
    if rad_model == "fvDOM" and not is_incompressible:
        files.append("IDefault")

    return files

#==============================================================================
def get_solid_field_files():
    """
    Determine which field files are needed for a solid region.
    
    :return: List of field filenames to create
    """
    return ["T", "p"]

#==============================================================================
# Field dimensions mapping for OpenFOAM field files
FIELD_DIMENSIONS = {
    "U":       "[0 1 -1 0 0 0 0]",      # velocity
    "T":       "[0 0 0 1 0 0 0]",       # temperature
    "p":       "[1 -1 -2 0 0 0 0]",     # pressure
    "p_rgh":   "[1 -1 -2 0 0 0 0]",     # hydrostatic pressure
    "nut":     "[0 2 -1 0 0 0 0]",      # turbulent kinematic viscosity
    "alphat":  "[1 -1 -1 0 0 0 0]",     # turbulent thermal diffusivity
    "k":       "[0 2 -2 0 0 0 0]",      # turbulent kinetic energy
    "epsilon": "[0 2 -3 0 0 0 0]",      # turbulent dissipation rate
    "omega":   "[0 0 -1 0 0 0 0]"       # specific dissipation rate
}

#==============================================================================
def validate_initial_conditions(initial_conditions_dict, all_regions):
    """
    Validates initial_conditions structure.
    
    :param initial_conditions_dict: Dictionary with method and regions as keys
    :param all_regions: List of all region names
    """
    # Check for method field first with a clear error
    if "method" not in initial_conditions_dict:
        sys.exit(f"Error in initial_conditions: Missing required 'method' key. "
                 f"Must specify 'method' (e.g., 'uniform'). "
                 f"Supported methods: 'uniform' (others coming soon)")
    
    method = initial_conditions_dict["method"]
    
    # Validate method type
    if not isinstance(method, str):
        sys.exit(f"Error in initial_conditions: 'method' must be a string, got {type(method).__name__}")
    
    # Only "uniform" method is supported for now
    if method == "uniform":
        pass  # Proceed with validation
    elif method == "potential-flow":
        sys.exit(f"Error: Initial condition method 'potential-flow' is not supported yet.")
    elif method == "steady-state":
        sys.exit(f"Error: Initial condition method 'steady-state' is not supported yet.")
    else:
        sys.exit(f"Error in initial_conditions: Unknown method '{method}'. "
                 f"Supported methods: 'uniform' (others coming soon)")
    
    # Check that all regions have initial conditions
    for region in all_regions:
        if region not in initial_conditions_dict:
            sys.exit(f"Error in initial_conditions: Region '{region}' is missing. "
                     f"Each region must have its own entry with field values.")
        
        region_data = initial_conditions_dict[region]
        if not isinstance(region_data, dict):
            sys.exit(f"Error in initial_conditions > {region}: Expected dict, got {type(region_data).__name__}")

#==============================================================================
def get_initial_field_value(region_name, field_name, initial_conditions_dict, reference_pressure,
                            is_fluid=True, is_incompressible=False, rho=None):
    """
    Get the initial field value for a specific region and field.
    Formats it as "uniform <value>" for OpenFOAM.

    For pressure fields (compressible): user provides gauge pressure, converted to absolute
    by adding reference_pressure.
    For pressure fields (incompressible): user provides gauge pressure (Pa), converted to
    kinematic pressure by dividing by rho: p_kin = p_gauge / rho.

    :param region_name: Name of the region
    :param field_name: Name of the field (e.g., 'U', 'T', 'p')
    :param initial_conditions_dict: Dictionary with method and region keys
    :param reference_pressure: Reference pressure from reference_conditions (for absolute conversion)
    :param is_fluid: True if this is a fluid region, False if solid
    :param is_incompressible: True for simpleFoam/pimpleFoam (kinematic pressure)
    :param rho: Fluid density [kg/m³] — required when is_incompressible=True
    :return: String formatted as "uniform <value>" for OpenFOAM
    """
    if region_name not in initial_conditions_dict:
        sys.exit(f"Error: Region '{region_name}' is missing from initial_conditions")

    region_data = initial_conditions_dict[region_name]

    # Handle p field
    if field_name == "p":
        if is_fluid:
            # For fluids, p must be in the dict (as gauge pressure in Pa)
            if "p" not in region_data:
                sys.exit(f"Error in initial_conditions > {region_name}: 'p' field is required for fluid regions")
            gauge_pressure = region_data["p"]
            if not isinstance(gauge_pressure, (int, float)):
                sys.exit(f"Error in initial_conditions > {region_name} field 'p': Expected numeric value, got {type(gauge_pressure).__name__}")
            if is_incompressible:
                # Kinematic pressure: p_kin = p_gauge / rho  [m²/s²]
                if not rho:
                    sys.exit(f"Error: rho is required for incompressible pressure conversion in region '{region_name}'")
                value = gauge_pressure / rho
            else:
                # Convert gauge to absolute pressure [Pa]
                value = gauge_pressure + reference_pressure
        else:
            # For solids, use reference_pressure (absolute) directly
            value = reference_pressure
        return f"uniform {value}"
    
    # Handle p_rgh: use p value (as gauge) + reference_pressure (fluid only)
    if field_name == "p_rgh":
        if "p" not in region_data:
            sys.exit(f"Error in initial_conditions > {region_name}: 'p' field is required (p_rgh will use this value)")
        gauge_pressure = region_data["p"]
        if not isinstance(gauge_pressure, (int, float)):
            sys.exit(f"Error in initial_conditions > {region_name} field 'p': Expected numeric value, got {type(gauge_pressure).__name__}")
        # Convert gauge to absolute pressure
        value = gauge_pressure + reference_pressure
        return f"uniform {value}"
    
    # Handle nut and alphat: use default 1e-10 if not specified (fluid only)
    if field_name in ["nut", "alphat"]:
        if field_name not in region_data:
            return "uniform 1e-10"
        value = region_data[field_name]
    else:
        # All other fields must be in the dict
        if field_name not in region_data:
            sys.exit(f"Error: Field '{field_name}' is missing from initial_conditions > {region_name}")
        value = region_data[field_name]
    
    # Handle vector fields (U) vs scalar fields
    if isinstance(value, list):
        # Vector field: format as (x y z)
        if len(value) != 3:
            sys.exit(f"Error in region '{region_name}' field '{field_name}': "
                     f"Vector field must have 3 components, got {len(value)}")
        value_str = f"({value[0]} {value[1]} {value[2]})"
    else:
        # Scalar field
        if not isinstance(value, (int, float)):
            sys.exit(f"Error in region '{region_name}' field '{field_name}': "
                     f"Expected numeric value, got {type(value).__name__}")
        value_str = str(value)
    
    return f"uniform {value_str}"

#==============================================================================
def get_residual_entries(residuals_dict, pres_var_name=None, region_type="fluid",
                         is_incompressible=False):
    """
    Pre-processes a residuals dictionary into a list of template-ready dicts.

    Filters out entries with a value of -1 (disabled) and converts valid
    tolerances to a clean scientific notation string.

    :param residuals_dict: Dict of residual tolerances from JSON
    :param pres_var_name: Pressure variable name, required for fluid regions
    :param region_type: "fluid" (default) or "solid"
    :param is_incompressible: When True, energy residual is omitted (no energy equation)
    :return: List of {"field": foam_field, "tol": tol_str} dicts for tolerances > 0
    """
    if region_type == "solid":
        field_mapping = {"energy": "h"}
    else:
        field_mapping = {
            "pressure":   pres_var_name,
            "velocity":   "U",
            "turbulence": '"(k|epsilon|omega)"',
        }
        # Energy equation not solved by incompressible isothermal solvers
        if not is_incompressible:
            field_mapping["energy"] = '"(h|e)"'

    entries = []
    for json_key, foam_field in field_mapping.items():
        tol = residuals_dict.get(json_key, -1)
        if tol > 0:
            tol_str = f"{tol:.0e}".replace("e-0", "e-").replace("e+0", "e+")
            entries.append({"field": foam_field, "tol": tol_str})
    return entries

#==============================================================================
def validate_boundary_conditions(bc_dict, all_regions, fluids, turb_model,
                                 is_incompressible=False):
    """
    Validates boundary_conditions structure and content.
    Supports velocity-inlet, pressure-outlet, no-slip-wall for fluid regions.
    Supports thermal BCs for solid regions.

    :param bc_dict: The boundary_conditions dictionary from JSON
    :param all_regions: List of all region names
    :param fluids: List of fluid region names
    :param turb_model: Turbulence model name or None
    :param is_incompressible: When True, thermal BCs are not required/validated
    """
    if not isinstance(bc_dict, dict):
        sys.exit(f"Config Error: boundary_conditions must be a dictionary.")

    solids = [r for r in all_regions if r not in fluids]

    for region_name, region_bcs in bc_dict.items():
        # Skip cht_interfaces - it's handled separately
        if region_name == "cht_interfaces":
            continue

        if region_name not in all_regions:
            sys.exit(f"Config Error: In boundary_conditions, region '{region_name}' is not defined in regions.")

        if not isinstance(region_bcs, dict):
            sys.exit(f"Config Error: boundary_conditions > {region_name} must be a dictionary.")

        is_fluid = region_name in fluids

        for patch_name, patch_bc in region_bcs.items():
            if not isinstance(patch_bc, dict):
                sys.exit(f"Config Error: boundary_conditions > {region_name} > {patch_name} must be a dictionary.")

            bc_type = patch_bc.get("type")

            # Validate fluid-specific BCs
            if is_fluid:
                if bc_type == "velocity-inlet":
                    validate_velocity_inlet_bc(patch_bc, region_name, patch_name, turb_model,
                                               is_incompressible=is_incompressible)
                elif bc_type == "pressure-outlet":
                    validate_pressure_outlet_bc(patch_bc, region_name, patch_name, turb_model)
                elif bc_type == "total-pressure-inlet":
                    validate_total_pressure_inlet_bc(patch_bc, region_name, patch_name, turb_model,
                                                     is_incompressible=is_incompressible)
                elif bc_type == "no-slip-wall":
                    validate_no_slip_wall_bc(patch_bc, region_name, patch_name, turb_model,
                                             is_incompressible=is_incompressible)
                elif bc_type == "slip-wall":
                    validate_slip_wall_bc(patch_bc, region_name, patch_name)
                elif bc_type in CONSTRAINT_TYPES:
                    pass  # no sub-dict validation needed; setConstraintTypes handles field BCs
            # Validate solid BCs (constraint types require no sub-dict)
            else:
                if bc_type not in CONSTRAINT_TYPES:
                    validate_solid_bc(patch_bc, region_name, patch_name)


#==============================================================================
#==============================================================================
def validate_inlet_common_conditions(inlet_dict, region_name, patch_name, turb_model,
                                     label="inlet", is_incompressible=False):
    """
    Validates thermal and turbulence conditions common to all inlet-like BCs
    (velocity-inlet, total-pressure-inlet, and backflow_conditions).

    :param inlet_dict: The inlet condition dictionary (must contain thermal + turbulence)
    :param region_name: Region name
    :param patch_name: Patch name
    :param turb_model: Turbulence model name or None
    :param label: Label for error messages (e.g., "velocity-inlet", "backflow_conditions")
    :param is_incompressible: When True, thermal validation is skipped (no energy equation)
    """
    # Thermal dictionary is mandatory for compressible/CHT solvers; skipped for incompressible
    if not is_incompressible:
        if "thermal" not in inlet_dict:
            sys.exit(f"Config Error: {label} at {region_name}/{patch_name} missing 'thermal' dictionary.")
        thermal_dict = inlet_dict["thermal"]
        validate_thermal_bc(thermal_dict, region_name, patch_name, allowed_types=["temperature"])

    # Validate turbulence (mandatory if turbulence is active)
    if turb_model:
        if "turbulence" not in inlet_dict:
            sys.exit(f"Config Error: {label} at {region_name}/{patch_name} missing 'turbulence' key.")
        turb_dict = inlet_dict["turbulence"]
        validate_turbulence_dict(turb_dict, region_name, patch_name, turb_model, label=f" > {label} > turbulence")

#==============================================================================
def validate_total_pressure_inlet_bc(patch_bc, region_name, patch_name, turb_model,
                                     is_incompressible=False):
    """
    Validates total-pressure-inlet boundary condition structure.

    :param patch_bc: The patch BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    :param turb_model: Turbulence model name or None
    :param is_incompressible: When True, thermal validation is skipped
    """
    # Validate total_pressure (mandatory)
    if "total_pressure" not in patch_bc:
        sys.exit(f"Config Error: total-pressure-inlet at {region_name}/{patch_name} missing 'total_pressure' key.")
    total_pressure = patch_bc["total_pressure"]
    if not isinstance(total_pressure, (int, float)):
        sys.exit(f"Config Error: total_pressure at {region_name}/{patch_name} must be a number.")

    # Validate thermal and turbulence using common validator
    validate_inlet_common_conditions(patch_bc, region_name, patch_name, turb_model,
                                     label="total-pressure-inlet",
                                     is_incompressible=is_incompressible)

#==============================================================================
def validate_no_slip_wall_bc(patch_bc, region_name, patch_name, turb_model,
                             is_incompressible=False):
    """
    Validates no-slip-wall boundary condition structure.

    :param patch_bc: The patch BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    :param turb_model: Turbulence model name or None
    :param is_incompressible: When True, thermal validation is skipped
    """
    # Thermal BC is optional for no-slip-wall, and fully absent for incompressible solvers
    if not is_incompressible and "thermal" in patch_bc:
        thermal_dict = patch_bc["thermal"]
        validate_thermal_bc(thermal_dict, region_name, patch_name)

    # Emissivity is optional; used only when radiation is active
    if "emissivity" in patch_bc:
        val = patch_bc["emissivity"]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
            sys.exit(f"Config Error: 'emissivity' at {region_name}/{patch_name} must be a number in [0, 1].")

#==============================================================================
def validate_slip_wall_bc(patch_bc, region_name, patch_name):
    """
    Validates slip-wall boundary condition structure.

    slip-wall requires no turbulence or thermal sub-dicts — velocity, T, and
    turbulence fields all use the 'slip' BC type, and nut/alphat are 'calculated'.
    Any unexpected keys are silently ignored; this function guards against the user
    accidentally supplying thermal or turbulence sub-dicts that would be ignored.

    :param patch_bc: The patch BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    """
    if "thermal" in patch_bc:
        sys.exit(
            f"Config Error: slip-wall at {region_name}/{patch_name} does not support "
            f"a 'thermal' sub-dict. Temperature uses the 'slip' BC automatically."
        )
    if "turbulence" in patch_bc:
        sys.exit(
            f"Config Error: slip-wall at {region_name}/{patch_name} does not support "
            f"a 'turbulence' sub-dict. Turbulence fields use the 'slip' BC automatically."
        )

    # Emissivity is optional; used only when radiation is active
    if "emissivity" in patch_bc:
        val = patch_bc["emissivity"]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
            sys.exit(f"Config Error: 'emissivity' at {region_name}/{patch_name} must be a number in [0, 1].")

#==============================================================================
#==============================================================================
#==============================================================================
def validate_velocity_inlet_bc(patch_bc, region_name, patch_name, turb_model,
                                is_incompressible=False):
    """
    Validates velocity-inlet boundary condition structure.

    :param patch_bc: The patch BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    :param turb_model: Turbulence model name or None
    """
    # Validate velocity
    if "velocity" not in patch_bc:
        sys.exit(f"Config Error: velocity-inlet at {region_name}/{patch_name} missing 'velocity' key.")
    
    vel_dict = patch_bc["velocity"]
    if not isinstance(vel_dict, dict):
        sys.exit(f"Config Error: velocity at {region_name}/{patch_name} must be a dictionary.")
    
    vel_mode = vel_dict.get("mode")
    if vel_mode not in ["components", "normal-magnitude"]:
        sys.exit(f"Config Error: velocity mode at {region_name}/{patch_name} must be 'components' or 'normal-magnitude'.")
    
    # Check for either value OR time_varying (not both)
    has_value = "value" in vel_dict
    has_time_varying = "time_varying" in vel_dict
    
    if not has_value and not has_time_varying:
        sys.exit(f"Config Error: velocity at {region_name}/{patch_name} must have either 'value' or 'time_varying' key.")
    
    if has_value and has_time_varying:
        sys.exit(f"Config Error: velocity at {region_name}/{patch_name} cannot have both 'value' and 'time_varying'.")
    
    # Validate constant value (existing logic)
    if has_value:
        vel_value = vel_dict["value"]
        if vel_mode == "components":
            if not isinstance(vel_value, list) or len(vel_value) != 3:
                sys.exit(f"Config Error: velocity value for 'components' mode must be a 3-element list [Ux, Uy, Uz].")
            if not all(isinstance(x, (int, float)) for x in vel_value):
                sys.exit(f"Config Error: velocity components must be numbers.")
        elif vel_mode == "normal-magnitude":
            if not isinstance(vel_value, (int, float)):
                sys.exit(f"Config Error: velocity value for 'normal-magnitude' mode must be a scalar number.")
    
    # Validate time-varying (supports both components and normal-magnitude modes)
    if has_time_varying:
        time_varying_dict = vel_dict["time_varying"]
        validate_time_varying_bc(time_varying_dict, "velocity", region_name, patch_name, mode=vel_mode)
    
    # Validate thermal and turbulence using common validator
    validate_inlet_common_conditions(patch_bc, region_name, patch_name, turb_model,
                                     label="velocity-inlet",
                                     is_incompressible=is_incompressible)

#==============================================================================
def validate_solid_bc(patch_bc, region_name, patch_name):
    """
    Validates solid region boundary condition structure.
    Solids use "solid-wall" BC type with nested thermal dictionary.
    
    :param patch_bc: The patch BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    """
    # Validate BC type
    if "type" not in patch_bc:
        sys.exit(f"Config Error: Solid BC at {region_name}/{patch_name} missing 'type' key.")
    
    bc_type = patch_bc.get("type")
    if bc_type != "solid-wall":
        sys.exit(f"Config Error: Solid BC type at {region_name}/{patch_name} must be 'solid-wall', got '{bc_type}'.")
    
    # Validate thermal dictionary
    if "thermal" not in patch_bc:
        sys.exit(f"Config Error: solid-wall at {region_name}/{patch_name} missing 'thermal' dictionary.")
    
    thermal_dict = patch_bc["thermal"]
    if not isinstance(thermal_dict, dict):
        sys.exit(f"Config Error: thermal at {region_name}/{patch_name} must be a dictionary.")
    
    validate_thermal_bc(thermal_dict, region_name, patch_name)

#==============================================================================
#==============================================================================
def validate_csv_table_dict(csv_dict, context_name, expected_component_count=1):
    """
    Generic CSV table dictionary validator.
    Validates structure: csv_file, ref_column, component_columns, skip_rows.
    Also validates that the CSV file exists.
    
    :param csv_dict: The CSV dictionary from config
    :param context_name: Description for error messages (e.g., "faceZone 'fan-baffle' fan_curve")
    :param expected_component_count: Expected number of component columns (1 for scalar, 3 for vector)
    """
    if not isinstance(csv_dict, dict):
        sys.exit(f"Config Error: {context_name} must be a dictionary.")
    
    # Validate csv_file
    if "csv_file" not in csv_dict:
        sys.exit(f"Config Error: {context_name} missing 'csv_file' key.")
    
    csv_file = csv_dict["csv_file"]
    if not isinstance(csv_file, str):
        sys.exit(f"Config Error: csv_file in {context_name} must be a string.")
    
    if not csv_file.strip():
        sys.exit(f"Config Error: csv_file in {context_name} cannot be empty.")
    
    # Check if CSV file exists in inputData directory
    csv_path = f"inputData/{csv_file}"
    if not os.path.exists(csv_path):
        sys.exit(f"Config Error: CSV file not found at '{csv_path}' "
                f"for {context_name}. Please ensure the file exists in the inputData/ directory.")
    
    # Validate ref_column
    if "ref_column" not in csv_dict:
        sys.exit(f"Config Error: {context_name} missing 'ref_column' key.")
    
    ref_column = csv_dict["ref_column"]
    if not isinstance(ref_column, int):
        sys.exit(f"Config Error: ref_column in {context_name} must be an integer.")
    
    if ref_column < 0:
        sys.exit(f"Config Error: ref_column in {context_name} must be >= 0.")
    
    # Validate component_columns
    if "component_columns" not in csv_dict:
        sys.exit(f"Config Error: {context_name} missing 'component_columns' key.")
    
    component_columns = csv_dict["component_columns"]
    if not isinstance(component_columns, list):
        sys.exit(f"Config Error: component_columns in {context_name} must be a list.")
    
    if len(component_columns) != expected_component_count:
        sys.exit(f"Config Error: component_columns in {context_name} must have exactly {expected_component_count} element(s).")
    
    if not all(isinstance(col, int) for col in component_columns):
        sys.exit(f"Config Error: component_columns in {context_name} must contain only integers.")
    
    if not all(col >= 0 for col in component_columns):
        sys.exit(f"Config Error: all component_columns in {context_name} must be >= 0.")
    
    # Validate skip_rows (optional, defaults to 1)
    skip_rows = csv_dict.get("skip_rows", 1)
    if not isinstance(skip_rows, int):
        sys.exit(f"Config Error: skip_rows in {context_name} must be an integer.")
    
    if skip_rows < 0:
        sys.exit(f"Config Error: skip_rows in {context_name} must be >= 0.")

#==============================================================================
def validate_fan_curve_dict(fan_curve_dict, faceZone_name, region_name):
    """
    Validates a fan curve dictionary from faceZone_conditions.
    
    :param fan_curve_dict: The fan_curve dictionary (contains CSV table info)
    :param faceZone_name: Name of the faceZone
    :param region_name: Name of the region
    """
    context_name = f"region '{region_name}', faceZone '{faceZone_name}' fan_curve"
    # Fan curves are scalar fields (1 component = pressure drop)
    validate_csv_table_dict(fan_curve_dict, context_name, expected_component_count=1)

#==============================================================================
def validate_time_varying_bc(time_varying_dict, field_type, region_name, patch_name, mode=None):
    """
    Unified time-varying BC validator.
    Routes based on field_type to determine validation requirements.
    
    :param time_varying_dict: The time_varying dictionary
    :param field_type: "velocity" | "temperature"
    :param region_name: Region name
    :param patch_name: Patch name
    :param mode: For velocity, "components" | "normal-magnitude"
    """
    if not isinstance(time_varying_dict, dict):
        sys.exit(f"Config Error: time_varying at {region_name}/{patch_name} must be a dictionary.")
    
    # Validate common fields: csv_file, ref_column, skip_rows
    if "csv_file" not in time_varying_dict:
        sys.exit(f"Config Error: time_varying at {region_name}/{patch_name} missing 'csv_file' key.")
    
    csv_file = time_varying_dict["csv_file"]
    if not isinstance(csv_file, str):
        sys.exit(f"Config Error: csv_file at {region_name}/{patch_name} must be a string.")
    
    if not csv_file.strip():
        sys.exit(f"Config Error: csv_file at {region_name}/{patch_name} cannot be empty.")
    
    # Validate ref_column
    if "ref_column" not in time_varying_dict:
        sys.exit(f"Config Error: time_varying at {region_name}/{patch_name} missing 'ref_column' key.")
    
    ref_column = time_varying_dict["ref_column"]
    if not isinstance(ref_column, int):
        sys.exit(f"Config Error: ref_column at {region_name}/{patch_name} must be an integer.")
    
    if ref_column < 0:
        sys.exit(f"Config Error: ref_column at {region_name}/{patch_name} must be >= 0.")
    
    # Validate component_columns (field-specific length)
    if "component_columns" not in time_varying_dict:
        sys.exit(f"Config Error: time_varying at {region_name}/{patch_name} missing 'component_columns' key.")
    
    component_columns = time_varying_dict["component_columns"]
    if not isinstance(component_columns, list):
        sys.exit(f"Config Error: component_columns at {region_name}/{patch_name} must be a list.")
    
    # Determine expected column count based on field type and mode
    if field_type == "velocity":
        if mode == "components":
            expected_len = 3
            mode_desc = "velocity components (Ux, Uy, Uz)"
        elif mode == "normal-magnitude":
            expected_len = 1
            mode_desc = "velocity magnitude"
        else:
            sys.exit(f"Config Error: unknown velocity mode '{mode}' at {region_name}/{patch_name}.")
    
    elif field_type == "temperature":
        expected_len = 1
        mode_desc = "temperature (scalar field)"
    
    else:
        sys.exit(f"Config Error: unknown field_type '{field_type}' at {region_name}/{patch_name}.")
    
    # Validate component_columns length
    if len(component_columns) != expected_len:
        sys.exit(f"Config Error: component_columns at {region_name}/{patch_name} must have exactly {expected_len} element(s) for {mode_desc}.")
    
    if not all(isinstance(col, int) for col in component_columns):
        sys.exit(f"Config Error: component_columns at {region_name}/{patch_name} must contain only integers.")
    
    if not all(col >= 0 for col in component_columns):
        sys.exit(f"Config Error: all component_columns at {region_name}/{patch_name} must be >= 0.")
    
    # Validate skip_rows (optional, defaults to 1)
    skip_rows = time_varying_dict.get("skip_rows", 1)
    if not isinstance(skip_rows, int):
        sys.exit(f"Config Error: skip_rows at {region_name}/{patch_name} must be an integer.")
    
    if skip_rows < 0:
        sys.exit(f"Config Error: skip_rows at {region_name}/{patch_name} must be >= 0.")

#==============================================================================
def validate_thermal_bc(thermal_dict, region_name, patch_name, allowed_types=None):
    """
    Unified thermal boundary condition validation for all BC types.
    
    :param thermal_dict: The thermal BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    :param allowed_types: List of allowed thermal modes (default: all modes)
    """
    # Default to all supported modes if not specified
    if allowed_types is None:
        allowed_types = ["temperature", "heat-flux", "heat-transfer-rate", 
                        "heat-transfer-coefficient"]
    
    if not isinstance(thermal_dict, dict):
        sys.exit(f"Config Error: thermal BC at {region_name}/{patch_name} must be a dictionary.")
    
    if "mode" not in thermal_dict:
        sys.exit(f"Config Error: thermal BC at {region_name}/{patch_name} missing 'mode' key. "
                f"Must specify one of {allowed_types}. (Are you using the old 'type' key instead of 'mode'?)")
    
    thermal_mode = thermal_dict.get("mode")
    if thermal_mode not in allowed_types:
        sys.exit(f"Config Error: thermal mode at {region_name}/{patch_name} is '{thermal_mode}', "
                f"but must be one of {allowed_types}.")
    
    # Validate based on thermal mode
    if thermal_mode == "temperature":
        # Check for either value OR time_varying (not both)
        has_value = "value" in thermal_dict
        has_time_varying = "time_varying" in thermal_dict
        
        if not has_value and not has_time_varying:
            sys.exit(f"Config Error: specified-temperature at {region_name}/{patch_name} must have either 'value' or 'time_varying' key.")
        
        if has_value and has_time_varying:
            sys.exit(f"Config Error: specified-temperature at {region_name}/{patch_name} cannot have both 'value' and 'time_varying'.")
        
        # Validate constant value
        if has_value:
            if not isinstance(thermal_dict["value"], (int, float)):
                sys.exit(f"Config Error: temperature value at {region_name}/{patch_name} must be a number.")
        
        # Validate time-varying
        if has_time_varying:
            time_varying_dict = thermal_dict["time_varying"]
            validate_time_varying_bc(time_varying_dict, "temperature", region_name, patch_name)
    
    elif thermal_mode == "heat-flux":
        if "value" not in thermal_dict:
            sys.exit(f"Config Error: heat-flux at {region_name}/{patch_name} missing 'value' key.")
        if not isinstance(thermal_dict["value"], (int, float)):
            sys.exit(f"Config Error: heat flux value at {region_name}/{patch_name} must be a number.")
    
    elif thermal_mode == "heat-transfer-rate":
        if "value" not in thermal_dict:
            sys.exit(f"Config Error: heat-transfer-rate at {region_name}/{patch_name} missing 'value' key.")
        if not isinstance(thermal_dict["value"], (int, float)):
            sys.exit(f"Config Error: heat transfer rate value at {region_name}/{patch_name} must be a number.")
    
    elif thermal_mode == "heat-transfer-coefficient":
        if "htc" not in thermal_dict:
            sys.exit(f"Config Error: heat-transfer-coefficient at {region_name}/{patch_name} missing 'htc' key.")
        if not isinstance(thermal_dict["htc"], (int, float)):
            sys.exit(f"Config Error: htc value at {region_name}/{patch_name} must be a number.")
        
        if "ambient_temperature" not in thermal_dict:
            sys.exit(f"Config Error: heat-transfer-coefficient at {region_name}/{patch_name} missing 'ambient_temperature' key.")
        if not isinstance(thermal_dict["ambient_temperature"], (int, float)):
            sys.exit(f"Config Error: ambient_temperature value at {region_name}/{patch_name} must be a number.")
        
        # Validate optional outer_emissivity (default 0.0)
        if "outer_emissivity" in thermal_dict:
            if not isinstance(thermal_dict["outer_emissivity"], (int, float)):
                sys.exit(f"Config Error: outer_emissivity value at {region_name}/{patch_name} must be a number.")
        
        # Validate optional thermal_layers
        if "thermal_layers" in thermal_dict:
            _validate_thermal_layers(thermal_dict["thermal_layers"], region_name, patch_name)

#==============================================================================
def _validate_thermal_layers(layers, region_name, patch_name):
    """
    Validates thermal_layers structure.
    
    :param layers: List of thermal layer dictionaries
    :param region_name: Region name
    :param patch_name: Patch name
    """
    if not isinstance(layers, list):
        sys.exit(f"Config Error: thermal_layers at {region_name}/{patch_name} must be a list.")
    
    if len(layers) == 0:
        sys.exit(f"Config Error: thermal_layers at {region_name}/{patch_name} cannot be empty.")
    
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict):
            sys.exit(f"Config Error: thermal_layers[{i}] at {region_name}/{patch_name} must be a dictionary.")
        
        if "thickness" not in layer:
            sys.exit(f"Config Error: thermal_layers[{i}] at {region_name}/{patch_name} missing 'thickness' key.")
        if not isinstance(layer["thickness"], (int, float)):
            sys.exit(f"Config Error: thickness in thermal_layers[{i}] at {region_name}/{patch_name} must be a number.")
        
        if "conductivity" not in layer:
            sys.exit(f"Config Error: thermal_layers[{i}] at {region_name}/{patch_name} missing 'conductivity' key.")
        if not isinstance(layer["conductivity"], (int, float)):
            sys.exit(f"Config Error: conductivity in thermal_layers[{i}] at {region_name}/{patch_name} must be a number.")

#==============================================================================
def validate_and_fix_polymesh_patch(case_dir, region_name, patch_name, expected_type="patch", is_single_region=False):
    """
    Validates and fixes polyMesh boundary entry for patches.
    
    :param case_dir: Case directory path
    :param region_name: Region name
    :param patch_name: Patch name
    :param expected_type: Expected patch type ("patch" for inlets/outlets, "wall" for wall patches)
    :param is_single_region: When True, polyMesh is at constant/polyMesh (flat layout)
    """
    if is_single_region:
        boundary_file = os.path.join(case_dir, "constant/polyMesh/boundary")
    else:
        boundary_file = os.path.join(case_dir, f"constant/{region_name}/polyMesh/boundary")
    
    if not os.path.exists(boundary_file):
        sys.exit(f"Error: polyMesh boundary file not found at {boundary_file}")
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    # OpenFOAM boundary file format: patch name is not quoted, followed by { }
    # Pattern: whitespace, patch_name, whitespace, { ... }
    patch_pattern = rf'(\s{re.escape(patch_name)}\s*\{{[^}}]*\}})'
    match = re.search(patch_pattern, content, re.DOTALL)

    if not match:
        # List available patches for debugging
        available_patches = re.findall(r'\n\s+(\w+)\s*\{', content)
        patch_list = ', '.join(available_patches) if available_patches else "none found"
        sys.exit(f"Error: Patch '{patch_name}' not found in {boundary_file}\n"
                f"Available patches: {patch_list}")

    patch_block = match.group(0)
    original_block = patch_block
    
    if expected_type == "patch":
        # For inlet/outlet patches: type should be "patch", inGroups should contain "patches"
        # Check and fix type field (use regex to handle variable spacing)
        if not re.search(r'type\s+patch;', patch_block):
            if re.search(r'type\s+wall;', patch_block):
                patch_block = re.sub(r'type\s+wall;', 'type            patch;', patch_block)
                print(f"Warning: Patch '{patch_name}' in region '{region_name}' had type 'wall'; auto-fixed to 'patch'")
            else:
                sys.exit(f"Error: Patch '{patch_name}' type is not 'patch' or 'wall'. Cannot auto-fix.")
        
        # Check and fix inGroups
        if 'inGroups        1(patches);' not in patch_block:
            # Replace existing inGroups
            patch_block = re.sub(r'inGroups\s+\d+\([^)]*\);', 'inGroups        1(patches);', patch_block)
            print(f"Warning: Patch '{patch_name}' in region '{region_name}' inGroups fixed to '1(patches)'")
    
    elif expected_type == "wall":
        # For wall patches: type should be "wall", inGroups should contain "walls"
        # Check and fix type field (use regex to handle variable spacing)
        if not re.search(r'type\s+wall;', patch_block):
            if re.search(r'type\s+patch;', patch_block):
                patch_block = re.sub(r'type\s+patch;', 'type            wall;', patch_block)
                print(f"Warning: Patch '{patch_name}' in region '{region_name}' had type 'patch'; auto-fixed to 'wall'")
            else:
                sys.exit(f"Error: Patch '{patch_name}' type is not 'patch' or 'wall'. Cannot auto-fix.")
        
        # Check and fix inGroups
        if 'inGroups        1(walls);' not in patch_block:
            # Replace existing inGroups
            patch_block = re.sub(r'inGroups\s+\d+\([^)]*\);', 'inGroups        1(walls);', patch_block)
            print(f"Warning: Patch '{patch_name}' in region '{region_name}' inGroups fixed to '1(walls)'")

    elif expected_type in CONSTRAINT_TYPES:
        # For constraint patches: type must exactly match — these are mesh-topology types set by
        # the mesher and cannot be auto-fixed. Only inGroups is corrected if needed.
        if not re.search(rf'type\s+{re.escape(expected_type)};', patch_block):
            sys.exit(
                f"Error: Patch '{patch_name}' in region '{region_name}' has wrong type in "
                f"polyMesh/boundary. Expected '{expected_type}' (a constraint type set by the mesher). "
                f"Please verify your mesh and ensure the patch type is correct."
            )
        # Fix inGroups if it doesn't already match
        if not re.search(rf'inGroups\s+\d+\({re.escape(expected_type)}\);', patch_block):
            new_block = re.sub(r'inGroups\s+\d+\([^)]*\);',
                               f'inGroups        1({expected_type});', patch_block)
            if new_block != patch_block:
                patch_block = new_block
                print(f"Warning: Patch '{patch_name}' in region '{region_name}' inGroups fixed to '1({expected_type})'")
            else:
                print(f"Warning: Could not locate inGroups entry for patch '{patch_name}' in region "
                      f"'{region_name}'. Please verify the boundary file manually.")

    
    # Replace the patch block in the file
    content = content.replace(original_block, patch_block)
    
    with open(boundary_file, 'w') as f:
        f.write(content)


#==============================================================================
def check_default_bc_conflict(boundary_file, region_name):
    """
    Checks if a patch literally named '__default__' exists in polyMesh/boundary.
    Raises fatal error if conflict found - user must rename the patch.
    
    :param boundary_file: Path to constant/REGION/polyMesh/boundary file
    :param region_name: Region name (for error messages)
    """
    if not os.path.exists(boundary_file):
        return  # No file to check against
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    # Search for '__default__' as a patch name
    if re.search(r'\n\s+__default__\s*\{', content):
        sys.exit(f"Config Error: Patch '__default__' exists in {region_name} polyMesh/boundary.\n"
                f"The '__default__' name is reserved for the default boundary condition in JSON.\n"
                f"Please rename this patch in OpenFOAM to something else (e.g., '__default__wall' or 'catchall_patch')\n"
                f"and update the configuration accordingly.")


#==============================================================================
def get_cht_interfaces(config):
    """
    Extracts CHT interfaces from config.
    Reads definitions from region_parts > cht_interfaces
    Reads thermal_layers overrides from boundary_conditions > cht_interfaces (if present)
    
    :param config: The main configuration dictionary
    :return: Dictionary of cht_interfaces or empty dict if not present
    """
    # Get main CHT interface definitions from region_parts
    region_parts_dict = get_config_value(config, "region_parts", expected_type=dict, required=True)
    cht_interfaces = get_config_value(region_parts_dict, "cht_interfaces", expected_type=dict, required=False)
    
    if not cht_interfaces:
        return {}
    
    # Get thermal_layers overrides from boundary_conditions if present
    boundary_conditions_dict = get_config_value(config, "boundary_conditions", expected_type=dict, required=False)
    if boundary_conditions_dict:
        cht_bc_overrides = get_config_value(boundary_conditions_dict, "cht_interfaces", expected_type=dict, required=False)
        # Merge thermal_layers and emissivity from boundary_conditions into cht_interfaces
        if cht_bc_overrides:
            for interface_name, overrides in cht_bc_overrides.items():
                if interface_name in cht_interfaces:
                    if "thermal_layers" in overrides:
                        cht_interfaces[interface_name]["thermal_layers"] = overrides["thermal_layers"]
                    if "emissivity" in overrides:
                        val = overrides["emissivity"]
                        if isinstance(val, bool) or not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
                            sys.exit(f"Config Error: 'emissivity' for CHT interface '{interface_name}' must be a number in [0, 1].")
                        cht_interfaces[interface_name]["emissivity"] = float(val)
    
    return cht_interfaces


#==============================================================================
def get_patch_nfaces(case_dir, region_name, patch_name):
    """
    Extracts nFaces value from a patch in polyMesh/boundary file.
    
    :param case_dir: Case directory path
    :param region_name: Region name
    :param patch_name: Patch name
    :return: nFaces value (int) or None if not found
    """
    boundary_file = os.path.join(case_dir, f"constant/{region_name}/polyMesh/boundary")
    
    if not os.path.exists(boundary_file):
        return None
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    patch_pattern = rf'(\s{re.escape(patch_name)}\s*\{{[^}}]*\}})'
    match = re.search(patch_pattern, content, re.DOTALL)

    if not match:
        return None

    patch_block = match.group(0)
    nfaces_match = re.search(r'nFaces\s+(\d+);', patch_block)

    if nfaces_match:        return int(nfaces_match.group(1))
    
    return None


#==============================================================================
def validate_and_fix_cht_patch(case_dir, region_name, patch_name, sample_region, sample_patch, conformal):
    """
    Validates and creates/fixes CHT interface patch in polyMesh/boundary.
    Only updates CHT-specific entries; preserves nFaces and startFace from mesh.
    
    :param case_dir: Case directory path
    :param region_name: Region name
    :param patch_name: Patch name in this region
    :param sample_region: The paired region name
    :param sample_patch: The paired patch name
    :param conformal: Boolean indicating if interface is conformal
    """
    boundary_file = os.path.join(case_dir, f"constant/{region_name}/polyMesh/boundary")
    
    if not os.path.exists(boundary_file):
        sys.exit(f"Error: polyMesh boundary file not found at {boundary_file}")
    
    with open(boundary_file, 'r') as f:
        content = f.read()
    
    sample_mode = "nearestPatchFace" if conformal else "nearestPatchFaceAMI"
    
    # Pattern to find existing patch block
    patch_pattern = rf'(\s{re.escape(patch_name)}\s*\{{[^}}]*\}})'
    match = re.search(patch_pattern, content, re.DOTALL)
    
    if match:
        # Patch exists - verify and fix if needed
        patch_block = match.group(0)
        original_block = patch_block
        
        # Extract the patch content (everything between { and })
        inner_match = re.search(rf'{re.escape(patch_name)}\s*\{{(.*?)\}}', patch_block, re.DOTALL)
        if not inner_match:
            return
        
        inner_content = inner_match.group(1)
        
        # Check that nFaces and startFace exist
        nfaces_match = re.search(r'nFaces\s+(\d+);', inner_content)
        startface_match = re.search(r'startFace\s+(\d+);', inner_content)
        
        if not nfaces_match or not startface_match:
            print(f"Error: CHT patch '{patch_name}' in region '{region_name}' is missing nFaces or startFace")
            print(f"  These must be provided by the mesh generation tool.")
            return
        
        # Standard indentation: patches at 4 spaces, content at 8 spaces
        patch_indent = '    '
        entry_indent = '        '
        
        # Extract nFaces and startFace - preserve them exactly
        nfaces = nfaces_match.group(1)
        startface = startface_match.group(1)
        
        # Build the complete patch block with proper formatting
        # Start with newline + indentation to match the format of other patches
        lines = []
        lines.append('')  # Empty line for leading newline
        lines.append(f'{patch_indent}{patch_name}')
        lines.append(f'{patch_indent}{{')
        lines.append(f'{entry_indent}type            mappedWall;')
        lines.append(f'{entry_indent}inGroups        2(wall walls);')
        lines.append(f'{entry_indent}nFaces          {nfaces};')
        lines.append(f'{entry_indent}startFace       {startface};')
        lines.append(f'{entry_indent}sampleMode      {sample_mode};')
        lines.append(f'{entry_indent}sampleRegion    {sample_region};')
        lines.append(f'{entry_indent}samplePatch     {sample_patch};')
        lines.append(f'{patch_indent}}}')
        
        patch_block_new = '\n'.join(lines) + '\n'
        
        # Check for conformal/nFaces mismatch
        nfaces_this = int(nfaces)
        nfaces_paired = get_patch_nfaces(case_dir, sample_region, sample_patch)
        
        if conformal and nfaces_paired and nfaces_this != nfaces_paired:
            print(f"Warning: CHT interface '{patch_name}' in region '{region_name}' is marked as conformal but meshes are non-conformal")
            print(f"  nFaces mismatch: {region_name} has {nfaces_this}, {sample_region} has {nfaces_paired}")
        
        if not conformal and nfaces_paired and nfaces_this == nfaces_paired:
            print(f"Warning: CHT interface '{patch_name}' in region '{region_name}' is marked as non-conformal but meshes appear to be conformal")
            print(f"  matching nFaces: {nfaces_this}")
        
        # Report if changes were made
        if patch_block_new.strip() != original_block.strip():
            content = content.replace(original_block, patch_block_new)
            with open(boundary_file, 'w') as f:
                f.write(content)
            print(f"Updated CHT interface patch '{patch_name}' in region '{region_name}'")
        else:
            print(f"Verified CHT interface patch '{patch_name}' in region '{region_name}'")
    else:
        # Patch doesn't exist - create it
        print(f"Error: Patch '{patch_name}' not found in {boundary_file}")
        print(f"  CHT interface patches must be created by the mesh generation tool.")
        print(f"  Please ensure both '{patch_name}' (in {region_name}) and '{sample_patch}' (in {sample_region}) exist in the mesh.")


#==============================================================================
def process_cht_interfaces(case_dir, cht_interfaces, all_regions):
    """
    Processes all CHT interfaces from config.
    Validates and creates/fixes polyMesh patches for each interface.
    
    :param case_dir: Case directory path
    :param cht_interfaces: Dictionary of CHT interfaces from config
    :param all_regions: List of all region names for validation
    """
    if not cht_interfaces:
        return
    
    for interface_name, interface_config in cht_interfaces.items():
        pair = get_config_value(interface_config, "pair", expected_type=list, required=True)
        conformal = get_config_value(interface_config, "conformal", expected_type=bool, required=True)
        
        if len(pair) != 2:
            sys.exit(f"Config Error: CHT interface '{interface_name}' must have exactly 2 regions in 'pair', got {len(pair)}")
        
        region1_info = pair[0]
        region2_info = pair[1]
        
        region1 = get_config_value(region1_info, "region", expected_type=str, required=True)
        patch1 = get_config_value(region1_info, "boundary", expected_type=str, required=True)
        region2 = get_config_value(region2_info, "region", expected_type=str, required=True)
        patch2 = get_config_value(region2_info, "boundary", expected_type=str, required=True)
        
        # Validate regions exist
        if region1 not in all_regions:
            sys.exit(f"Config Error: CHT interface '{interface_name}': region '{region1}' not found in all_regions")
        if region2 not in all_regions:
            sys.exit(f"Config Error: CHT interface '{interface_name}': region '{region2}' not found in all_regions")
        
        # Process both sides of the interface
        validate_and_fix_cht_patch(case_dir, region1, patch1, region2, patch2, conformal)
        validate_and_fix_cht_patch(case_dir, region2, patch2, region1, patch1, conformal)


#==============================================================================
def get_cht_interface_bcs(cht_interfaces, region_name, fluids, solids):
    """
    Extracts CHT interface BCs for a specific region.
    Returns a dictionary mapping patch names to BC configurations for the region.
    
    :param cht_interfaces: Dictionary of CHT interfaces from config
    :param region_name: The region to get BCs for
    :param fluids: List of fluid region names
    :param solids: List of solid region names
    :return: Dictionary {patch_name: {neighbor_region, thermal_layers (optional), is_first_region}}
    """
    cht_bcs = {}
    
    if not cht_interfaces:
        return cht_bcs
    
    is_fluid = region_name in fluids
    
    for interface_name, interface_config in cht_interfaces.items():
        pair = interface_config.get("pair", [])
        
        if len(pair) != 2:
            continue
        
        region1_info = pair[0]
        region2_info = pair[1]
        
        region1 = region1_info.get("region")
        patch1 = region1_info.get("boundary")
        region2 = region2_info.get("region")
        patch2 = region2_info.get("boundary")
        
        thermal_layers = interface_config.get("thermal_layers")
        emissivity = interface_config.get("emissivity", 0.9)
        
        # Check if this region is in the interface pair
        if region_name == region1:
            neighbor_is_fluid = region2 in fluids
            cht_bcs[patch1] = {
                "neighbor_region": region2,
                "neighbor_is_fluid": neighbor_is_fluid,
                "thermal_layers": thermal_layers,
                "is_first_region": True,
                "emissivity": emissivity,
            }
        elif region_name == region2:
            neighbor_is_fluid = region1 in fluids
            cht_bcs[patch2] = {
                "neighbor_region": region1,
                "neighbor_is_fluid": neighbor_is_fluid,
                "thermal_layers": None,  # thermal_layers only applied to first region
                "is_first_region": False,
                "emissivity": emissivity,
            }
    
    return cht_bcs


#==============================================================================
def get_inlet_temperature(patch_bc):
    """
    Extracts temperature thermal dictionary from inlet BC.
    Handles both constant and time-varying (CSV) specified-temperature type.
    
    :param patch_bc: The patch BC dictionary
    :return: Thermal dict (with 'value' or 'time_varying') or None
    """
    if "thermal" not in patch_bc:
        return None
    
    thermal_dict = patch_bc["thermal"]
    if not isinstance(thermal_dict, dict):
        return None
    
    if thermal_dict.get("mode") == "temperature":
        # Return thermal dict (contains either 'value' or 'time_varying')
        return thermal_dict
    
    return None


#==============================================================================
def validate_turbulence_dict(turb_dict, region_name, patch_name, turb_model, label=""):
    """
    Helper function to validate turbulence dictionary structure.
    Reusable for velocity-inlet and pressure-outlet backflow_conditions.
    
    :param turb_dict: Turbulence dictionary to validate
    :param region_name: Region name (for error messages)
    :param patch_name: Patch name (for error messages)
    :param turb_model: Turbulence model name or None
    :param label: Optional label for error messages (e.g., "backflow_conditions")
    """
    valid_turb_modes = ["dirichlet", "intensity-and-length-scale"]
    
    if not isinstance(turb_dict, dict):
        sys.exit(f"Config Error: turbulence at {region_name}/{patch_name}{label} must be a dictionary.")
    
    if "mode" not in turb_dict:
        sys.exit(f"Config Error: turbulence at {region_name}/{patch_name}{label} missing 'mode' key. "
                f"Must specify one of {valid_turb_modes}. (Are you using the old 'method' key instead of 'mode'?)")
    
    turb_mode = turb_dict.get("mode")
    if turb_mode not in valid_turb_modes:
        sys.exit(f"Config Error: turbulence mode at {region_name}/{patch_name}{label} is '{turb_mode}', "
                f"but must be one of {valid_turb_modes}.")
    
    if turb_mode == "dirichlet":
        if "k" not in turb_dict:
            sys.exit(f"Config Error: dirichlet turbulence at {region_name}/{patch_name}{label} missing 'k' key.")
        if not isinstance(turb_dict["k"], (int, float)):
            sys.exit(f"Config Error: k value must be a number.")
        
        if turb_model in ["kEpsilon", "RNGkEpsilon", "realizableKE"]:
            if "epsilon" not in turb_dict:
                sys.exit(f"Config Error: dirichlet turbulence for {turb_model} model at {region_name}/{patch_name}{label} missing 'epsilon' key.")
            if not isinstance(turb_dict["epsilon"], (int, float)):
                sys.exit(f"Config Error: epsilon value must be a number.")
        elif turb_model in ["kOmega", "kOmegaSST"]:
            if "omega" not in turb_dict:
                sys.exit(f"Config Error: dirichlet turbulence for {turb_model} model at {region_name}/{patch_name}{label} missing 'omega' key.")
            if not isinstance(turb_dict["omega"], (int, float)):
                sys.exit(f"Config Error: omega value must be a number.")
    
    elif turb_mode == "intensity-and-length-scale":
        if "intensity" not in turb_dict:
            sys.exit(f"Config Error: intensity-and-length-scale turbulence at {region_name}/{patch_name}{label} missing 'intensity' key.")
        if not isinstance(turb_dict["intensity"], (int, float)):
            sys.exit(f"Config Error: intensity value must be a number.")
        
        if "length_scale" not in turb_dict:
            sys.exit(f"Config Error: intensity-and-length-scale turbulence at {region_name}/{patch_name}{label} missing 'length_scale' key.")
        if not isinstance(turb_dict["length_scale"], (int, float)):
            sys.exit(f"Config Error: length_scale value must be a number.")

#==============================================================================
def validate_pressure_outlet_bc(patch_bc, region_name, patch_name, turb_model):
    """
    Validates pressure-outlet boundary condition structure.
    
    :param patch_bc: The patch BC dictionary
    :param region_name: Region name
    :param patch_name: Patch name
    :param turb_model: Turbulence model name or None
    """
    # Validate pressure
    if "pressure" not in patch_bc:
        sys.exit(f"Config Error: pressure-outlet at {region_name}/{patch_name} missing 'pressure' key.")
    
    pressure = patch_bc["pressure"]
    if not isinstance(pressure, (int, float)):
        sys.exit(f"Config Error: pressure at {region_name}/{patch_name} must be a number.")
    
    # Validate prevent_backflow (mandatory boolean)
    if "prevent_backflow" not in patch_bc:
        sys.exit(f"Config Error: pressure-outlet at {region_name}/{patch_name} missing 'prevent_backflow' key (must be boolean).")
    
    prevent_backflow = patch_bc["prevent_backflow"]
    if not isinstance(prevent_backflow, bool):
        sys.exit(f"Config Error: prevent_backflow at {region_name}/{patch_name} must be a boolean.")
    
    # Validate backflow_conditions (only required when prevent_backflow is false)
    if not prevent_backflow:
        if "backflow_conditions" not in patch_bc:
            sys.exit(f"Config Error: pressure-outlet at {region_name}/{patch_name} with prevent_backflow=false missing 'backflow_conditions' key.")
        
        backflow_dict = patch_bc["backflow_conditions"]
        if not isinstance(backflow_dict, dict):
            sys.exit(f"Config Error: backflow_conditions at {region_name}/{patch_name} must be a dictionary.")
        
        # Validate thermal and turbulence using common validator
        validate_inlet_common_conditions(backflow_dict, region_name, patch_name, turb_model, label="pressure-outlet > backflow_conditions")

#==============================================================================
def _normalize_thermal_inlet(conditions):
    """
    Normalize thermal inlet BC dict for Jinja2 T template rendering.
    Handles velocity-inlet, total-pressure-inlet, and pressure-outlet backflow.

    :param conditions: patch_bc dict (or backflow_conditions sub-dict)
    :return: Normalized dict with is_time_varying + value or time_varying, or None
    """
    thermal_dict = get_inlet_temperature(conditions)
    if not thermal_dict:
        return None
    if "time_varying" in thermal_dict:
        tv = thermal_dict["time_varying"]
        return {
            "is_time_varying": True,
            "time_varying": {
                "csv_file": tv["csv_file"],
                "ref_column": tv["ref_column"],
                "component_columns": tv["component_columns"],
                "skip_rows": tv.get("skip_rows", 1),
            },
        }
    return {
        "is_time_varying": False,
        "value": thermal_dict["value"],
    }


#==============================================================================
def _normalize_thermal_wall(thermal_dict, rad_is_active=False, region_type="fluid",
                             kappa_type="isotropic"):
    """
    Normalize thermal wall BC dict for Jinja2 T template rendering.
    Handles no-slip-wall (fluid) and solid-wall (solid) thermal modes.

    :param thermal_dict: thermal sub-dict from JSON config
    :param rad_is_active: Whether radiation is globally active
    :param region_type: "fluid" or "solid"
    :param kappa_type: "isotropic" or "anisotropic" (solids only, affects kappaMethod)
    :return: Normalized dict for template, or None if no thermal_dict
    """
    if not thermal_dict:
        return None
    mode = thermal_dict.get("mode")

    # kappaMethod: directionalSolidThermo for anisotropic solids, else fluidThermo/solidThermo
    if region_type == "solid" and kappa_type == "anisotropic":
        kappa_method = "directionalSolidThermo"
    else:
        kappa_method = "fluidThermo" if region_type == "fluid" else "solidThermo"

    qr_value = "qr" if (rad_is_active and region_type == "fluid") else "none"

    result = {
        "mode": mode,
        "kappa_method": kappa_method,
        "qr_value": qr_value,
        "is_anisotropic": (region_type == "solid" and kappa_type == "anisotropic"),
    }

    if mode == "temperature":
        if "time_varying" in thermal_dict:
            tv = thermal_dict["time_varying"]
            result["is_time_varying"] = True
            result["time_varying"] = {
                "csv_file": tv["csv_file"],
                "ref_column": tv["ref_column"],
                "component_columns": tv["component_columns"],
                "skip_rows": tv.get("skip_rows", 1),
            }
        else:
            result["is_time_varying"] = False
            result["value"] = thermal_dict["value"]

    elif mode == "heat-flux":
        result["q"] = thermal_dict["value"]

    elif mode == "heat-transfer-rate":
        result["Q"] = thermal_dict["value"]

    elif mode == "heat-transfer-coefficient":
        result["htc"] = thermal_dict["htc"]
        result["ambient_temperature"] = thermal_dict["ambient_temperature"]
        emissivity = thermal_dict.get("outer_emissivity", 0.0)
        result["emissivity"] = emissivity
        result["has_emissivity"] = emissivity > 0.0
        if "thermal_layers" in thermal_dict:
            layers = thermal_dict["thermal_layers"]
            result["has_thermal_layers"] = True
            result["thermal_layers"] = layers
        else:
            result["has_thermal_layers"] = False

    return result


#==============================================================================
def _normalize_turb_dict(turb_dict):
    """
    Normalize turbulence dict for Jinja2 template use.
    
    :param turb_dict: Raw turbulence dict from JSON config
    :return: Normalized dict with mode and relevant values, or None
    """
    if not turb_dict:
        return None
    mode = turb_dict.get("mode")
    if not mode:
        return None
    result = {"mode": mode}
    if mode == "intensity-and-length-scale":
        result["intensity"] = turb_dict.get("intensity")
        result["length_scale"] = turb_dict.get("length_scale")
    elif mode == "dirichlet":
        result["k"] = turb_dict.get("k")
        result["epsilon"] = turb_dict.get("epsilon")
        result["omega"] = turb_dict.get("omega")
    return result


#==============================================================================
def build_radiation_boundary_list(region_bcs, all_boundaries, cht_boundary_names):
    """
    Builds the list of patch entries for boundaryRadiationProperties.

    Uses actual mesh boundary names (not the normalized/wildcard names from
    prepare_bc_patches) to produce one explicit entry per patch.  CHT boundaries
    and constraint-type patches are excluded; the caller handles CHT entries
    separately from cht_interface_bcs.

    Emissivity rules:
      - no-slip-wall / slip-wall : user-supplied "emissivity" key, default 0.9
      - other non-constraint types (inlets, outlets): 1.0  (black-body approximation)
      - constraint types            : excluded entirely

    :param region_bcs: Raw {patch_name: patch_bc} dict from JSON config.
                       May contain comma-separated grouped keys and a "__default__" key.
    :param all_boundaries: Ordered list of actual mesh boundary names for this region
                           (from region_parts[region]["boundaries"]).  Only include patches
                           that are physics boundaries (walls, inlets, outlets).  Constraint
                           patches (symmetry, cyclic, wedge, …) should either be absent from
                           this list or have their BC type set explicitly in region_bcs so they
                           are filtered via CONSTRAINT_TYPES.  Patches not explicitly configured
                           that fall through to __default__ are assigned __default__'s type;
                           if __default__ is a wall type and the patch is actually a constraint,
                           it will incorrectly appear in the output file.
    :param cht_boundary_names: Set of boundary names that are CHT interface patches
                               (to exclude from this list).
    :return: List of {"name": str, "emissivity": float}.
    """
    # Expand grouped / default keys into a per-patch lookup
    per_patch_bc = {}
    default_bc = None
    for raw_name, patch_bc in (region_bcs or {}).items():
        if raw_name.strip() == "__default__":
            default_bc = patch_bc
        else:
            for pname in raw_name.split(","):
                pname = pname.strip()
                if pname:
                    per_patch_bc[pname] = patch_bc

    result = []
    for boundary in all_boundaries:
        if boundary in cht_boundary_names:
            continue  # CHT entries are handled separately

        bc = per_patch_bc.get(boundary) or default_bc or {}
        bc_type = bc.get("type", "")

        if bc_type in CONSTRAINT_TYPES:
            continue  # constraint patches are omitted from boundaryRadiationProperties

        if bc_type in ("no-slip-wall", "slip-wall"):
            emissivity = float(bc.get("emissivity", 0.9))
        else:
            emissivity = 1.0  # inlets/outlets use black-body assumption

        result.append({"name": boundary, "emissivity": emissivity})

    return result


#==============================================================================
def prepare_bc_patches(region_bcs, cht_interface_bcs, reference_pressure, wall_function, thermal_wall_function,
                       rad_is_active=False, region_type="fluid", is_incompressible=False, rho=None,
                       kappa_type="isotropic"):
    """
    Converts raw region BC dicts and CHT interface info into normalized dicts
    for Jinja2 template rendering (all fields including T).

    :param region_bcs: Dict of {patch_name: patch_bc} from JSON config
    :param cht_interface_bcs: Dict from get_cht_interface_bcs()
    :param reference_pressure: Reference pressure for absolute pressure conversion
    :param wall_function: Wall function type ("Standard" or "Automatic")
    :param thermal_wall_function: Thermal wall function type ("Standard" or "Jayatilleke")
    :param rad_is_active: Whether radiation is globally active (affects T qr field)
    :param region_type: "fluid" or "solid" (affects kappa_method and qr for T)
    :param is_incompressible: True for simpleFoam/pimpleFoam — pressure stored as kinematic (Pa/rho)
    :param rho: Fluid density [kg/m³] — required when is_incompressible=True
    :param kappa_type: "isotropic" or "anisotropic" (solids only, affects kappaMethod and alphaAni)
    :return: (patches, cht_patches) tuple of normalized dicts
    """
    # Pre-compute wall function type strings
    nut_wf = "nutUSpaldingWallFunction" if wall_function == "Automatic" else "nutkWallFunction"
    if thermal_wall_function == "Jayatilleke":
        alphat_wf = "compressible::alphatJayatillekeWallFunction"
    else:
        alphat_wf = "compressible::alphatWallFunction"
    omega_blended = "true" if wall_function == "Automatic" else "false"

    patches = []
    for raw_name, patch_bc in (region_bcs or {}).items():
        name = normalize_patch_name(raw_name)
        bc_type = patch_bc.get("type")

        patch = {"name": name, "bc_type": bc_type, "is_wall": bc_type in ("no-slip-wall", "solid-wall")}

        if bc_type == "velocity-inlet":
            vel_dict = patch_bc["velocity"]
            mode = vel_dict.get("mode")
            vel_out = {"mode": mode, "is_time_varying": "time_varying" in vel_dict}
            if vel_out["is_time_varying"]:
                tv = vel_dict["time_varying"]
                vel_out["time_varying"] = {
                    "csv_file": tv["csv_file"],
                    "ref_column": tv["ref_column"],
                    "component_columns": tv["component_columns"],
                    "skip_rows": tv.get("skip_rows", 1),
                }
            else:
                value = vel_dict["value"]
                if mode == "components":
                    vel_out["of_value"] = to_openfoam_vector(value)
                elif mode == "normal-magnitude":
                    vel_out["ref_value"] = -1.0 * value
            patch["velocity"] = vel_out
            if "turbulence" in patch_bc:
                patch["turbulence"] = _normalize_turb_dict(patch_bc["turbulence"])
            patch["thermal"] = _normalize_thermal_inlet(patch_bc)

        elif bc_type == "pressure-outlet":
            patch["prevent_backflow"] = patch_bc.get("prevent_backflow", False)
            gauge = patch_bc["pressure"]
            if is_incompressible:
                patch["abs_pressure"] = gauge / rho
            else:
                patch["abs_pressure"] = gauge + reference_pressure
            if not patch["prevent_backflow"] and "backflow_conditions" in patch_bc:
                bf = patch_bc["backflow_conditions"]
                patch["backflow_turbulence"] = _normalize_turb_dict(bf.get("turbulence")) if "turbulence" in bf else None
                patch["backflow_thermal"] = _normalize_thermal_inlet(bf)
            else:
                patch["backflow_thermal"] = None

        elif bc_type == "total-pressure-inlet":
            patch["prevent_backflow"] = False
            gauge = patch_bc["total_pressure"]
            if is_incompressible:
                patch["abs_pressure"] = gauge / rho
            else:
                patch["abs_pressure"] = gauge + reference_pressure
            if "turbulence" in patch_bc:
                patch["backflow_turbulence"] = _normalize_turb_dict(patch_bc["turbulence"])
            patch["thermal"] = _normalize_thermal_inlet(patch_bc)

        elif bc_type in ("no-slip-wall", "solid-wall"):
            thermal_dict = patch_bc.get("thermal")
            patch["thermal"] = _normalize_thermal_wall(thermal_dict, rad_is_active, region_type, kappa_type)

        # slip-wall needs no extra patch data — all fields use 'slip' or 'calculated' in templates

        # Wall function types for wall patches
        if patch["is_wall"]:
            patch["nut_wf"] = nut_wf
            patch["alphat_wf"] = alphat_wf
            patch["omega_blended"] = omega_blended

        patches.append(patch)

    # CHT patches — walls for non-T fields; turbulentTemperatureRadCoupledMixed for T
    if region_type == "solid" and kappa_type == "anisotropic":
        kappa_method = "directionalSolidThermo"
    else:
        kappa_method = "fluidThermo" if region_type == "fluid" else "solidThermo"
    qr_value = "qr" if (rad_is_active and region_type == "fluid") else "none"
    is_anisotropic = (region_type == "solid" and kappa_type == "anisotropic")

    cht_patches = []
    for patch_name, cht_info in (cht_interface_bcs or {}).items():
        neighbor_is_fluid = cht_info["neighbor_is_fluid"]
        qr_nbr = "qr" if (rad_is_active and neighbor_is_fluid) else "none"
        thermal_layers = cht_info.get("thermal_layers")
        cht_patches.append({
            "name": patch_name,
            "neighbor_region": cht_info["neighbor_region"],
            "neighbor_is_fluid": neighbor_is_fluid,
            "is_first_region": cht_info["is_first_region"],
            "thermal_layers": thermal_layers,
            "has_thermal_layers": bool(thermal_layers),
            "kappa_method": kappa_method,
            "is_anisotropic": is_anisotropic,
            "qr_value": qr_value,
            "qr_nbr": qr_nbr,
            "nut_wf": nut_wf,
            "alphat_wf": alphat_wf,
            "omega_blended": omega_blended,
        })

    # Ensure '.*' (default wildcard) is always last in boundaryField — OpenFOAM convention
    patches.sort(key=lambda p: p["name"] == '".*"')

    return patches, cht_patches

#==============================================================================
def validate_faceZone_conditions(config, region_parts, all_regions):
    """
    Validates faceZone_conditions configuration.
    
    :param config: Main configuration dictionary
    :param region_parts: Dictionary of region parts (boundaries, cellZones, faceZones)
    :param all_regions: List of all region names
    :return: Dictionary with validated faceZone_conditions, or empty dict if not present
    """
    # faceZone_conditions is optional
    if "faceZone_conditions" not in config:
        return {}
    
    fz_conditions = get_config_value(config, "faceZone_conditions", expected_type=dict, required=False)
    if not fz_conditions:
        return {}
    
    validated_conditions = {}
    
    for region in all_regions:
        if region not in fz_conditions:
            continue
        
        region_fz_dict = get_config_value(fz_conditions, region, expected_type=dict, required=False)
        if not region_fz_dict:
            continue
        
        # Get faceZones for this region
        region_fz_list = region_parts[region]["faceZones"]
        
        validated_conditions[region] = {}
        
        for faceZone_name, fz_config in region_fz_dict.items():
            # Validate that faceZone exists in region_parts
            if faceZone_name not in region_fz_list:
                sys.exit(f"Config Error: faceZone '{faceZone_name}' in faceZone_conditions for "
                        f"region '{region}' is not defined in region_parts.")
            
            if not isinstance(fz_config, dict):
                sys.exit(f"Config Error: faceZone_conditions[{region}][{faceZone_name}] must be a dictionary.")
            
            # Extract and validate type
            fz_type = get_config_value(fz_config, "type", expected_type=str, required=True)
            
            if fz_type == "fan":
                # Validate fan-specific fields
                patch_name = get_config_value(fz_config, "patch_name", expected_type=str, required=True)
                fan_curve = get_config_value(fz_config, "fan_curve", expected_type=dict, required=True)
                
                # Validate fan_curve CSV structure
                validate_fan_curve_dict(fan_curve, faceZone_name, region)
                
                validated_conditions[region][faceZone_name] = {
                    "type": fz_type,
                    "patch_name": patch_name,
                    "fan_curve": fan_curve
                }
            else:
                sys.exit(f"Config Error: Unknown faceZone_conditions type '{fz_type}' "
                        f"for faceZone '{faceZone_name}' in region '{region}'.")
    
    return validated_conditions

#==============================================================================
def prepare_fan_baffle_context(faceZone_name, patch_name, fan_curve_dict, reference_pressure):
    """
    Builds a context dictionary for a fan-type baffle, ready for the
    createBafflesDict Jinja2 template.

    :param faceZone_name: Name of the faceZone
    :param patch_name: Name of the patch to create
    :param fan_curve_dict: Dictionary with csv_file, ref_column, component_columns, skip_rows
    :param reference_pressure: Reference pressure (for 'value' field)
    :return: Dict consumed by the render_fan_baffle macro in createBafflesDict.template
    """
    component_columns = fan_curve_dict["component_columns"]
    return {
        "type": "fan",
        "faceZone_name": faceZone_name,
        "patch_name": patch_name,
        "csv_file": fan_curve_dict["csv_file"],
        "ref_column": fan_curve_dict["ref_column"],
        "component_columns": " ".join(str(c) for c in component_columns),
        "skip_rows": fan_curve_dict.get("skip_rows", 1),
        "reference_pressure": reference_pressure,
    }


def validate_function_objects(config, all_regions, solid_regions=None,
                              incompressible_regions=None):
    """
    Validate function_objects section in configuration.

    :param config: Complete configuration dictionary
    :param all_regions: List of all region names (fluid + solid)
    :param solid_regions: List of solid region names; used to apply solid-specific restrictions
    :param incompressible_regions: List of incompressible fluid region names; temperature-based
                                   FOs are blocked there (no energy equation is solved)
    :return: Dictionary with validated function_objects, or None if not present
    :raises: sys.exit() on validation failure
    """
    function_objects_dict = get_config_value(config, "function_objects", expected_type=dict, required=False)

    if not function_objects_dict:
        return None

    solid_regions          = solid_regions          or []
    incompressible_regions = incompressible_regions or []

    # Types that require density/flux/velocity fields unavailable in solid regions
    _solid_forbidden_types = {"mass_average", "mass_integral", "mass_flow_rate", "volume_flow_rate"}

    # Fields that require the energy equation (not present for incompressible solvers)
    _thermal_fields = {"temperature", "wallHeatFlux"}

    # Validate each region
    for region_name, fo_list in function_objects_dict.items():
        if region_name not in all_regions:
            sys.exit(f"Config Error: Region '{region_name}' in function_objects does not exist.\n"
                    f"  -> Valid regions: {all_regions}")

        if not isinstance(fo_list, list):
            sys.exit(f"Config Error: function_objects['{region_name}'] must be a list.\n"
                    f"  -> Found: {type(fo_list)}")

        is_solid          = region_name in solid_regions
        is_incompressible = region_name in incompressible_regions

        # Validate each function object in the region
        for idx, fo_item in enumerate(fo_list):
            if not isinstance(fo_item, dict):
                sys.exit(f"Config Error: function_objects['{region_name}'][{idx}] must be a dictionary.\n"
                        f"  -> Found: {type(fo_item)}")

            # Check required fields
            fo_type = get_config_value(fo_item, "type", expected_type=str, required=True)
            valid_types = ["volume_average", "volume_integral", "mass_average", "mass_integral",
                          "volume_min", "volume_max", "volume_sum", "area_average", "area_integral",
                          "surface_min", "surface_max", "surface_sum", "cellZone_average",
                          "mass_flow_rate", "volume_flow_rate"]

            # Solid regions: mass-based and flux-based types are not applicable
            if is_solid and fo_type in _solid_forbidden_types:
                solid_valid = [t for t in valid_types if t not in _solid_forbidden_types]
                sys.exit(f"Config Error: Function object type '{fo_type}' is not allowed for solid region "
                         f"'{region_name}'[{idx}].\n"
                         f"  -> Solid regions have no density/flux fields (rho, phi).\n"
                         f"  -> Valid options for solid regions: {', '.join(solid_valid)}")

            if fo_type not in valid_types:
                sys.exit(f"Config Error: Invalid function object type in '{region_name}'[{idx}].\n"
                        f"  -> Found: '{fo_type}'\n"
                        f"  -> Valid options: {', '.join(valid_types)}")

            # mass_flow_rate uses phi; volume_flow_rate uses U — field key is not required for either
            if fo_type in ("mass_flow_rate", "volume_flow_rate"):
                field_name = "phi" if fo_type == "mass_flow_rate" else "U"
            else:
                field_name = get_config_value(fo_item, "field", expected_type=str, required=True)
                if not field_name.strip():
                    sys.exit(f"Config Error: Field name cannot be empty in '{region_name}'[{idx}]")
                # Solid regions only carry T and wallHeatFlux (post-processed by wallHeatFlux FO)
                _solid_valid_fields = {"temperature", "wallHeatFlux"}
                if is_solid and field_name not in _solid_valid_fields:
                    sys.exit(f"Config Error: Invalid field '{field_name}' for solid region '{region_name}'[{idx}].\n"
                             f"  -> Valid fields for solid regions: {', '.join(sorted(_solid_valid_fields))}")
                # Incompressible regions have no energy equation — temperature and wallHeatFlux don't exist
                if is_incompressible and field_name in _thermal_fields:
                    sys.exit(f"Config Error: Field '{field_name}' is not available for incompressible region "
                             f"'{region_name}'[{idx}].\n"
                             f"  -> simpleFoam / pimpleFoam do not solve an energy equation.\n"
                             f"  -> Remove temperature-based function objects for this region.")

            # cellZone_average requires a mandatory "cellZones" list; singular "cellZone" is not allowed
            if fo_type == "cellZone_average":
                if "cellZone" in fo_item:
                    sys.exit(f"Config Error: 'cellZone_average' in '{region_name}'[{idx}] uses 'cellZones' (list), "
                             f"not 'cellZone' (string).\n"
                             f"  -> Replace '\"cellZone\": \"...\"' with '\"cellZones\": [\"...\"]'")
                cell_zones = get_config_value(fo_item, "cellZones", expected_type=list, required=True)
                if not cell_zones:
                    sys.exit(f"Config Error: 'cellZones' cannot be empty in '{region_name}'[{idx}]")
                for z_idx, z in enumerate(cell_zones):
                    if not isinstance(z, str) or not z.strip():
                        sys.exit(f"Config Error: Each entry in 'cellZones' must be a non-empty string "
                                 f"in '{region_name}'[{idx}][{z_idx}]")
            else:
                # Check optional cellZone (for other volume operations)
                cell_zone = get_config_value(fo_item, "cellZone", expected_type=str, required=False)
                if cell_zone is not None and not cell_zone.strip():
                    sys.exit(f"Config Error: cellZone cannot be empty in '{region_name}'[{idx}]")

            # Check patch/faceZone/cuttingPlane for area, surface, mass_flow_rate, and volume_flow_rate operations
            if fo_type in ["area_average", "area_integral", "surface_min", "surface_max", "surface_sum",
                           "mass_flow_rate", "volume_flow_rate"]:
                patch         = get_config_value(fo_item, "patch",         expected_type=str,  required=False)
                face_zone     = get_config_value(fo_item, "faceZone",      expected_type=str,  required=False)
                cutting_plane = get_config_value(fo_item, "cuttingPlane",  expected_type=dict, required=False)

                scope_count = sum(x is not None for x in [patch, face_zone, cutting_plane])
                if scope_count == 0:
                    sys.exit(f"Config Error: Surface operation in '{region_name}'[{idx}] requires exactly one of "
                             f"'patch', 'faceZone', or 'cuttingPlane'.\n"
                             f"  -> Found: none specified")
                if scope_count > 1:
                    sys.exit(f"Config Error: Surface operation in '{region_name}'[{idx}] must specify exactly one of "
                             f"'patch', 'faceZone', or 'cuttingPlane'.\n"
                             f"  -> Found: multiple specified simultaneously")

                if patch is not None and not patch.strip():
                    sys.exit(f"Config Error: patch cannot be empty in '{region_name}'[{idx}]")

                if face_zone is not None and not face_zone.strip():
                    sys.exit(f"Config Error: faceZone cannot be empty in '{region_name}'[{idx}]")

                if cutting_plane is not None:
                    cp_name = get_config_value(cutting_plane, "name", expected_type=str, required=True)
                    if not cp_name.strip():
                        sys.exit(f"Config Error: cuttingPlane.name cannot be empty in '{region_name}'[{idx}]")

                    cp_point = get_config_value(cutting_plane, "point", expected_type=list, required=True)
                    if len(cp_point) != 3 or not all(isinstance(v, (int, float)) for v in cp_point):
                        sys.exit(f"Config Error: cuttingPlane.point must be a list of 3 numbers "
                                 f"in '{region_name}'[{idx}].\n"
                                 f"  -> Found: {cp_point}")

                    cp_normal = get_config_value(cutting_plane, "normal", expected_type=list, required=True)
                    if len(cp_normal) != 3 or not all(isinstance(v, (int, float)) for v in cp_normal):
                        sys.exit(f"Config Error: cuttingPlane.normal must be a list of 3 numbers "
                                 f"in '{region_name}'[{idx}].\n"
                                 f"  -> Found: {cp_normal}")
                    if all(v == 0 for v in cp_normal):
                        sys.exit(f"Config Error: cuttingPlane.normal cannot be a zero vector "
                                 f"in '{region_name}'[{idx}]")

    return function_objects_dict


def prepare_function_objects_context(function_objects_dict, all_regions,
                                     density_by_region=None):
    """
    Prepare user-defined function objects as a list of context dicts for Jinja2 rendering.

    The automatic yPlus and wallHeatFlux entries are handled directly in the
    functionObjects.template via {% for %} loops over fluid_regions / all_regions.
    This function only processes user-defined entries from the config.

    For incompressible regions (simpleFoam/pimpleFoam), phi carries volume flux (m³/s)
    and p is kinematic pressure (m²/s²).  A scaleFactor = rho is automatically injected
    for mass_flow_rate FOs (phi → kg/s) and pressure-field FOs (p → Pa).

    :param function_objects_dict: Dict of region -> list of FO configs (from validate_function_objects)
    :param all_regions: List of all region names (preserves ordering)
    :param density_by_region: Optional dict mapping region name → density (kg/m³) for
                              incompressible regions.  When provided, scaleFactor is
                              auto-injected for phi and p operations.
    :return: Tuple of (list of dicts ready for template context,
                       ordered list of unique foam field names that appear in cellZone_average entries)
    :raises: sys.exit() on unknown type
    """
    if not function_objects_dict:
        return [], []

    type_mapper = {
        "volume_average":   ("volFieldValue",     "volAverage",            "volAvg"),
        "volume_integral":  ("volFieldValue",     "volIntegrate",          "volInt"),
        "mass_average":     ("volFieldValue",     "weightedVolAverage",    "massAvg"),
        "mass_integral":    ("volFieldValue",     "weightedVolIntegrate",  "massInt"),
        "volume_min":       ("volFieldValue",     "min",                   "min"),
        "volume_max":       ("volFieldValue",     "max",                   "max"),
        "volume_sum":       ("volFieldValue",     "sum",                   "sum"),
        "area_average":     ("surfaceFieldValue", "areaAverage",           "areaAvg"),
        "area_integral":    ("surfaceFieldValue", "areaIntegrate",         "areaInt"),
        "surface_min":      ("surfaceFieldValue", "min",                   "min"),
        "surface_max":      ("surfaceFieldValue", "max",                   "max"),
        "surface_sum":      ("surfaceFieldValue", "sum",                   "sum"),
        "cellZone_average": ("volFieldValue",     "volAverage",            "czAvg"),
        "mass_flow_rate":   ("surfaceFieldValue", "sum",                   "massFlowRate"),
        "volume_flow_rate": ("surfaceFieldValue", "areaNormalIntegrate",   "volFlowRate"),
    }

    field_mapper = {
        "temperature": "T",
        "velocity":    "U",
        "pressure":    "p",
        "density":     "rho",
    }

    density_by_region = density_by_region or {}

    result = []
    # Tracks unique foam fields used in cellZone_average entries (insertion-ordered)
    cellzone_avg_fields_seen = {}

    for region_name in all_regions:
        if region_name not in function_objects_dict:
            continue

        # Density used for incompressible scaleFactor injection (None for compressible regions)
        rho = density_by_region.get(region_name)

        for fo_item in function_objects_dict[region_name]:
            fo_type       = fo_item.get("type")
            field_name    = fo_item.get("field")
            cell_zone     = fo_item.get("cellZone")
            patch         = fo_item.get("patch")
            face_zone     = fo_item.get("faceZone")
            cutting_plane = fo_item.get("cuttingPlane")

            if fo_type not in type_mapper:
                sys.exit(f"Error: Unknown function object type '{fo_type}'")

            fo_class, operation, op_short = type_mapper[fo_type]

            # mass_flow_rate uses phi; volume_flow_rate uses U — both omit field suffix from FO name
            if fo_type == "mass_flow_rate":
                foam_field = "phi"
            elif fo_type == "volume_flow_rate":
                foam_field = "U"
            else:
                foam_field = field_mapper.get(field_name, field_name)

            # cellZone_average: expand each zone in "cellZones" into a separate entry
            if fo_type == "cellZone_average":
                cell_zones = fo_item.get("cellZones", [])
                cellzone_avg_fields_seen[foam_field] = True
                for zone in cell_zones:
                    zone_clean = zone.replace(" ", "_").replace("-", "_")
                    fo_name = f"{op_short}-{region_name}-{zone_clean}-{foam_field}"
                    result.append({
                        "name":               fo_name,
                        "fo_class":           fo_class,
                        "operation":          operation,
                        "foam_field":         foam_field,
                        "region":             region_name,
                        "cell_zone":          zone,
                        "weight_field":       None,
                        "boundary_type":      None,
                        "boundary_name":      None,
                        "is_cellzone_average": True,
                        "is_cutting_plane":   False,
                        "cutting_plane_name": None,
                        "cutting_plane_point": None,
                        "cutting_plane_normal": None,
                        "scale_factor":       None,
                    })
                continue

            is_boundary      = fo_class == "surfaceFieldValue"
            is_cutting_plane = cutting_plane is not None and is_boundary
            if is_cutting_plane:
                boundary_name = cutting_plane.get("name", "")
                boundary_type = "sampledSurface"
            else:
                boundary_name = patch if patch else face_zone
                boundary_type = "patch" if patch else "faceZone"

            # Build a unique descriptive name; mass_flow_rate and volume_flow_rate omit the field suffix;
            # cuttingPlane uses the plane name as the scope label instead of a patch/faceZone name
            if fo_type in ("mass_flow_rate", "volume_flow_rate") or is_cutting_plane:
                boundary_clean = boundary_name.replace(" ", "_").replace("-", "_")
                fo_name = f"{op_short}-{region_name}-{boundary_clean}"
            elif is_boundary:
                boundary_clean = boundary_name.replace(" ", "_").replace("-", "_")
                fo_name = f"{op_short}-{region_name}-{boundary_clean}-{foam_field}"
            elif cell_zone:
                zone_clean = cell_zone.replace(" ", "_").replace("-", "_")
                fo_name = f"{op_short}-{region_name}-{zone_clean}-{foam_field}"
            else:
                fo_name = f"{op_short}-{region_name}-{foam_field}"

            # Auto-inject scaleFactor = rho for incompressible regions:
            #   - mass_flow_rate (phi, volume flux m³/s) → kg/s requires * rho
            #   - pressure-field surface operations (kinematic p, m²/s²) → Pa requires * rho
            scale_factor = None
            if rho is not None:
                if fo_type == "mass_flow_rate":
                    scale_factor = rho
                elif foam_field == "p" and is_boundary:
                    scale_factor = rho

            result.append({
                "name":                 fo_name,
                "fo_class":             fo_class,
                "operation":            operation,
                "foam_field":           foam_field,
                "region":               region_name,
                "cell_zone":            cell_zone,
                "weight_field":         "rho" if operation in ("weightedVolAverage", "weightedVolIntegrate") else None,
                "boundary_type":        boundary_type,
                "boundary_name":        boundary_name,
                "is_cellzone_average":  False,
                "is_cutting_plane":     is_cutting_plane,
                "cutting_plane_name":   cutting_plane.get("name", "") if is_cutting_plane else None,
                "cutting_plane_point":  to_openfoam_vector(cutting_plane["point"]) if is_cutting_plane else None,
                "cutting_plane_normal": to_openfoam_vector(cutting_plane["normal"]) if is_cutting_plane else None,
                "scale_factor":         scale_factor,
            })

    return result, list(cellzone_avg_fields_seen.keys())

def validate_fvOptions(fvoptions_config, all_regions, cell_zones_by_region):
    """Validate fvOptions configuration structure and semantics.
    
    Args:
        fvoptions_config: Dictionary with region names as keys, arrays of fvOptions as values
        all_regions: List of valid region names
        cell_zones_by_region: Dict mapping region names to lists of cell zone names
    
    Validates:
        - Region names exist
        - Type is "heat-source"
        - Mode is "absolute" or "specific"
        - If cellZone specified, it must exist in the region
    """
    if not fvoptions_config:
        return
    
    if not isinstance(fvoptions_config, dict):
        sys.exit("Error: fv_options must be a dictionary with region names as keys")
    
    for region_name, options_list in fvoptions_config.items():
        # Validate region exists
        if region_name not in all_regions:
            sys.exit(f"Error: fv_options region '{region_name}' not found in defined regions")
        
        # Validate options_list is an array
        if not isinstance(options_list, list):
            sys.exit(f"Error: fv_options['{region_name}'] must be an array")
        
        for idx, option in enumerate(options_list):
            if not isinstance(option, dict):
                sys.exit(f"Error: fv_options['{region_name}'][{idx}] must be a dictionary")
            
            # Validate type
            option_type = get_config_value(option, "type", expected_type=str, 
                                          valid_options=["heat-source"])
            
            # Validate mode
            mode = get_config_value(option, "mode", expected_type=str,
                                   valid_options=["absolute", "specific"])
            
            # Validate value
            value = get_config_value(option, "value", expected_type=(int, float))
            
            # Validate cellZone if present
            if "cellZone" in option:
                cell_zone = option["cellZone"]
                if not isinstance(cell_zone, str):
                    sys.exit(f"Error: fv_options['{region_name}'][{idx}].cellZone must be a string")
                
                # Check cellZone exists in region
                if region_name in cell_zones_by_region:
                    if cell_zone not in cell_zones_by_region[region_name]:
                        sys.exit(f"Error: cellZone '{cell_zone}' not found in region '{region_name}'")
