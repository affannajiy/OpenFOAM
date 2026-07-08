# ANR-03 — Affan's packaged / distributable version

**Author:** Affan Najiy Rusdi (ANR). Third GUI version. Same PyQt5 GUI + VIJ-02 backend as ANR-02, now **packaged into a Windows .exe** so it can ship to users who don't set up Python themselves.

## What this version adds

Everything in ANR-02, plus packaging and a new in-house backend.

| File | Function |
|------|----------|
| `openfoam_ui_launcher.py` | Thin Windows launcher — splash, WSL pre-flight checks, then starts `openfoam_ui.py` inside WSL. |
| `build_exe.bat` | Build script — runs PyInstaller, produces the exe. |
| `openfoam_ui_launcher.spec`, `version_info.txt` | PyInstaller config + Windows version metadata. |
| `OpenFOAM_UI.exe`, `dist/OpenFOAM_UI.exe` | The built launcher executable. |
| `snappy_generator.py` | **New in-house snappy backend** — appears here alongside the older `setup_snappy.py`, starting the move to a project-specific engine. |
| (all `ui_*`, templates, defaults.json) | Carried over from ANR-02. |

## Key traits

- First **shippable .exe** via PyInstaller + a WSL launcher.
- Both backends present: the older `setup_snappy.py` and the new `snappy_generator.py` (transition in progress).

## Place in the project

Turns the tool from "run the Python yourself" into "double-click the exe." Groundwork for the clean shipping layout that ANR-04 finalizes.
