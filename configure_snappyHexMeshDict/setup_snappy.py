#!/usr/bin/env python3
"""
snappyHexMeshDict Generator
Parses snappy_inputs.json and generates OpenFOAM snappyHexMeshDict file.
"""

import json
import math
import re
import sys
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

try:
    import trimesh
except ImportError:
    trimesh = None

# ── Release metadata ─────────────────────────────────────────────────────────
JSON_VERSION      = "1.0"
JSON_VERSION_DATE = "2026-04-29"
OPENFOAM_VERSION  = "v2512"   # target OpenFOAM version (used in file headers)
# ─────────────────────────────────────────────────────────────────────────────

VALID_SHAPE_TYPES = [
    "searchableBox", "searchableSphere", "searchableCylinder",
    "searchableCone", "searchableRotatedBox", "searchableDisk",
    "searchablePlate", "searchablePlane", "searchableSurfaceWithGaps"
]


CASE_ONLY_KEYS = {"geometry", "surfaceHandling", "volumeRefinement"}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure the utility directory is on sys.path so auto_refinement can be imported
# regardless of which case directory setup_snappy.py is called from.
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from auto_refinement import (
    parse_auto_encoded_name,
    validate_auto_refinement_params,
    compute_auto_levels_for_geometry,
)
from encoding_utils import build_tags, decode_surf_tag, vol_direction, empty_encoded_result


def deep_merge(base, override):
    """
    Recursively merge two dicts. override wins on individual keys.
    Non-dict values in override always replace base values.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_snappy_config(config_file="snappy_inputs.json"):
    """
    Load configuration by merging defaults.json (utility dir) with
    snappy_inputs.json (case dir). snappy_inputs.json always wins.
    geometry, surfaceHandling, and volumeRefinement are case-only and
    forbidden in defaults.json.
    """
    defaults_file = os.path.join(SCRIPT_DIR, "defaults.json")
    if not os.path.exists(defaults_file):
        sys.exit(f"Error: defaults.json not found in utility directory ({SCRIPT_DIR})")

    try:
        with open(defaults_file, 'r') as f:
            defaults = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: Invalid JSON in defaults.json: {e}")

    forbidden = CASE_ONLY_KEYS & set(defaults.keys())
    if forbidden:
        sys.exit(
            f"Error: defaults.json must not contain case-specific keys: {sorted(forbidden)}.\n"
            f"       Move {sorted(forbidden)} to snappy_inputs.json."
        )

    if not os.path.exists(config_file):
        sys.exit(f"Error: {config_file} not found in current directory")

    try:
        with open(config_file, 'r') as f:
            case_config = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: Invalid JSON in {config_file}: {e}")

    return deep_merge(defaults, case_config)


def load_geometry_files(files_value):
    """
    Load geometry file list from an inline array or a text file (ls -1 output).
    Returns list of filename strings. Each entry validated for extension, stem,
    and physical existence in constant/triSurface/.
    """
    VALID_EXTENSIONS = {'.stl', '.obj'}
    TRI_SURFACE_DIR = os.path.join("constant", "triSurface")

    if isinstance(files_value, str):
        if not os.path.exists(files_value):
            sys.exit(f"Error: geometry.files path '{files_value}' does not exist")
        with open(files_value, 'r') as f:
            lines = f.readlines()
        filenames = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith('#')]
    elif isinstance(files_value, list):
        filenames = files_value
    else:
        sys.exit("Error: 'geometry.files' must be an array of filenames or a path to a text file")

    normalised = []
    for filename in filenames:
        if not isinstance(filename, str):
            sys.exit(f"Error: geometry.files entries must be strings, got {type(filename).__name__}")
        # Accept bare names ("foo.stl") or full paths ("constant/triSurface/foo.stl")
        bare = os.path.basename(filename)
        ext = os.path.splitext(bare)[1].lower()
        if ext not in VALID_EXTENSIONS:
            sys.exit(
                f"Error: geometry file '{filename}' must have a .stl or .obj extension"
            )
        stem = os.path.splitext(bare)[0]
        if not re.match(r'^[a-zA-Z_]', stem):
            sys.exit(
                f"Error: geometry file '{filename}' has an invalid filename stem '{stem}'.\n"
                f"       Stems must start with a letter (a-z, A-Z) or underscore.\n"
                f"       Fix: rename the file."
            )
        expected_path = os.path.join(TRI_SURFACE_DIR, bare)
        if not os.path.exists(expected_path):
            sys.exit(
                f"Error: geometry file '{bare}' not found at '{expected_path}'.\n"
                f"       All geometry files must reside in {TRI_SURFACE_DIR}/"
            )
        normalised.append(bare)

    return normalised


def validate_config(config):
    """Validate required configuration parameters."""
    if "settings" not in config or not isinstance(config["settings"], dict):
        sys.exit("Error: Missing required 'settings' dictionary in snappy_inputs.json")

    settings = config["settings"]
    required_params = {
        "addLayers": bool,
        "mergeTolerance": (int, float)
    }

    for param, expected_type in required_params.items():
        if param not in settings:
            sys.exit(f"Error: Missing required parameter 'settings.{param}' in snappy_inputs.json")

        if isinstance(expected_type, tuple):
            if not isinstance(settings[param], expected_type):
                sys.exit(f"Error: 'settings.{param}' must be a number, got {type(settings[param]).__name__}")
        else:
            if not isinstance(settings[param], expected_type):
                sys.exit(f"Error: 'settings.{param}' must be {expected_type.__name__}, got {type(settings[param]).__name__}")

    if "extractRefinementFromNames" in settings:
        if not isinstance(settings["extractRefinementFromNames"], bool):
            sys.exit("Error: 'settings.extractRefinementFromNames' must be a boolean")

    # geometryUnit is mandatory in snappy_inputs.json (never in defaults.json)
    ALLOWED_UNITS = {"m", "mm", "cm", "um", "in", "ft"}
    if "geometryUnit" not in settings:
        sys.exit(
            "Error: 'settings.geometryUnit' is required in snappy_inputs.json.\n"
            f"       Allowed values: {sorted(ALLOWED_UNITS)}"
        )
    if settings["geometryUnit"] not in ALLOWED_UNITS:
        sys.exit(
            f"Error: 'settings.geometryUnit' = '{settings['geometryUnit']}' is not recognised.\n"
            f"       Allowed values: {sorted(ALLOWED_UNITS)}"
        )

    # locationInMesh is mandatory in snappy_inputs.json castellatedMeshControls (never in defaults.json)
    castellated = config.get("castellatedMeshControls", {})
    if "locationInMesh" not in castellated:
        sys.exit(
            "Error: 'castellatedMeshControls.locationInMesh' is required in snappy_inputs.json.\n"
            "       Provide a 3-element list: \"castellatedMeshControls\": {\"locationInMesh\": [x, y, z]}"
        )
    loc = castellated["locationInMesh"]
    if not isinstance(loc, list) or len(loc) != 3 or not all(isinstance(v, (int, float)) for v in loc):
        sys.exit(
            "Error: 'castellatedMeshControls.locationInMesh' must be a list of 3 numbers, e.g. [120, 70, 320].\n"
            f"       Got: {loc}"
        )

    # Validate encodingConvention (sourced from defaults.json, overridable)
    convention = config.get("encodingConvention", {})
    required_conv_keys = ["surfacePrefix", "volumePrefix", "boundary", "faceZone", "cellZone"]
    for key in required_conv_keys:
        if key not in convention:
            sys.exit(f"Error: 'encodingConvention.{key}' is missing. Check defaults.json.")
        val = convention[key]
        if not isinstance(val, str) or not re.match(r'^[A-Z][A-Z0-9]*$', val):
            sys.exit(
                f"Error: 'encodingConvention.{key}' must be an uppercase string (letters and digits only), "
                f"got '{val}'.\n"
                f"       Example: \"surfacePrefix\": \"SURF\""
            )


def validate_background_mesh(config):
    """
    Validate backgroundMesh section. Required in snappy_inputs.json.
    Returns the validated section dict.
    """
    if "backgroundMesh" not in config:
        sys.exit(
            "Error: 'backgroundMesh' is required in snappy_inputs.json.\n"
            "       Provide at minimum 'referenceGeometry' and 'baseGrid':\n"
            "       \"backgroundMesh\": {\"referenceGeometry\": \"outer-domain.stl\", \"baseGrid\": 5.0}"
        )

    bm = config["backgroundMesh"]
    if not isinstance(bm, dict):
        sys.exit("Error: 'backgroundMesh' must be a dictionary")

    # referenceGeometry — mandatory
    if "referenceGeometry" not in bm:
        sys.exit(
            "Error: 'backgroundMesh.referenceGeometry' is required.\n"
            "       Provide the filename (with extension) of the geometry to base the bounding box on.\n"
            "       Example: \"referenceGeometry\": \"outer-domain.stl\""
        )
    ref_geom = bm["referenceGeometry"]
    if not isinstance(ref_geom, str):
        sys.exit("Error: 'backgroundMesh.referenceGeometry' must be a string (filename with extension)")

    ext = os.path.splitext(ref_geom)[1].lower()
    if ext not in (".stl", ".obj"):
        sys.exit(
            f"Error: 'backgroundMesh.referenceGeometry' must be an .stl or .obj file, got '{ref_geom}'"
        )

    # Check the file is declared in geometry.files (handles both inline list and text file)
    geometry_files = config.get("geometry", {}).get("files", [])
    declared_files = load_geometry_files(geometry_files) if geometry_files else []
    if ref_geom not in declared_files:
        sys.exit(
            f"Error: 'backgroundMesh.referenceGeometry' = '{ref_geom}' is not listed in geometry.files.\n"
            f"       Declared files: {declared_files}"
        )

    # baseGrid — mandatory, scalar or [dx, dy, dz]
    if "baseGrid" not in bm:
        sys.exit(
            "Error: 'backgroundMesh.baseGrid' is required.\n"
            "       Provide a scalar (isotropic) or [dx, dy, dz] (anisotropic).\n"
            "       Examples: \"baseGrid\": 5.0   or   \"baseGrid\": [5.0, 3.0, 2.0]"
        )
    base_grid = bm["baseGrid"]
    if isinstance(base_grid, (int, float)):
        if base_grid <= 0:
            sys.exit("Error: 'backgroundMesh.baseGrid' must be positive")
        bm["_baseGrid"] = [float(base_grid)] * 3
    elif isinstance(base_grid, list):
        if len(base_grid) != 3 or not all(isinstance(v, (int, float)) and v > 0 for v in base_grid):
            sys.exit(
                "Error: 'backgroundMesh.baseGrid' as a list must be [dx, dy, dz] with three positive numbers"
            )
        bm["_baseGrid"] = [float(v) for v in base_grid]
    else:
        sys.exit("Error: 'backgroundMesh.baseGrid' must be a positive number or a list [dx, dy, dz]")

    # enlargementFactor — from defaults.json, must be > 1
    ef = bm.get("enlargementFactor", 1.1)
    if not isinstance(ef, (int, float)) or ef <= 1.0:
        sys.exit(
            f"Error: 'backgroundMesh.enlargementFactor' must be a number greater than 1, got {ef}"
        )
    bm["enlargementFactor"] = ef

    return bm


def parse_encoded_name(raw_name, convention):
    """
    Parse encoded prefix from geometry name/filename stem using the active encodingConvention.
    Format: [<SURF>_(<BND>|<FZ>|<FZ>_<CZ>)_L<min>_L<max>_][<VOL>_(IN|OUT)_L<level>_]<cleanName>
    Returns dict with: clean_name, has_encoding, surf_type, has_cell_zone,
                       surf_levels, vol_mode, vol_level
    Fatal error if name starts with surfacePrefix_ or volumePrefix_ but cannot be decoded.
    """
    tags      = build_tags(convention)
    result    = empty_encoded_result(raw_name)
    remaining = raw_name

    # Try SURF block
    if remaining.startswith(tags['surf_prefix']):
        surf_pattern = (
            rf'^{re.escape(tags["surf_prefix"])}'
            rf'({tags["surf_tags_pattern"]})_L(\d+)_L(\d+)_(.+)$'
        )
        m = re.match(surf_pattern, remaining)
        if not m:
            sys.exit(
                f"Error: '{raw_name}' starts with '{tags['surf_prefix']}' but could not be decoded.\n"
                f"       Expected format: {tags['surf_prefix']}"
                f"({tags['bnd_tag']}|{tags['fz_tag']}|{tags['fz_cz_tag']})_L<min>_L<max>_<name>\n"
                f"       Example: {tags['surf_prefix']}{tags['fz_tag']}_L1_L2_mosfet"
            )
        result['has_encoding'] = True
        result['surf_type'], result['has_cell_zone'] = decode_surf_tag(m.group(1), tags)
        result['surf_levels'] = [int(m.group(2)), int(m.group(3))]
        remaining = m.group(4)

    # Try VOL block
    if remaining.startswith(tags['vol_prefix']):
        vol_pattern = rf'^{re.escape(tags["vol_prefix"])}(IN|OUT)_L(\d+)_(.+)$'
        m = re.match(vol_pattern, remaining)
        if not m:
            sys.exit(
                f"Error: '{raw_name}' contains '{tags['vol_prefix']}' block that could not be decoded.\n"
                f"       Expected format: {tags['vol_prefix']}(IN|OUT)_L<level>_<name>\n"
                f"       Example: {tags['vol_prefix']}IN_L4_hotSpot"
            )
        result['has_encoding'] = True
        result['vol_mode']  = vol_direction(m.group(1))
        result['vol_level'] = int(m.group(2))
        remaining = m.group(3)

    result['clean_name'] = remaining
    return result


def validate_vector_3d(value, name, geom_idx):
    """Validate 3D vector [x, y, z]."""
    if not isinstance(value, list) or len(value) != 3:
        sys.exit(f"Error: geometry[{geom_idx}].{name} must be [x, y, z]")
    if not all(isinstance(v, (int, float)) for v in value):
        sys.exit(f"Error: geometry[{geom_idx}].{name} must contain numbers")


def validate_positive_number(value, name, geom_idx):
    """Validate positive number."""
    if not isinstance(value, (int, float)) or value <= 0:
        sys.exit(f"Error: geometry[{geom_idx}].{name} must be a positive number")


def validate_standard_shape(shape, geom_idx):
    """Validate standard searchable shape configuration."""
    if "name" not in shape:
        sys.exit(f"Error: geometry[{geom_idx}] missing required field 'name'")

    if not isinstance(shape["name"], str):
        sys.exit(f"Error: geometry[{geom_idx}].name must be a string")

    shape_type = shape.get("type")

    if shape_type == "searchableBox":
        validate_searchable_box(shape, geom_idx)
    elif shape_type == "searchableSphere":
        validate_searchable_sphere(shape, geom_idx)
    elif shape_type == "searchableCylinder":
        validate_searchable_cylinder(shape, geom_idx)
    elif shape_type == "searchableCone":
        validate_searchable_cone(shape, geom_idx)
    elif shape_type == "searchableRotatedBox":
        validate_searchable_rotated_box(shape, geom_idx)
    elif shape_type == "searchableDisk":
        validate_searchable_disk(shape, geom_idx)
    elif shape_type == "searchablePlate":
        validate_searchable_plate(shape, geom_idx)
    elif shape_type == "searchablePlane":
        validate_searchable_plane(shape, geom_idx)
    elif shape_type == "searchableSurfaceWithGaps":
        validate_searchable_surface_with_gaps(shape, geom_idx)
    else:
        sys.exit(f"Error: geometry[{geom_idx}].type '{shape_type}' is not a valid standard shape type")


def validate_searchable_box(shape, geom_idx):
    """Validate searchableBox parameters."""
    if "min" not in shape or "max" not in shape:
        sys.exit(f"Error: geometry[{geom_idx}] (searchableBox) missing 'min' or 'max'")
    validate_vector_3d(shape["min"], "min", geom_idx)
    validate_vector_3d(shape["max"], "max", geom_idx)


def validate_searchable_sphere(shape, geom_idx):
    """Validate searchableSphere parameters."""
    if "centre" not in shape or "radius" not in shape:
        sys.exit(f"Error: geometry[{geom_idx}] (searchableSphere) missing 'centre' or 'radius'")
    validate_vector_3d(shape["centre"], "centre", geom_idx)
    validate_positive_number(shape["radius"], "radius", geom_idx)


def validate_searchable_cylinder(shape, geom_idx):
    """Validate searchableCylinder parameters."""
    required = ["point1", "point2", "radius"]
    for field in required:
        if field not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchableCylinder) missing '{field}'")
    
    validate_vector_3d(shape["point1"], "point1", geom_idx)
    validate_vector_3d(shape["point2"], "point2", geom_idx)
    validate_positive_number(shape["radius"], "radius", geom_idx)


def validate_searchable_cone(shape, geom_idx):
    """Validate searchableCone parameters."""
    required = ["point1", "radius1", "point2", "radius2"]
    for field in required:
        if field not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchableCone) missing '{field}'")
    
    validate_vector_3d(shape["point1"], "point1", geom_idx)
    validate_positive_number(shape["radius1"], "radius1", geom_idx)
    validate_vector_3d(shape["point2"], "point2", geom_idx)
    validate_positive_number(shape["radius2"], "radius2", geom_idx)
    
    # Validate optional inner radii
    if "innerRadius1" in shape:
        if not isinstance(shape["innerRadius1"], (int, float)) or shape["innerRadius1"] < 0:
            sys.exit(f"Error: geometry[{geom_idx}].innerRadius1 must be non-negative")
    
    if "innerRadius2" in shape:
        if not isinstance(shape["innerRadius2"], (int, float)) or shape["innerRadius2"] < 0:
            sys.exit(f"Error: geometry[{geom_idx}].innerRadius2 must be non-negative")


def validate_searchable_rotated_box(shape, geom_idx):
    """Validate searchableRotatedBox parameters."""
    required = ["span", "origin", "e1", "e3"]
    for field in required:
        if field not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchableRotatedBox) missing '{field}'")
    
    validate_vector_3d(shape["span"], "span", geom_idx)
    validate_vector_3d(shape["origin"], "origin", geom_idx)
    validate_vector_3d(shape["e1"], "e1", geom_idx)
    validate_vector_3d(shape["e3"], "e3", geom_idx)


def validate_searchable_disk(shape, geom_idx):
    """Validate searchableDisk parameters."""
    required = ["origin", "normal", "radius"]
    for field in required:
        if field not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchableDisk) missing '{field}'")
    
    validate_vector_3d(shape["origin"], "origin", geom_idx)
    validate_vector_3d(shape["normal"], "normal", geom_idx)
    validate_positive_number(shape["radius"], "radius", geom_idx)


def validate_searchable_plate(shape, geom_idx):
    """Validate searchablePlate parameters."""
    required = ["origin", "span"]
    for field in required:
        if field not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchablePlate) missing '{field}'")
    
    validate_vector_3d(shape["origin"], "origin", geom_idx)
    validate_vector_3d(shape["span"], "span", geom_idx)
    
    # Check that exactly one span component is zero
    span = shape["span"]
    zero_count = sum(1 for v in span if v == 0)
    if zero_count != 1:
        sys.exit(f"Error: geometry[{geom_idx}] (searchablePlate) span must have exactly one zero component")


def validate_searchable_plane(shape, geom_idx):
    """Validate searchablePlane parameters."""
    if "planeType" not in shape:
        sys.exit(f"Error: geometry[{geom_idx}] (searchablePlane) missing 'planeType'")
    
    plane_type = shape["planeType"]
    
    if plane_type == "pointAndNormal":
        if "basePoint" not in shape or "normal" not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchablePlane/pointAndNormal) missing 'basePoint' or 'normal'")
        validate_vector_3d(shape["basePoint"], "basePoint", geom_idx)
        validate_vector_3d(shape["normal"], "normal", geom_idx)
    
    elif plane_type == "embeddedPoints":
        required = ["point1", "point2", "point3"]
        for field in required:
            if field not in shape:
                sys.exit(f"Error: geometry[{geom_idx}] (searchablePlane/embeddedPoints) missing '{field}'")
        validate_vector_3d(shape["point1"], "point1", geom_idx)
        validate_vector_3d(shape["point2"], "point2", geom_idx)
        validate_vector_3d(shape["point3"], "point3", geom_idx)
    
    elif plane_type == "planeEquation":
        required = ["a", "b", "c", "d"]
        for field in required:
            if field not in shape:
                sys.exit(f"Error: geometry[{geom_idx}] (searchablePlane/planeEquation) missing '{field}'")
        if not all(isinstance(shape[f], (int, float)) for f in required):
            sys.exit(f"Error: geometry[{geom_idx}] (searchablePlane/planeEquation) a, b, c, d must be numbers")
    
    else:
        sys.exit(f"Error: geometry[{geom_idx}] (searchablePlane) planeType '{plane_type}' not recognized")


def validate_searchable_surface_with_gaps(shape, geom_idx):
    """Validate searchableSurfaceWithGaps parameters."""
    required = ["surface", "gap"]
    for field in required:
        if field not in shape:
            sys.exit(f"Error: geometry[{geom_idx}] (searchableSurfaceWithGaps) missing '{field}'")
    
    if not isinstance(shape["surface"], str):
        sys.exit(f"Error: geometry[{geom_idx}].surface must be a string")
    
    validate_positive_number(shape["gap"], "gap", geom_idx)


def validate_geometry(geometry, extract_from_names):
    """Validate geometry dict structure (files + standardShapes)."""
    if not isinstance(geometry, dict):
        sys.exit("Error: 'geometry' must be a dictionary with 'files' and/or 'standardShapes'")

    has_files = "files" in geometry
    has_shapes = "standardShapes" in geometry

    if not has_files and not has_shapes:
        sys.exit("Error: 'geometry' must have at least one of 'files' or 'standardShapes'")

    if has_shapes:
        shapes = geometry["standardShapes"]
        if not isinstance(shapes, list):
            sys.exit("Error: 'geometry.standardShapes' must be an array")
        if len(shapes) == 0:
            sys.exit("Error: 'geometry.standardShapes' cannot be empty if present")
        for idx, shape in enumerate(shapes):
            if not isinstance(shape, dict):
                sys.exit(f"Error: geometry.standardShapes[{idx}] must be a dictionary")
            validate_standard_shape(shape, idx)


def validate_selected_parts(section_name, section, geometry_map, extract_from_names=False):
    """Validate the selectedParts list in a surfaceHandling or volumeRefinement section."""
    if "selectedParts" not in section:
        if not extract_from_names:
            sys.exit(f"Error: '{section_name}' missing required field 'selectedParts'")
        section["selectedParts"] = []  # auto-mode: treat as empty, encoded entries are auto-selected
        return
    if not isinstance(section["selectedParts"], list):
        sys.exit(f"Error: '{section_name}.selectedParts' must be an array")
    for part in section["selectedParts"]:
        if not isinstance(part, str):
            sys.exit(f"Error: '{section_name}.selectedParts' entries must be strings")
        if part not in geometry_map:
            sys.exit(f"Error: {section_name}.selectedParts references unknown geometry '{part}'")


def validate_refinement_levels(levels, path):
    """Validate a [min, max] refinement level pair."""
    if not isinstance(levels, list) or len(levels) != 2:
        sys.exit(f"Error: {path}.refinementLevels must be [min, max]")
    if not all(isinstance(v, (int, float)) for v in levels):
        sys.exit(f"Error: {path}.refinementLevels must contain numbers")


def validate_surface_handling_section(surf_section, geometry_map, extract_from_names=False):
    """Validate surfaceHandling section structure."""
    if not isinstance(surf_section, dict):
        sys.exit("Error: 'surfaceHandling' must be a dictionary")

    validate_selected_parts("surfaceHandling", surf_section, geometry_map, extract_from_names)
    selected_parts = set(surf_section.get("selectedParts", []))

    surfaces = surf_section.get("surfaces", {})
    if not isinstance(surfaces, dict):
        sys.exit("Error: 'surfaceHandling.surfaces' must be a dictionary")

    forbidden_in_defaults = {"faceZoneName", "cellZoneName", "regions"}

    for name, entry in surfaces.items():
        if not isinstance(entry, dict):
            sys.exit(f"Error: surfaceHandling.surfaces['{name}'] must be a dictionary")

        if name == "__defaults__":
            for field in forbidden_in_defaults:
                if field in entry:
                    sys.exit(f"Error: surfaceHandling.surfaces.__defaults__ cannot have '{field}'")
            continue

        if name not in selected_parts:
            is_auto_entry = (
                name in geometry_map and geometry_map[name]['encoded'].get('is_auto', False)
            )
            if not is_auto_entry:
                sys.exit(
                    f"Error: surfaceHandling.surfaces has an explicit entry for '{name}' "
                    f"but '{name}' is not in selectedParts.\n"
                    f"       Add '{name}' to surfaceHandling.selectedParts to enable the override."
                )

        if "type" in entry and entry["type"] not in ["boundary", "faceZone"]:
            sys.exit(f"Error: surfaceHandling.surfaces['{name}'].type must be 'boundary' or 'faceZone'")

        if "refinementLevels" in entry:
            validate_refinement_levels(entry["refinementLevels"], f"surfaceHandling.surfaces['{name}']")

        if "faceType" in entry and entry["faceType"] not in ["internal", "baffle", "boundary"]:
            sys.exit(f"Error: surfaceHandling.surfaces['{name}'].faceType must be 'internal', 'baffle', or 'boundary'")

        if "cellZoneInside" in entry and entry["cellZoneInside"] not in ["inside", "outside"]:
            sys.exit(f"Error: surfaceHandling.surfaces['{name}'].cellZoneInside must be 'inside' or 'outside'")

        if "regions" in entry:
            if not isinstance(entry["regions"], dict):
                sys.exit(f"Error: surfaceHandling.surfaces['{name}'].regions must be a dictionary")
            for rname, rdata in entry["regions"].items():
                if not isinstance(rdata, dict):
                    sys.exit(f"Error: surfaceHandling.surfaces['{name}'].regions['{rname}'] must be a dictionary")
                allowed_region_keys = {"refinementLevels"}
                unknown = set(rdata.keys()) - allowed_region_keys
                if unknown:
                    sys.exit(
                        f"Error: surfaceHandling.surfaces['{name}'].regions['{rname}'] "
                        f"has unknown fields: {sorted(unknown)}.\n"
                        f"       Only 'refinementLevels' is allowed in region entries."
                    )
                if "refinementLevels" in rdata:
                    validate_refinement_levels(rdata["refinementLevels"], f"surfaceHandling.surfaces['{name}'].regions['{rname}']")


def validate_volume_refinement_section(vol_section, geometry_map, extract_from_names=False):
    """Validate volumeRefinement section structure."""
    if not isinstance(vol_section, dict):
        sys.exit("Error: 'volumeRefinement' must be a dictionary")

    validate_selected_parts("volumeRefinement", vol_section, geometry_map, extract_from_names)
    selected_parts = set(vol_section.get("selectedParts", []))

    regions = vol_section.get("regions", {})
    if not isinstance(regions, dict):
        sys.exit("Error: 'volumeRefinement.regions' must be a dictionary")

    for name, entry in regions.items():
        if not isinstance(entry, dict):
            sys.exit(f"Error: volumeRefinement.regions['{name}'] must be a dictionary")

        if name == "__defaults__":
            continue

        if name not in selected_parts:
            is_auto_entry = (
                name in geometry_map and geometry_map[name]['encoded'].get('is_auto', False)
            )
            if not is_auto_entry:
                sys.exit(
                    f"Error: volumeRefinement.regions has an explicit entry for '{name}' "
                    f"but '{name}' is not in selectedParts.\n"
                    f"       Add '{name}' to volumeRefinement.selectedParts to enable the override."
                )

        if "mode" in entry and entry["mode"] not in ["inside", "outside", "distance"]:
            sys.exit(f"Error: volumeRefinement.regions['{name}'].mode must be 'inside', 'outside', or 'distance'")

        if entry.get("mode") == "distance":
            if "levels" not in entry:
                sys.exit(f"Error: volumeRefinement.regions['{name}'] with mode='distance' must have 'levels'")
            if not isinstance(entry["levels"], list) or len(entry["levels"]) == 0:
                sys.exit(f"Error: volumeRefinement.regions['{name}'].levels must be a non-empty array")
            for i, pair in enumerate(entry["levels"]):
                if not isinstance(pair, list) or len(pair) != 2:
                    sys.exit(f"Error: volumeRefinement.regions['{name}'].levels[{i}] must be [distance, level]")
                if not all(isinstance(v, (int, float)) for v in pair):
                    sys.exit(f"Error: volumeRefinement.regions['{name}'].levels[{i}] must contain numbers")


def _register_geometry_entry(raw_key, geom, parsed, src_desc, geometry_map, seen_clean_names, processed, fix_hint):
    """Register a geometry entry, checking for duplicate raw keys and clean names."""
    if raw_key in geometry_map:
        sys.exit(
            f"Error: Duplicate geometry key '{raw_key}'.\n"
            f"       First defined by: {geometry_map[raw_key]['src_desc']}\n"
            f"       Conflicting entry: {src_desc}\n"
            f"       Fix: {fix_hint}"
        )
    clean_name = geom["name"]
    if clean_name in seen_clean_names:
        sys.exit(
            f"Error: Duplicate snappyHexMeshDict name '{clean_name}'.\n"
            f"       Produced by '{raw_key}' and '{seen_clean_names[clean_name]}'.\n"
            f"       Both strip to the same name — rename one."
        )
    seen_clean_names[clean_name] = raw_key
    geometry_map[raw_key] = {'geom': geom, 'encoded': parsed, 'src_desc': src_desc}
    processed.append(geom)


def _empty_parsed(clean_name):
    """Return a no-encoding parsed dict for a geometry entry."""
    return {
        'has_encoding': False, 'is_auto': False, 'clean_name': clean_name,
        'surf_type': None, 'has_cell_zone': False,
        'surf_levels': None, 'vol_mode': None, 'vol_level': None
    }


def process_geometry(config, extract_from_names, convention):
    """
    Process geometry entries, derive names, build geometry_map.
    Returns (processed_list, geometry_map).
    geometry_map key = raw stem (filename stem or shape name as written).
    geom['name'] = clean name (prefix-stripped if encoded), used when writing snappyHexMeshDict.
    """
    if "geometry" not in config:
        return [], {}

    geometry = config["geometry"]
    validate_geometry(geometry, extract_from_names)

    processed = []
    geometry_map = {}
    seen_clean_names = {}  # clean_name -> raw_key (for check #2)

    # Process file-based geometries
    if "files" in geometry:
        filenames = load_geometry_files(geometry["files"])
        for filename in filenames:
            geom = {"file": filename, "is_standard_shape": False}
            file_stem = os.path.splitext(os.path.basename(filename))[0]
            raw_key = file_stem

            if file_stem.startswith("AUTO_"):
                if not extract_from_names:
                    sys.exit(
                        f"Error: '{filename}' uses AUTO_ encoding but "
                        f"'settings.extractRefinementFromNames' is false.\n"
                        f"       Set \"extractRefinementFromNames\": true in snappy_inputs.json "
                        f"to use AUTO_-encoded geometry."
                    )
                parsed = parse_auto_encoded_name(file_stem, convention)
                geom["name"] = parsed['clean_name']
            elif extract_from_names:
                parsed = parse_encoded_name(file_stem, convention)
                geom["name"] = parsed['clean_name']
            else:
                parsed = _empty_parsed(file_stem)
                geom["name"] = file_stem

            src_desc = f"file '{filename}' (stem: '{raw_key}')"

            _register_geometry_entry(
                raw_key, geom, parsed, src_desc,
                geometry_map, seen_clean_names, processed,
                "each file must have a unique stem."
            )

    # Process standard shapes
    for idx, shape in enumerate(geometry.get("standardShapes", [])):
        geom = dict(shape)
        geom["is_standard_shape"] = True
        raw_key = shape["name"]

        if raw_key.startswith("AUTO_"):
            sys.exit(
                f"Error: geometry.standardShapes[{idx}] name '{raw_key}' starts with 'AUTO_'.\n"
                f"       AUTO_ automatic refinement is not supported for standardShapes — "
                f"only for file-based geometry (.stl/.obj).\n"
                f"       Either rename the shape or use explicit refinement levels via "
                f"surfaceHandling / volumeRefinement."
            )

        if extract_from_names:
            parsed = parse_encoded_name(raw_key, convention)
            geom["name"] = parsed['clean_name']
        else:
            parsed = _empty_parsed(raw_key)

        src_desc = f"standard shape '{raw_key}' (type: {shape['type']})"

        _register_geometry_entry(
            raw_key, geom, parsed, src_desc,
            geometry_map, seen_clean_names, processed,
            "shape name must not duplicate a file stem."
        )

    return processed, geometry_map


def _apply_facezone_fields(resolved, clean_name, has_cell_zone):
    """Set faceZone (and optionally cellZone) fields on a resolved surface dict."""
    resolved['faceType']    = 'internal'
    resolved['faceZoneName'] = clean_name
    if has_cell_zone:
        resolved['cellZoneInside'] = 'inside'
        resolved['cellZoneName']   = clean_name


def resolve_surface_handling(config, geometry_map, extract_from_names, auto_levels_map=None):
    """
    Resolve surface refinement for each selected part.
    When extractRefinementFromNames=True, encoded entries with a SURF block are
    auto-included without needing to be in selectedParts.
    AUTO_-encoded entries are always auto-included and get levels from auto_levels_map.
    Resolution order: defaults → encoded name / auto levels → explicit entry (if in selectedParts).
    Returns list of resolved surface refinement dicts.
    """
    surf_section = config.get("surfaceHandling")
    if not surf_section:
        return []

    selected_parts = surf_section.get("selectedParts", [])
    surfaces = surf_section.get("surfaces", {})
    defaults = surfaces.get("__defaults__", {})

    # Build candidate set:
    # 1. Explicit selectedParts
    # 2. AUTO_-encoded entries with a SURF block (always auto-selected)
    # 3. Regular encoded entries with a SURF block (only when extractRefinementFromNames=True)
    candidate_set = list(selected_parts)
    for raw_key, entry in geometry_map.items():
        enc = entry['encoded']
        if raw_key in candidate_set:
            continue
        if enc.get('is_auto') and enc['surf_type'] is not None:
            candidate_set.append(raw_key)
        elif extract_from_names and enc['has_encoding'] and enc['surf_type'] is not None:
            candidate_set.append(raw_key)

    result = []

    for part_name in candidate_set:
        clean_name = geometry_map[part_name]['geom']['name']

        # Start from defaults
        resolved = {
            'name': clean_name,
            'type': defaults.get('type', 'boundary'),
            'refinementLevels': defaults.get('refinementLevels', [0, 0]),
            'faceType': defaults.get('faceType', 'internal'),
            'faceZoneName': None,
            'cellZoneInside': None,
            'cellZoneName': None,
            'regions': None,
        }

        enc = geometry_map[part_name]['encoded']

        # Apply AUTO_ levels (independent of extractRefinementFromNames)
        if enc.get('is_auto') and enc['surf_type'] is not None:
            resolved['type'] = enc['surf_type']
            if auto_levels_map and part_name in auto_levels_map:
                auto = auto_levels_map[part_name]
                resolved['refinementLevels'] = [auto['surface_min'], auto['surface_max']]
            if enc['surf_type'] == 'faceZone':
                _apply_facezone_fields(resolved, clean_name, enc['has_cell_zone'])

        # Apply regular encoded name (when extractRefinementFromNames=True, non-AUTO_)
        elif extract_from_names and enc['has_encoding'] and enc['surf_type'] is not None:
            resolved['type'] = enc['surf_type']
            resolved['refinementLevels'] = enc['surf_levels']
            if enc['surf_type'] == 'faceZone':
                _apply_facezone_fields(resolved, clean_name, enc['has_cell_zone'])

        # Apply explicit entry (overrides encoded and defaults)
        explicit = surfaces.get(part_name, {})
        for key in ('type', 'refinementLevels', 'faceType', 'faceZoneName',
                    'cellZoneInside', 'cellZoneName', 'regions'):
            if key in explicit:
                resolved[key] = explicit[key]

        # Post-processing defaults for faceZone type
        if resolved['type'] == 'faceZone':
            if resolved['faceZoneName'] is None:
                resolved['faceZoneName'] = clean_name
            if resolved['cellZoneInside'] is not None and resolved['cellZoneName'] is None:
                resolved['cellZoneName'] = resolved['faceZoneName']
        else:
            # boundary type: clear faceZone/cellZone fields
            resolved['faceZoneName'] = None
            resolved['cellZoneInside'] = None
            resolved['cellZoneName'] = None

        result.append(resolved)

    return result


def resolve_volume_refinement(config, geometry_map, extract_from_names, auto_levels_map=None):
    """
    Resolve volume refinement for each selected part.
    When extractRefinementFromNames=True, encoded entries with a VOL block are
    auto-included without needing to be in selectedParts.
    AUTO_-encoded entries are always auto-included and get levels from auto_levels_map.
    Resolution order: defaults → encoded name / auto levels → explicit entry (if in selectedParts).
    Returns list of resolved volume refinement dicts.
    """
    vol_section = config.get("volumeRefinement")
    if not vol_section:
        return []

    selected_parts = vol_section.get("selectedParts", [])
    regions = vol_section.get("regions", {})
    defaults = regions.get("__defaults__", {})

    # Build candidate set:
    # 1. Explicit selectedParts
    # 2. AUTO_-encoded entries with a VOL block (always auto-selected)
    # 3. Regular encoded entries with a VOL block (only when extractRefinementFromNames=True)
    candidate_set = list(selected_parts)
    for raw_key, entry in geometry_map.items():
        enc = entry['encoded']
        if raw_key in candidate_set:
            continue
        if enc.get('is_auto') and enc['vol_mode'] is not None:
            candidate_set.append(raw_key)
        elif extract_from_names and enc['has_encoding'] and enc['vol_mode'] is not None:
            candidate_set.append(raw_key)

    result = []

    for part_name in candidate_set:
        clean_name = geometry_map[part_name]['geom']['name']

        # Start from defaults
        resolved = {
            'name': clean_name,
            'mode': defaults.get('mode', 'inside'),
            'level': defaults.get('level', None),
            'levels': defaults.get('levels', None),
        }

        enc = geometry_map[part_name]['encoded']

        # Apply AUTO_ levels (independent of extractRefinementFromNames)
        if enc.get('is_auto') and enc['vol_mode'] is not None:
            resolved['mode'] = enc['vol_mode']
            if auto_levels_map and part_name in auto_levels_map:
                resolved['level'] = auto_levels_map[part_name]['volume_level']
            resolved['levels'] = None

        # Apply regular encoded name (when extractRefinementFromNames=True, non-AUTO_)
        elif extract_from_names and enc['has_encoding'] and enc['vol_mode'] is not None:
            resolved['mode'] = enc['vol_mode']
            resolved['level'] = enc['vol_level']
            resolved['levels'] = None

        # Apply explicit entry (overrides)
        explicit = regions.get(part_name, {})
        if explicit:
            if 'mode' in explicit:
                resolved['mode'] = explicit['mode']
            if 'level' in explicit:
                resolved['level'] = explicit['level']
                resolved['levels'] = None
            if 'levels' in explicit:
                resolved['levels'] = explicit['levels']
                resolved['level'] = None
                if 'mode' not in explicit:
                    resolved['mode'] = 'distance'

        # Distance mode must have explicit levels (cannot come from encoding alone)
        if resolved['mode'] == 'distance' and not resolved['levels']:
            sys.exit(
                f"Error: volumeRefinement for '{part_name}' has mode='distance' but no 'levels'. "
                f"Distance mode cannot come from encoded names — must be explicit."
            )

        result.append(resolved)

    return result


def get_template_dir():
    """Get the templates directory path."""
    template_dir = Path(SCRIPT_DIR) / "templates"
    if not template_dir.exists():
        sys.exit(f"Error: templates directory not found at {template_dir}")
    return template_dir


def render_template(config, geometry, surface_refinements, volume_refinements, template_dir, openfoam_version="2506"):
    """Render snappyHexMeshDict template with configuration."""
    env = Environment(loader=FileSystemLoader(template_dir))

    try:
        template = env.get_template("snappyHexMeshDict.template")
    except TemplateNotFound:
        sys.exit(f"Error: snappyHexMeshDict.template not found in {template_dir}")

    try:
        rendered = template.render(
            openfoamVersion=openfoam_version,
            addLayers=config["settings"]["addLayers"],
            mergeTolerance=config["settings"]["mergeTolerance"],
            castellatedMeshControls=config["castellatedMeshControls"],
            locationInMesh=config["castellatedMeshControls"]["locationInMesh"],
            snapControls=config["snapControls"],
            addLayersControls=config["addLayersControls"],
            meshQualityControls=config["meshQualityControls"],
            geometry=geometry,
            surface_refinements=surface_refinements,
            volume_refinements=volume_refinements,
            castellatedMesh=True,
            snap=True
        )
    except Exception as e:
        sys.exit(f"Error: Failed to render template: {e}")

    return rendered


def ensure_system_directory():
    """Create system directory if it doesn't exist."""
    system_dir = Path("system")
    system_dir.mkdir(exist_ok=True, parents=True)
    return system_dir


def write_snappyhexmeshdict(rendered_content, output_dir="system"):
    """Write rendered snappyHexMeshDict to output directory."""
    output_file = Path(output_dir) / "snappyHexMeshDict"

    try:
        with open(output_file, 'w') as f:
            f.write(rendered_content)
    except IOError as e:
        sys.exit(f"Error: Failed to write snappyHexMeshDict: {e}")

    return output_file


def compute_block_mesh_params(bm_config):
    """
    Compute blockMeshDict vertex coordinates and cell counts from a validated
    backgroundMesh config dict. Uses trimesh to load the reference geometry file
    and derive its bounding box, then expands it by enlargementFactor and snaps
    maxCoords to exact multiples of the base grid.

    Returns dict with keys: xMin, yMin, zMin, xMax, yMax, zMax, nx, ny, nz.
    """
    if trimesh is None:
        sys.exit(
            "Error: 'trimesh' library is required for backgroundMesh generation.\n"
            "       Install it with: pip install trimesh"
        )

    ref_geom = bm_config["referenceGeometry"]
    tri_surface_path = os.path.join("constant", "triSurface", ref_geom)

    try:
        mesh = trimesh.load(tri_surface_path, force='mesh')
    except Exception as e:
        sys.exit(f"Error: Failed to load '{tri_surface_path}' with trimesh: {e}")

    bounds = mesh.bounds  # shape (2, 3): [[xMin, yMin, zMin], [xMax, yMax, zMax]]
    min_coords = list(bounds[0])
    max_coords = list(bounds[1])

    ef = bm_config["enlargementFactor"]
    for i in range(3):
        centre = 0.5 * (min_coords[i] + max_coords[i])
        min_coords[i] = centre - ef * (centre - min_coords[i])
        max_coords[i] = centre + ef * (max_coords[i] - centre)

    dx, dy, dz = bm_config["_baseGrid"]
    deltas = [dx, dy, dz]
    cell_counts = []
    for i in range(3):
        length = max_coords[i] - min_coords[i]
        if length <= 0:
            sys.exit(f"Error: Bounding box has zero or negative extent in axis {i}. Check geometry file.")
        if length <= deltas[i]:
            sys.exit(
                f"Error: Bounding box extent in axis {i} ({length:.6g}) is not greater than baseGrid ({deltas[i]:.6g})."
            )
        n = math.ceil(length / deltas[i])
        max_coords[i] = min_coords[i] + n * deltas[i]
        cell_counts.append(n)

    return {
        "xMin": min_coords[0], "yMin": min_coords[1], "zMin": min_coords[2],
        "xMax": max_coords[0], "yMax": max_coords[1], "zMax": max_coords[2],
        "nx": cell_counts[0], "ny": cell_counts[1], "nz": cell_counts[2],
    }


def render_block_mesh_template(params, openfoam_version, template_dir):
    """Render blockMeshDict template with computed parameters."""
    env = Environment(loader=FileSystemLoader(template_dir))
    try:
        template = env.get_template("blockMeshDict.template")
    except TemplateNotFound:
        sys.exit(f"Error: blockMeshDict.template not found in {template_dir}")

    try:
        rendered = template.render(openfoamVersion=openfoam_version, **params)
    except Exception as e:
        sys.exit(f"Error: Failed to render blockMeshDict template: {e}")

    return rendered


def write_blockmeshdict(rendered_content, output_dir="system"):
    """Write rendered blockMeshDict to output directory."""
    output_file = Path(output_dir) / "blockMeshDict"
    try:
        with open(output_file, 'w') as f:
            f.write(rendered_content)
    except IOError as e:
        sys.exit(f"Error: Failed to write blockMeshDict: {e}")
    return output_file


def _check_dependencies():
    """Verify required packages are installed and warn about optional ones."""
    missing_required = []
    missing_optional = []

    try:
        import jinja2  # noqa: F401
    except ImportError:
        missing_required.append("jinja2")

    for pkg in ("trimesh", "numpy"):
        try:
            __import__(pkg)
        except ImportError:
            missing_optional.append(pkg)

    if missing_required:
        pkgs = " ".join(missing_required)
        print(f"ERROR: Missing required package(s): {pkgs}")
        print(f"       Install with:  pip install {pkgs}")
        sys.exit(1)

    if missing_optional:
        pkgs = " ".join(missing_optional)
        print(f"Note: Optional package(s) not found: {pkgs}")
        print(f"      Install with:  pip install {pkgs}")
        print("      (Required only for the AUTO_ auto-refinement feature)")


def main():
    """Main workflow: Load config, validate, render template, write output."""
    _check_dependencies()
    print("Loading snappy_inputs.json...")
    config = load_snappy_config()

    # Startup banner
    json_ver = config.get("_version", None)
    print("━" * 55)
    print(f"  snappyHexMeshDict Generator")
    print(f"  JSON config version : {JSON_VERSION}  ({JSON_VERSION_DATE})")
    print(f"  Target OpenFOAM     : {OPENFOAM_VERSION}")
    if json_ver is None:
        print(f"  Note: '_version' not set in config — add"
              f" \"_version\": \"{JSON_VERSION}\" to your snappy_inputs.json")
    elif str(json_ver) != JSON_VERSION:
        print(f"  ⚠ Warning: config '_version' ({json_ver}) differs from "
              f"tool version ({JSON_VERSION}). Check CHANGELOG.md.")
    print("━" * 55)

    print("Validating configuration...")
    validate_config(config)
    bm_config = validate_background_mesh(config)

    extract_from_names = config["settings"].get("extractRefinementFromNames", False)
    convention = config["encodingConvention"]
    of_version_str = OPENFOAM_VERSION.lstrip("v")  # strip leading 'v' for OF header

    print("Processing geometry...")
    geometry, geometry_map = process_geometry(config, extract_from_names, convention)

    if "surfaceHandling" in config:
        validate_surface_handling_section(config["surfaceHandling"], geometry_map, extract_from_names)

    if "volumeRefinement" in config:
        validate_volume_refinement_section(config["volumeRefinement"], geometry_map, extract_from_names)

    # Auto-refinement: detect AUTO_-encoded files and compute levels
    has_auto_entries = any(
        entry['encoded'].get('is_auto', False) for entry in geometry_map.values()
    )
    auto_levels_map = {}
    if has_auto_entries:
        print("Computing auto-refinement levels...")
        auto_params = validate_auto_refinement_params(config)
        auto_levels_map = compute_auto_levels_for_geometry(geometry_map, bm_config, auto_params)
        print(f"  Auto-refinement complete: {len(auto_levels_map)} geometry file(s) processed.")

    print("Resolving surface handling...")
    surface_refinements = resolve_surface_handling(
        config, geometry_map, extract_from_names, auto_levels_map
    )

    print("Resolving volume refinement...")
    volume_refinements = resolve_volume_refinement(
        config, geometry_map, extract_from_names, auto_levels_map
    )

    print("Getting template directory...")
    template_dir = get_template_dir()

    print("Rendering snappyHexMeshDict template...")
    rendered_content = render_template(
        config, geometry, surface_refinements, volume_refinements,
        template_dir, of_version_str
    )

    print("Creating system directory...")
    ensure_system_directory()

    print("Writing snappyHexMeshDict...")
    output_file = write_snappyhexmeshdict(rendered_content)

    print(f"✅ Successfully generated {output_file}")
    print(f"   Configuration: addLayers={config['settings']['addLayers']}, mergeTolerance={config['settings']['mergeTolerance']}")
    print(f"   Geometry entries:     {len(geometry)}")
    print(f"   Surface refinements:  {len(surface_refinements)}")
    print(f"   Volume refinements:   {len(volume_refinements)}")

    print("Computing background mesh bounding box...")
    bm_params = compute_block_mesh_params(bm_config)

    print("Rendering blockMeshDict template...")
    bm_rendered = render_block_mesh_template(bm_params, of_version_str, template_dir)

    print("Writing blockMeshDict...")
    bm_file = write_blockmeshdict(bm_rendered)

    print(f"✅ Successfully generated {bm_file}")
    print(f"   Reference geometry:  {bm_config['referenceGeometry']}")
    print(f"   Enlargement factor:  {bm_config['enlargementFactor']}")
    print(f"   Base grid (dx,dy,dz): {bm_config['_baseGrid']}")
    print(f"   Cell counts (nx,ny,nz): ({bm_params['nx']}, {bm_params['ny']}, {bm_params['nz']})")


if __name__ == "__main__":
    main()
