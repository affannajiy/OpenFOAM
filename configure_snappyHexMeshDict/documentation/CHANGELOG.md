# Changelog

All notable changes to the `snappy_inputs.json` schema are documented here.

Version numbers follow **Semantic Versioning** (MAJOR.MINOR):
- **MAJOR** — breaking change: existing `snappy_inputs.json` files require edits
- **MINOR** — backward-compatible addition or clarification

The `_version` field in `snappy_inputs.json` should match the version the config
was written for. `setup_snappy.py` warns at startup if there is a mismatch.

---

## v1.0 — 2026-04-29

Initial release.

**Validated against:** OpenFOAM v2512

### Schema sections
- `settings` — `extractRefinementFromNames`, `addLayers`, `mergeTolerance`, `geometryUnit`
- `geometry` — `files`, `textFile`, `standardShapes` (9 searchable shape types)
- `backgroundMesh` — automatic `blockMeshDict` generation from a reference geometry
- `autoRefinementParams` — automatic surface/volume level derivation via trimesh analysis
- `surfaceHandling` — `selectedParts`, `surfaces` dict, `__defaults__`,
  boundary / faceZone / faceZone+cellZone types, multi-region `regions` dict
- `volumeRefinement` — `selectedParts`, `regions` dict, inside / outside / distance modes
- Encoded filename convention (`SURF_`, `VOL_`, `AUTO_` prefixes)
