#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensureConsistentCellZones.py

Generates system/topoSetDict_consistentCellZones for OpenFOAM solid regions.
See readme.md in this directory for full usage, algorithm, and workflow documentation.
"""

import argparse
import os
import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from _common import (
    OPENFOAM_VERSION,
    YELLOW,
    RESET,
    warn,
    fatal,
    get_template_dir,
    extract_cellzone_names_from_checkmesh_log,
)

TEMPLATE_NAME    = "topoSetDict_consistentCellZones.template"
SUPPORTED_EXTS   = (".stl", ".obj")
OUTPUT_FILE      = os.path.join("system", "topoSetDict_consistentCellZones")


def _norm_ext(filename: str) -> str:
    """Return filename with its extension lowercased; stem casing is preserved."""
    stem, ext = os.path.splitext(filename)
    return stem + ext.lower()


# ── Surface discovery ─────────────────────────────────────────────────────────

def discover_surfaces(surface_dir: str, exclude: List[str]) -> List[str]:
    """Return sorted list of .stl/.obj filenames in *surface_dir*, minus *exclude*."""
    if not os.path.isdir(surface_dir):
        fatal(f"--surfaceDir not found: {surface_dir}")

    exclude_set = {_norm_ext(e) for e in exclude}
    found = sorted(
        f for f in os.listdir(surface_dir)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        and _norm_ext(f) not in exclude_set
    )
    if not found:
        fatal(
            f"No .stl/.obj files found in {surface_dir} after applying --exclude.\n"
            "Check --surfaceDir path and --exclude list."
        )
    return found


# ── Validation ────────────────────────────────────────────────────────────────

def validate_zones(
    mapping: List[Tuple[str, str]],
    check_mesh_log: str,
    create_new: bool,
) -> List[str]:
    """Cross-check zone names against the checkMesh log.

    Default mode:         warn (yellow) for zones not found in the log.
    --createNewCellZones: fatal error for zones already found in the log.

    Returns list of zone names that triggered a warning (default mode only).
    """
    existing_zones = set(extract_cellzone_names_from_checkmesh_log(check_mesh_log))
    if not existing_zones and not create_new:
        fatal(
            f"Could not extract any cellZone names from {check_mesh_log}.\n"
            "Ensure the log contains a 'Checking basic cellZone addressing...' section."
        )

    warnings: List[str] = []

    if create_new:
        # Zones must NOT already exist
        already_exist = [zone for _, zone in mapping if zone in existing_zones]
        if already_exist:
            fatal(
                "The following zone(s) already exist in the mesh "
                f"({check_mesh_log}).\n"
                "Cannot create new zones with the same name — this would overwrite "
                "existing cellZone data. Use default mode instead, or rename your "
                "surface files:\n  - " + "\n  - ".join(already_exist)
            )
    else:
        # Zones must already exist — warn if not
        for surface, zone in mapping:
            if zone not in existing_zones:
                warnings.append(zone)
                warn(
                    f"{surface}: no matching cellZone '{zone}' found in the "
                    f"checkMesh log.\n"
                    f"     Check if this file should be excluded with --exclude, or if\n"
                    f"     you intended to create a new zone — in that case use "
                    f"--createNewCellZones."
                )

    return warnings


# ── Template rendering ────────────────────────────────────────────────────────

def render_template(
    mapping: List[Tuple[str, str]],
    template_dir: Path,
    create_new: bool,
) -> str:
    """Build Jinja2 context from *mapping* and render the topoSetDict template.

    Priority-wins overlap: zone_i only subtracts higher-priority surfaces (j < i).
    """
    # Build subtract groups in priority order: each entry is (zone, [surface, ...])
    # preserving the zone order from mapping (priority 2 first, then 3, etc.).
    subtract_groups: List[Tuple[str, List[str]]] = []
    for i, (_, zone_i) in enumerate(mapping):
        higher_surfaces = [surface_j for j, (surface_j, _) in enumerate(mapping) if j < i]
        if higher_surfaces:
            subtract_groups.append((zone_i, higher_surfaces))

    env = Environment(loader=FileSystemLoader(str(template_dir)), keep_trailing_newline=True)
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateNotFound:
        fatal(f"{TEMPLATE_NAME} not found in {template_dir}")

    try:
        return template.render(
            openfoam_version=OPENFOAM_VERSION,
            mapping=mapping,
            subtract_groups=subtract_groups,
            create_new=create_new,
        )
    except Exception as e:
        fatal(f"Failed to render template: {e}")


# ── Summary output ────────────────────────────────────────────────────────────

def print_summary(
    mapping: List[Tuple[str, str]],
    surface_dir: str,
    excluded: List[str],
    create_new: bool,
    warnings: List[str],
    dry_run: bool,
) -> None:
    label = "[DRY-RUN] " if dry_run else ""
    mode  = "--createNewCellZones" if create_new else "default (update existing)"

    print(f"\n{label}ensureConsistentCellZones summary")
    print(f"  Case       : {os.getcwd()}")
    print(f"  Mode       : {mode}")
    print(f"  surfaceDir : {os.path.abspath(surface_dir)}")
    if excluded:
        print(f"  Excluded   : {', '.join(excluded)}")
    print()

    print("Priority order (1 = highest — wins overlap cells):")
    for priority, (surface, zone) in enumerate(mapping, start=1):
        flag = f"  {YELLOW}⚠ no matching cellZone in log{RESET}" if zone in warnings else ""
        print(f"  {priority}. {zone}  ←  {surface}{flag}")

    print("\nOperations (per zone):\n")
    for i, (surface_i, zone_i) in enumerate(mapping):
        higher = [sf for j, (sf, _) in enumerate(mapping) if j < i]
        print(f"  {zone_i}  [priority {i + 1}]:")
        if create_new:
            print(f"    NEW       from: {surface_i}  (create + fill)")
        else:
            print(f"    CLEAR     (reset)")
            print(f"    ADD       from: {surface_i}")
        if higher:
            print(f"    SUBTRACT  from: {', '.join(higher)}  (higher-priority zones)")
        else:
            print(f"    SUBTRACT  from: (none — highest priority)")
        print()

    if len(mapping) >= 2:
        print(
            "  NOTE: Overlap cells are assigned to the highest-priority zone.\n"
            "        Check cell counts after running topoSet to confirm no zone\n"
            "        ended up unexpectedly small.\n"
        )

    n     = len(mapping)
    n_sub = n * (n - 1) // 2
    if create_new:
        total = n + n_sub
        count_str = f"{n} NEW + {n_sub} SUBTRACT = {total} total"
    else:
        total = n + n + n_sub
        count_str = f"{n} CLEAR + {n} ADD + {n_sub} SUBTRACT = {total} total"

    if dry_run:
        print(f"  Actions to be written : {count_str}")
        print(f"  Target (skipped)      : {OUTPUT_FILE}")
    else:
        print(f"  Actions written : {count_str}")
        print(f"  Wrote           : {OUTPUT_FILE}")


def parse_list_arg(list_str: Optional[str]) -> List[str]:
    """Parse a space-separated list optionally wrapped in parentheses/quotes."""
    if list_str is None:
        return []
    s = list_str.strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        s = s[1:-1].strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    return re.findall(r"\S+", s)


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: List[str] = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate system/topoSetDict_consistentCellZones. Auto-discovers "
            ".stl/.obj surface files in --surfaceDir, derives zone names from "
            "basenames, and ensures mutual exclusivity with a priority-wins overlap policy."
        )
    )
    parser.add_argument(
        "--surfaceDir",
        default="constant/triSurface",
        metavar="DIR",
        help="Directory containing the surface files (.stl/.obj) to process. Defaults to constant/triSurface.",
    )
    parser.add_argument(
        "--checkMeshLog",
        required=True,
        metavar="LOG",
        help=(
            "Path to a checkMesh log file (e.g. log.checkMesh_start). "
            "Used to validate zone names against the mesh."
        ),
    )
    parser.add_argument(
        "--createNewCellZones",
        action="store_true",
        help=(
            "Create brand-new cellZones that do not yet exist in the mesh. "
            "Uses 'action new' (create + fill) instead of 'clear' + 'add'. "
            "Exits with an error if any zone already exists in the checkMesh log."
        ),
    )
    parser.add_argument(
        "--exclude",
        required=False,
        default=None,
        metavar="LIST",
        help=(
            "Space-separated list (optionally in parentheses) of filenames to "
            "skip during auto-discovery, e.g. --exclude '(outer-domain.stl fluid-box.stl)'."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print summary without writing any file.",
    )

    args = parser.parse_args(argv)

    if not os.path.isfile(os.path.join("system", "controlDict")):
        fatal(
            "system/controlDict not found in the current directory.\n"
            "Run this script from the OpenFOAM case root."
        )

    excluded = parse_list_arg(args.exclude)
    surfaces = discover_surfaces(args.surfaceDir, excluded)

    # Derive zone names from basenames — check for duplicates
    zone_names = [os.path.splitext(f)[0] for f in surfaces]
    dupes: Dict[str, List[str]] = {}
    for sf, z in zip(surfaces, zone_names):
        dupes.setdefault(z, []).append(sf)
    dupes = {z: ss for z, ss in dupes.items() if len(ss) > 1}
    if dupes:
        msgs = [f"'{z}' from: {', '.join(ss)}" for z, ss in dupes.items()]
        fatal("Duplicate zone names derived from surface basenames:\n  - " + "\n  - ".join(msgs))

    mapping: List[Tuple[str, str]] = list(zip(surfaces, zone_names))

    warnings = validate_zones(mapping, args.checkMeshLog, create_new=args.createNewCellZones)

    template_dir = get_template_dir()
    rendered = render_template(mapping, template_dir, create_new=args.createNewCellZones)

    if args.dry_run:
        print_summary(mapping, args.surfaceDir, excluded, args.createNewCellZones, warnings, dry_run=True)
        return

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rendered)
    print_summary(mapping, args.surfaceDir, excluded, args.createNewCellZones, warnings, dry_run=False)

if __name__ == "__main__":
    main()

