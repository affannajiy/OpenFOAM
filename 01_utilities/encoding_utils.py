"""
encoding_utils.py
-----------------
Shared utilities for parsing and building snappyHexMesh filename encoding.

Both setup_snappy.py (parse_encoded_name) and auto_refinement.py
(parse_auto_encoded_name) import from here to avoid duplicating:
  - tag derivation from the encodingConvention dict
  - surface-tag → surf_type / has_cell_zone mapping
  - VOL tag → OpenFOAM mode string
  - the base result-dict structure
"""

import re
import sys


def build_tags(convention):
    """
    Derive all tag strings from an encodingConvention dict.

    Returns a dict with keys:
        surf_prefix, vol_prefix,
        bnd_tag, fz_tag, cz_tag, fz_cz_tag,
        surf_tags_pattern   ← regex alternation, longest match first
    """
    bnd_tag   = convention["boundary"]
    fz_tag    = convention["faceZone"]
    cz_tag    = convention["cellZone"]
    fz_cz_tag = fz_tag + "_" + cz_tag   # e.g. "FZ_CZ" — matched before "FZ"

    return {
        'surf_prefix':       convention["surfacePrefix"] + "_",
        'vol_prefix':        convention["volumePrefix"]  + "_",
        'bnd_tag':           bnd_tag,
        'fz_tag':            fz_tag,
        'cz_tag':            cz_tag,
        'fz_cz_tag':         fz_cz_tag,
        'surf_tags_pattern': "|".join(re.escape(t) for t in [fz_cz_tag, fz_tag, bnd_tag]),
    }


def decode_surf_tag(surf_tag, tags):
    """
    Map a matched surface tag to (surf_type, has_cell_zone).

    surf_tag : one of tags['bnd_tag'], tags['fz_tag'], tags['fz_cz_tag']
    Returns  : (str, bool)  e.g. ('faceZone', True)
    """
    if surf_tag == tags['bnd_tag']:
        return 'boundary', False
    elif surf_tag == tags['fz_tag']:
        return 'faceZone', False
    elif surf_tag == tags['fz_cz_tag']:
        return 'faceZone', True
    else:
        sys.exit(f"Internal error: unrecognised surface tag '{surf_tag}' — this is a bug.")


def vol_direction(tag):
    """Map a VOL tag string ('IN' or 'OUT') to an OpenFOAM mode string."""
    return 'inside' if tag == 'IN' else 'outside'


def empty_encoded_result(raw_name):
    """
    Return the base result dict used by both name parsers.

    Fields match the shape expected by setup_snappy.py's geometry_map
    and resolve_surface_handling / resolve_volume_refinement.
    """
    return {
        'clean_name':    raw_name,
        'has_encoding':  False,
        'is_auto':       False,
        'surf_type':     None,
        'has_cell_zone': False,
        'surf_levels':   None,
        'vol_mode':      None,
        'vol_level':     None,
    }
