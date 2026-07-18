# Contributing

Thanks for helping improve OpenFOAM Mesh Generation Utilities! This page covers setup, conventions, and how to get a change merged.

## Getting Set Up

1. Windows 11 (or Win10 build 21362+) with WSL2 + Ubuntu and OpenFOAM v2506 installed — see the [README](README.md#installing-by-hand-optional).
2. Clone the repo somewhere Windows-reachable, e.g. `C:\OpenFOAM` (WSL sees it at `/mnt/c/OpenFOAM`).
3. Python deps inside WSL: `sudo apt-get install python3-pyqt5 python3-numpy python3-jinja2`.
4. Run from source (no build needed):
   ```bash
   source /usr/lib/openfoam/openfoam2506/etc/bashrc
   python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py
   ```

`.py` edits take effect on the next launch — you only need `deploy\build.bat` (Windows CMD) when changing the launcher or cutting a release installer.

## Project Rules

- **Do not modify** `generateBackgroundMesh.py` and `generateSnappyHexMeshDict.py` — standalone CLI tools kept stable.
- **Popups**: always use the card-style wrappers in `ui_shared.py` (`msg_info/msg_warning/msg_critical/msg_question`, `pick_open_file(s)/pick_existing_dir`) — never stock `QMessageBox`/`QFileDialog.get*`. Stock dialogs misbehave under WSLg's window manager.
- **Tooltips**: every new interactive widget gets a `setToolTip` in plain, jargon-free words; any widget with its own stylesheet must append `STYLE_TOOLTIP`.
- **Meshing logic** (`snappy_generator.py`, `templates/`, `defaults.json`) changes need a meshed test case demonstrating the result is still correct — correctness beats speed here.
- Qt5/WSLg has several styling landmines (invisible borders, broken combo arrows, cascading QSS). Read the "Qt5 stylesheet rules" section of [CLAUDE.md](CLAUDE.md) before touching styles.
- No `os.chdir()` — pass `cwd=` to subprocesses. Convert Windows paths with `to_wsl_path`.

## Making a Change

1. Branch off `main`.
2. Keep the change focused; match the surrounding code style.
3. Test in the real environment: launch the GUI in WSL, run the affected flow end-to-end (Demo-01/Demo-02 are good test cases — don't commit their generated outputs: `polyMesh/`, `*.foam`, `snappy_inputs.json`).
4. If it changes behaviour users can see, add a line to [CHANGELOG.md](CHANGELOG.md) and update the README if needed.
5. Open a pull request describing what changed and why, with screenshots for UI changes.

## Reporting Bugs

Open an issue with: what you did, what happened, what you expected, plus the launcher log (`%TEMP%\openfoam_ui_launcher.log`) or the in-app Output Log content. Use **Copy Details** on any error dialog. Security issues: see [SECURITY.md](SECURITY.md) — privately, please.

## Licensing & Conduct

Contributions are accepted under [GPL-3.0](LICENSE). Be excellent to each other — [Code of Conduct](CODE_OF_CONDUCT.md).
