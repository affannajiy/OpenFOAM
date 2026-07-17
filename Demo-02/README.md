# Demo-02 — Power Electronics Meshing Demo

Demo case for the OpenFOAM UI: a power-electronics assembly (PCB, heat sinks,
MOSFETs, inductor, transformer, EMI shields, fan) inside an outer air domain.

The case is kept in a **clean pre-mesh state** — only geometry and solver
control dicts. Everything else is generated live by the GUI.

## Demo flow

1. Launch `OpenFOAM_UI.exe` → **Open Existing Project** → select this folder.
2. **Background Mesh** tab: pick `constant/triSurface/outer-domain.stl`,
   set grid spacing, **Run** — writes `system/blockMeshDict`, runs `blockMesh`.
3. Click **Continue to Snappy Hex Mesh →** on the green success banner.
4. **SnappyHexMesh** tab: table lists every STL.
   - `outer-domain.stl` → Surface Type **Boundary** (auto-suggested for the
     largest shell).
   - Components (heat sinks, MOSFETs, inductor, …) → **FaceZone + Cell Zone**,
     Vol Dir **Inside** — interior cells kept and named per component.
5. **Suggest point** for Location In Mesh, then **Generate & Run**.
6. Green banner → open the result in ParaView via the header button
   (`Demo-02.foam`).

## Contents

- `constant/triSurface/*.stl` — component geometry (millimetres).
- `system/controlDict`, `fvSchemes`, `fvSolution`, `decomposeParDict` —
  solver controls (untouched by the meshing GUI).

`system/blockMeshDict`, `system/snappyHexMeshDict`, `constant/polyMesh/`,
`snappy_inputs.json`, and `*.foam` are generated at demo time — delete them to
reset the case.
