#!/usr/bin/env python3
"""
find_interior_point.py — Find a point strictly inside a closed geometry file.

Useful for setting ``locationInMesh`` in snappyHexMeshDict.

Usage:
    python3 find_interior_point.py <file.stl|obj>
    python3 find_interior_point.py <file.stl> --format foam
    python3 find_interior_point.py <file.stl> --repair
    python3 find_interior_point.py <file.stl> --repair --grid-resolution 20

Output formats:
    default  →  x y z          (space-separated, easy to copy-paste)
    json     →  {"x": ..., "y": ..., "z": ...}
    foam     →  (x y z)        (OpenFOAM locationInMesh format)

--repair mode (for meshes with small holes or inconsistent normals):
    Step A: trimesh hole-filling and winding repair, then retry.
    Step B: if still open, voxelisation-based fallback (approximate).
"""

import sys
import json
import argparse
from pathlib import Path

try:
    import numpy as np
    import trimesh
except ImportError:
    sys.exit("Error: 'numpy' and 'trimesh' are required.\n"
             "       Install with: pip install numpy trimesh")

VALID_EXTENSIONS = {'.stl', '.stlb', '.obj'}


def find_interior_point(mesh, grid_resolution=10):
    """
    Find a point strictly inside a watertight mesh.

    Strategy (fastest first, fallback on failure):
      1. Bounding-box centre — works for most convex shapes.
      2. Uniform grid search (grid_resolution^3 candidates) — handles
         concave or hollow shapes where the centre falls in a void.
         Returns the interior hit closest to the bounding-box centre.
      3. trimesh.sample.volume_mesh() — random sampling fallback using
         signed-volume decomposition; guaranteed interior for watertight meshes.

    Returns a numpy array [x, y, z] or None if no interior point can be found.
    Caller must ensure the mesh is watertight before calling.
    """
    bounds = mesh.bounds          # [[xmin,ymin,zmin], [xmax,ymax,zmax]]
    centre = bounds.mean(axis=0)

    # Step 1 — bounding-box centre
    if mesh.contains([centre])[0]:
        return centre

    # Step 2 — uniform grid search
    lo, hi = bounds[0], bounds[1]
    margin = (hi - lo) * 0.01    # nudge inward to avoid landing on the surface
    xs = np.linspace(lo[0] + margin[0], hi[0] - margin[0], grid_resolution)
    ys = np.linspace(lo[1] + margin[1], hi[1] - margin[1], grid_resolution)
    zs = np.linspace(lo[2] + margin[2], hi[2] - margin[2], grid_resolution)
    candidates = np.array([[x, y, z] for x in xs for y in ys for z in zs])
    hits = candidates[mesh.contains(candidates)]
    if len(hits) > 0:
        dists = np.linalg.norm(hits - centre, axis=1)
        return hits[np.argmin(dists)]

    # Step 3 — random sampling fallback
    samples = trimesh.sample.volume_mesh(mesh, count=64)
    if len(samples) > 0:
        dists = np.linalg.norm(samples - centre, axis=1)
        return samples[np.argmin(dists)]

    return None


def find_interior_point_voxel(mesh, voxel_resolution=30):
    """
    Voxelisation-based interior point for meshes that remain open after repair.

    Converts the mesh to a voxel grid and returns the centroid of the enclosed
    voxel closest to the bounding-box centre. Works for meshes with holes
    because the voxeliser uses inside/outside voting, not ray-casting.

    Returns a numpy array [x, y, z] or None if no enclosed voxels are found.
    """
    bounds = mesh.bounds
    centre = bounds.mean(axis=0)
    pitch = (bounds[1] - bounds[0]).max() / voxel_resolution

    try:
        voxels = mesh.voxelized(pitch).fill()
        points = voxels.points          # centroids of all filled voxels
        if len(points) == 0:
            return None
        dists = np.linalg.norm(points - centre, axis=1)
        return points[np.argmin(dists)]
    except Exception:
        return None


def attempt_repair(mesh):
    """
    Apply trimesh hole-filling and winding repair in-place.
    Returns (repaired_mesh, holes_filled) where holes_filled is a count
    (or None if trimesh does not report it).
    """
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_inversion(mesh)
    filled = trimesh.repair.fill_holes(mesh)
    return mesh, filled


def main():
    parser = argparse.ArgumentParser(
        description="Find a point strictly inside a closed geometry file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
output formats:
  default   x y z           space-separated (easy to copy-paste)
  json      {"x":..., ...}
  foam      (x y z)         OpenFOAM locationInMesh format
        """
    )
    parser.add_argument("file", type=str, help="Path to the geometry file (.stl, .stlb, .obj)")
    parser.add_argument(
        "--format", choices=["default", "json", "foam"], default="default",
        help="Output format (default: space-separated)"
    )
    parser.add_argument(
        "--grid-resolution", type=int, default=10, metavar="N",
        help="Grid resolution for Step 2 search (N^3 candidates, default: 10)"
    )
    parser.add_argument(
        "--repair", action="store_true",
        help="Attempt automatic mesh repair (hole filling, winding fix) before "
             "searching for an interior point. Falls back to voxelisation if the "
             "mesh remains open after repair."
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"Error: file not found — '{path}'")
    if path.suffix.lower() not in VALID_EXTENSIONS:
        sys.exit(f"Error: unsupported file type '{path.suffix}'. "
                 f"Expected one of: {', '.join(sorted(VALID_EXTENSIONS))}")

    mesh = trimesh.load(str(path), force='mesh')
    mesh.process()

    if len(mesh.faces) == 0:
        sys.exit(f"Error: '{path.name}' is empty or contains no valid faces.")

    approximate = False

    if not mesh.is_watertight:
        if not args.repair:
            sys.exit(
                f"Error: '{path.name}' is not a closed (watertight) mesh.\n"
                "       A closed surface is required to find a reliable interior point.\n"
                "       Options:\n"
                "         1. Re-run with --repair to attempt automatic hole filling.\n"
                "         2. Check for flipped normals: python3 flip_normals.py <file>\n"
                "         3. Inspect the mesh: surfaceCheck <file>"
            )

        # --repair path
        print(f"Note: '{path.name}' is not watertight — attempting repair...",
              file=sys.stderr)
        mesh, filled = attempt_repair(mesh)

        if mesh.is_watertight:
            print(f"  Repair succeeded (holes filled: {filled}). "
                  f"Searching for interior point...", file=sys.stderr)
        else:
            print(f"  Mesh still open after repair (holes filled: {filled}). "
                  f"Falling back to voxelisation (result is approximate).",
                  file=sys.stderr)
            point = find_interior_point_voxel(mesh)
            if point is None:
                sys.exit(
                    f"Error: voxelisation fallback also failed for '{path.name}'.\n"
                    "       The mesh may have severe defects. Try repairing it with:\n"
                    "         pip install pymeshfix\n"
                    "         python3 -c \"import pymeshfix; pymeshfix.MeshFix"
                    "(v, f).repair(); ...\"\n"
                    "       or inspect it in a CAD tool (MeshLab, FreeCAD)."
                )
            approximate = True
            x, y, z = float(point[0]), float(point[1]), float(point[2])
            _print_result(x, y, z, args.format, approximate)
            return

    point = find_interior_point(mesh, grid_resolution=args.grid_resolution)

    if point is None:
        sys.exit(f"Error: could not find an interior point in '{path.name}'.")

    x, y, z = float(point[0]), float(point[1]), float(point[2])
    _print_result(x, y, z, args.format, approximate)


def _print_result(x, y, z, fmt, approximate):
    if approximate:
        print("Warning: result is approximate (voxelisation fallback).",
              file=sys.stderr)
    if fmt == "json":
        print(json.dumps({"x": x, "y": y, "z": z, "approximate": approximate},
                         indent=4))
    elif fmt == "foam":
        print(f"({x} {y} {z})")
    else:
        print(f"{x} {y} {z}")


if __name__ == "__main__":
    main()

