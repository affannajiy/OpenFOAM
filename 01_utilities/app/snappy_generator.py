#!/usr/bin/env python3
"""
snappy_generator.py — Backend for Tab 2 (SnappyHexMesh Dict generator and runner).

Generates snappyHexMeshDict via foamDictionary subprocess calls, mirroring
the call sequence from generateSnappyHexMeshDict.py, then runs snappyHexMesh.

Config dict schema (passed in from ui_snappy_hex._collect_data):
    {
        "geometry": {
            "files": [
                {
                    "filename": "wall.stl",       # just the filename
                    "surface_type": "boundary",   # "none" | "boundary" | "faceZone"
                    "cell_zone": False,            # True only when surface_type=="faceZone"
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
            "implicitFeatureSnap": True
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
_OF_BASHRC = "/usr/lib/openfoam/openfoam2506/etc/bashrc"


def _load_defaults() -> dict:
    with open(_DEFAULTS_PATH) as f:
        return json.load(f)


def _fmt_vec(v: list) -> str:
    """Format a 3-element list as an OpenFOAM vector literal, e.g. '(0.0 1.0 -1.0)'."""
    return f"({v[0]} {v[1]} {v[2]})"


def _of_bool(v) -> str:
    """Convert a Python bool or string to an OpenFOAM boolean literal ('true'/'false')."""
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).lower()
    return s if s in ("true", "false") else str(v)


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


def _write_header(dict_path: str, geometry_unit: str) -> None:
    with open(dict_path, "w") as f:
        f.write("/*--------------------------------*- C++ -*----------------------------------*\\\n")
        f.write("| =========                 |                                                 |\n")
        f.write("| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n")
        f.write("|  \\\\    /   O peration     | Version:  v2506                                 |\n")
        f.write("|   \\\\  /    A nd           | Website:  www.openfoam.com                      |\n")
        f.write("|    \\\\/     M anipulation  |                                                 |\n")
        f.write("\\*---------------------------------------------------------------------------*/\n")
        f.write("FoamFile\n")
        f.write("{\n")
        f.write("\tversion     2.0;\n")
        f.write("\tformat      ascii;\n")
        f.write("\tclass       dictionary;\n")
        f.write("\tobject      snappyHexMeshDict;\n")
        f.write("}\n")
        f.write("// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n")
        f.write(f"// Geometry unit: {geometry_unit} (reference only — STL files assumed to be in simulation units)\n")
        f.write("\n")


def _inject_features_block(dict_path: str, edge_files: list, log_cb) -> None:
    """
    Splice the features block into castellatedMeshControls by direct file manipulation.

    foamDictionary cannot write list-of-dict syntax used by the features entry,
    so we read the file, find the closing brace of castellatedMeshControls, and
    insert the features block just before it — matching the technique in
    generateSnappyHexMeshDict.py.
    """
    with open(dict_path) as f:
        lines = f.readlines()

    modified = []
    inside_castelled = False
    for line in lines:
        stripped = line.strip()
        modified.append(line)
        if stripped.startswith("castellatedMeshControls"):
            inside_castelled = True
        if inside_castelled and stripped == "}":
            modified.insert(-1, "    features\n")
            modified.insert(-1, "    (\n")
            for ef in edge_files:
                modified.insert(-1, "        {\n")
                modified.insert(-1, f'        file    "{ef}";\n')
                modified.insert(-1,  "        level    0;\n")
                modified.insert(-1, "        }\n")
            modified.insert(-1, "    );\n")
            inside_castelled = False

    with open(dict_path, "w") as f:
        f.writelines(modified)
    log_cb("[features] Injected features block into castellatedMeshControls.", "info")


def _write_fv_files(sys_dir: str, log_cb) -> None:
    """Write fvSchemes and fvSolution needed for displacementMotionSolver layer addition."""
    fv_schemes = """\
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          fvSchemes;
}

divSchemes
{

}

gradSchemes
{
    grad(cellDisplacement)  cellLimited leastSquares 1;

}

laplacianSchemes
{
    laplacian(diffusivity,cellDisplacement) Gauss linear limited corrected 0.5;
}

"""
    fv_solution = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers
{
   cellDisplacement
   {
       solver          GAMG;
       smoother        GaussSeidel;
       minIter         1;
       tolerance       1e-7;
       relTol          0.01;
   }
}

"""
    for fname, content in [("fvSchemes", fv_schemes), ("fvSolution", fv_solution)]:
        path = os.path.join(sys_dir, fname)
        with open(path, "w") as fp:
            fp.write(content)
        log_cb(f"[layers] Wrote system/{fname}", "info")


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
            "Set at least one file to Surface Type = Boundary in Section 01.")

    vol_dirs = [f.get("vol_direction", "none").lower() for f in files]
    non_none = [v for v in vol_dirs if v != "none"]
    if non_none and all(v == "outside" for v in non_none):
        raise ValueError(
            "Every STL with a Vol Direction is set to Outside — this is almost "
            "always wrong.\n"
            "For an outer domain box, use Vol Direction = None.\n"
            "For a solid body in fluid, use Vol Direction = Inside.")


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

    defaults = _load_defaults()
    dc = defaults.get("castellatedMeshControls", {})
    ds = defaults.get("snapControls", {})
    dl = defaults.get("addLayersControls", {})
    dq = defaults.get("meshQualityControls", {})
    merge_tol = defaults.get("settings", {}).get("mergeTolerance", 1e-6)

    geom_cfg    = config.get("geometry", {})
    cast_cfg    = config.get("castellated", {})
    snap_cfg    = config.get("snap", {})
    layers_cfg  = config.get("layers", {})
    files_cfg   = geom_cfg.get("files", [])
    shapes_cfg  = geom_cfg.get("standard_shapes", [])
    add_layers  = layers_cfg.get("enabled", False)
    implicit    = snap_cfg.get("implicitFeatureSnap", True)
    geom_unit   = cast_cfg.get("geometry_unit", "m")

    sys_dir  = os.path.join(case_dir, "system")
    const_dir = os.path.join(case_dir, "constant")
    dict_path = os.path.join(sys_dir, "snappyHexMeshDict")
    dict_rel  = "system/snappyHexMeshDict"

    # ── Inner helpers that close over case_dir / dict_rel / log_cb ───────────────

    def _bash(cmd_str: str) -> subprocess.CompletedProcess:
        """Run cmd_str with the OF environment sourced; closes over case_dir."""
        return subprocess.run(
            ["bash", "-c", f"source {_OF_BASHRC} && {cmd_str}"],
            cwd=case_dir, capture_output=True, text=True)

    def fd(entry: str, value: str) -> None:
        """Run foamDictionary -add for the given entry/value."""
        cmd_str = f"foamDictionary {dict_rel} -entry {entry} -add {value}"
        log_cb(f"  {cmd_str}", "cmd")
        res = _bash(cmd_str)
        if res.returncode != 0:
            log_cb(res.stderr.strip(), "error")
            raise RuntimeError(f"foamDictionary failed: {entry}")

    def fd_set(entry: str, value: str) -> None:
        """Run foamDictionary -set for the given entry/value."""
        cmd_str = f"foamDictionary {dict_rel} -entry {entry} -set {value}"
        log_cb(f"  {cmd_str}", "cmd")
        res = _bash(cmd_str)
        if res.returncode != 0:
            log_cb(res.stderr.strip(), "error")
            raise RuntimeError(f"foamDictionary -set failed: {entry}")

    # ── Write header ─────────────────────────────────────────────────────────────
    log_cb("[generate] Writing snappyHexMeshDict header...", "info")
    _write_header(dict_path, geom_unit)

    # ── Top-level switches ───────────────────────────────────────────────────────
    fd("castellatedMesh", "true")
    fd("snap", "true")
    fd("addLayers", "true" if add_layers else "false")

    # ── Empty section dicts (must exist before sub-key writes) ───────────────────
    fd("geometry",                '"{}"')
    fd("castellatedMeshControls", '"{}"')
    fd("snapControls",            '"{}"')
    fd("addLayersControls",       '"{}"')
    fd("meshQualityControls",     '"{}"')
    fd("mergeTolerance",          str(merge_tol))

    # ── Geometry: STL/OBJ files ──────────────────────────────────────────────────
    log_cb("[generate] Writing geometry section...", "info")

    for finfo in files_cfg:
        fname = finfo["filename"]
        mesh_name, zones = _mesh_name_for_stl(fname, const_dir)
        finfo["_mesh_name"] = mesh_name
        finfo["_zones"]     = zones

        fd(f"geometry/{fname}",      '"{}"')
        fd(f"geometry/{fname}/type", "triSurfaceMesh")
        fd(f"geometry/{fname}/name", mesh_name)

        if len(zones) > 1:
            fd(f"geometry/{fname}/regions", '"{}"')
            for zone in zones:
                fd(f"geometry/{fname}/regions/{zone}",      '"{}"')
                fd(f"geometry/{fname}/regions/{zone}/name", zone)

    # ── Geometry: standard shapes ────────────────────────────────────────────────
    for shape in shapes_cfg:
        name   = shape["name"]
        stype  = shape["type"]
        params = shape.get("params", {})

        fd(f"geometry/{name}",      '"{}"')
        fd(f"geometry/{name}/type", stype)

        if stype == "searchableBox":
            mn = params.get("min", [0, 0, 0])
            mx = params.get("max", [1, 1, 1])
            fd(f"geometry/{name}/min", f'"{_fmt_vec(mn)}"')
            fd(f"geometry/{name}/max", f'"{_fmt_vec(mx)}"')
        elif stype == "searchableSphere":
            c = params.get("centre", [0, 0, 0])
            r = params.get("radius", 1.0)
            fd(f"geometry/{name}/centre", f'"{_fmt_vec(c)}"')
            fd(f"geometry/{name}/radius", str(r))
        elif stype == "searchableCylinder":
            p1 = params.get("point1", [0, 0, 0])
            p2 = params.get("point2", [1, 0, 0])
            r  = params.get("radius", 0.5)
            fd(f"geometry/{name}/point1", f'"{_fmt_vec(p1)}"')
            fd(f"geometry/{name}/point2", f'"{_fmt_vec(p2)}"')
            fd(f"geometry/{name}/radius", str(r))

    # ── CastellatedMeshControls: basic controls ──────────────────────────────────
    log_cb("[generate] Writing castellatedMeshControls...", "info")
    fd("castellatedMeshControls/maxLocalCells",       str(dc.get("maxLocalCells",       100000000)))
    fd("castellatedMeshControls/maxGlobalCells",      str(dc.get("maxGlobalCells",      300000000)))
    fd("castellatedMeshControls/minRefinementCells",  str(dc.get("minRefinementCells",  10)))
    fd("castellatedMeshControls/maxLoadUnbalance",    str(dc.get("maxLoadUnbalance",    0.1)))

    # ── features block — direct file manipulation (foamDictionary can't write lists)
    edge_files = [fi["filename"] for fi in files_cfg
                  if fi["filename"].lower().endswith(".emesh")]
    _inject_features_block(dict_path, edge_files, log_cb)

    # ── refinementRegions ────────────────────────────────────────────────────────
    # Collect entries first so the parent dict and children are written in a single
    # pass — keeps the structure obvious and avoids any chance of the foamDictionary
    # "-add into an existing empty dict" edge case some OF builds have.
    region_entries: list = []   # (name, mode, level)
    for finfo in files_cfg:
        fname     = finfo["filename"]
        mesh_name = finfo.get("_mesh_name") or os.path.splitext(fname)[0]
        surf_type = finfo.get("surface_type", "none").lower()
        cell_zone = finfo.get("cell_zone", False)
        vol_dir   = finfo.get("vol_direction", "none").lower()
        # Also write refinementRegions for faceZone+cellZone even when vol_direction is "none",
        # since cellZoneInside=inside requires a matching refinementRegions entry to work.
        force_inside = (surf_type == "facezone" and cell_zone and vol_dir == "none")
        if vol_dir == "none" and not force_inside:
            continue
        if vol_dir == "outside":
            log_cb(
                f"[warn] {fname}: vol_direction=outside refines cells OUTSIDE this surface. "
                "For an outer domain box this is almost certainly wrong — use vol_direction=None.",
                "warn")
        mode  = vol_dir if vol_dir != "none" else "inside"
        level = finfo.get("vol_level", 1)
        region_entries.append((mesh_name, mode, level))

    for shape in shapes_cfg:
        name    = shape["name"]
        vol_dir = shape.get("vol_direction", "none").lower()
        if vol_dir == "none":
            continue
        mode  = "inside" if vol_dir == "inside" else "outside"
        level = shape.get("vol_level", 1)
        region_entries.append((name, mode, level))

    fd("castellatedMeshControls/refinementRegions", '"{}"')
    for name, mode, level in region_entries:
        fd(f"castellatedMeshControls/refinementRegions/{name}",        '"{}"')
        fd(f"castellatedMeshControls/refinementRegions/{name}/mode",   mode)
        fd(f"castellatedMeshControls/refinementRegions/{name}/levels", f'"((1.0 {level}))"')

    # ── refinementSurfaces ───────────────────────────────────────────────────────
    fd("castellatedMeshControls/refinementSurfaces", '"{}"')

    for finfo in files_cfg:
        fname     = finfo["filename"]
        mesh_name = finfo.get("_mesh_name") or os.path.splitext(fname)[0]
        zones     = finfo.get("_zones", [])
        surf_type = finfo.get("surface_type", "none").lower()
        cell_zone = finfo.get("cell_zone", False)
        smin      = finfo.get("surface_min", 0)
        smax      = finfo.get("surface_max", 1)

        if surf_type == "none":
            continue

        fd(f"castellatedMeshControls/refinementSurfaces/{mesh_name}",       '"{}"')
        fd(f"castellatedMeshControls/refinementSurfaces/{mesh_name}/level", f'"({smin} {smax})"')

        if len(zones) > 1:
            fd(f"castellatedMeshControls/refinementSurfaces/{mesh_name}/regions", '"{}"')
            for zone in zones:
                base = f"castellatedMeshControls/refinementSurfaces/{mesh_name}/regions/{zone}"
                fd(base,          '"{}"')
                fd(f"{base}/level", f'"({smin} {smax})"')
                _write_surface_patch_info(fd, base, surf_type, cell_zone, zone, mesh_name)
        else:
            base = f"castellatedMeshControls/refinementSurfaces/{mesh_name}"
            _write_surface_patch_info(fd, base, surf_type, cell_zone, mesh_name, mesh_name)

    # ── CastellatedMeshControls: remaining controls ──────────────────────────────
    ncbl = cast_cfg.get("nCellsBetweenLevels", dc.get("nCellsBetweenLevels", 2))
    loc  = cast_cfg.get("locationInMesh", [0.0, 0.0, 0.0])
    fd("castellatedMeshControls/resolveFeatureAngle",        str(dc.get("resolveFeatureAngle", 30)))
    fd("castellatedMeshControls/nCellsBetweenLevels",        str(ncbl))
    fd("castellatedMeshControls/locationInMesh",             f'"{_fmt_vec(loc)}"')
    fd("castellatedMeshControls/allowFreeStandingZoneFaces", "true")

    # ── snapControls ─────────────────────────────────────────────────────────────
    log_cb("[generate] Writing snapControls...", "info")
    fd("snapControls/nSmoothPatch",     str(ds.get("nSmoothPatch",     3)))
    fd("snapControls/nSmoothInternal",  str(ds.get("nSmoothInternal",  5)))
    fd("snapControls/tolerance",        str(ds.get("tolerance",        2.0)))
    fd("snapControls/nSolveIter",       str(ds.get("nSolveIter",       30)))
    fd("snapControls/nRelaxIter",       str(ds.get("nRelaxIter",       5)))
    fd("snapControls/nFeatureSnapIter", str(ds.get("nFeatureSnapIter", 10)))

    if implicit:
        fd("snapControls/implicitFeatureSnap",    "true")
        fd("snapControls/explicitFeatureSnap",    "false")
        fd("snapControls/multiRegionFeatureSnap", "false")
    else:
        fd("snapControls/implicitFeatureSnap",    "false")
        fd("snapControls/explicitFeatureSnap",    "true")
        fd("snapControls/multiRegionFeatureSnap", "true" if edge_files else "false")

    # ── addLayersControls ────────────────────────────────────────────────────────
    if add_layers:
        log_cb("[generate] Writing addLayersControls...", "info")
        fd_set("addLayers", "true")  # ensure correct value after initial -add false

        fd("addLayersControls/relativeSizes",         _of_bool(dl.get("relativeSizes",         True)))
        fd("addLayersControls/minThickness",          str(dl.get("minThickness",          0.1)))
        fd("addLayersControls/featureAngle",          str(dl.get("featureAngle",          120)))
        fd("addLayersControls/nGrow",                 str(dl.get("nGrow",                 0)))
        fd("addLayersControls/maxFaceThicknessRatio", str(dl.get("maxFaceThicknessRatio", 0.5)))
        fd("addLayersControls/nBufferCellsNoExtrude", str(dl.get("nBufferCellsNoExtrude", 0)))
        fd("addLayersControls/nLayerIter",            str(dl.get("nLayerIter",            50)))
        fd("addLayersControls/nSmoothThickness",      str(dl.get("nSmoothThickness",      10)))
        fd("addLayersControls/nRelaxIter",            str(dl.get("nRelaxIter",            5)))
        fd("addLayersControls/nRelaxedIter",          str(dl.get("nRelaxedIter",          20)))
        fd("addLayersControls/nSmoothSurfaceNormals", str(dl.get("nSmoothSurfaceNormals", 1)))
        fd("addLayersControls/thicknessModel",        str(dl.get("thicknessModel",        "finalAndExpansion")))
        fd("addLayersControls/finalLayerThickness",   str(dl.get("finalLayerThickness",   0.5)))
        fd("addLayersControls/expansionRatio",        str(dl.get("expansionRatio",        1.1)))
        fd("addLayersControls/layers",                '"{}"')

        patch_list = "( "
        for patch_info in layers_cfg.get("patches", []):
            pname = patch_info["name"]
            n     = patch_info.get("nSurfaceLayers", 3)
            patch_list += pname + " "
            fd(f"addLayersControls/layers/{pname}",                  '"{}"')
            fd(f"addLayersControls/layers/{pname}/nSurfaceLayers",   str(n))
        patch_list += ");"

        fd("addLayersControls/meshShrinker", "displacementMotionSolver")
        fd("addLayersControls/solver",       "displacementLaplacian")

        # patch_list is an OF list literal "( p1 p2 );" — embed directly into the dict value
        text_string = "{ diffusivity quadratic inverseDistance " + patch_list + " }"
        cmd_str = (f'foamDictionary {dict_rel} -entry addLayersControls/displacementLaplacianCoeffs'
                   f' -add "{text_string}"')
        log_cb(f"  {cmd_str}", "cmd")
        res = _bash(cmd_str)
        if res.returncode != 0:
            log_cb(res.stderr.strip(), "error")
            raise RuntimeError("foamDictionary failed: displacementLaplacianCoeffs")

        _write_fv_files(sys_dir, log_cb)

    # ── meshQualityControls ──────────────────────────────────────────────────────
    log_cb("[generate] Writing meshQualityControls...", "info")
    fd("meshQualityControls/maxNonOrtho",         str(dq.get("maxNonOrtho",         65)))
    fd("meshQualityControls/maxBoundarySkewness", str(dq.get("maxBoundarySkewness", 20)))
    fd("meshQualityControls/maxInternalSkewness", str(dq.get("maxInternalSkewness", 4)))
    fd("meshQualityControls/maxConcave",          str(dq.get("maxConcave",          80)))
    fd("meshQualityControls/minFlatness",         str(dq.get("minFlatness",         0.5)))
    fd("meshQualityControls/minVol",              str(dq.get("minVol",              1e-13)))
    fd("meshQualityControls/minTetQuality",       str(dq.get("minTetQuality",       -1e-30)))
    fd("meshQualityControls/minArea",             str(dq.get("minArea",             -1)))
    fd("meshQualityControls/minTwist",            str(dq.get("minTwist",            0.02)))
    fd("meshQualityControls/minDeterminant",      str(dq.get("minDeterminant",      0.001)))
    fd("meshQualityControls/minFaceWeight",       str(dq.get("minFaceWeight",       0.05)))
    fd("meshQualityControls/minVolRatio",         str(dq.get("minVolRatio",         0.01)))
    fd("meshQualityControls/minTriangleTwist",    str(dq.get("minTriangleTwist",    -1)))
    fd("meshQualityControls/minEdgeLength",       str(dq.get("minEdgeLength",       -1)))
    fd("meshQualityControls/relaxed",             '"{}"')
    fd("meshQualityControls/relaxed/maxNonOrtho", str(dq.get("relaxed", {}).get("maxNonOrtho", 70)))
    fd("meshQualityControls/nSmoothScale",        str(dq.get("nSmoothScale",        4)))
    fd("meshQualityControls/errorReduction",      str(dq.get("errorReduction",      0.75)))

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


def _write_surface_patch_info(
    fd,
    base_entry: str,
    surf_type: str,
    cell_zone: bool,
    zone_name: str,
    stem: str,
) -> None:
    """Write patchInfo / faceZone / cellZone entries for a refinementSurfaces region."""
    if surf_type == "boundary":
        fd(f"{base_entry}/patchInfo",          '"{}"')
        fd(f"{base_entry}/patchInfo/type",     "wall")
        fd(f"{base_entry}/patchInfo/inGroups", '"(walls)"')
    elif surf_type == "facezone":
        fd(f"{base_entry}/faceZone", zone_name)
        fd(f"{base_entry}/faceType", "internal")
        if cell_zone:
            fd(f"{base_entry}/cellZone",       zone_name)
            fd(f"{base_entry}/cellZoneInside", "inside")
