# OpenFOAM Mesh Utilities — Setup & Deployment Guide

Complete guide for installing the environment from scratch and sharing the tool with another engineer.

---

## Part 1 — Fresh Installation (Windows + WSL + OpenFOAM)

> Skip this part if WSL and OpenFOAM are already installed.

### 1. Install WSL

1. Run **PowerShell as Administrator**
2. Run:
   ```powershell
   wsl --install
   ```
3. **Restart** your device

### 2. Install Ubuntu

1. Run **PowerShell as Administrator**
2. Run:
   ```powershell
   wsl --install Ubuntu
   ```
3. **Restart** your device

### 3. Open WSL

**Option A — via Terminal UI:**
1. Open **Terminal**
2. Click the **down arrow (⌄)** next to the tab bar
3. Select **Ubuntu**

**Option B — via command:**
1. Open **Terminal**
2. Run:
   ```powershell
   wsl -d Ubuntu
   ```

### 4. Install OpenFOAM

From the **Ubuntu Terminal**, run the following commands in order:

```bash
curl -s https://dl.openfoam.com/add-debian-repo.sh | sudo bash
```

```bash
sudo apt-get update
sudo apt-get upgrade
```

```bash
sudo apt-get install openfoam2506-default
```

---

## Part 2 — Tool Setup

### 5. Get the Tool Files

#### Sending the tool to another engineer

Zip the following two folders from `C:\OpenFOAM\`:

```
01_utilities\        ← all Python tooling and templates
03_mesh_session\     ← example OpenFOAM case to test against
```

**Quick zip (run in Command Prompt on your machine):**

```powershell
tar -a -c -f C:\OpenFOAM\openfoam_tools.zip C:\OpenFOAM\01_utilities
```

#### Files inside `01_utilities\` (do not omit any)

```
openfoam_ui.py                   ← GUI entry point — run this
ui_background_mesh.py
ui_snappy_hex.py
ui_log_drawer.py
ui_landing.py
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

### 6. Place the Files

Extract the zip anywhere on Windows. The WSL path must be reachable under `/mnt/`. Recommended location:

```
C:\OpenFOAM\
├── 01_utilities\
└── 03_mesh_session\
```

WSL equivalent: `/mnt/c/OpenFOAM/`

### 7. Install Python Dependencies

**Recommended (system packages, no venv needed):**

```bash
sudo apt-get install python3-pip
sudo apt-get install python3-pyqt5 python3-numpy python3-jinja2
```

**Alternative (pip):**

```bash
pip3 install -r /mnt/c/OpenFOAM/01_utilities/requirements.txt --break-system-packages
```

Optional — only needed for `AUTO_`-prefixed STL auto-refinement:

```bash
pip3 install trimesh --break-system-packages
# or: sudo apt-get install python3-trimesh
```

| Package | Required | Purpose |
|---------|----------|---------|
| `PyQt5` | Yes | GUI framework |
| `numpy` | Yes | Bounding box arithmetic |
| `jinja2` | Yes | Dictionary template rendering |
| `trimesh` | Optional | `AUTO_` auto-refinement geometry analysis |

### 8. Set Up Aliases (optional but recommended)

1. Open the aliases file in vi:
   ```bash
   vi ~/.bash_aliases
   ```

2. Add the following content:
   ```bash
   alias myDir="cd /mnt/c/OpenFOAM"

   # OpenFOAM environment
   alias of2506="source /usr/lib/openfoam/openfoam2506/etc/bashrc"

   # Python scripts for OpenFOAM workflow
   alias generateBackgroundMesh="python3 /mnt/c/OpenFOAM/01_utilities/generateBackgroundMesh.py"
   alias generateSnappyHexMeshDict="python3 /mnt/c/OpenFOAM/01_utilities/generateSnappyHexMeshDict.py"
   alias openfoamUI="python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py"
   ```

3. Press **`Esc`** to exit insert mode

4. Save and quit:
   ```
   :wq
   ```

   | vi command | Action |
   |------------|--------|
   | `:q` | Quit |
   | `:q!` | Force quit and discard changes |
   | `:x` | Save and quit (only if changes were made) |
   | `i` | Enter insert mode |

5. Source the aliases file:
   ```bash
   source ~/.bash_aliases
   ```

### 9. Source the OpenFOAM Environment

Add to `~/.bashrc` so it is always active, or run it manually before each session:

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
```

If you set up the alias in step 8, you can use:

```bash
of2506
```

---

## Part 3 — Running the Tool

### 10. Launch the GUI

```bash
source /usr/lib/openfoam/openfoam2506/etc/bashrc
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
```

With the alias:

```bash
of2506 && openfoamUI
```

The GUI requires a display. On **Windows 11** this works automatically via WSLg. On **Windows 10** start an X server (VcXsrv or MobaXterm) first.

#### Landing page

A **landing page** opens on first launch. The engineer can:

- **New project** — enter a name and parent folder; the tool creates `constant/triSurface/`, `system/`, `0/`, and stub dictionaries (`controlDict`, `fvSchemes`, `fvSolution`).
- **Open existing** — browse to a case folder or pick from the recent-projects list (max 10 entries; each has a × button to remove it).

Then choose a utility (**Background Mesh** or **SnappyHexMesh Dict**) and click **Continue →** to open the main workspace.

> The working directory does **not** need to be set before launching — the landing page handles it. The ← Home button always returns to the landing page.

### 11. Case Directory Requirements

A valid working directory must have:

```
<case-root>/
├── constant/           ← required; geometry files go in any subfolder here
│   └── <any-name>/    ← e.g. triSurface/, geometry/, surfaces/ — name is flexible
│       └── *.stl / *.obj
└── system/             ← required; generated dicts are written here
```

The GUI scans **all of `constant/`** recursively for `.stl` and `.obj` files — the geometry subfolder name does not matter.

### 12. Using Your Own Case

1. Make sure the case has `constant/` and `system/` folders.
2. Place STL/OBJ geometry files inside any subfolder of `constant/`.
3. Launch the GUI (the landing page lets you browse to or create the case), or use the **Change** button in Tab 2 to switch while the GUI is running.

### 13. Typical First-Run Workflow

```bash
# 1. Source environment
source /usr/lib/openfoam/openfoam2506/etc/bashrc

# 2. Launch GUI (no need to cd first — landing page handles project selection)
python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py

# In the landing page:
#   → Create a new project (or open an existing one)
#   → Select "Background Mesh" utility
#   → Click Continue →

# In the GUI:
# Tab 1 — browse for your STL, set DX/DY/DZ, click Generate Background Mesh
# Tab 2 — configure surface types and refinement, click Generate then Run snappyHexMesh
```

---

## Part 4 — Reference

### 14. Troubleshooting

| Problem | Fix |
|---------|-----|
| `python3: command not found` | `sudo apt-get install python3` |
| `No module named 'PyQt5'` | `sudo apt-get install python3-pyqt5` |
| `No module named 'jinja2'` | `sudo apt-get install python3-jinja2` |
| `blockMesh: command not found` | Source the OpenFOAM environment first |
| Blank window / no display | Windows 10: start VcXsrv or MobaXterm; Windows 11: WSLg should work out of the box |
| `Not found: .../constant` | The selected directory is not an OpenFOAM case root — it must contain `constant/` and `system/` |
| No files appear in Tab 2 geometry table | No `.stl` or `.obj` files found under `constant/`; check file placement |
| ParaView button does nothing | Install ParaView on Windows under `C:\Program Files\ParaView*\` |
| `Could not parse stylesheet` in terminal | Harmless Qt5 warning on Linux/WSL — the GUI suppresses these automatically; no action needed |

### 15. Installing Additional Python Libraries

To install any other library:

```bash
sudo apt-get install python3-<library_name>
```

Replace `<library_name>` with the actual library name, e.g. `python3-scipy`.

Or with pip:

```bash
pip3 install <library_name> --break-system-packages
```
