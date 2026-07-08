#!/usr/bin/env python3
"""
Extract boundary patches, face zones, and cell zones from OpenFOAM checkMesh log file.
Filters out entries with zero elements/faces.
"""

import re
import json
import sys
import argparse


def extract_patches(log_content):
    """
    Extract patch names from the 'Checking patch topology' section.
    Ignores wildcard entries (containing regex patterns).
    """
    patches = []
    
    # Find the section between "Checking patch topology" and "Detected X bad edges"
    pattern = r'Checking patch topology.*?\n\s+Patch\s+Faces\s+Points\s+Surface topology\n(.*?)(?:Detected|Checking)'
    match = re.search(pattern, log_content, re.DOTALL)
    
    if not match:
        return patches
    
    section = match.group(1)
    
    # Parse each row: patch_name faces points topology_info
    # Skip rows that are just separators or empty
    for line in section.split('\n'):
        line = line.strip()
        if not line or line.startswith('-'):
            continue
        
        # Extract patch name (first whitespace-delimited token)
        tokens = line.split()
        if len(tokens) < 4:
            continue
        
        patch_name = tokens[0]
        
        # Skip wildcard/regex patches (contains quotes or regex chars)
        if '"' in patch_name or '.*' in patch_name:
            continue
        
        patches.append(patch_name)
    
    return patches


def extract_faceZones(log_content):
    """
    Extract face zone names from the 'Checking faceZone topology' section.
    Filters to only zones with non-zero faces.
    """
    zones = []
    
    # Find the section between "Checking faceZone topology" and "Checking basic cellZone"
    pattern = r'Checking faceZone topology.*?\n\s+FaceZone\s+Faces\s+Points\s+Surface topology\n(.*?)(?:Checking basic cellZone)'
    match = re.search(pattern, log_content, re.DOTALL)
    
    if not match:
        return zones
    
    section = match.group(1)
    
    # Parse each row: zone_name faces points topology_info
    for line in section.split('\n'):
        line = line.strip()
        if not line or line.startswith('-') or line.startswith('<<'):
            continue
        
        tokens = line.split()
        if len(tokens) < 4:
            continue
        
        zone_name = tokens[0]
        
        # Skip non-numeric face counts
        try:
            faces = int(tokens[1])
        except ValueError:
            continue
        
        # Only include zones with non-zero faces
        if faces > 0:
            zones.append(zone_name)
    
    return zones


def extract_cellZones(log_content):
    """
    Extract cell zone names from the 'Checking basic cellZone addressing' section.
    Filters to only zones with non-zero cells.
    """
    zones = []
    
    # Find the section between "Checking basic cellZone addressing" and "Checking basic pointZone"
    pattern = r'Checking basic cellZone addressing.*?\n\s+CellZone\s+Cells\s+Points.*?\n(.*?)(?:Checking basic pointZone)'
    match = re.search(pattern, log_content, re.DOTALL)
    
    if not match:
        return zones
    
    section = match.group(1)
    
    # Parse each row: zone_name cells points bounding_box_info
    for line in section.split('\n'):
        line = line.strip()
        if not line or line.startswith('-'):
            continue
        
        tokens = line.split()
        if len(tokens) < 3:
            continue
        
        zone_name = tokens[0]
        
        # Skip non-numeric cell counts
        try:
            cells = int(tokens[1])
        except ValueError:
            continue
        
        # Only include zones with non-zero cells
        if cells > 0:
            zones.append(zone_name)
    
    return zones


def main():
    parser = argparse.ArgumentParser(
        description='Extract mesh parts (boundaries, face zones, cell zones) from OpenFOAM checkMesh log file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 fetchMeshParts.py log.checkMesh
  python3 fetchMeshParts.py /path/to/log.checkMesh_domainFluid > mesh_parts.json
        """
    )
    
    parser.add_argument(
        'log_file',
        help='Path to the checkMesh log file'
    )
    
    args = parser.parse_args()
    
    try:
        with open(args.log_file, 'r') as f:
            log_content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.log_file}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Extract all mesh parts
    patches = extract_patches(log_content)
    face_zones = extract_faceZones(log_content)
    cell_zones = extract_cellZones(log_content)
    
    # Format output as specified
    output = {
        "boundaries": patches,
        "faceZones": face_zones,
        "cellZones": cell_zones
    }
    
    # Print formatted JSON
    print(json.dumps(output, indent=4))


if __name__ == "__main__":
    main()
