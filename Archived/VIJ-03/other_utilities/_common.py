#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_common.py — Shared utilities for the other_utilities scripts.

Not intended to be run directly.

Exports
-------
OPENFOAM_VERSION : str
SCRIPT_DIR       : str
YELLOW, RED, RESET : str   (ANSI colour codes, empty when not a TTY)
warn(msg)        : prints a yellow-warning line to stdout
fatal(msg)       : prints a red FATAL line to stderr and exits
get_template_dir()                          -> Path
extract_cellzone_names_from_checkmesh_log() -> List[str]
"""

import os
import re
import sys
from pathlib import Path
from typing import List, NoReturn

OPENFOAM_VERSION = "v2512"
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))

_USE_COLOR = sys.stderr.isatty() and sys.stdout.isatty()
YELLOW = "\033[33m" if _USE_COLOR else ""
RED    = "\033[31m" if _USE_COLOR else ""
RESET  = "\033[0m"  if _USE_COLOR else ""

warn = lambda msg: print(f"  {YELLOW}⚠{RESET}  {msg}")


def fatal(msg: str) -> NoReturn:
    print(f"{RED}FATAL:{RESET} {msg}", file=sys.stderr)
    sys.exit(1)


# ── Template helpers ──────────────────────────────────────────────────────────

def get_template_dir() -> Path:
    """Return the templates/ directory that lives next to this file."""
    template_dir = Path(SCRIPT_DIR) / "templates"
    if not template_dir.exists():
        fatal(f"templates directory not found at {template_dir}")
    return template_dir


# ── checkMesh log parser ──────────────────────────────────────────────────────

def extract_cellzone_names_from_checkmesh_log(log_path: str) -> List[str]:
    """Extract cellZone names from a checkMesh log file.

    Parses the table that appears under:
        Checking basic cellZone addressing...
                        CellZone        Cells    Points    VolumeBoundingBox
                         zone-1          9724     13185    ...

    Exit condition: the first non-matching line after the header terminates
    the table scan.  This is intentionally strict — stopping even at an
    indented non-matching continuation line — to prevent picking up
    zone-like tokens from later log sections.

    Duplicate names (e.g. from a concatenated log) are deduplicated in
    insertion order; a warning is printed if any are found.
    """
    if not os.path.isfile(log_path):
        fatal(f"checkMesh log not found: {log_path}")

    names: List[str] = []
    header_re = re.compile(r"CellZone\s+Cells\s+Points", re.IGNORECASE)
    row_re    = re.compile(r"^\s+([A-Za-z0-9_.\-/]+)\s+(\d+)\s+")

    in_table = False
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not in_table:
                if header_re.search(line):
                    in_table = True
                continue
            m = row_re.match(line)
            if m:
                names.append(m.group(1))
            else:
                break

    # Deduplicate (preserve insertion order) and warn on repeats.
    seen: dict = {}
    for name in names:
        seen[name] = seen.get(name, 0) + 1
    duplicates = [n for n, count in seen.items() if count > 1]
    if duplicates:
        warn(
            f"Duplicate cellZone names found in {log_path}: "
            + ", ".join(duplicates)
            + "\n     Check whether the log was produced from a single checkMesh run."
        )
    return list(seen.keys())
