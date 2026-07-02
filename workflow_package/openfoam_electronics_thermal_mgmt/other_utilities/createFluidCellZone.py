#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
createFluidCellZone.py

Generates system/topoSetDict_fluidCellZone for OpenFOAM by creating a new
cellZone (default: 'domain_fluid') that is the complement of the union of all
existing solid cellZones discovered from a checkMesh log.

Logic:
  1) Parse cellZone names from --checkMeshLog (same table used by
     ensureConsistentCellZones.py).
  2) Produce actions via Jinja2 template:
     - First zone:  action new;  source zoneToCell; zone <firstZone>
     - Others:      action add;  source zoneToCell; zone <zone>
     - Finally:     action invert; (on the target zone)

CLI:
  python3 createFluidCellZone.py --checkMeshLog <log> [-name domain_fluid] [--dry-run]

Outputs:
  - Writes to system/topoSetDict_fluidCellZone (overwrite if exists)
  - With --dry-run, prints a summary and does not write any file
"""

import argparse
import os
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from _common import (
    OPENFOAM_VERSION,
    fatal,
    get_template_dir,
    extract_cellzone_names_from_checkmesh_log,
)

TEMPLATE_NAME    = "topoSetDict_fluidCellZone.template"
OUTPUT_FILE      = os.path.join("system", "topoSetDict_fluidCellZone")



# ── Template rendering ────────────────────────────────────────────────────────

def render_template(zone_names: List[str], target_zone: str, template_dir: Path) -> str:
    """Render the topoSetDict_fluidCellZone Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(template_dir)), keep_trailing_newline=True)
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateNotFound:
        fatal(f"{TEMPLATE_NAME} not found in {template_dir}")

    try:
        return template.render(
            openfoam_version=OPENFOAM_VERSION,
            zone_names=zone_names,
            target_zone=target_zone,
        )
    except Exception as e:
        fatal(f"Failed to render template: {e}")


# ── Summary output ────────────────────────────────────────────────────────────

def print_summary(zone_names: List[str], target_zone: str, dry_run: bool) -> None:
    label = "[DRY-RUN] " if dry_run else ""
    n_add = max(0, len(zone_names) - 1)
    total = (1 if zone_names else 0) + n_add + 1  # new + adds + invert

    print(f"\n{label}createFluidCellZone summary")
    print(f"  Case        : {os.getcwd()}")
    print(f"  Target zone : {target_zone}")
    print(f"  Solid zones ({len(zone_names)}) : {', '.join(zone_names)}")
    print()

    if zone_names:
        print("Planned actions:")
        print(f"  new    ← {zone_names[0]}  (seed {target_zone})")
        for zn in zone_names[1:]:
            print(f"  add    ← {zn}  (into {target_zone})")
        print(f"  invert   (on {target_zone})")
        print()

    count_str = f"1 NEW + {n_add} ADD + 1 INVERT = {total} total"
    if dry_run:
        print(f"  Actions to be written : {count_str}")
        print(f"  Target (skipped)      : {OUTPUT_FILE}")
    else:
        print(f"  Actions written : {count_str}")
        print(f"  Wrote           : {OUTPUT_FILE}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: List[str] = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate system/topoSetDict_fluidCellZone. Unions all solid cellZones "
            "discovered from a checkMesh log into a target zone, then inverts it "
            "to obtain the fluid complement."
        )
    )
    parser.add_argument(
        "--checkMeshLog",
        required=True,
        metavar="LOG",
        help=(
            "Path to a checkMesh log file (e.g. log.checkMesh_start). "
            "Used to discover existing solid cellZone names."
        ),
    )
    parser.add_argument(
        "-name",
        dest="target_name",
        default="domain_fluid",
        help="Name of the fluid cellZone to create (default: domain_fluid).",
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

    zone_names = extract_cellzone_names_from_checkmesh_log(args.checkMeshLog)
    if not zone_names:
        fatal(
            f"Could not extract any cellZone names from {args.checkMeshLog}.\n"
            "Ensure the log contains a 'Checking basic cellZone addressing...' section."
        )

    if args.target_name in zone_names:
        fatal(
            f"Target zone name '{args.target_name}' already exists as a solid cellZone "
            f"in {args.checkMeshLog}.\n"
            "Choose a different name with -name to avoid overwriting a solid zone."
        )

    template_dir = get_template_dir()
    rendered = render_template(zone_names, args.target_name, template_dir)

    if args.dry_run:
        print_summary(zone_names, args.target_name, dry_run=True)
        return

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rendered)

    print_summary(zone_names, args.target_name, dry_run=False)


if __name__ == "__main__":
    main()
