# VIJ-02 — Vijaya Kumar's template + JSON snappy configurator

**Author:** Vijaya Kumar (developer, India). Second Vijay version. This is the codebase most of the ANR GUI backend logic is based on — the Jinja2 template + JSON config idea for building `snappyHexMeshDict` comes from here.

## What this version is

A proper CLI package (still no GUI). Instead of poking the dict entry-by-entry with `foamDictionary`, it renders the whole dict in one pass from a template driven by a JSON input file.

| File / folder | Function |
|------|----------|
| `setup_snappy.py` | Main engine. Parses `snappy_inputs.json`, renders `system/snappyHexMeshDict` from `templates/snappyHexMeshDict.template` (Jinja2), runs the mesher. |
| `auto_refinement.py` | Auto refinement-level logic (uses `trimesh` to inspect geometry). |
| `encoding_utils.py` | Text/encoding helpers. |
| `defaults.json` | Default control blocks and numbers (minVol, quality controls, etc.). |
| `templates/` | `blockMeshDict.template`, `snappyHexMeshDict.template`. |
| `documentation/` | CHANGELOG, JSON schema guide, quick reference, troubleshooting. |
| `examples/` | Standard-shape samples + a full `01_thermal_mgmt_case_2` electronics thermal-management case (heat sinks, MOSFETs, inductor, EMI shields, PCB). |
| `requirements.txt` | Python deps (jinja2, trimesh, numpy). |

## Meshing pipeline

`surfaceCheck` → `blockMesh` → render `snappyHexMeshDict` from template+JSON → `snappyHexMesh`.

## Place in the project

The template + JSON approach that the ANR GUI adopts. ANR-02 onward pulls `setup_snappy.py`, `auto_refinement.py`, `defaults.json` and the templates straight from this Vijay codebase. The thermal-management example here is the reference workflow the whole project targets.
