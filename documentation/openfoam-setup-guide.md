# OpenFOAM Setup Guide (WSL + Ubuntu)

---

## 1. Installing WSL

1. Run **PowerShell as Administrator**
2. Run the following command:
   ```powershell
   wsl --install
   ```
3. **Restart** your device

---

## 2. Installing Linux Distro (Ubuntu)

1. Run **PowerShell as Administrator**
2. Run the following command:
   ```powershell
   wsl --install Ubuntu
   ```
3. **Restart** your device

---

## 3. Opening WSL

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

---

## 4. Installing OpenFOAM

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

## 5. Go to Root Directory

```bash
cd /
```

---

## 6. Place the Project Files
Clone or copy the repository there if it isn't already present:

```bash
mkdir -p /mnt/c/OpenFOAM
mkdir 01_utilities
```

The directory should contain at minimum:
- `01_utilities/openfoam_ui.py` — GUI entry point
- `01_utilities/ui_shared.py`, `ui_log_drawer.py`, `ui_background_mesh.py`, `ui_snappy_hex.py` — GUI modules
- `01_utilities/setup_snappy.py` — snappyHexMeshDict backend
- `01_utilities/encoding_utils.py` — filename encoding helpers
- `01_utilities/auto_refinement.py` — AUTO_ analysis (optional)
- `01_utilities/defaults.json` — default mesh control values
- `01_utilities/templates/` — Jinja2 templates directory
- `01_utilities/generateBackgroundMesh.py` — CLI: blockMesh from STL bbox
- `01_utilities/generateSnappyHexMeshDict.py` — CLI: interactive snappyHexMeshDict

---

## 7. Install Python Dependencies

```bash
sudo apt-get install python3-pip
sudo apt-get install python3-numpy python3-pyqt5 python3-jinja2
```

Or install everything from the requirements file:

```bash
pip3 install -r /mnt/c/OpenFOAM/01_utilities/requirements.txt --break-system-packages
```

| Package | Required | Purpose |
|---------|----------|---------|
| `python3-pyqt5` | Yes | GUI framework (`openfoam_ui.py`) |
| `python3-numpy` | Yes | Bounding box arithmetic (background mesh) |
| `python3-jinja2` | Yes | Dictionary template rendering (snappyHexMeshDict) |
| `python3-trimesh` | Optional | `AUTO_` auto-refinement geometry analysis |

> To enable `AUTO_`-prefixed STL auto-refinement, install trimesh separately:
> ```bash
> sudo apt-get install python3-trimesh
> ```

---

## 8. Create Aliases

1. Open the aliases file in vi:
   ```bash
   vi ~/.bash_aliases
   ```

2. Add the following content:
   ```bash
   alias myDir="cd /mnt/c/OpenFOAM"

   # OpenFOAM versions
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

> **Other vi commands:**
> | Command | Action |
> |---------|--------|
> | `:q` | Quit |
> | `:q!` | Force quit and discard changes |
> | `:x` | Save and quit (only if changes were made) |
> | `i` | Insert mode

5. Source the aliases file:
   ```bash
   source ~/.bash_aliases
   ```

---

## 9. Open OpenFOAM

1. Source the OpenFOAM environment:
   ```bash
   of2506
   ```

2. Navigate to the working directory:
   ```bash
   myDir
   ```

---

## 10. Installing Additional Python Libraries

To install any other library:
```bash
sudo apt-get install python3-<library_name>
```

> Replace `<library_name>` with the actual library name, e.g. `python3-scipy`
