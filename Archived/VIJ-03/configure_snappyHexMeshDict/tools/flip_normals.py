#!/usr/bin/env python3
"""
flip_normals.py — Flip face normals of an STL file in-place.

Usage:
    python3 flip_normals.py <file.stl>
    python3 flip_normals.py <file1.stl> <file2.stl> ...

The original file is overwritten. A backup is NOT created — ensure the
file is under version control or copy it manually beforehand if needed.
"""

import sys
from pathlib import Path

try:
    import trimesh
except ImportError:
    sys.exit("Error: 'trimesh' is required.\n       Install with: pip install trimesh")


def flip_normals(stl_path: Path) -> None:
    mesh = trimesh.load(str(stl_path), force='mesh')

    if len(mesh.faces) == 0:
        sys.exit(f"Error: '{stl_path}' is empty or contains no valid faces.")

    mesh.invert()
    mesh.export(str(stl_path))
    print(f"  ✓  {stl_path.name}  ({len(mesh.faces):,} faces — normals flipped)")


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 flip_normals.py <file.stl> [file2.stl ...]")

    paths = [Path(p) for p in sys.argv[1:]]

    for p in paths:
        if not p.exists():
            sys.exit(f"Error: file not found — '{p}'")
        if p.suffix.lower() not in {'.stl', '.stlb'}:
            sys.exit(f"Error: '{p}' is not an STL file (expected .stl or .stlb)")

    for p in paths:
        flip_normals(p)


if __name__ == "__main__":
    main()
