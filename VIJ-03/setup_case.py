#!/usr/bin/env python3

import sys as sys
import path_config
import os as os
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from common.utils import (
    execute_command,
    get_boolean_input,
    load_config_file,
    get_config_value,
    resolve_config_aliases,
    get_region_config,
    get_vector_input,
    get_pressure_variable_name,
    parse_matrix_solvers,
    get_residual_entries,
    to_openfoam_vector,
    to_openfoam_list,
    check_and_reset_directory,
    init_constant_directory,
    validate_solver_name,
    is_incompressible_solver,
    get_turbulence_content,
    get_radiation_content,
    validate_fluid_material_properties,
    validate_incompressible_material_properties,
    build_thermophysical_properties,
    build_transport_properties,
    get_region_parts,
    get_cht_interfaces,
    process_cht_interfaces,
    get_cht_interface_bcs,
    validate_solid_material_properties,
    build_solid_thermophysical_properties,
    get_fluid_field_files,
    get_solid_field_files,
    validate_initial_conditions,
    get_initial_field_value,
    validate_boundary_conditions,
    validate_and_fix_polymesh_patch,
    check_default_bc_conflict,
    validate_faceZone_conditions,
    prepare_fan_baffle_context,
    validate_function_objects,
    prepare_function_objects_context,
    validate_fvOptions,
    prepare_bc_patches,
    build_radiation_boundary_list,
    load_materials_library,
    resolve_material_reference,
    CONSTRAINT_TYPES,
)

# root directory for the case setup
case_dir = os.getcwd()

OPENFOAM_VERSION = "v2512"

# Jinja2 template environment — templates/ lives alongside this script
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(_SCRIPT_DIR, "templates")),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

def _render_template(template_name, **context):
    try:
        return _jinja_env.get_template(template_name).render(**context)
    except TemplateNotFound:
        sys.exit(f"Template not found: {template_name}")



def main():
    config = load_config_file("sim_inputs.json")

    # Resolve aliases early, after loading but before using config values
    sim_dict = get_config_value(config, "simulation", expected_type=dict, required=True)
    reference_conditions_dict = get_config_value(config, "reference_conditions", expected_type=dict, required=True)
    config = resolve_config_aliases(config, reference_conditions_dict)

    sim_dict = get_config_value(config, "simulation", expected_type=dict, required=True)
    sim_type = get_config_value(sim_dict, "type", expected_type=str, valid_options=["steady-state", "transient"], required=True)

    fluids, solids = get_region_config(config)

    all_regions = fluids + solids
    is_multi_region = (len(fluids) + len(solids) > 1)
    is_single_region = not is_multi_region

    # Read solver_name from config and validate
    solver_name = get_config_value(sim_dict, "solver_name", expected_type=str, required=True)
    validate_solver_name(solver_name, sim_type, fluids, solids)
    is_incompressible = is_incompressible_solver(solver_name)

    #=============================================================================#
    # Pre-run workspace scan
    #=============================================================================#
    def _pre_run_scan(all_regions, is_single_region):
        """
        Scans the workspace for files and directories that will be removed or
        overwritten during case setup. Prints a grouped summary. Returns True if
        anything was found, False if the workspace is clean.
        """
        found = []

        # 0/ directory
        if os.path.exists("0"):
            found.append("  0/          → directory will be fully removed and recreated")

        # system/ directory
        if os.path.exists("system"):
            found.append("  system/     → directory will be fully removed and recreated")

        # Files (not dirs) in constant/
        if os.path.isdir("constant"):
            const_files = sorted(
                f for f in os.listdir("constant")
                if os.path.isfile(os.path.join("constant", f))
            )
            for f in const_files:
                found.append(f"  constant/{f}  → will be overwritten")

        # For multi-region: files (not dirs) in constant/{region}/
        if not is_single_region:
            for region in all_regions:
                region_path = os.path.join("constant", region)
                if os.path.isdir(region_path):
                    region_files = sorted(
                        f for f in os.listdir(region_path)
                        if os.path.isfile(os.path.join(region_path, f))
                    )
                    for f in region_files:
                        found.append(f"  constant/{region}/{f}  → will be overwritten")

        print("\n=== Pre-run Workspace Scan ===")
        if found:
            for line in found:
                print(line)
        else:
            print("  Clean workspace — nothing to remove.")
        print()
        return bool(found)

    _workspace_dirty = _pre_run_scan(all_regions, is_single_region)
    if _workspace_dirty:
        if not get_boolean_input("Proceed with case setup?"):
            sys.exit("Setup aborted by user.")
        print()

    #=============================================================================#
    # constant directory setup
    #=============================================================================#
    init_constant_directory(solids, fluids, is_single_region=is_single_region)

    # Configuring constant/g file (skipped for incompressible solvers)
    gravity = None
    if not is_incompressible:
        gravity = get_vector_input(config, "gravity")

    # Reading reference conditions - available to entire script
    reference_conditions_dict = get_config_value(config, "reference_conditions", expected_type=dict, required=True)
    reference_pressure = get_config_value(reference_conditions_dict, "pressure", expected_type=float, required=True)
    reference_temperature = get_config_value(reference_conditions_dict, "temperature", expected_type=float, required=True)

    # Reading region parts (boundaries, cellZones, faceZones) - available to entire script
    region_parts = get_region_parts(config, all_regions)

    # Reading and validating faceZone_conditions (optional)
    faceZone_conditions = validate_faceZone_conditions(config, region_parts, all_regions)

    # Reading CHT interfaces if present
    cht_interfaces = get_cht_interfaces(config)

    # Reading and validating material properties for fluid regions - available to entire script
    material_properties_dict = get_config_value(config, "material_properties", expected_type=dict, required=True)

    # Load materials library (built-in + auto-detected custom_materials_library.json)
    _materials_library = load_materials_library()

    # Resolve all material references → fully-expanded property dicts
    density_by_region = {}   # populated for incompressible regions; empty for compressible
    if fluids:
        for region in fluids:
            region_cfg = get_config_value(material_properties_dict, region, required=True)
            if is_incompressible:
                # For incompressible, resolve library reference if needed, then validate rho+mu only
                if isinstance(region_cfg, str):
                    material_properties_dict[region] = resolve_material_reference(region_cfg, region, "fluid", _materials_library)
                else:
                    material_properties_dict[region] = region_cfg
                validate_incompressible_material_properties(material_properties_dict[region], region)
            else:
                material_properties_dict[region] = resolve_material_reference(region_cfg, region, "fluid", _materials_library)
                validate_fluid_material_properties(material_properties_dict[region], region, reference_pressure)

    # Reading and validating solid material properties
    if solids:
        for region in solids:
            region_cfg = get_config_value(material_properties_dict, region, required=True)
            material_properties_dict[region] = resolve_material_reference(region_cfg, region, "solid", _materials_library)
            validate_solid_material_properties(material_properties_dict[region], region)

    print("\n=== constant/ ===")
    if not is_incompressible:
        with open("constant/g", "w") as f:
            f.write(_render_template("constant/shared/g.template",
                                      gravity=to_openfoam_vector(gravity),
                                      openfoam_version=OPENFOAM_VERSION))
        print("  Written: constant/g")

    # Configuring constant/regionProperties file (multi-region only)
    if is_multi_region:
        with open("constant/regionProperties", "w") as f:
            f.write(_render_template(
                "constant/shared/regionProperties.template",
                solids_list=to_openfoam_list(solids),
                fluids_list=to_openfoam_list(fluids),
                openfoam_version=OPENFOAM_VERSION,
            ))
        print("  Written: constant/regionProperties")

    # Helper: resolve the constant/ or system/ subdir path for a region
    def _const_dir(region):
        return "constant" if is_single_region else os.path.join("constant", region)

    def _sys_dir(region):
        return "system" if is_single_region else os.path.join("system", region)

    # Configuring turbulenceProperties
    is_turb_active, turb_model = False, None
    if fluids:
        is_turb_active, turb_model, turb_template, turb_context = get_turbulence_content(config)
        for region in fluids:
            curr_file_path = os.path.join(_const_dir(region), "turbulenceProperties")
            location = "constant" if is_single_region else f"constant/{region}"
            with open(curr_file_path, "w") as f:
                f.write(_render_template(
                    turb_template,
                    location=location,
                    openfoam_version=OPENFOAM_VERSION,
                    **turb_context,
                ))
            print(f"  Written: {curr_file_path}")

    # Configuring radiationProperties (skipped for incompressible solvers)
    if fluids and not is_incompressible:
        is_rad_active, rad_model, rad_template, rad_context = get_radiation_content(config)
        for region in fluids:
            curr_file_path = os.path.join(_const_dir(region), "radiationProperties")
            location = "constant" if is_single_region else f"constant/{region}"
            with open(curr_file_path, "w") as f:
                f.write(_render_template(
                    rad_template,
                    location=location,
                    openfoam_version=OPENFOAM_VERSION,
                    **rad_context,
                ))
            print(f"  Written: {curr_file_path}")

    # Configuring thermophysicalProperties for fluid regions (compressible)
    # or transportProperties (incompressible)
    if fluids:
        if is_incompressible:
            for region in fluids:
                region_props = get_config_value(material_properties_dict, region, expected_type=dict, required=True)
                transport_template, transport_context = build_transport_properties(region_props, region)
                curr_file_path = os.path.join(_const_dir(region), "transportProperties")
                location = "constant" if is_single_region else f"constant/{region}"
                with open(curr_file_path, "w") as f:
                    f.write(_render_template(
                        transport_template,
                        location=location,
                        openfoam_version=OPENFOAM_VERSION,
                        **transport_context,
                    ))
                print(f"  Written: {curr_file_path}")
                # Capture density for scaleFactor injection in function objects
                density_by_region[region] = region_props["rho"]["value"]
        else:
            for region in fluids:
                region_props = get_config_value(material_properties_dict, region, expected_type=dict, required=True)
                thermo_template, thermo_context = build_thermophysical_properties(region_props, region, reference_pressure)
                curr_file_path = os.path.join(_const_dir(region), "thermophysicalProperties")
                location = "constant" if is_single_region else f"constant/{region}"
                with open(curr_file_path, "w") as f:
                    f.write(_render_template(thermo_template, location=location, openfoam_version=OPENFOAM_VERSION, **thermo_context))
                print(f"  Written: {curr_file_path}")

    # Configuring thermophysicalProperties for solid regions
    if solids and material_properties_dict:
        for region in solids:
            region_props = get_config_value(material_properties_dict, region, expected_type=dict, required=True)
            thermo_template, thermo_context = build_solid_thermophysical_properties(region_props, region)
            curr_file_path = os.path.join(_const_dir(region), "thermophysicalProperties")
            location = "constant" if is_single_region else f"constant/{region}"
            with open(curr_file_path, "w") as f:
                f.write(_render_template(thermo_template, location=location, openfoam_version=OPENFOAM_VERSION, **thermo_context))
            print(f"  Written: {curr_file_path}")

    #=============================================================================#
    # 0 directory setup (initial conditions)
    #=============================================================================#
    # Determine pressure variable name (needed for field files)
    pres_var_name = None
    if fluids:
        pres_var_name = get_pressure_variable_name(solver_name)

    initial_conditions_dict = get_config_value(config, "initial_conditions", expected_type=dict, required=True)
    validate_initial_conditions(initial_conditions_dict, all_regions)

    # Extract wall functions from turbulence config if turbulence is active
    wall_function = None
    thermal_wall_function = None
    if is_turb_active and turb_model:
        turbulence_dict = get_config_value(config, "turbulence", expected_type=dict, required=True)
        rans_config = get_config_value(turbulence_dict, "RANS_config", expected_type=dict, required=True)
        wall_function = get_config_value(rans_config, "wall_function", expected_type=str, required=False)
        thermal_wall_function = get_config_value(rans_config, "thermal_wall_function", expected_type=str, required=False)

    # Get radiation status for BC determination (incompressible: always inactive)
    if is_incompressible:
        rad_is_active, rad_model = False, None
    else:
        rad_is_active, rad_model, _, _ = get_radiation_content(config)

    # Read and validate boundary conditions
    boundary_conditions_dict = get_config_value(config, "boundary_conditions", expected_type=dict, required=False)
    if boundary_conditions_dict:
        validate_boundary_conditions(boundary_conditions_dict, all_regions, fluids, turb_model,
                                     is_incompressible=is_incompressible)

    # Read and validate fvOptions
    fvoptions_dict = get_config_value(config, "fv_options", expected_type=dict, required=False)
    if fvoptions_dict:
        # Build cell_zones_by_region for validation
        cell_zones_by_region = {}
        for region in all_regions:
            region_cell_zones = region_parts.get(region, {}).get("cellZones", [])
            cell_zones_by_region[region] = region_cell_zones
        validate_fvOptions(fvoptions_dict, all_regions, cell_zones_by_region)

    # Create 0 directory for each region and generate field files
    print("\n=== 0/ — Initial Conditions ===")
    for region in all_regions:
        region_dir = "0" if is_single_region else os.path.join("0", region)
        field_location = "0" if is_single_region else f"0/{region}"
        check_and_reset_directory(region_dir)

        # Determine if this is a fluid or solid region
        is_fluid = region in fluids

        # Get list of required field files
        if is_fluid:
            field_files = get_fluid_field_files(pres_var_name, turb_model, is_incompressible=is_incompressible,
                                                rad_model=rad_model)
        else:
            field_files = get_solid_field_files()

        # Get region-specific boundary conditions if they exist
        region_bcs = boundary_conditions_dict.get(region, {}) if boundary_conditions_dict else {}

        # Get CHT interface BCs for this region
        cht_interface_bcs = get_cht_interface_bcs(cht_interfaces, region, fluids, solids)

        # Pre-process BC patches once (used by all field templates including T)
        region_rho = density_by_region.get(region)  # None for compressible regions
        if is_fluid:
            patches, cht_patches = prepare_bc_patches(
                region_bcs, cht_interface_bcs, reference_pressure, wall_function, thermal_wall_function,
                rad_is_active=rad_is_active, region_type="fluid",
                is_incompressible=is_incompressible, rho=region_rho,
            )
        else:
            patches, cht_patches = [], []

        # Create each field file
        for field_name in field_files:
            # IDefault: template is self-contained (internalField always uniform 0);
            # skip get_initial_field_value entirely and render directly.
            if field_name == "IDefault":
                curr_file_path = os.path.join(region_dir, field_name)
                idefault_patches = [p for p in patches if p["bc_type"] not in CONSTRAINT_TYPES]
                content = _render_template(
                    "0/IDefault.template",
                    region=region,
                    location=field_location,
                    patches=idefault_patches,
                    cht_patches=cht_patches,
                )
                with open(curr_file_path, "w") as f:
                    f.write(content)
                print(f"  Created: {curr_file_path}")
                continue

            field_value = get_initial_field_value(region, field_name, initial_conditions_dict, reference_pressure,
                                                  is_fluid, is_incompressible=is_incompressible, rho=region_rho)

            curr_file_path = os.path.join(region_dir, field_name)

            if field_name == "T":
                # For T, solid regions need their own patches (fluid patches already computed above)
                if is_fluid:
                    T_patches, T_cht_patches = patches, cht_patches
                else:
                    # Determine kappa_type from resolved material properties (needed for anisotropic BCs)
                    region_props = get_config_value(material_properties_dict, region, expected_type=dict, required=True)
                    region_kappa_type = get_config_value(region_props, "kappa_type", expected_type=str,
                                                        required=False) or "isotropic"
                    T_patches, T_cht_patches = prepare_bc_patches(
                        region_bcs, cht_interface_bcs, reference_pressure, wall_function, thermal_wall_function,
                        rad_is_active=rad_is_active, region_type="solid",
                        kappa_type=region_kappa_type,
                    )
                content = _render_template(
                    "0/T.template",
                    region=region,
                    location=field_location,
                    internal_field=field_value,
                    patches=T_patches,
                    cht_patches=T_cht_patches,
                )
                with open(curr_file_path, "w") as f:
                    f.write(content)
                print(f"  Created: {curr_file_path}")
            else:
                # Non-T fields: render via Jinja2 template
                ctx = {
                    "region": region,
                    "location": field_location,
                    "internal_field": field_value,
                    "patches": patches,
                    "cht_patches": cht_patches,
                }
                if field_name == "p":
                    ctx["p_is_derived"] = is_fluid and (pres_var_name == "p_rgh")
                    ctx["is_incompressible"] = is_incompressible
                content = _render_template(f"0/{field_name}.template", **ctx)
                with open(curr_file_path, "w") as f:
                    f.write(content)
                print(f"  Created: {curr_file_path}")

        # Write boundaryRadiationProperties for fluid regions when radiation is active
        if is_fluid and rad_is_active:
            rad_props_path = os.path.join(_const_dir(region), "boundaryRadiationProperties")
            location = "constant" if is_single_region else f"constant/{region}"
            rad_patches = build_radiation_boundary_list(
                region_bcs,
                region_parts[region]["boundaries"],
                set(cht_interface_bcs.keys()),
            )
            cht_rad_patches = [
                {"name": p, "emissivity": float(cht_interface_bcs[p].get("emissivity", 0.9))}
                for p in cht_interface_bcs
            ]
            content = _render_template(
                "constant/fluid/boundaryRadiationProperties.template",
                location=location,
                openfoam_version=OPENFOAM_VERSION,
                rad_patches=rad_patches,
                cht_rad_patches=cht_rad_patches,
            )
            with open(rad_props_path, "w") as f:
                f.write(content)
            print(f"  Written: {rad_props_path}")

        # Validate and fix polyMesh patches
        if region_bcs:
            # Check for conflicts with __default__ reserved name
            if is_single_region:
                boundary_file = os.path.join(case_dir, "constant/polyMesh/boundary")
            else:
                boundary_file = os.path.join(case_dir, f"constant/{region}/polyMesh/boundary")
            check_default_bc_conflict(boundary_file, region)

            if is_fluid:
                for patch_name, patch_bc in region_bcs.items():
                    # Skip __default__ key in polyMesh validation (it's not a real patch)
                    if patch_name.strip() == "__default__":
                        continue

                    bc_type = patch_bc.get("type")
                    # Expand comma-separated patch names for polyMesh validation
                    individual_patches = [p.strip() for p in patch_name.split(",")]
                    for individual_patch in individual_patches:
                        if bc_type in ["velocity-inlet", "pressure-outlet", "total-pressure-inlet"]:
                            validate_and_fix_polymesh_patch(case_dir, region, individual_patch, is_single_region=is_single_region)
                        elif bc_type == "no-slip-wall":
                            # no-slip-wall patches should be of type 'wall' with inGroups containing 'walls'
                            validate_and_fix_polymesh_patch(case_dir, region, individual_patch, expected_type="wall", is_single_region=is_single_region)
                        elif bc_type == "slip-wall":
                            # slip-wall patches must also be of type 'wall'
                            validate_and_fix_polymesh_patch(case_dir, region, individual_patch, expected_type="wall", is_single_region=is_single_region)
                        elif bc_type in CONSTRAINT_TYPES:
                            # constraint patches: verify type matches and fix inGroups
                            validate_and_fix_polymesh_patch(case_dir, region, individual_patch, expected_type=bc_type, is_single_region=is_single_region)
            else:
                # For solid regions, all thermal BC patches should be of type 'wall' with inGroups containing 'walls'
                for patch_name, patch_bc in region_bcs.items():
                    # Skip __default__ key in polyMesh validation (it's not a real patch)
                    if patch_name.strip() == "__default__":
                        continue

                    # Expand comma-separated patch names for polyMesh validation
                    individual_patches = [p.strip() for p in patch_name.split(",")]
                    for individual_patch in individual_patches:
                        solid_bc_type = patch_bc.get("type")
                        if solid_bc_type in CONSTRAINT_TYPES:
                            # constraint patches: verify type matches and fix inGroups
                            validate_and_fix_polymesh_patch(case_dir, region, individual_patch, expected_type=solid_bc_type, is_single_region=is_single_region)
                        else:
                            validate_and_fix_polymesh_patch(case_dir, region, individual_patch, expected_type="wall", is_single_region=is_single_region)

    # Process CHT interfaces
    if cht_interfaces:
        process_cht_interfaces(case_dir, cht_interfaces, all_regions)

    #=============================================================================#
    # system directory setup
    #=============================================================================#
    check_and_reset_directory("system")

    end_time = -1
    write_interval = -1

    if sim_type == "steady-state":
        end_time = get_config_value(sim_dict, "end_time", expected_type=int, min_val=1)
        write_interval = get_config_value(sim_dict, "write_interval", expected_type=int, min_val=1)
    else:
        end_time = get_config_value(sim_dict, "end_time", expected_type=float, min_val=0.0)
        write_interval = get_config_value(sim_dict, "write_interval", expected_type=float, min_val=0.0)

    write_format    = get_config_value(sim_dict, "write_format",    expected_type=str, valid_options=["ascii", "binary"])
    write_precision = get_config_value(sim_dict, "write_precision", expected_type=int, min_val=1)
    time_precision  = get_config_value(sim_dict, "time_precision",  expected_type=int, min_val=1)

    # adjustTimeStep is always off for steady-state; for transient it is user-controlled
    if sim_type == "steady-state":
        delta_t = 1
        adjust_timestep = False
        max_co = None
        max_di = None
        max_delta_t = None
        write_control = "runTime"
    else:
        delta_t = get_config_value(sim_dict, "delta_t", expected_type=float, min_val=1e-15, required=True)
        adjust_timestep = get_config_value(sim_dict, "adjust_timestep", expected_type=bool, required=True)
        if adjust_timestep:
            max_co      = get_config_value(sim_dict, "max_co",      expected_type=float, min_val=1e-6, required=True)
            max_di      = get_config_value(sim_dict, "max_di",      expected_type=float, min_val=1e-6, required=True)
            max_delta_t = get_config_value(sim_dict, "max_delta_t", expected_type=float, min_val=1e-15, required=True)
            write_control = "adjustableRunTime"
        else:
            max_co = None
            max_di = None
            max_delta_t = None
            write_control = "runTime"

    # Creating files directly under system directory, i.e., 1) controlDict, 2) fvSchemes, 3) fvSolution, 4) decomposeParDict
    # 1) controlDict
    print("\n=== system/ ===")
    # Validate and get function objects if present
    incompressible_regions = fluids if is_incompressible else []
    function_objects_dict = validate_function_objects(config, all_regions, solids,
                                                       incompressible_regions=incompressible_regions)
    user_fos, cellzone_avg_fields = prepare_function_objects_context(
        function_objects_dict, all_regions, density_by_region=density_by_region)

    # 1) controlDict
    curr_file_path = "system/controlDict"
    with open(curr_file_path, "w") as f:
        f.write(_render_template(
            "system/shared/controlDict.template",
            solver_name=solver_name,
            end_time=end_time,
            write_interval=write_interval,
            delta_t=delta_t,
            write_format=write_format,
            write_precision=write_precision,
            time_precision=time_precision,
            write_control=write_control,
            adjust_timestep=adjust_timestep,
            max_co=max_co,
            max_di=max_di,
            max_delta_t=max_delta_t,
            openfoam_version=OPENFOAM_VERSION,
        ))
    print(f"  Written: {curr_file_path}")

    # 2) system/functionObjects (included by controlDict via #include)
    with open("system/functionObjects", "w") as f:
        f.write(_render_template(
            "system/shared/functionObjects.template",
            fluid_regions=fluids,
            all_regions=all_regions,
            user_function_objects=user_fos,
            cellzone_average_fields=cellzone_avg_fields,
            is_single_region=is_single_region,
            incompressible_regions=incompressible_regions,
        ))
    print("  Written: system/functionObjects")

    # 3) fvSchemes (top-level stub for multi-region; actual content written later per region for single-region)
    if is_multi_region:
        with open("system/fvSchemes", "w") as f:
            f.write(_render_template("system/shared/fvSchemes.template", openfoam_version=OPENFOAM_VERSION))
        print("  Written: system/fvSchemes")

    # 3) fvSolution: for multi-region write stub (holds global PIMPLE nOuterCorrectors for transient);
    #               for single-region, the actual fvSolution is written later in the region loop.
    matrix_solvers = get_config_value(config, "matrix_solvers", expected_type=dict)
    iterative_solver_dict = get_config_value(config, "iterative_solver", expected_type=dict)

    # Read max_outer_iterations from iterative_solver (only for transient simulations)
    outer_correctors = None
    if sim_type == "transient":
        outer_correctors = get_config_value(iterative_solver_dict, "max_outer_iterations", expected_type=int, min_val=1, max_val=100)

    if is_multi_region:
        with open("system/fvSolution", "w") as f:
            f.write(_render_template(
                "system/shared/fvSolution.template",
                show_outer_correctors=(sim_type == "transient" and outer_correctors is not None),
                outer_correctors=outer_correctors,
                openfoam_version=OPENFOAM_VERSION,
            ))
        print("  Written: system/fvSolution")

    # 4) decomposeParDict
    num_cores = get_config_value(sim_dict, "num_cores", expected_type=int, min_val=1)

    if num_cores > 1:
        with open("system/decomposeParDict", "w") as f:
            f.write(_render_template("system/shared/decomposeParDict.template", num_cores=num_cores, openfoam_version=OPENFOAM_VERSION))
        print("  Written: system/decomposeParDict")
    else:
        print("  Skipping system/decomposeParDict (num_cores = 1, serial run).")

    def _build_fvoptions_entries(opts, region):
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

    # Create and populate region folders under system directory (multi-region only)
    # For single-region: fvOptions goes directly to system/fvOptions; no subdirs needed.
    for region in all_regions:
        if is_single_region:
            # Write fvOptions directly under system/ if configured
            if fvoptions_dict and region in fvoptions_dict and fvoptions_dict[region]:
                opt_entries = _build_fvoptions_entries(fvoptions_dict[region], region)
                with open("system/fvOptions", "w") as f:
                    f.write(_render_template(
                        "system/shared/fvOptions.template",
                        openfoam_version=OPENFOAM_VERSION,
                        location="system",
                        options=opt_entries,
                    ))
                print("  Written: system/fvOptions")
        else:
            region_path = os.path.join("system", region)
            try:
                os.makedirs(region_path)
                print(f"  Created directory: {region_path}/")
                os.chdir(region_path)
                execute_command("ln -s ../decomposeParDict") if num_cores > 1 else None

                # Create fvOptions file if region has fvOptions configuration
                if fvoptions_dict and region in fvoptions_dict and fvoptions_dict[region]:
                    opt_entries = _build_fvoptions_entries(fvoptions_dict[region], region)
                    with open("fvOptions", "w") as f:
                        f.write(_render_template(
                            "system/shared/fvOptions.template",
                            openfoam_version=OPENFOAM_VERSION,
                            location=f"system/{region}",
                            options=opt_entries,
                        ))
                    print(f"  Written: {region_path}/fvOptions")

            except OSError as e:
                sys.exit(f"Error creating '{region_path}': {e}")
            finally:
                os.chdir(case_dir)

    # Generate createBafflesDict files for fan-type faceZones
    if faceZone_conditions:
        for region, region_fz_dict in faceZone_conditions.items():
            baffle_dict_path = "system/createBafflesDict" if is_single_region else f"system/{region}/createBafflesDict"
            baffle_location  = "system"                   if is_single_region else f"system/{region}"
            baffle_entries = []

            for faceZone_name, fz_config in region_fz_dict.items():
                if fz_config["type"] == "fan":
                    baffle_entries.append(prepare_fan_baffle_context(
                        faceZone_name,
                        fz_config["patch_name"],
                        fz_config["fan_curve"],
                        reference_pressure,
                    ))
                # Add further elif branches here for future baffle types

            if baffle_entries:
                try:
                    with open(baffle_dict_path, "w") as f:
                        f.write(_render_template(
                            "system/shared/createBafflesDict.template",
                            openfoam_version=OPENFOAM_VERSION,
                            location=baffle_location,
                            baffles=baffle_entries,
                        ))
                    fan_names = ", ".join(fz for fz, cfg in region_fz_dict.items() if cfg.get("type") == "fan")
                    print(f"Created '{baffle_dict_path}' with {len(baffle_entries)} baffle(s): {fan_names}")
                except Exception as e:
                    sys.exit(f"Error writing '{baffle_dict_path}': {e}")



    # # 1) fvSchemes setup in region dirs
    numerics_dict = get_config_value(config, "numerical_schemes", expected_type=dict)

    ### Reading time scheme and validating it
    json_time_scheme = get_config_value(numerics_dict, "time", expected_type=str, valid_options=["none", "Euler", "CrankNicolson", "backward"])

    time_scheme_mapper = {
        "none": "steadyState",
        "Euler": "Euler",
        "CrankNicolson": "CrankNicolson 0.9",
        "backward": "backward"
    }

    time_scheme = time_scheme_mapper.get(json_time_scheme)

    if sim_type == "steady-state" and time_scheme != "steadyState":
        sys.exit(
            f"Config Error: Simulation is set to '{sim_type}', but you provided an invalid time scheme."
            f"\n  -> Found: '{json_time_scheme}'"
            f"\n  -> Required: 'none'"
        )

    if sim_type == "transient" and time_scheme == "steadyState":
        sys.exit(
            f"Config Error: Simulation is set to '{sim_type}', but you provided an invalid time scheme."
            f"\n  -> Found: '{json_time_scheme}'"
            f"\n  -> Required: 'euler' or 'crank-nicolson' or 'backward'"
        )

    ### Reading gradient scheme and validating the inputs
    json_grad_scheme = get_config_value(numerics_dict, "gradients", expected_type=str, valid_options=["green-gauss", "least-squares"])

    grad_scheme_mapper = {
        "green-gauss": "Gauss linear",
        "least-squares": "leastSquares"
    }

    grad_scheme = grad_scheme_mapper.get(json_grad_scheme)

    ### Reading convection schemes (per-field subdict) and validating the inputs
    convection_dict = get_config_value(numerics_dict, "convection", expected_type=dict)

    valid_convection_options = ["first-order-upwind", "second-order-upwind"]
    convection_scheme_mapper = {
        "first-order-upwind": "upwind",
        "second-order-upwind": "linearUpwind"
    }

    json_momentum_scheme   = get_config_value(convection_dict, "momentum",   expected_type=str, valid_options=valid_convection_options)
    json_energy_scheme     = get_config_value(convection_dict, "energy",     expected_type=str, valid_options=valid_convection_options,
                                              required=not is_incompressible)
    json_turbulence_scheme = get_config_value(convection_dict, "turbulence", expected_type=str, valid_options=valid_convection_options,
                                              required=is_turb_active)

    def _build_convection_scheme(json_scheme, field_type):
        """Map JSON convection option to OpenFOAM Gauss scheme string. Returns None if json_scheme is None."""
        if json_scheme is None:
            return None
        of_scheme = convection_scheme_mapper.get(json_scheme)
        if of_scheme == "upwind":
            return f"Gauss {of_scheme}"
        elif of_scheme == "linearUpwind":
            if field_type == "momentum":
                return f"Gauss {of_scheme}V LIMITED"
            else:
                return f"Gauss {of_scheme} LIMITED"
        else:
            sys.exit(f"Unconfigured convection scheme for {field_type}: '{json_scheme}'")

    velocity_scheme   = _build_convection_scheme(json_momentum_scheme,   "momentum")
    energy_scheme     = _build_convection_scheme(json_energy_scheme,     "energy")
    turbulence_scheme = _build_convection_scheme(json_turbulence_scheme, "turbulence")

    convection_prefix = ""
    if sim_type == "steady-state":
        convection_prefix = "bounded "

    # Configuring fvSchemes for fluid regions
    if fluids:
        for region in fluids:
            curr_file_path = os.path.join(_sys_dir(region), "fvSchemes")
            location = "system" if is_single_region else f"system/{region}"
            with open(curr_file_path, "w") as f:
                f.write(_render_template(
                    "system/fluid/fvSchemes.template",
                    openfoam_version=OPENFOAM_VERSION,
                    location=location,
                    time_scheme=time_scheme,
                    grad_scheme=grad_scheme,
                    convection_prefix=convection_prefix,
                    velocity_scheme=velocity_scheme,
                    energy_scheme=energy_scheme,
                    turbulence_scheme=turbulence_scheme,
                    is_incompressible=is_incompressible,
                    is_turb_active=is_turb_active,
                    rad_is_active=rad_is_active,
                    rad_model=rad_model,
                ))
            print(f"  Written: {curr_file_path}")

    # Configuring fvSchemes for solid regions
    if solids:
        for region in solids:
            curr_file_path = os.path.join(_sys_dir(region), "fvSchemes")
            location = "system" if is_single_region else f"system/{region}"
            region_props = get_config_value(material_properties_dict, region, expected_type=dict, required=True)
            prop_type  = get_config_value(region_props, "type",       expected_type=str, required=True)
            kappa_type = get_config_value(region_props, "kappa_type", expected_type=str, required=False) or "isotropic"
            is_zone_mixture = (prop_type == "cell_zone_specific")
            # Harmonic interpolation is appropriate when sharp jumps in isotropic
            # thermal conductivity exist between cell zones.  For anisotropic
            # conductivity the tensor nature of kappa makes harmonic averaging
            # ill-defined, so linear is always used.
            laplacian_interpolation = "harmonic" if (is_zone_mixture and kappa_type == "isotropic") else "linear"
            with open(curr_file_path, "w") as f:
                f.write(_render_template(
                    "system/solid/fvSchemes.template",
                    openfoam_version=OPENFOAM_VERSION,
                    location=location,
                    time_scheme=time_scheme,
                    grad_scheme=grad_scheme,
                    laplacian_interpolation=laplacian_interpolation,
                ))
            print(f"  Written: {curr_file_path}")

    ## 2) fvSolution setup in region dirs
    ### Content accumulation for fluid fvSolution

    fluid_matrix_solvers = None
    solid_matrix_solvers = None

    if fluids:
        fluid_matrix_solvers = get_config_value(matrix_solvers, "fluid", expected_type=dict, required=True)
    if solids:
        solid_matrix_solvers = get_config_value(matrix_solvers, "solid", expected_type=dict, required=True)

    pres_solver = None
    others_solver = None
    pres_vel_scheme = None
    consistent_flag = None
    pressure_correctors = None
    non_orthogonal_correctors = None
    solve_turb_once_per_timestep = None
    momentum_predictor = None
    fluid_residuals_dict = None
    urf = None

    convergence_dict = get_config_value(config, "convergence_criteria", expected_type=dict)

    if fluids:
        pres_solver_dict = get_config_value(fluid_matrix_solvers, "pressure", expected_type=dict)
        others_solver_dict = get_config_value(fluid_matrix_solvers, "others", expected_type=dict)

        pres_solver = parse_matrix_solvers(pres_solver_dict, "pressure")
        others_solver = parse_matrix_solvers(others_solver_dict, "others")

        fluid_iterative_solver_dict = get_config_value(iterative_solver_dict, "fluid", expected_type=dict)
        pres_vel_scheme = get_config_value(fluid_iterative_solver_dict, "scheme", expected_type=str, valid_options=['SIMPLE', 'SIMPLEC'])
        consistent_flag = "true" if pres_vel_scheme == "SIMPLEC" else "false"
        pressure_correctors = get_config_value(fluid_iterative_solver_dict, "pressure_correctors", expected_type=int, min_val=1)
        non_orthogonal_correctors = get_config_value(fluid_iterative_solver_dict, "non_orthogonal_correctors", expected_type=int, min_val=0)
        solve_turb_once_per_timestep = get_config_value(fluid_iterative_solver_dict, "solve_turb_once_per_timestep", expected_type=bool, required=(sim_type == "transient" and is_turb_active))
        if solve_turb_once_per_timestep is None:
            solve_turb_once_per_timestep = False  # steady-state default
        momentum_predictor = get_config_value(fluid_iterative_solver_dict, "momentum_predictor", expected_type=bool, required=(sim_type == "transient"))
        if momentum_predictor is None:
            momentum_predictor = True  # steady-state default

        if sim_type=="steady-state" and solve_turb_once_per_timestep:
            sys.exit("For steady-state simulations, iterative_solver > fluid > solve_turb_once_per_timestep must be false")

        if sim_type=="steady-state" and not momentum_predictor:
            sys.exit("For steady-state simulations, iterative_solver > fluid > momentum_predictor must be true")

        fluid_convergence_dict = get_config_value(convergence_dict, "fluid", expected_type=dict)
        fluid_residuals_dict = get_config_value(fluid_convergence_dict, "residuals", expected_type=dict)

    solid_residuals_dict = None
    solid_non_orthogonal_correctors = None

    if solids:
        solid_iterative_solver_dict = get_config_value(iterative_solver_dict, "solid", expected_type=dict)
        solid_non_orthogonal_correctors = get_config_value(solid_iterative_solver_dict, "non_orthogonal_correctors", expected_type=int, min_val=0)

        solid_convergence_dict = get_config_value(convergence_dict, "solid", expected_type=dict)
        solid_residuals_dict = get_config_value(solid_convergence_dict, "residuals", expected_type=dict)

    fluid_fvSolution_content = ""

    # contents of relaxation_factors dict
    relaxation_factors_dict = get_config_value(config, "relaxation_factors", expected_type=dict)
    solid_urf = None

    if fluids:
        fluid_relaxation_factors_dict = get_config_value(relaxation_factors_dict, "fluid", expected_type=dict)
        if is_incompressible:
            urf_keys = ["pressure", "velocity"]
        else:
            urf_keys = ["density", "pressure", "velocity", "energy"]
        if is_turb_active:
            urf_keys.append("turbulence")
        urf = {k: get_config_value(fluid_relaxation_factors_dict, k, expected_type=float, min_val=1e-5, max_val=1.0)
               for k in urf_keys}

        if not is_incompressible and sim_type == "transient" and urf.get("density", 1.0) < 1.0:
            print(f"Warning: A relaxation factor of {urf['density']} was provided for 'density', "
                  "but it will not be considered, since this is a transient case.")

        show_fluid_outer_correctors = (sim_type == "transient" and is_single_region and outer_correctors is not None)
        fluid_residuals = get_residual_entries(fluid_residuals_dict, pres_var_name=pres_var_name,
                                               region_type="fluid", is_incompressible=is_incompressible)

        for region in fluids:
            fvsol_path = os.path.join(_sys_dir(region), "fvSolution")
            location = "system" if is_single_region else f"system/{region}"
            with open(fvsol_path, "w") as f:
                f.write(_render_template(
                    "system/fluid/fvSolution.template",
                    openfoam_version=OPENFOAM_VERSION,
                    location=location,
                    sim_type=sim_type,
                    pres_var_name=pres_var_name,
                    pres_solver=pres_solver,
                    others_solver=others_solver,
                    momentum_predictor=momentum_predictor,
                    consistent_flag=consistent_flag,
                    pressure_correctors=pressure_correctors,
                    non_orthogonal_correctors=non_orthogonal_correctors,
                    solve_turb_once_per_timestep=solve_turb_once_per_timestep,
                    show_outer_correctors=show_fluid_outer_correctors,
                    outer_correctors=outer_correctors,
                    residuals=fluid_residuals,
                    urf=urf,
                    rad_is_active=rad_is_active,
                    rad_model=rad_model,
                    is_incompressible=is_incompressible,
                ))
            print(f"  Written: {fvsol_path}")

    if solids:
        solid_relaxation_factors_dict = get_config_value(relaxation_factors_dict, "solid", expected_type=dict)
        solid_urf = {"energy": get_config_value(solid_relaxation_factors_dict, "energy", expected_type=float, min_val=1e-5, max_val=1.0)}

        solid_energy_solver_dict = get_config_value(solid_matrix_solvers, "energy", expected_type=dict)
        solid_energy_solver = parse_matrix_solvers(solid_energy_solver_dict, "energy", region_type="solid")

        show_solid_outer_correctors = (sim_type == "transient" and is_single_region and outer_correctors is not None)
        solid_residuals = get_residual_entries(solid_residuals_dict, region_type="solid")

        for region in solids:
            fvsol_path = os.path.join(_sys_dir(region), "fvSolution")
            location = "system" if is_single_region else f"system/{region}"
            with open(fvsol_path, "w") as f:
                f.write(_render_template(
                    "system/solid/fvSolution.template",
                    openfoam_version=OPENFOAM_VERSION,
                    location=location,
                    sim_type=sim_type,
                    energy_solver=solid_energy_solver,
                    non_orthogonal_correctors=solid_non_orthogonal_correctors,
                    show_outer_correctors=show_solid_outer_correctors,
                    outer_correctors=outer_correctors,
                    residuals=solid_residuals,
                    urf=solid_urf,
                ))
            print(f"  Written: {fvsol_path}")
    #=============================================================================#



if __name__ == "__main__":
    main()
