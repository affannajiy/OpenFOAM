#!/usr/bin/env python3
"""
check_env.py — Verify Python environment before running the other_utilities workflow.

Usage:
    python3 check_env.py

Checks:
  - Python version (3.12+)
  - jinja2         (required — ensureConsistentCellZones.py, createFluidCellZone.py)
"""

import sys

_USE_COLOR = sys.stdout.isatty()
RESET  = "\033[0m"  if _USE_COLOR else ""
GREEN  = "\033[32m" if _USE_COLOR else ""
YELLOW = "\033[33m" if _USE_COLOR else ""
RED    = "\033[31m" if _USE_COLOR else ""
BOLD   = "\033[1m"  if _USE_COLOR else ""

ok   = lambda s: print(f"  {GREEN}✓{RESET}  {s}")
warn = lambda s: print(f"  {YELLOW}!{RESET}  {s}")
fail = lambda s: print(f"  {RED}✗{RESET}  {s}")


def check_python():
    major, minor = sys.version_info[:2]
    ver = f"{major}.{minor}.{sys.version_info[2]}"
    if (major, minor) >= (3, 12):
        ok(f"Python {ver}")
        return True
    else:
        fail(f"Python {ver} — 3.12 or later required")
        return False


def _parse_version(ver_str):
    """Parse a version string into a tuple of ints for comparison."""
    try:
        return tuple(int(x) for x in ver_str.split(".")[:3])
    except (ValueError, AttributeError):
        return (0,)


def check_package(name, min_version=None, required=True):
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", "unknown")
        label = f"{name} {ver}"
        if min_version and ver != "unknown":
            if _parse_version(ver) < _parse_version(min_version):
                (fail if required else warn)(f"{label} — {min_version}+ required")
                return False
        ok(label)
        return True
    except ImportError:
        msg = f"{name} not found"
        if required:
            fail(f"{msg}  →  pip install {name}")
        else:
            warn(f"{msg} (optional)  →  pip install {name}")
        return False


def main():
    print()
    print(f"{BOLD}Environment check — other_utilities workflow{RESET}")
    print("─" * 45)

    py_ok = check_python()

    print()
    print("Required packages:")
    jinja_ok = check_package("jinja2", min_version="3.1")

    print()
    print("─" * 45)

    if not py_ok or not jinja_ok:
        print(f"{RED}Environment is not ready.{RESET} Fix the issues above, then re-run.")
        print(f"  Install dependencies:  pip install -r requirements.txt")
        sys.exit(1)
    else:
        print(f"{GREEN}All checks passed.{RESET} Environment is ready.")

    print()


if __name__ == "__main__":
    main()
