# snappyHexMeshDict Generator

Python-based workflow for generating OpenFOAM `snappyHexMeshDict` and
`blockMeshDict` from a single JSON configuration file.

---

## Quick Start

```bash
# 1. Check your environment
python3 check_env.py

# 2. Run the generator from your case directory
python3 /path/to/setup_snappy.py
```

The script reads `snappy_inputs.json` from the current working directory and
writes `system/snappyHexMeshDict` and `system/blockMeshDict`.

---

## Dependencies

```bash
pip install -r requirements.txt
```

| Package | Required? | Used by |
|---------|-----------|---------|
| `jinja2 >= 3.1` | **Always** | Template rendering |
| `trimesh >= 4.0` | Optional | AUTO_ auto-refinement, `flip_normals.py` |
| `numpy >= 1.24` | Optional | Required alongside trimesh |

Run `python3 check_env.py` to verify your environment before first use.

---

## Main Script

### `setup_snappy.py`

Reads `snappy_inputs.json` and generates the two OpenFOAM dictionaries.

Key features:
- Geometry defined by STL/OBJ files or standard parametric shapes
- Surface and volume refinement configured via JSON or encoded filenames
- Auto-refinement levels computed from mesh geometry analysis (`AUTO_` prefix)
- Layer addition support
- Background mesh bounding box derived automatically from a reference geometry

See [`documentation/`](documentation/) for the full JSON schema reference,
quick-reference tables, and troubleshooting guide.

---

## Tools

Standalone utilities in [`tools/`](tools/) that support the workflow:

| Tool | Type | Purpose |
|------|------|---------|
| `geometry_renamer.html` | Browser | Assign encoding prefixes to STL files; generate rename script |
| `flip_normals.py` | Python | Flip face normals of an STL file in-place |
| `find_interior_point.py` | Python | Find a point inside a watertight STL for `locationInMesh` |

See [`tools/README.md`](tools/README.md) for usage details.

---

## Documentation

| Document | Contents |
|----------|----------|
| [`documentation/README.md`](documentation/README.md) | Index, workflow overview, dependency table |
| [`documentation/QUICK_REFERENCE.md`](documentation/QUICK_REFERENCE.md) | Field tables, copy-paste templates |
| [`documentation/JSON_SCHEMA_GUIDE.md`](documentation/JSON_SCHEMA_GUIDE.md) | Full parameter reference with examples |
| [`documentation/TROUBLESHOOTING.md`](documentation/TROUBLESHOOTING.md) | Error messages and fixes |
| [`documentation/CHANGELOG.md`](documentation/CHANGELOG.md) | Schema version history |
