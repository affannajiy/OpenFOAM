# Deployment Guide — OpenFOAM Mesh Utilities GUI

How to share this tool with another engineer and get them running from scratch.

---

## What to send

Zip the following two folders from `C:\OpenFOAM\`:

```
01_utilities\        ← all Python tooling and templates
03_mesh_session\     ← example OpenFOAM case to test against
```

**Quick zip (run in PowerShell on your machine):**

```powershell
Compress-Archive -Path C:\OpenFOAM\01_utilities, C:\OpenFOAM\03_mesh_session `
  -DestinationPath C:\OpenFOAM\openfoam_tools.zip
```

### Files inside `01_utilities\` (do not omit any)

```
openfoam_ui.py                   ← GUI entry point — run this
ui_background_mesh.py
ui_snappy_hex.py
ui_log_drawer.py
ui_shared.py
setup_snappy.py
encoding_utils.py
auto_refinement.py
generateBackgroundMesh.py        ← standalone CLI
generateSnappyHexMeshDict.py     ← standalone CLI
defaults.json
requirements.txt
__init__.py
templates\
  blockMeshDict.template
  snappyHexMeshDict.template
```

**Do not include `__pycache__\`** — it is machine-specific and regenerates automatically.

---

## Receiver setup

### 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Windows 10/11 with WSL 2 | Run `wsl --install` if not present |
| Ubuntu in WSL | Default WSL distro works |
| OpenFOAM 2506 (or 2312) | See `documentation/openfoam-setup-guide.md` |
| ParaView (optional) | Install on Windows under `C:\Program Files\ParaView*\` |

### 2. Place the files

Extract the zip anywhere on Windows. The WSL path must be reachable under `/mnt/`. Example:

```
C:\OpenFOAM\
├── 01_utilities\
└── 03_mesh_session\
```

WSL equivalent: `/mnt/c/OpenFOAM/`

### 3. Install Python dependencies (run in WSL)

**Recommended (system packages, no venv needed):**

```bash
sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2
```

**Alternative (pip):**

```bash
pip3 install -r /mnt/c/OpenFOAM/01_utilities/requirements.txt --break-system-packages
```

Optional — only needed for `AUTO_`-prefixed STL auto-refinement:

```bash
pip3 install trimesh --break-system-packages
```

### 4. Source the OpenFOAM environment

Add this to `~/.bashrc` so it is always active, or run it manually before each session:

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
```

---

## Running the GUI

The tool must be launched from **inside an OpenFOAM case directory** — a folder that contains both `constant/` and `system/` subfolders.

```bash
cd /mnt/c/OpenFOAM/03_mesh_session
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```

The GUI requires a display. On **Windows 11** this works automatically via WSLg. On **Windows 10** start an X server (VcXsrv, MobaXterm) first.

---

## Case directory requirements

A valid working directory must have:

```
<case-root>/
├── constant/           ← required; geometry files go in any subfolder here
│   └── <any-name>/    ← e.g. triSurface/, geometry/, surfaces/ — name is flexible
│       └── *.stl / *.obj
└── system/             ← required; generated dicts are written here
```

The GUI scans **all of `constant/`** recursively for `.stl` and `.obj` files — the geometry subfolder name does not matter.

---

## Using your own case

If the engineer has their own OpenFOAM case:

1. Make sure the case has `constant/` and `system/` folders.
2. Place STL/OBJ geometry files inside any subfolder of `constant/`.
3. Launch the GUI from that case directory (or use the **Change** button in Tab 2 to switch).

---

## Typical first-run workflow

```bash
# 1. Source environment
source /usr/lib/openfoam/openfoam2506/etc/bashrc

# 2. Navigate to case
cd /mnt/c/OpenFOAM/03_mesh_session

# 3. Launch GUI
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py

# In the GUI:
# Tab 1 — browse for your STL, set DX/DY/DZ, click Generate Background Mesh
# Tab 2 — configure surface types and refinement, click Generate then Run
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python3: command not found` | `sudo apt-get install python3` |
| `No module named 'PyQt5'` | `sudo apt-get install python3-pyqt5` |
| `No module named 'jinja2'` | `sudo apt-get install python3-jinja2` |
| `blockMesh: command not found` | Source the OpenFOAM environment first |
| Blank window / no display | Windows 10: start VcXsrv; Windows 11: WSLg should work out of the box |
| `Not found: .../constant` | The selected directory is not an OpenFOAM case root — it must contain `constant/` and `system/` |
| No files appear in Tab 2 geometry table | No `.stl` or `.obj` files found under `constant/`; check placement |
| ParaView button does nothing | Install ParaView on Windows under `C:\Program Files\ParaView*\` |
