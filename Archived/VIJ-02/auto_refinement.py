"""
auto_refinement.py — Auto-refinement level computation for snappyHexMesh.

Provides:
  - parse_auto_encoded_name()         : parse AUTO_-prefixed geometry filenames
  - validate_auto_refinement_params() : validate the autoRefinementParams config section
  - compute_auto_levels_for_geometry(): run derive_snappy_levels() for every AUTO_ file
  - derive_snappy_levels()            : core geometry analysis (ported from
                                        get_grid_info_from_geometry.py, locationInMesh excluded)

AUTO_ encoding is only available when settings.extractRefinementFromNames = true.
Calling setup_snappy.py with AUTO_-encoded files while extractRefinementFromNames is
false is a fatal error (detected in process_geometry() in setup_snappy.py).
"""

import os
import re
import sys
from collections import defaultdict

# encoding_utils lives in the same directory; sys.path is extended by setup_snappy.py
# before this module is imported, so the import always succeeds.
from encoding_utils import build_tags, decode_surf_tag, vol_direction, empty_encoded_result

try:
    import numpy as np
    import trimesh as _trimesh
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------

def _check_deps(context):
    if not _DEPS_AVAILABLE:
        sys.exit(
            f"Error: 'numpy' and 'trimesh' are required for {context}.\n"
            "       Install them with: pip install numpy trimesh"
        )


# ---------------------------------------------------------------------------
# Private geometry-analysis helpers
# ---------------------------------------------------------------------------

def _compute_char_length(mesh, gap_multiplier):
    """
    Characteristic length of the geometry.

    Watertight (closed) meshes:
      - Compact (sphericity > 0.6): L_c = V^(1/3)
      - Flat/elongated (sphericity <= 0.6): L_c = gap_multiplier * V / A  (hydraulic diameter)

    Open meshes:
      L_c = min(sqrt(A), max_edge_length)

    Returns (char_length, is_closed, sphericity).
    """
    is_closed = mesh.is_watertight
    area = mesh.area
    sphericity = None

    if is_closed:
        vol = abs(mesh.volume)
        sphericity = (np.pi ** (1 / 3) * (6 * vol) ** (2 / 3)) / area if area > 0 else 0.0
        if sphericity > 0.6:
            char_length = vol ** (1 / 3)
        else:
            char_length = gap_multiplier * (vol / area)
    else:
        char_length = min(np.sqrt(area), np.max(mesh.edges_unique_length))

    return char_length, is_closed, sphericity


def _level_from_size(base_grid_size, target_size):
    """Refinement level needed to achieve target_size from base_grid_size."""
    if target_size < 1e-12:
        return 0
    return max(0, int(np.ceil(np.log2(base_grid_size / target_size))))


def _surface_min_level(char_length, surface_resolution_cells, base_grid_size):
    """Min surface level: ensures the whole surface is resolved proportionally to its scale."""
    return _level_from_size(base_grid_size, char_length / surface_resolution_cells)


def _surface_min_level_from_bbox(mesh, min_cells_across, base_grid_size):
    """
    Floor on surface_min based on the median bounding-box dimension.
    Guarantees at least min_cells_across cells span the median dimension.
    Returns (floor_level, median_bb).
    """
    extents = mesh.bounding_box.extents
    median_bb = float(np.median(extents))
    if min_cells_across <= 0 or median_bb < 1e-12:
        return 0, median_bb
    return _level_from_size(base_grid_size, median_bb / min_cells_across), median_bb


def _surface_max_level_from_features(mesh, feature_angle_rad, feature_resolution_cells,
                                     base_grid_size, char_length, noise_ratio):
    """
    Max surface refinement level driven by sharp geometric feature edges
    (dihedral > feature_angle_rad).

    Feature edges are grouped into connected curves (tessellation-invariant).
    Curves shorter than char_length / noise_ratio are dropped as CAD noise.
    The 10th percentile of remaining curve lengths drives the level.

    Returns (level, L_feature, n_total, n_after_filter) or (None, None, 0, 0).
    """
    if len(mesh.face_adjacency_angles) == 0:
        return None, None, 0, 0

    feature_mask = mesh.face_adjacency_angles > feature_angle_rad
    if not np.any(feature_mask):
        return None, None, 0, 0

    feature_edges = mesh.face_adjacency_edges[feature_mask]
    v = mesh.vertices
    edge_lengths = np.linalg.norm(v[feature_edges[:, 0]] - v[feature_edges[:, 1]], axis=1)

    degree = np.zeros(len(v), dtype=int)
    for e in feature_edges:
        degree[e[0]] += 1
        degree[e[1]] += 1

    n_real = len(v)
    virtual_id = np.full((len(feature_edges), 2), -1, dtype=int)
    next_virtual = n_real

    for i, e in enumerate(feature_edges):
        for side, vi in enumerate(e):
            if degree[vi] != 2:
                virtual_id[i, side] = next_virtual
                next_virtual += 1
            else:
                virtual_id[i, side] = vi

    parent = np.arange(next_virtual)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(feature_edges)):
        rx, ry = find(virtual_id[i, 0]), find(virtual_id[i, 1])
        if rx != ry:
            parent[rx] = ry

    curve_lengths = defaultdict(float)
    for i in range(len(feature_edges)):
        curve_lengths[find(virtual_id[i, 0])] += edge_lengths[i]

    all_curves = np.array(list(curve_lengths.values()))
    n_total = len(all_curves)

    noise_threshold = char_length / noise_ratio
    valid_curves = all_curves[all_curves >= noise_threshold]
    n_filtered = len(valid_curves)

    if n_filtered == 0:
        return None, None, n_total, 0

    L_feature = float(np.percentile(valid_curves, 10))
    level = _level_from_size(base_grid_size, L_feature / feature_resolution_cells)
    return level, L_feature, n_total, n_filtered


def _surface_max_level_from_curvature(mesh, feature_angle_rad, feature_resolution_cells,
                                      base_grid_size):
    """
    Max surface refinement level from smooth surface curvature (Gaussian curvature).
    Only vertices NOT on sharp feature edges are considered.
    The 10th percentile of radius-of-curvature drives the level.

    Returns (level, R_min) or (None, None) if no smoothly curved regions found.
    """
    if len(mesh.face_adjacency_angles) == 0:
        return None, None

    feature_mask = mesh.face_adjacency_angles > feature_angle_rad
    feature_verts = np.unique(mesh.face_adjacency_edges[feature_mask])
    smooth_verts = np.setdiff1d(np.arange(len(mesh.vertices)), feature_verts)

    if len(smooth_verts) == 0:
        return None, None

    defects = mesh.vertex_defects
    face_areas = mesh.area_faces
    vf = mesh.vertex_faces

    voronoi_area = np.array([
        np.sum(face_areas[vf[i][vf[i] >= 0]]) / 3.0
        for i in smooth_verts
    ])
    K_gauss = np.where(voronoi_area > 1e-15, defects[smooth_verts] / voronoi_area, 0.0)

    K_pos = K_gauss[K_gauss > 1e-6]
    if len(K_pos) == 0:
        return None, None

    R_min = float(np.percentile(1.0 / np.sqrt(K_pos), 10))
    level = _level_from_size(base_grid_size, R_min / feature_resolution_cells)
    return level, R_min


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def derive_snappy_levels(stl_path, base_grid_size, surface_resolution_cells,
                         feature_resolution_cells=2.0, volume_resolution_cells=10.0,
                         gap_multiplier=3.0, feature_angle=30.0,
                         noise_ratio=20.0, max_level_gap=2, min_cells_across=10):
    """
    Derive snappyHexMesh surface and volume refinement levels from a geometry file.

    Surface refinement:
      - Min level: stricter of two floors:
          (a) char_length / surface_resolution_cells
          (b) median_bb / min_cells_across  (bounding-box floor)
      - Max level: most demanding of sharp feature edges and smooth curvature,
        capped at surface_min + max_level_gap to prevent runaway refinement.

    Volume refinement:
      - char_length / volume_resolution_cells, capped at surface_min.

    Open meshes:
      Supported. char_length uses min(sqrt(A), max_edge_length). Feature and
      curvature paths still run. A warning flag 'is_watertight': False is set
      in the returned dict — treat results with caution for open surfaces.

    Returns dict with keys: status, is_watertight, surface_min, surface_max,
                            volume_level, diagnostics.
    On error: {"status": "error", "message": <str>}.
    """
    _check_deps("auto-refinement level computation")

    try:
        mesh = _trimesh.load(stl_path, force='mesh')
        mesh.process()

        if len(mesh.faces) == 0:
            raise ValueError("The geometry file is empty or contains only degenerate faces.")

        char_length, is_closed, sphericity = _compute_char_length(mesh, gap_multiplier)
        feature_angle_rad = np.radians(feature_angle)

        level_min_char = _surface_min_level(char_length, surface_resolution_cells, base_grid_size)
        level_min_bbox, median_bb = _surface_min_level_from_bbox(
            mesh, min_cells_across, base_grid_size
        )
        level_min = max(level_min_char, level_min_bbox)
        bbox_floor_active = level_min_bbox > level_min_char

        level_max_feature, L_feature, n_curves_total, n_curves_used = \
            _surface_max_level_from_features(
                mesh, feature_angle_rad, feature_resolution_cells,
                base_grid_size, char_length, noise_ratio
            )
        level_max_curvature, R_min_curvature = _surface_max_level_from_curvature(
            mesh, feature_angle_rad, feature_resolution_cells, base_grid_size
        )

        candidates = [level_min]
        if level_max_feature is not None:
            candidates.append(level_max_feature)
        if level_max_curvature is not None:
            candidates.append(level_max_curvature)
        level_max_raw = max(candidates)

        level_max = min(level_max_raw, level_min + max_level_gap)
        gap_capped = level_max < level_max_raw

        level_vol = _level_from_size(base_grid_size, char_length / volume_resolution_cells)
        level_vol = min(level_vol, level_min)

        return {
            "status":       "success",
            "is_watertight": bool(is_closed),
            "surface_min":  int(level_min),
            "surface_max":  int(level_max),
            "volume_level": int(level_vol),
            "diagnostics": {
                "sphericity":                float(sphericity) if sphericity is not None else None,
                "char_length":               float(char_length),
                "median_bb":                 float(median_bb),
                "level_min_from_char_length": int(level_min_char),
                "level_min_from_bbox_floor":  int(level_min_bbox),
                "bbox_floor_active":          bbox_floor_active,
                "level_max_from_features":    int(level_max_feature) if level_max_feature is not None else None,
                "smallest_feature_curve":     L_feature,
                "feature_curves_total":       n_curves_total,
                "feature_curves_used":        n_curves_used,
                "level_max_from_curvature":   int(level_max_curvature) if level_max_curvature is not None else None,
                "min_radius_of_curvature":    R_min_curvature,
                "level_gap_capped":           gap_capped,
            }
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# AUTO_ name parsing
# ---------------------------------------------------------------------------

def parse_auto_encoded_name(raw_name, convention):
    """
    Parse an AUTO_-prefixed geometry filename stem.

    Only called when settings.extractRefinementFromNames = true (enforced in
    process_geometry() in setup_snappy.py).

    Format (level numbers must NOT be specified — they are auto-derived):
        AUTO_<SURF>_(<BND>|<FZ>|<FZ>_<CZ>)_[<VOL>_(IN|OUT)_]<cleanName>
        AUTO_<VOL>_(IN|OUT)_<cleanName>

    Fatal error if:
      - The AUTO_ block cannot be decoded.
      - Explicit level numbers (e.g. _L1_L2_) are present after the surf/vol tag.

    Returns the same dict shape as parse_encoded_name() in setup_snappy.py,
    with surf_levels=None and vol_level=None (filled later by
    compute_auto_levels_for_geometry), plus 'is_auto': True.
    """
    AUTO_PREFIX = "AUTO_"
    tags = build_tags(convention)

    if not raw_name.startswith(AUTO_PREFIX):
        sys.exit(
            f"Internal error: parse_auto_encoded_name called on '{raw_name}' "
            f"which does not start with '{AUTO_PREFIX}'."
        )

    result            = empty_encoded_result(raw_name)
    result['is_auto'] = True
    result['has_encoding'] = True

    remaining = raw_name[len(AUTO_PREFIX):]

    # ---- SURF block (no level numbers) ----
    if remaining.startswith(tags['surf_prefix']):
        surf_pattern = (
            rf'^{re.escape(tags["surf_prefix"])}'
            rf'({tags["surf_tags_pattern"]})_(.+)$'
        )
        m = re.match(surf_pattern, remaining)
        if not m:
            sys.exit(
                f"Error: '{raw_name}' has AUTO_ prefix with SURF block but could not be decoded.\n"
                f"       Expected: AUTO_{tags['surf_prefix']}"
                f"({tags['bnd_tag']}|{tags['fz_tag']}|{tags['fz_cz_tag']})"
                f"_[{tags['vol_prefix']}(IN|OUT)_]<name>\n"
                f"       Example:  AUTO_{tags['surf_prefix']}{tags['fz_cz_tag']}"
                f"_{tags['vol_prefix']}IN_mosfet"
            )

        result['surf_type'], result['has_cell_zone'] = decode_surf_tag(m.group(1), tags)
        remaining = m.group(2)

        # Guard: level numbers must not follow the surf tag in AUTO_ names
        if re.match(r'^L\d+_', remaining):
            sys.exit(
                f"Error: '{raw_name}' is AUTO_-encoded but contains explicit level numbers.\n"
                f"       AUTO_ entries must not specify refinement levels — they are computed automatically.\n"
                f"       Remove the level numbers and use: "
                f"AUTO_{tags['surf_prefix']}{m.group(1)}_[{tags['vol_prefix']}(IN|OUT)_]<name>"
            )

    # ---- VOL block (no level number) ----
    if remaining.startswith(tags['vol_prefix']):
        vol_pattern = rf'^{re.escape(tags["vol_prefix"])}(IN|OUT)_(.+)$'
        m = re.match(vol_pattern, remaining)
        if not m:
            sys.exit(
                f"Error: '{raw_name}' has AUTO_ prefix with VOL block that could not be decoded.\n"
                f"       Expected: {tags['vol_prefix']}(IN|OUT)_<name>\n"
                f"       Example:  AUTO_{tags['surf_prefix']}{tags['fz_cz_tag']}"
                f"_{tags['vol_prefix']}IN_mosfet"
            )

        remaining = m.group(2)

        # Guard: level numbers must not follow the vol tag in AUTO_ names
        if re.match(r'^L\d+_', remaining):
            sys.exit(
                f"Error: '{raw_name}' is AUTO_-encoded but contains explicit level numbers after VOL tag.\n"
                f"       AUTO_ entries must not specify refinement levels — they are computed automatically."
            )

        result['vol_mode'] = vol_direction(m.group(1))

    if result['surf_type'] is None and result['vol_mode'] is None:
        sys.exit(
            f"Error: '{raw_name}' starts with 'AUTO_' but contains no recognisable SURF or VOL block.\n"
            f"       Expected at least one of: AUTO_{tags['surf_prefix']}... or AUTO_{tags['vol_prefix']}...\n"
            f"       Example: AUTO_{tags['surf_prefix']}{tags['fz_cz_tag']}_{tags['vol_prefix']}IN_mosfet"
        )

    result['clean_name'] = remaining
    return result


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def validate_auto_refinement_params(config):
    """
    Validate the autoRefinementParams section.
    Called only when at least one AUTO_-prefixed geometry file is present.

    Mandatory (must appear in snappy_inputs.json):
        surfaceResolutionCells  — positive number, typical range 3–10

    Optional (defaults live in defaults.json):
        featureResolutionCells, volumeResolutionCells, featureAngle,
        noiseRatio, gapMultiplier, maxLevelGap, minCellsAcross

    Returns the merged params dict.
    """
    params = config.get("autoRefinementParams", {})

    if "surfaceResolutionCells" not in params:
        sys.exit(
            "Error: 'autoRefinementParams.surfaceResolutionCells' is required "
            "when using AUTO_-encoded geometry.\n"
            "       Provide a positive number (typical range: 3–10).\n"
            "       Example: \"autoRefinementParams\": {\"surfaceResolutionCells\": 5}"
        )

    src = params["surfaceResolutionCells"]
    if not isinstance(src, (int, float)) or src <= 0:
        sys.exit("Error: 'autoRefinementParams.surfaceResolutionCells' must be a positive number")

    for key in ("featureResolutionCells", "volumeResolutionCells", "featureAngle",
                "noiseRatio", "gapMultiplier"):
        if key in params:
            v = params[key]
            if not isinstance(v, (int, float)) or v <= 0:
                sys.exit(f"Error: 'autoRefinementParams.{key}' must be a positive number")

    for key in ("maxLevelGap", "minCellsAcross"):
        if key in params:
            v = params[key]
            if not isinstance(v, int) or v < 0:
                sys.exit(f"Error: 'autoRefinementParams.{key}' must be a non-negative integer")

    return params


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def compute_auto_levels_for_geometry(geometry_map, bm_config, auto_params):
    """
    Run derive_snappy_levels() for every AUTO_-encoded geometry file.

    For anisotropic baseGrid [dx, dy, dz] the minimum value is used as
    base_grid_size, giving the most conservative (highest) refinement levels.
    A notice is printed when this fallback is applied.

    Prints per-file results (surface [min, max] and volume level) to stdout.
    Prints a warning for open meshes — results are still computed but may be
    less accurate than for watertight geometries.

    standardShapes with AUTO_ encoding are skipped (not yet supported).

    Returns dict: {raw_key: {'surface_min': int, 'surface_max': int, 'volume_level': int}}
    """
    _check_deps("auto-refinement level computation")

    base_grid_values = bm_config["_baseGrid"]
    base_grid_size = min(base_grid_values)

    if len(set(base_grid_values)) > 1:
        print(
            f"  Note: Anisotropic base grid {base_grid_values}. "
            f"Using minimum value {base_grid_size:.6g} as base_grid_size for "
            f"auto-refinement level computation (conservative — gives highest levels)."
        )

    surface_res     = auto_params["surfaceResolutionCells"]
    feature_res     = auto_params.get("featureResolutionCells", 2.0)
    volume_res      = auto_params.get("volumeResolutionCells",  10.0)
    feature_angle   = auto_params.get("featureAngle",           30.0)
    noise_ratio     = auto_params.get("noiseRatio",             20.0)
    max_level_gap   = auto_params.get("maxLevelGap",            3)
    min_cells_across = auto_params.get("minCellsAcross",        10)
    gap_multiplier  = auto_params.get("gapMultiplier",          3.0)

    auto_levels = {}
    count = 0

    for raw_key, entry in geometry_map.items():
        enc = entry['encoded']
        if not enc.get('is_auto', False):
            continue
        if entry['geom'].get('is_standard_shape', False):
            continue  # AUTO_ standardShapes are rejected upstream; skip defensively

        count += 1
        filename = entry['geom']['file']
        stl_path = os.path.join("constant", "triSurface", filename)
        print(f"  [{count}] Computing auto-refinement for '{filename}'...", flush=True)

        result = derive_snappy_levels(
            stl_path=stl_path,
            base_grid_size=base_grid_size,
            surface_resolution_cells=surface_res,
            feature_resolution_cells=feature_res,
            volume_resolution_cells=volume_res,
            gap_multiplier=gap_multiplier,
            feature_angle=feature_angle,
            noise_ratio=noise_ratio,
            max_level_gap=max_level_gap,
            min_cells_across=min_cells_across,
        )

        if result["status"] == "error":
            sys.exit(
                f"Error: Auto-refinement computation failed for '{filename}':\n"
                f"       {result['message']}"
            )

        surf_min  = result['surface_min']
        surf_max  = result['surface_max']
        vol_level = result['volume_level']
        diag      = result['diagnostics']

        if not result['is_watertight']:
            print(
                f"       Warning: '{filename}' is an OPEN mesh (not watertight). "
                f"char_length = min(sqrt(A), max_edge_length). "
                f"Refinement results may be less accurate — verify manually."
            )

        # ---- Surface min criterion ----
        lmin_char = diag['level_min_from_char_length']
        lmin_bbox = diag['level_min_from_bbox_floor']
        if diag['bbox_floor_active']:
            surf_min_criterion = (
                f"bbox floor (median_bb={diag['median_bb']:.4g}, "
                f"minCellsAcross → level {lmin_bbox})  "
                f"[char_length path gave level {lmin_char}]"
            )
        else:
            surf_min_criterion = (
                f"char_length={diag['char_length']:.4g} / surfaceResolutionCells "
                f"→ level {lmin_char}"
                + (f"  [bbox floor gave level {lmin_bbox}]" if lmin_bbox > 0 else "")
            )

        # ---- Surface max criterion ----
        lmax_feat = diag['level_max_from_features']
        lmax_curv = diag['level_max_from_curvature']
        if lmax_feat is None and lmax_curv is None:
            surf_max_criterion = "= surface_min (no feature edges or curvature detected)"
        else:
            parts = []
            if lmax_feat is not None:
                parts.append(f"feature edges → level {lmax_feat} "
                             f"({diag['feature_curves_used']}/{diag['feature_curves_total']} curves used)")
            if lmax_curv is not None:
                parts.append(f"curvature (R_min={diag['min_radius_of_curvature']:.4g}) → level {lmax_curv}")
            dominant = max(
                (lmax_feat if lmax_feat is not None else -1),
                (lmax_curv if lmax_curv is not None else -1),
            )
            winner = "feature edges" if (lmax_feat is not None and lmax_feat >= (lmax_curv or -1)) else "curvature"
            surf_max_criterion = f"{winner} dominates  [{', '.join(parts)}]"
            if diag['level_gap_capped']:
                surf_max_criterion += f"  → capped by maxLevelGap (raw level {dominant})"

        # ---- Volume criterion ----
        if vol_level == surf_min:
            vol_criterion = f"capped at surface_min ({surf_min})"
        else:
            vol_criterion = (
                f"char_length={diag['char_length']:.4g} / volumeResolutionCells → level {vol_level}"
            )

        print(f"       Surface min [{surf_min}] : {surf_min_criterion}")
        print(f"       Surface max [{surf_max}] : {surf_max_criterion}")
        print(f"       Volume      [{vol_level}] : {vol_criterion}")

        auto_levels[raw_key] = {
            'surface_min':  surf_min,
            'surface_max':  surf_max,
            'volume_level': vol_level,
        }

    return auto_levels
