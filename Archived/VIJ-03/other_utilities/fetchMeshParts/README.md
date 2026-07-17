# fetchMeshParts Utility

Extract boundary patches, face zones, and cell zones from OpenFOAM **checkMesh** log files.

## Features

- **Parses checkMesh output** to extract patch topology, face zones, and cell zones
- **Filters zero-element entries** automatically (returns only non-zero elements)
- **Ignores wildcard patches** (e.g., `".*"` regex patterns)
- **JSON output** format for easy integration with other tools

## Requirements

- **Python 3.6+** (standard library only; no external dependencies)
- OpenFOAM checkMesh log file

## Installation

No installation required. The utility uses only Python standard library modules.

## Usage

```bash
python3 fetchMeshParts.py <log_file>
```

### Examples

**Basic usage:**
```bash
python3 fetchMeshParts.py log.checkMesh
```

**Save output to file:**
```bash
python3 fetchMeshParts.py /path/to/log.checkMesh_domainFluid > mesh_parts.json
```

**View help:**
```bash
python3 fetchMeshParts.py --help
```

## Output Format

The utility produces JSON output with three categories:

```json
{
    "boundaries": [
        "Inflow",
        "Outflow",
        "all_walls",
        "domain_fluid_to_domain_solid",
        ...
    ],
    "faceZones": [
        "PBB",
        "PBT",
        "HS252-1",
        ...
    ],
    "cellZones": [
        "domain_fluid",
        "B1",
        "B2"
    ]
}
```

### Key Points

- **boundaries**: All boundary patches from the mesh (wildcard patterns excluded)
- **faceZones**: All face zones with **at least 1 face**
- **cellZones**: All cell zones with **at least 1 cell**

## How It Works

The utility parses three key sections from the checkMesh log:

1. **Patch Topology** — Extracts patch names and filters out wildcard entries
2. **FaceZone Topology** — Extracts face zones, filtering to non-zero entries
3. **CellZone Addressing** — Extracts cell zones, filtering to non-zero entries

## Error Handling

- **File not found**: Prints error to stderr and exits with code 1
- **IO errors**: Prints detailed error message to stderr and exits with code 1
- **Parsing issues**: Returns empty lists if sections are not found in the log

## Limitations

- Requires valid checkMesh log file format
- Assumes OpenFOAM standard output format
- Wildcard/regex patches (e.g., `".*"`) are excluded from boundaries list
