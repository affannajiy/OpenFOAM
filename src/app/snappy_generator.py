#!/usr/bin/env python3
"""
snappy_generator.py — Backend for Tab 2 (SnappyHexMesh Dict generator and runner).

Renders system/snappyHexMeshDict in one pass from a Jinja2 template
(templates/snappyHexMeshDict.template), following the template+JSON workflow
from workflow_package/openfoam_electronics_thermal_mgmt (Vijay's
setup_snappy.py), then runs snappyHexMesh -overwrite.

Key differences from the old foamDictionary-chain implementation:
  • Whole dictionary written atomically from a template — no partial dicts on
    failure, output is diffable and human-readable.
  • locationInMesh is nudged by +1e-6 so it can never coincide with a
    background-mesh cell face (a classic cause of empty/discarded meshes).
  • faceZone + cellZone surfaces produce named zones so cells INSIDE inner
    solid bodies are kept and tagged instead of silently discarded — this was
    the root cause of "inner cylinder invisible inside the cube".
  • Boundary surfaces get patchInfo { type wall; inGroups (walls); }.
  • Feature snapping is always implicit (no .eMesh files needed) —
    features ( ) stays empty, matching the reference workflow.
  • Layers use snappyHexMesh's built-in medial-axis shrinker — no
    fvSchemes/fvSolution writes needed.
  • The exact GUI inputs are recorded to <case>/snappy_inputs.json so a run
    can be inspected, shared, or reproduced without the GUI.

Config dict schema (passed in from ui_snappy_hex._collect_data):
    {
        "geometry": {
            "files": [
                {
                    "filename": "wall.stl",       # just the filename
                    "surface_type": "boundary",   # "none" | "boundary" | "facezone"
                    "cell_zone": False,            # True only when surface_type=="facezone"
                    "surface_min": 1,
                    "surface_max": 2,
                    "vol_direction": "inside",    # "none" | "inside" | "outside"
                    "vol_level": 2
                }
            ],
            "standard_shapes": [
                {
                    "name": "shape_1",
                    "type": "searchableBox",      # | "searchableSphere" | "searchableCylinder"
                    "params": {
                        "min": [0,0,0], "max": [1,1,1]   # Box
                        # "centre": [0,0,0], "radius": 1  # Sphere
                        # "point1":[0,0,0], "point2":[1,0,0], "radius":0.5  # Cylinder
                    },
                    "vol_direction": "inside",
                    "vol_level": 2
                }
            ]
        },
        "castellated": {
            "geometry_unit": "mm",
            "nCellsBetweenLevels": 2,
            "locationInMesh": [0.0, 0.0, 0.0]
        },
        "snap": {
            "implicitFeatureSnap": True           # kept for compatibility; always implicit
        },
        "layers": {
            "enabled": False,
            "patches": [{"name": "wall", "nSurfaceLayers": 3}]
        }
    }
"""

import os
import json
import subprocess
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULTS_PATH = os.path.join(_HERE, "defaults.json")
_TEMPLATE_DIR = os.path.join(_HERE, "templates")
_OF_BASHRC = "/usr/lib/openfoam/openfoam2506/etc/bashrc"

# Tiny offset added to locationInMesh so the point can never sit exactly on a
# background-mesh cell face/edge (snappyHexMesh discards the mesh in that case).
_LOCATION_OFFSET = 1e-6


def _load_defaults() -> dict:
    """Load defaults.json — the fixed snappyHexMesh control blocks
    (castellated/snap/layers/quality numbers) the GUI does not expose.
    Values stay aligned to the reference workflow (minVol 1e-40, etc.)."""
    with open(_DEFAULTS_PATH) as f:
        return json.load(f)


def _get_jinja_env():
    """Import jinja2 lazily so a missing package produces a friendly message
    in the log drawer instead of killing the whole application at import time."""
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        raise RuntimeError(
            "The 'jinja2' Python package is required to generate snappyHexMeshDict "
            "but is not installed in WSL.\n"
            "Install it with:  sudo apt-get install -y python3-jinja2\n"
            "then click Generate again.")
    return Environment(loader=FileSystemLoader(_TEMPLATE_DIR))


def _get_stl_zone_names(stl_path: str) -> list:
    """Parse solid names from an ASCII STL file."""
    try:
        with open(stl_path, errors="replace") as f:
            lines = f.readlines()
        zones = []
        for line in lines:
            stripped = line.strip().lower()
            if stripped.startswith("solid"):
                parts = line.strip().split(maxsplit=1)
                zones.append(parts[1] if len(parts) > 1 else "Unnamed")
        return zones
    except Exception:
        return []


def _find_file_in_constant(fname: str, constant_dir: str) -> str | None:
    """Walk constant/ to find the actual path of a geometry file."""
    for root, _, fnames in os.walk(constant_dir):
        if fname in fnames:
            return os.path.join(root, fname)
    return None


def _mesh_name_for_stl(fname: str, const_dir: str) -> tuple[str, list]:
    """
    Pick the OpenFOAM mesh/patch name for an STL file plus its zone list.

    If the STL has exactly one named solid (e.g. `solid external-walls`), use
    that solid name — OpenFOAM derives the patch name from the STL solid, not
    the filename, so the dict must reference the solid name to connect
    geometry → refinementSurfaces → boundary patch.

    Falls back to the filename stem for multi-zone STLs (handled per-region),
    files with a single unnamed solid, and non-STL geometry.
    """
    stem = os.path.splitext(fname)[0]
    if not fname.lower().endswith(".stl"):
        return stem, []
    path = _find_file_in_constant(fname, const_dir)
    if not path:
        return stem, []
    zones = _get_stl_zone_names(path)
    if len(zones) == 1 and zones[0] != "Unnamed":
        return zones[0], zones
    return stem, zones


def validate_config(config: dict) -> None:
    """
    Check the GUI config for common misconfigurations that produce broken or
    empty meshes, and raise ValueError with a human-readable message.

    Catches errors the UI cannot easily express as widget constraints:
      • locationInMesh == (0, 0, 0)  — almost always landing on a face/edge
      • no STL has surface_type != "none"  — nothing for snapping to attach to
      • every STL has vol_direction == "outside"  — likely a misuse of the field
      • surface_max < surface_min  — refinement levels are inverted

    Called at the start of generate_and_run() so backend invocations from
    scripts (not just the GUI) get the same guard.
    """
    files = config.get("geometry", {}).get("files", [])
    cast  = config.get("castellated", {})

    loc = cast.get("locationInMesh", [0.0, 0.0, 0.0])
    if all(float(c) == 0.0 for c in loc):
        raise ValueError(
            "locationInMesh is (0, 0, 0) — this will almost always land on a face "
            "or edge and snappyHexMesh will discard the mesh.\n"
            "Use the 'Suggest point' button or enter a point strictly inside "
            "your fluid domain.")

    for f in files:
        smin = f.get("surface_min", 0)
        smax = f.get("surface_max", 0)
        if f.get("surface_type", "none").lower() != "none" and smax < smin:
            raise ValueError(
                f"{f.get('filename', '?')}: S.Max ({smax}) must be >= S.Min ({smin}).")

    has_surface = any(
        f.get("surface_type", "none").lower() != "none" for f in files)
    if files and not has_surface:
        raise ValueError(
            "No STL has a Surface Type set — snappyHexMesh has no patches to snap "
            "to and will produce an empty mesh.\n"
            "Set the outer domain to Boundary and inner solid bodies to "
            "FaceZone with Cell Zone ticked in Section 01.")

    vol_dirs = [f.get("vol_direction", "none").lower() for f in files]
    non_none = [v for v in vol_dirs if v != "none"]
    if non_none and all(v == "outside" for v in non_none):
        raise ValueError(
            "Every STL with a Vol Direction is set to Outside — this is almost "
            "always wrong.\n"
            "For an outer domain box, use Vol Direction = None.\n"
            "For a solid body in fluid, use Vol Direction = Inside.")


def _flatten_shape(shape: dict) -> dict:
    """Flatten a GUI standard-shape dict into a template geometry entry."""
    geom = {"name": shape["name"], "type": shape["type"], "is_standard_shape": True}
    geom.update(shape.get("params", {}))
    return geom


def _build_render_context(config: dict, case_dir: str, defaults: dict, log_cb) -> dict:
    """Translate the GUI config into the variables the Jinja2 template expects."""
    geom_cfg   = config.get("geometry", {})
    cast_cfg   = config.get("castellated", {})
    layers_cfg = config.get("layers", {})
    files_cfg  = geom_cfg.get("files", [])
    shapes_cfg = geom_cfg.get("standard_shapes", [])
    add_layers = layers_cfg.get("enabled", False)

    const_dir = os.path.join(case_dir, "constant")

    geometry = []
    surface_refinements = []
    volume_refinements = []

    # One pass over the GUI file rows: each row contributes up to three things —
    # a geometry{} entry (always), a refinementSurfaces entry (if it has a
    # surface type), and a refinementRegions entry (if it has a Vol Direction).
    for finfo in files_cfg:
        fname = finfo["filename"]
        mesh_name, zones = _mesh_name_for_stl(fname, const_dir)
        finfo["_mesh_name"] = mesh_name

        geom = {"file": fname, "name": mesh_name, "is_standard_shape": False}
        if len(zones) > 1:
            # Multi-solid STL: list every solid as a named region so each one
            # becomes its own patch in the final mesh.
            geom["regions"] = [{"originalName": z, "renamedAs": z} for z in zones]
        geometry.append(geom)

        surf_type = finfo.get("surface_type", "none").lower()
        cell_zone = finfo.get("cell_zone", False)
        vol_dir   = finfo.get("vol_direction", "none").lower()

        if surf_type != "none":
            surf = {
                "name": mesh_name,
                "refinementLevels": [finfo.get("surface_min", 0), finfo.get("surface_max", 1)],
                "type": "faceZone" if surf_type == "facezone" else "boundary",
                "regions": None,
                "faceZoneName": None,
                "faceType": None,
                "cellZoneInside": None,
                "cellZoneName": None,
            }
            if surf["type"] == "faceZone":
                # Solid body inside the domain: tag its faces (faceZone) and —
                # when Cell Zone is ticked — keep and name the cells inside it
                # (cellZoneInside/cellZone). Without the cell zone the inner
                # cells are thrown away, which made inner solids "invisible".
                surf["faceZoneName"] = mesh_name
                surf["faceType"] = "internal"
                if cell_zone:
                    surf["cellZoneInside"] = "inside"
                    surf["cellZoneName"] = mesh_name
                else:
                    log_cb(
                        f"[warn] {fname}: FaceZone without Cell Zone — faces are tagged "
                        "but cells inside are NOT kept as a named group. Tick Cell Zone "
                        "if this is a solid body inside the domain.", "warn")
            surface_refinements.append(surf)

        if vol_dir in ("inside", "outside"):
            volume_refinements.append({
                "name": mesh_name,
                "mode": vol_dir,
                "level": finfo.get("vol_level", 1),
            })
        elif surf_type == "facezone" and cell_zone:
            log_cb(
                f"[info] {fname}: tip — Vol Dir = Inside adds refinement inside this "
                "body and helps snappyHexMesh capture small parts.", "info")

    for shape in shapes_cfg:
        geometry.append(_flatten_shape(shape))
        vol_dir = shape.get("vol_direction", "none").lower()
        if vol_dir in ("inside", "outside"):
            volume_refinements.append({
                "name": shape["name"],
                "mode": vol_dir,
                "level": shape.get("vol_level", 1),
            })

    # locationInMesh: apply the anti-cell-face nudge (in-memory only)
    loc = [float(v) + _LOCATION_OFFSET for v in cast_cfg.get("locationInMesh", [0, 0, 0])]

    # castellatedMeshControls: defaults + GUI override for nCellsBetweenLevels
    cmc = dict(defaults.get("castellatedMeshControls", {}))
    cmc["nCellsBetweenLevels"] = cast_cfg.get(
        "nCellsBetweenLevels", cmc.get("nCellsBetweenLevels", 2))

    # addLayersControls: defaults + per-patch layers dict from the GUI
    alc = dict(defaults.get("addLayersControls", {}))
    layers = {}
    if add_layers:
        for patch_info in layers_cfg.get("patches", []):
            layers[patch_info["name"]] = {
                "nSurfaceLayers": patch_info.get("nSurfaceLayers", 3)}
    alc["layers"] = layers

    return {
        "openfoamVersion": "v" + str(defaults.get("settings", {}).get("openfoamVersion", "2506")),
        "castellatedMesh": True,
        "snap": True,
        "addLayers": add_layers,
        "geometry": geometry,
        "surface_refinements": surface_refinements,
        "volume_refinements": volume_refinements,
        "locationInMesh": loc,
        "castellatedMeshControls": cmc,
        "snapControls": defaults.get("snapControls", {}),
        "addLayersControls": alc,
        "meshQualityControls": defaults.get("meshQualityControls", {}),
        "mergeTolerance": defaults.get("settings", {}).get("mergeTolerance", 1e-6),
    }


def _write_inputs_record(config: dict, case_dir: str, defaults: dict, log_cb) -> None:
    """
    Write snappy_inputs.json into the case directory — a human-readable record
    of exactly what the GUI meshed, in a schema close to the reference
    workflow's (workflow_package). Informational only: the engine renders from
    the in-memory config, never from this file.
    """
    files_cfg  = config.get("geometry", {}).get("files", [])
    shapes_cfg = config.get("geometry", {}).get("standard_shapes", [])
    cast_cfg   = config.get("castellated", {})
    layers_cfg = config.get("layers", {})

    surfaces = {}
    vol_regions = {}
    surf_selected = []
    vol_selected = []

    for finfo in files_cfg:
        stem = os.path.splitext(finfo["filename"])[0]
        surf_type = finfo.get("surface_type", "none").lower()
        if surf_type != "none":
            surf_selected.append(stem)
            entry = {
                "type": "faceZone" if surf_type == "facezone" else "boundary",
                "refinementLevels": [finfo.get("surface_min", 0), finfo.get("surface_max", 1)],
            }
            if surf_type == "facezone" and finfo.get("cell_zone", False):
                entry["cellZoneInside"] = "inside"
            surfaces[stem] = entry
        if finfo.get("vol_direction", "none").lower() in ("inside", "outside"):
            vol_selected.append(stem)
            vol_regions[stem] = {
                "mode": finfo["vol_direction"].lower(),
                "level": finfo.get("vol_level", 1),
            }

    for shape in shapes_cfg:
        if shape.get("vol_direction", "none").lower() in ("inside", "outside"):
            vol_selected.append(shape["name"])
            vol_regions[shape["name"]] = {
                "mode": shape["vol_direction"].lower(),
                "level": shape.get("vol_level", 1),
            }

    record = {
        "_generator": "openfoam_ui — GUI run record (backgroundMesh handled by Background Mesh tab)",
        "settings": {
            "geometryUnit": cast_cfg.get("geometry_unit", "m"),
            "addLayers": layers_cfg.get("enabled", False),
            "mergeTolerance": defaults.get("settings", {}).get("mergeTolerance", 1e-6),
        },
        "geometry": {
            "files": [f["filename"] for f in files_cfg],
            "standardShapes": [
                {"name": s["name"], "type": s["type"], **s.get("params", {})}
                for s in shapes_cfg
            ],
        },
        "surfaceHandling": {"selectedParts": surf_selected, "surfaces": surfaces},
        "volumeRefinement": {"selectedParts": vol_selected, "regions": vol_regions},
        "castellatedMeshControls": {
            "locationInMesh": cast_cfg.get("locationInMesh", [0, 0, 0]),
            "nCellsBetweenLevels": cast_cfg.get("nCellsBetweenLevels", 2),
        },
    }
    if layers_cfg.get("enabled", False):
        record["layers"] = {
            p["name"]: {"nSurfaceLayers": p.get("nSurfaceLayers", 3)}
            for p in layers_cfg.get("patches", [])
        }

    path = os.path.join(case_dir, "snappy_inputs.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=4)
    log_cb(f"[generate] Inputs recorded to {path}", "info")


def generate_and_run(config: dict, case_dir: str, log_cb) -> bool:
    """
    Generate snappyHexMeshDict and run snappyHexMesh in one shot.

    Parameters
    ----------
    config : dict
        GUI-collected configuration (see module docstring for schema).
    case_dir : str
        Absolute path to the OpenFOAM case root (must contain system/ and constant/).
    log_cb : callable
        Function accepting (message: str, tag: str) for streaming output to LogDrawer.
        Tags: "info", "error", "warn", "cmd"

    Returns
    -------
    bool
        True if snappyHexMesh exited with code 0, False otherwise.
    """
    validate_config(config)

    env = _get_jinja_env()
    defaults = _load_defaults()

    sys_dir = os.path.join(case_dir, "system")
    os.makedirs(sys_dir, exist_ok=True)
    dict_path = os.path.join(sys_dir, "snappyHexMeshDict")

    # ── Build context and render the whole dictionary in one pass ───────────────
    log_cb("[generate] Building snappyHexMeshDict from template...", "info")
    context = _build_render_context(config, case_dir, defaults, log_cb)

    try:
        template = env.get_template("snappyHexMeshDict.template")
        rendered = template.render(**context)
    except Exception as e:
        raise RuntimeError(f"Template rendering failed: {e}")

    with open(dict_path, "w") as f:
        f.write(rendered)
    log_cb(f"[generate] Wrote {dict_path}", "info")
    log_cb(
        f"[generate] Surfaces: {len(context['surface_refinements'])}, "
        f"volume regions: {len(context['volume_refinements'])}, "
        f"layers: {'on' if context['addLayers'] else 'off'}", "info")

    # ── Record the GUI inputs next to the case ──────────────────────────────────
    _write_inputs_record(config, case_dir, defaults, log_cb)

    log_cb("[generate] snappyHexMeshDict written successfully.\n", "info")

    # ── Run snappyHexMesh ────────────────────────────────────────────────────────
    log_cb("[snappyHexMesh] Starting snappyHexMesh -overwrite...\n", "info")
    cmd = f"source {_OF_BASHRC} && snappyHexMesh -overwrite"
    proc = subprocess.Popen(
        ["bash", "-c", cmd],
        cwd=case_dir,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        log_cb(line.rstrip('\r'), "info")
    rc = proc.wait()

    if rc != 0:
        log_cb(f"[snappyHexMesh] Exited with code {rc}\n", "error")
        return False

    # ── Post-run cleanup ─────────────────────────────────────────────────────────
    # snappyHexMesh -overwrite writes the final mesh into constant/polyMesh, but
    # can still leave numbered time directories behind. They are intermediate
    # output only and confuse ParaView, so remove every non-zero numeric dir.
    for entry in os.listdir(case_dir):
        entry_path = os.path.join(case_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        try:
            if float(entry) != 0.0:
                shutil.rmtree(entry_path)
                log_cb(f"[cleanup] Removed time directory: {entry}/", "info")
        except ValueError:
            pass

    # Recreate the (empty) <case>.foam sentinel so ParaView picks up the fresh
    # mesh — remove any stale .foam files first.
    case_name = os.path.basename(case_dir)
    for f in os.listdir(case_dir):
        if f.endswith(".foam"):
            try:
                os.remove(os.path.join(case_dir, f))
            except Exception:
                pass
    foam_path = os.path.join(case_dir, f"{case_name}.foam")
    open(foam_path, "w").close()
    log_cb(f"[snappyHexMesh] .foam updated: {foam_path}\n", "info")
    log_cb("[snappyHexMesh] Done.\n", "info")
    return True
